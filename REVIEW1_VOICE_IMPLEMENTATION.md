# Review 1 — Voice-Driven Claim Intake: Backend Implementation Handoff

**Project:** Voice-Driven Agentic Insurance Claim Intake & Data Collection System
**Repo:** https://github.com/RaghavS16/insurance_claim_intake
**Scope of this document:** Backend implementation for Review 1 (voice conversation, STT/TTS, VAD, conversation graph). Frontend voice UI and tests are **not** included here — implement backend first, confirm it runs, then proceed to frontend.

---

## 0. Instructions for the implementing agent

1. **Do not rebuild the repository.** Inspect the existing codebase first. Every file below is either a **NEW FILE** (create as-is) or an **APPEND / MODIFY** to an existing file (only add the shown content; do not touch unrelated existing code in that file).
2. **Do not remove or rewrite** `src/agents/nodes.py` functions `policy_validator`, `coverage_checker`, `fraud_detector`, `route_decision`, `response_formatter`, or the evaluation graph in `src/agents/graph.py`. These are frozen Review-3 foundation — out of scope for Review 1, but must remain intact and importable.
3. **Do not modify** existing `ClaimState` keys, existing `Claim`/`Document`/`Policy`/`Adjuster` model columns, or existing API endpoints (`/api/v1/claims/intake`, `/api/v1/claims/{ticket_id}/confirm`, `/api/v1/claims/{ticket_id}/documents`) — only add to them.
4. After each file is added, verify: imports resolve, `pytest` still passes for existing tests in `backend/tests/`, and the FastAPI app still boots (`uvicorn src.api.main:app`).
5. Apply the SQL migration (`database/migrate_voice.sql`) against the running Postgres instance — do not hand-edit `schema.sql`'s existing tables, only append the new table/column as shown.
6. Work incrementally: DB migration → models → state → voice/ package → agent nodes → graph → API/WebSocket wiring. Test importability after each stage before moving to the next.
7. Stop and flag rather than guess if: Piper binary/voice model isn't available in the environment (TTS should degrade to `agent_text_fallback` text-only, not crash), or `webrtcvad` fails to build on the target OS (suggest `webrtcvad-wheels` as a fallback PyPI package on Windows).

---

## 1. Architecture Summary

**What already exists (KEEP, unchanged):** FastAPI backend, SQLAlchemy models (`Claim`, `Document`, `Policy`, `Adjuster`, `AuditLog`, `PaymentRequest`), a two-graph LangGraph setup (intake graph: `claim_extractor → mandatory_field_checker → document_requirement_checker`; evaluation graph: `policy_validator → coverage_checker → fraud_detector → route_decision → response_formatter`), S3 document storage, Postgres/pgvector, a React step-wizard frontend.

**What's being added (Review 1):** A voice layer (STT via faster-whisper, TTS via Piper, VAD via webrtcvad) sitting on top of the existing extraction logic, plus a new **conversation graph** that wraps the existing intake nodes with turn-taking, correction-handling, and natural follow-up question generation. A WebSocket endpoint streams audio in/out per claim session. A new `conversation_turns` table persists transcript history.

**Data flow:**
```
User audio (WebSocket, PCM16 16kHz)
  → VAD segmenter (webrtcvad) buffers until utterance boundary
  → faster-whisper STT → transcript text
  → conversation graph (new) invoked with transcript as claim_text
      → conversation_turn_processor (handles repeat/don't-know/defer/correction intents)
      → claim_extractor (EXISTING, unchanged)
      → mandatory_field_checker (EXISTING, unchanged)
      → next_question_generator (NEW) OR document_requirement_checker (EXISTING) → document_request_generator (NEW) / intake_completion_marker (NEW)
  → result.next_question text
  → Piper TTS → WAV audio bytes
  → streamed back over WebSocket
```

Confirming/evaluating a claim (running the frozen evaluation graph) remains a separate, later, explicit step via the existing `/confirm` endpoint — voice intake does not call it.

---

## 2. Dependencies

Append to `backend/requirements.txt`:

```txt
faster-whisper==1.0.3
piper-tts==1.2.0
webrtcvad==2.0.10
websockets==12.0
numpy>=1.26.0
```

> Windows note: if `webrtcvad` fails to build (no C compiler available), install `webrtcvad-wheels` instead — same import name (`import webrtcvad`), prebuilt wheels.

---

## 3. Database Migration — NEW FILE

**Path:** `database/migrate_voice.sql`

```sql
-- Review 1: conversation history table. Additive — does not touch existing
-- claims/documents/policies/adjusters tables.
CREATE TABLE IF NOT EXISTS conversation_turns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id     UUID NOT NULL REFERENCES claims(id),
    turn_number  INTEGER NOT NULL,
    speaker      VARCHAR NOT NULL,   -- 'user' | 'agent'
    text         TEXT NOT NULL,
    audio_url    VARCHAR,            -- optional S3 path to raw audio segment
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_claim_id
    ON conversation_turns(claim_id, turn_number);

-- conversation_status distinct from claim.status ("draft"/"evaluated") because
-- a claim can be mid-intake-conversation for many turns before it's even a
-- candidate for evaluation. Mirrors the closure_status vs final_decision split
-- already established for the evaluation graph.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS conversation_status VARCHAR NOT NULL DEFAULT 'not_started';
-- not_started | in_progress | awaiting_documents | intake_complete
```

Run against the dev DB:
```
DATABASE_URL=postgresql://postgres:DBpassword@localhost:5433/insurance_claims psql -f database/migrate_voice.sql
```

---

## 4. SQLAlchemy Model Additions — MODIFY `backend/src/database/models.py`

Add this new class (append to the file, after the existing `AuditLog` class):

```python
class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = _UUID(ForeignKey("claims.id"), nullable=False, default=None)
    turn_number = Column(Integer, nullable=False)
    speaker = Column(String, nullable=False)          # "user" | "agent"
    text = Column(String, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

Add this single column inside the existing `Claim` class (do not touch any other column):

```python
    # Review 1: tracks the voice conversation lifecycle, distinct from `status`
    # ("draft"/"evaluated") which tracks the evaluation-graph lifecycle.
    conversation_status = Column(String, default="not_started")
    # not_started | in_progress | awaiting_documents | intake_complete
```

---

## 5. ClaimState Extension — MODIFY `backend/src/agents/state.py`

Replace the file contents with the following (all original keys preserved verbatim; new keys appended in a clearly marked section at the bottom):

```python
from typing import List, Dict, Any, TypedDict


class ClaimState(TypedDict, total=False):
    # ---- Intake (Stage 1-2: FNOL, extraction, confirmation) ----
    claim_text: str
    input_mode: str  # "voice" or "text"
    claim_type_hint: str  # optional, if user selects claim type in UI before speaking

    extracted_data: Dict[str, Any]
    missing_fields: List[str]          # fields still needed from user
    awaiting_confirmation: bool        # True once fields are complete and shown back to user
    confirmed: bool                    # True once user has confirmed the extracted data

    # R3-8: Proxy confidence score — ratio of required fields that are non-null
    # after extraction. Wired to the `extraction_confidence` DB column.
    # Range: 0.0 (all required fields missing) to 1.0 (all required fields present).
    extraction_confidence: float

    # ---- Documents (Stage 3) ----
    documents: List[Dict[str, Any]]        # [{document_type, filename, file_path}]
    required_documents: List[str]          # required doc types for this claim_type
    missing_documents: List[str]           # required but not yet uploaded
    documents_needed: bool                 # False if this claim_type needs no documents at all

    # ---- Policy validation (Stage 4) ----
    policy_data: Dict[str, Any]
    validation_status: str  # "valid" | "rejected" | "type_mismatch"

    # ---- Coverage + deductible (Stage 4) ----
    coverage_eligible: bool
    coverage_reasoning: str
    deductible_amount: float
    payout_amount: float

    # ---- Risk assessment (Stage 5) ----
    fraud_score: float
    fraud_flags: List[str]

    # ---- Decision + routing (Stage 6) ----
    assigned_adjuster: Dict[str, Any]
    ticket_id: str
    final_decision: str  # "need_more_info" | "need_documents" | "approved" | "denied" | "flagged_for_review" | "manual_review"

    # ---- Closure + feedback (Stage 7) ----
    closure_status: str  # "closed" | "pending_review" | "awaiting_user"
    response_message: str   # shown as text
    spoken_response: str    # read aloud via TTS -- same content, kept separate so
                             # voice phrasing can diverge from display text later without
                             # touching decision logic

    audit_log: List[str]

    # =========================================================
    # REVIEW 1 ADDITIONS — voice-driven conversational intake
    # =========================================================

    # ---- Conversation lifecycle ----
    conversation_status: str          # not_started | in_progress | awaiting_documents | intake_complete
    turn_number: int                  # incremented once per user utterance processed
    conversation_history: List[Dict[str, str]]  # [{turn, speaker, text}] mirror of DB rows, kept in-state for fast access without a re-query

    # ---- Next-question / agent output for this turn ----
    next_question: str                # text the agent should say next (fed to TTS)
    next_question_field: str          # which field next_question targets, so we can detect "repeat" and corrections against it
    awaiting_document_request: bool   # True when the agent's last utterance was a document request, not a question

    # ---- Correction / uncertainty handling ----
    last_user_utterance: str          # raw text of most recent turn, used for correction/"repeat"/"don't know" detection
    unknown_fields: List[str]         # fields user explicitly said "I don't know" / "later" for — treated as resolved-but-empty, not re-asked every turn

    # ---- Extended claim schema (per spec) — nested under extracted_data,
    # these keys just document what claim_extractor now also populates:
    # claimant_name, contact_information, incident_time, third_party_involved,
    # third_party_information, vehicle_number. No new top-level ClaimState keys
    # needed for these; they live inside extracted_data like the existing fields.
```

---

## 6. Voice Package — NEW FILES

### 6.1 `backend/src/voice/__init__.py`

```python
```
(empty file — just makes `voice` a package)

### 6.2 `backend/src/voice/vad.py`

```python
"""
Voice Activity Detection using WebRTC VAD (Google's open-source, BSD-licensed
VAD via the `webrtcvad` Python binding). Chosen over ML-based VAD (e.g.
silero-vad) for Review 1 because it's CPU-only, dependency-light, and more
than sufficient for detecting end-of-utterance in a turn-based conversation —
we don't need barge-in/overlap detection for Review 1's UX.

Frame requirements are strict: webrtcvad only accepts 16-bit mono PCM at
8000/16000/32000/48000 Hz, in 10/20/30ms frames. faster-whisper also wants
16kHz mono, so we standardize the whole voice pipeline on 16kHz.
"""
import collections
from typing import Generator, List

import webrtcvad

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30          # 10, 20, or 30 only
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0) * 2)  # 16-bit = 2 bytes/sample

# How many consecutive silent frames end an utterance. 900ms of silence.
SILENCE_FRAMES_TO_END = int(900 / FRAME_DURATION_MS)
# Ring buffer size for the "is this actually speech starting" check.
PADDING_FRAMES = 10


class Frame:
    __slots__ = ("bytes", "timestamp", "duration")

    def __init__(self, frame_bytes: bytes, timestamp: float, duration: float):
        self.bytes = frame_bytes
        self.timestamp = timestamp
        self.duration = duration


def frame_generator(audio_bytes: bytes) -> Generator[Frame, None, None]:
    """Slice raw PCM16 mono 16kHz audio into fixed-size VAD frames."""
    offset = 0
    timestamp = 0.0
    duration = FRAME_DURATION_MS / 1000.0
    while offset + FRAME_BYTES <= len(audio_bytes):
        yield Frame(audio_bytes[offset:offset + FRAME_BYTES], timestamp, duration)
        timestamp += duration
        offset += FRAME_BYTES


class UtteranceSegmenter:
    """
    Stateful segmenter: feed it audio chunks as they arrive from the
    WebSocket, it buffers, runs VAD frame-by-frame, and yields complete
    utterances (as raw PCM16 bytes) once it detects ~900ms of trailing
    silence after speech has started.

    Aggressiveness 0-3 (3 = most aggressive at filtering non-speech).
    2 is a reasonable default: filters background noise without cutting
    off quiet speech, which matters for a claims-intake use case where
    users may speak hesitantly.
    """

    def __init__(self, aggressiveness: int = 2):
        self._vad = webrtcvad.Vad(aggressiveness)
        self._ring_buffer: collections.deque = collections.deque(maxlen=PADDING_FRAMES)
        self._triggered = False
        self._voiced_frames: List[Frame] = []
        self._leftover = b""  # bytes that didn't fill a complete frame yet

    def feed(self, chunk: bytes) -> List[bytes]:
        """
        Feed raw PCM16 bytes (any chunk size). Returns a list of completed
        utterances (usually 0 or 1) as raw PCM16 bytes ready for STT.
        """
        self._leftover += chunk
        completed_utterances: List[bytes] = []

        # Consume as many complete frames as we have bytes for.
        frames = list(frame_generator(self._leftover))
        if frames:
            consumed = len(frames) * FRAME_BYTES
            self._leftover = self._leftover[consumed:]

        for frame in frames:
            is_speech = self._vad.is_speech(frame.bytes, SAMPLE_RATE)

            if not self._triggered:
                self._ring_buffer.append((frame, is_speech))
                num_voiced = len([f for f, speech in self._ring_buffer if speech])
                # Start of an utterance: majority of the ring buffer is speech.
                if num_voiced > 0.9 * self._ring_buffer.maxlen:
                    self._triggered = True
                    self._voiced_frames.extend(f for f, _ in self._ring_buffer)
                    self._ring_buffer.clear()
            else:
                self._voiced_frames.append(frame)
                self._ring_buffer.append((frame, is_speech))
                num_unvoiced = len([f for f, speech in self._ring_buffer if not speech])
                if num_unvoiced > 0.9 * self._ring_buffer.maxlen:
                    # End of utterance: enough trailing silence.
                    utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
                    completed_utterances.append(utterance_bytes)
                    self._triggered = False
                    self._voiced_frames = []
                    self._ring_buffer.clear()

        return completed_utterances

    def flush(self) -> bytes | None:
        """Call on connection close to grab any in-progress utterance."""
        if self._triggered and self._voiced_frames:
            utterance_bytes = b"".join(f.bytes for f in self._voiced_frames)
            self._triggered = False
            self._voiced_frames = []
            return utterance_bytes
        return None
```

### 6.3 `backend/src/voice/stt.py`

```python
"""
Speech-to-text using faster-whisper (CTranslate2 reimplementation of Whisper —
open-source, MIT-licensed, runs efficiently CPU-only which matters for a
local dev / low-budget deployment target).

Loaded once at module import (like `llm` in agents/nodes.py) so the model
isn't reloaded per request.
"""
import io
import logging
import wave
from typing import Optional

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# "small" balances accuracy vs latency for CPU inference. "base" is faster but
# noticeably worse on accented/noisy speech; "medium"+ is too slow without a GPU.
# Flag for viva: this tradeoff is worth being able to explain — "small" was
# chosen because Review 1's demo needs <5s end-to-end latency per success metrics.
_MODEL_SIZE = "small"
_model: Optional[WhisperModel] = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading faster-whisper model: %s", _MODEL_SIZE)
        _model = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """faster-whisper's transcribe() accepts a file path or file-like object;
    wrapping raw PCM in a WAV header lets us hand it an in-memory buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf.read()


def transcribe_pcm16(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe a single utterance (already VAD-segmented) of raw PCM16 mono
    audio. Returns "" on empty/silent input rather than raising, so callers
    can treat empty transcript as "didn't catch that" without a try/except.
    """
    if len(pcm_bytes) < sample_rate * 2 * 0.2:  # < 200ms of audio, not worth running
        return ""

    wav_bytes = _pcm16_to_wav_bytes(pcm_bytes, sample_rate)
    try:
        segments, info = get_model().transcribe(
            io.BytesIO(wav_bytes),
            language="en",       # pin to English for Review 1; multi-lingual is future work
            vad_filter=False,    # already VAD-segmented upstream; avoid double-filtering
            beam_size=5,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info("STT transcribed %d bytes -> %r (lang_prob=%.2f)", len(pcm_bytes), text, info.language_probability)
        return text
    except Exception:
        logger.exception("STT transcription failed")
        return ""
```

### 6.4 `backend/src/voice/tts.py`

```python
"""
Text-to-speech using Piper (open-source, fast, self-hostable neural TTS from
the Rhasspy project). Piper ships as a CLI binary + ONNX voice models; shell
out to it rather than depend on an unofficial Python binding, since the
official interface is the `piper` executable.

Requires:
  - `piper` binary on PATH (or PIPER_BIN env var pointing to it)
  - a downloaded voice model, e.g. en_US-lessac-medium.onnx (+ .onnx.json)
    referenced via PIPER_VOICE_MODEL env var
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PIPER_BIN = os.getenv("PIPER_BIN", "piper")
PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL")  # path to .onnx file


class TTSError(Exception):
    pass


def synthesize(text: str) -> bytes:
    """
    Synthesize `text` to 22050Hz mono WAV bytes via Piper. Raises TTSError on
    failure so callers (the WebSocket handler) can fall back to text-only
    display rather than silently sending empty audio.
    """
    if not PIPER_VOICE_MODEL:
        raise TTSError("PIPER_VOICE_MODEL environment variable is not set.")
    if not text or not text.strip():
        raise TTSError("Cannot synthesize empty text.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [PIPER_BIN, "--model", PIPER_VOICE_MODEL, "--output_file", str(out_path)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise TTSError(f"piper exited {result.returncode}: {result.stderr.decode(errors='replace')}")

        audio_bytes = out_path.read_bytes()
        if not audio_bytes:
            raise TTSError("piper produced empty audio output.")
        return audio_bytes
    except subprocess.TimeoutExpired:
        raise TTSError("piper synthesis timed out.")
    except FileNotFoundError:
        raise TTSError(f"piper binary not found at '{PIPER_BIN}'. Set PIPER_BIN or install piper on PATH.")
    finally:
        out_path.unlink(missing_ok=True)
```

### 6.5 `backend/src/voice/session.py`

```python
"""
Per-connection voice session state. Holds the UtteranceSegmenter for the life
of a WebSocket connection — deliberately NOT persisted to DB (it's just audio
buffering state), unlike ClaimState which lives in claims.pipeline_state.
"""
from dataclasses import dataclass, field

from src.voice.vad import UtteranceSegmenter


@dataclass
class VoiceSession:
    ticket_id: str
    segmenter: UtteranceSegmenter = field(default_factory=UtteranceSegmenter)
    turn_number: int = 0

    def next_turn(self) -> int:
        self.turn_number += 1
        return self.turn_number
```

---

## 7. Agent Node Additions — APPEND to `backend/src/agents/nodes.py`

Add this block at the end of the existing file (after `response_formatter`). Do not modify anything above it.

```python
# =============================================================================
# REVIEW 1 ADDITIONS — conversational turn nodes
# =============================================================================

# Sentinel value for fields the user explicitly declined to answer right now.
# Kept distinct from None so mandatory_field_checker can treat it as "resolved
# but empty" rather than re-prompting every turn, while response_formatter /
# document/eval logic downstream still sees it as missing real data.
UNKNOWN_SENTINEL = "UNKNOWN"

CORRECTION_MARKERS = (
    "actually", "sorry, i meant", "i meant to say", "no wait", "correction",
    "let me correct", "scratch that", "i said that wrong",
)
DONT_KNOW_MARKERS = ("i don't know", "i dont know", "not sure", "no idea", "i'll check")
DEFER_MARKERS = ("i'll provide it later", "later", "not right now", "i'll get back to you")
REPEAT_MARKERS = ("repeat that", "say that again", "come again", "what was that", "pardon")


def _detect_utterance_intent(text: str) -> str:
    """
    Classify the user's utterance for conversation-control purposes, separate
    from field extraction. Returns one of: 'correction' | 'dont_know' | 'defer'
    | 'repeat' | 'normal'. This is intentionally simple keyword matching for
    Review 1 — an LLM-based intent classifier is reasonable future work but
    keyword matching is explainable, fast, and auditable for a viva.
    """
    lowered = text.lower().strip()
    if any(m in lowered for m in REPEAT_MARKERS):
        return "repeat"
    if any(m in lowered for m in CORRECTION_MARKERS):
        return "correction"
    if any(m in lowered for m in DONT_KNOW_MARKERS):
        return "dont_know"
    if any(m in lowered for m in DEFER_MARKERS):
        return "defer"
    return "normal"


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    """
    Entry node for the conversation graph. Runs before claim_extractor on every
    turn. Handles conversation-control intents (repeat/don't-know/defer/
    correction) that shouldn't just fall through to normal extraction:

      - 'repeat'    -> re-emit the SAME next_question, skip extraction entirely.
      - 'dont_know' / 'defer' -> mark the currently-asked field as UNKNOWN_SENTINEL
                        so it's resolved-but-empty, skip extraction for this turn.
      - 'correction' -> unlock the previously-asked field specifically (field-
                        locking in claim_extractor normally protects confirmed
                        fields; a detected correction bypasses the lock for that
                        one field only) then fall through to normal extraction.
      - 'normal'    -> fall through to claim_extractor unchanged.
    """
    utterance = state.get("claim_text", "")
    state["last_user_utterance"] = utterance
    intent = _detect_utterance_intent(utterance)
    target_field = state.get("next_question_field")

    if intent == "repeat":
        _audit(state, f"User asked to repeat. Re-emitting question for '{target_field}'.")
        state["conversation_status"] = "in_progress"
        # Signal downstream (graph routing) to skip extraction and go straight
        # to re-emitting next_question — handled via early return marker.
        state["_skip_extraction"] = True
        return state

    if intent in ("dont_know", "defer") and target_field:
        extracted = dict(state.get("extracted_data") or {})
        extracted[target_field] = UNKNOWN_SENTINEL
        state["extracted_data"] = extracted
        unknowns = list(state.get("unknown_fields") or [])
        if target_field not in unknowns:
            unknowns.append(target_field)
        state["unknown_fields"] = unknowns
        _audit(state, f"User deferred field '{target_field}' (intent={intent}); marked UNKNOWN, not re-asking.")
        state["_skip_extraction"] = True
        return state

    if intent == "correction" and target_field:
        prior = dict(state.get("extracted_data") or {})
        prior[target_field] = None  # unlock: claim_extractor's field-locking only
        state["extracted_data"] = prior  # protects non-null values, so nulling it out lets the new answer through
        _audit(state, f"Detected correction for field '{target_field}'; unlocked for re-extraction.")

    state["_skip_extraction"] = False
    return state


def next_question_generator(state: ClaimState) -> ClaimState:
    """
    Decide and phrase the next thing the agent should say. Runs after
    mandatory_field_checker. Picks the FIRST missing field (stable order from
    REQUIRED_FIELDS) rather than all of them at once — Review 1 spec requires
    one natural follow-up question at a time, not a field dump.
    """
    if state.get("_skip_extraction") and state.get("next_question"):
        # 'repeat' case: keep the existing next_question/next_question_field as-is.
        _audit(state, "Re-emitting previous question (repeat request).")
        return state

    missing = state.get("missing_fields", [])
    if not missing:
        state["next_question"] = ""
        state["next_question_field"] = ""
        return state

    field = missing[0]
    state["next_question_field"] = field
    state["next_question"] = FIELD_PROMPTS.get(field, f"Could you tell me {field.replace('_', ' ')}?")
    state["conversation_status"] = "in_progress"
    _audit(state, f"Next question targets field '{field}'")
    return state


def document_request_generator(state: ClaimState) -> ClaimState:
    """
    Runs when all mandatory fields are present but required documents are
    missing. Phrases a spoken document request, mirrors response_formatter's
    document-missing branch but produces a conversational (not final-response)
    utterance since the conversation continues after this.
    """
    missing_docs = state.get("missing_documents", [])
    if not missing_docs:
        state["awaiting_document_request"] = False
        state["conversation_status"] = "intake_complete"
        _audit(state, "No documents missing; intake complete.")
        return state

    labels = [DOCUMENT_LABELS.get(d, d) for d in missing_docs]
    state["next_question"] = (
        "I've collected the initial claim information. I'll need "
        + " and ".join(labels) + ". You can upload them now."
    )
    state["next_question_field"] = ""
    state["awaiting_document_request"] = True
    state["conversation_status"] = "awaiting_documents"
    _audit(state, f"Requesting documents: {missing_docs}")
    return state


def intake_completion_marker(state: ClaimState) -> ClaimState:
    """Terminal node: all fields present, all documents present (or none required)."""
    state["conversation_status"] = "intake_complete"
    state["next_question"] = (
        "Thank you. I've collected everything needed to register your claim. "
        f"Your claim reference is {state.get('ticket_id', 'pending')}."
    )
    _audit(state, "Intake complete.")
    return state
```

---

## 8. Conversation Graph — APPEND to `backend/src/agents/graph.py`

Add this block at the end of the existing file (after `build_evaluation_graph`). Do not modify `_build_intake_graph`, `build_intake_graph`, or `build_evaluation_graph`.

```python
# ---------------------------------------------------------------------------
# Graph 3 (Review 1): Conversation turn graph.
# Runs once per user utterance. Reuses claim_extractor and
# mandatory_field_checker unchanged; adds conversation-control routing on top.
# No DB dependency -> compiled once at import time, like the intake graph.
# ---------------------------------------------------------------------------

def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("conversation_turn_processor", nodes.conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", nodes.next_question_generator)
    graph.add_node("document_requirement_checker", nodes.document_requirement_checker)
    graph.add_node("document_request_generator", nodes.document_request_generator)
    graph.add_node("intake_completion_marker", nodes.intake_completion_marker)

    graph.set_entry_point("conversation_turn_processor")

    # 'repeat' / 'dont_know' / 'defer' intents set _skip_extraction=True and
    # bypass claim_extractor entirely (their field-level updates were already
    # applied in conversation_turn_processor).
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda s: "skip" if s.get("_skip_extraction") else "extract",
        {"extract": "claim_extractor", "skip": "mandatory_field_checker"},
    )

    graph.add_edge("claim_extractor", "mandatory_field_checker")

    graph.add_conditional_edges(
        "mandatory_field_checker",
        lambda s: "missing" if s.get("missing_fields") else "complete",
        {"missing": "next_question_generator", "complete": "document_requirement_checker"},
    )

    graph.add_edge("next_question_generator", END)

    graph.add_conditional_edges(
        "document_requirement_checker",
        lambda s: "missing" if s.get("missing_documents") else "ready",
        {"missing": "document_request_generator", "ready": "intake_completion_marker"},
    )

    graph.add_edge("document_request_generator", END)
    graph.add_edge("intake_completion_marker", END)

    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    """Return the pre-compiled conversation-turn graph singleton."""
    return _conversation_graph
```

---

## 9. WebSocket Endpoint — NEW FILE `backend/src/api/voice_ws.py`

```python
"""
WebSocket endpoint for streaming voice conversation. One connection per
claim session (ticket_id). Client streams raw PCM16 mono 16kHz audio chunks
(any size); server VAD-segments into utterances, transcribes, runs the
conversation graph, synthesizes the reply, and streams audio + a JSON event
back on the same socket.

Protocol (binary frames = audio, text frames = JSON control/status events):
  Client -> Server: binary PCM16 chunks
  Client -> Server: text {"type": "end_session"}
  Server -> Client: text {"type": "transcript", "text": "..."}
  Server -> Client: text {"type": "state_update", "extracted_data": {...}, "missing_fields": [...]}
  Server -> Client: binary  (synthesized WAV audio of the agent's reply)
  Server -> Client: text {"type": "error", "detail": "..."}
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.database.session import SessionLocal
from src.database.models import Claim, ConversationTurn
from src.agents.graph import build_conversation_graph
from src.voice.session import VoiceSession
from src.voice.stt import transcribe_pcm16
from src.voice.tts import synthesize, TTSError

logger = logging.getLogger(__name__)
router = APIRouter()


def _persist_turn(db: Session, claim: Claim, speaker: str, text: str, turn_number: int) -> None:
    db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_number, speaker=speaker, text=text))
    db.commit()


async def _run_turn(db: Session, claim: Claim, voice_session: VoiceSession, user_text: str) -> dict:
    """Run one conversation-graph turn and persist state + transcript."""
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    turn_number = voice_session.next_turn()

    _persist_turn(db, claim, "user", user_text, turn_number)

    graph_input = {
        **prior_state,
        "claim_text": user_text,
        "ticket_id": claim.ticket_id,
    }

    graph = build_conversation_graph()
    result = graph.invoke(graph_input)

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "conversation_status", result.get("conversation_status", "in_progress"))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    db.commit()

    agent_text = result.get("next_question", "")
    if agent_text:
        _persist_turn(db, claim, "agent", agent_text, turn_number)

    return result


@router.websocket("/ws/claims/{ticket_id}/voice")
async def voice_conversation(websocket: WebSocket, ticket_id: str):
    await websocket.accept()
    db = SessionLocal()

    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        await websocket.send_json({"type": "error", "detail": "ticket_id not found"})
        await websocket.close(code=4404)
        db.close()
        return

    voice_session = VoiceSession(ticket_id=ticket_id)

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"] is not None:
                utterances = voice_session.segmenter.feed(message["bytes"])
                for pcm_bytes in utterances:
                    await _handle_utterance(websocket, db, claim, voice_session, pcm_bytes)

            elif "text" in message and message["text"] is not None:
                import json
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "end_session":
                    leftover = voice_session.segmenter.flush()
                    if leftover:
                        await _handle_utterance(websocket, db, claim, voice_session, leftover)
                    break

    except WebSocketDisconnect:
        logger.info("Voice session %s disconnected", ticket_id)
    except Exception:
        logger.exception("Voice session %s crashed", ticket_id)
        try:
            await websocket.send_json({"type": "error", "detail": "Internal error. Please try again."})
        except Exception:
            pass
    finally:
        db.close()


async def _handle_utterance(websocket, db, claim, voice_session, pcm_bytes: bytes) -> None:
    text = transcribe_pcm16(pcm_bytes)

    if not text:
        await websocket.send_json({
            "type": "transcript_empty",
            "message": "I didn't catch that. Could you please repeat that?",
        })
        return

    await websocket.send_json({"type": "transcript", "text": text})

    try:
        result = await _run_turn(db, claim, voice_session, text)
    except Exception:
        logger.exception("Conversation turn failed for claim %s", claim.ticket_id)
        await websocket.send_json({
            "type": "error",
            "detail": "Something went wrong processing that. Please try again.",
        })
        return

    await websocket.send_json({
        "type": "state_update",
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "missing_documents": result.get("missing_documents", []),
        "conversation_status": result.get("conversation_status"),
    })

    agent_text = result.get("next_question", "")
    if not agent_text:
        return

    try:
        audio_bytes = synthesize(agent_text)
        await websocket.send_bytes(audio_bytes)
    except TTSError as exc:
        logger.warning("TTS failed, falling back to text-only: %s", exc)
        await websocket.send_json({"type": "agent_text_fallback", "text": agent_text})
```

---

## 10. REST Wiring — MODIFY `backend/src/api/main.py`

1. Add to the existing import block:
```python
from src.database.models import Claim, Document, PaymentRequest, Policy, ConversationTurn
from src.api.voice_ws import router as voice_router
```

2. After `app = FastAPI(title="Insurance Claim Intake API")` (and after CORS middleware setup), add:
```python
app.include_router(voice_router)
```

3. Add two new endpoints (place near the existing claims endpoints, e.g. after `/api/v1/claims/{ticket_id}` at the bottom of the file):

```python
@app.post("/api/v1/claims/voice-session")
def start_voice_session(db: Session = Depends(get_db)):
    """Creates an empty draft claim and returns its ticket_id so the frontend
    can open the WebSocket at /ws/claims/{ticket_id}/voice immediately."""
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    claim = Claim(ticket_id=ticket_id, input_mode="voice", status="draft", conversation_status="not_started")
    db.add(claim)
    db.commit()
    return {"ticket_id": ticket_id}


@app.get("/api/v1/claims/{ticket_id}/conversation")
def get_conversation_history(ticket_id: str, db: Session = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.claim_id == claim.id)
        .order_by(ConversationTurn.turn_number, ConversationTurn.created_at)
        .all()
    )
    return [{"turn": t.turn_number, "speaker": t.speaker, "text": t.text, "created_at": t.created_at} for t in turns]
```

---

## 11. Environment Setup Checklist

```bash
# 1. Python deps (Windows: use webrtcvad-wheels if webrtcvad build fails)
cd backend
pip install -r requirements.txt --break-system-packages

# 2. Download a Piper voice model, e.g.:
#    https://github.com/rhasspy/piper/releases -> en_US-lessac-medium.onnx + .onnx.json
#    Place both files somewhere on disk, then set:
set PIPER_VOICE_MODEL=C:\path\to\en_US-lessac-medium.onnx
set PIPER_BIN=piper   REM only needed if piper isn't already on PATH

# 3. Apply DB migration
psql -U postgres -d insurance_claims -f ..\database\migrate_voice.sql

# 4. Boot and sanity check
uvicorn src.api.main:app --reload
# then: POST /api/v1/claims/voice-session  -> should return {"ticket_id": "CLAIM-XXXXXXXX"}
# then: open ws://localhost:8000/ws/claims/{ticket_id}/voice and stream 16kHz mono PCM16 audio
```

---

## 12. Explicit Non-Goals for This Pass (do not implement)

- Policy RAG / IRDAI RAG (Review 2)
- OCR / document classification / document-intelligence extraction (Review 2)
- Any changes to `policy_validator`, `coverage_checker`, `fraud_detector`, `route_decision`, `response_formatter`, or the evaluation graph (Review 3 — frozen, not touched)
- Frontend voice UI (separate follow-up task)
- Automated tests for the new nodes/graph (separate follow-up task — flagged for a subsequent pass covering correction/don't-know/repeat/normal-turn cases)

---

## 13. Suggested Next Steps After This Implementation Lands

1. `pytest` regression pass — confirm nothing in `backend/tests/test_claims_pipeline.py` broke.
2. Add `backend/tests/test_conversation_graph.py` covering: normal turn, correction turn, don't-know turn, repeat turn, missing-documents turn, intake-complete turn.
3. Build the voice-first frontend (mic capture → PCM16 conversion → WebSocket streaming → live transcript/state panel), replacing the primary UX of `ClaimForm.tsx` per the Review 1 spec, while keeping the existing text-form components available as a fallback/debug path.
4. Update `TECH_DEBT_AUDIT.md` and `ARCHITECTURE.md` to reflect the new `voice/` package and conversation graph.
