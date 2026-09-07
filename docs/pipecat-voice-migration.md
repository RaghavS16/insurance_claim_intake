# Pipecat Voice Migration

## Architecture

The legacy hand-built voice engine has been replaced by a Pipecat pipeline. The insurance conversation graph remains application-owned.

```text
Browser PCM16 WebSocket
        |
        v
Pipecat FastAPI WebSocket Transport
        |
WebRTC VAD -> faster-whisper -> ClaimAgentProcessor -> Piper HTTP TTS
        |                         |
        |                         +--> existing LangGraph claim workflow
        v
Browser WAV audio + JSON events
```

### Responsibilities

**Pipecat / voice layer**
- WebSocket transport and connection lifecycle
- Audio frame routing
- WebRTC VAD and interruption propagation
- faster-whisper STT
- Piper HTTP TTS integration
- Pipeline cancellation/error boundaries

**Insurance application**
- Claim state and persistence
- Claim extraction and validation
- Follow-up question generation
- Policy verification
- Confirmation/submission workflow

## Piper setup

The application intentionally calls Piper through its standalone HTTP server. Install Piper in a separate environment/container and expose its `/synthesize` endpoint:

```bash
python3 -m pip install "piper-tts[http]"
python3 -m piper.download_voices en_US-lessac-medium
python3 -m piper.http_server -m en_US-lessac-medium
```

The application then uses:

```text
PIPER_HTTP_URL=http://localhost:5000/synthesize
PIPER_VOICE=en_US-lessac-medium
```

This keeps Piper runtime ownership outside the insurance backend dependency set.

## WebSocket contract

The existing claimant PCM16 browser contract is retained to make the migration incremental:

- client -> server: binary PCM16 mono 16 kHz audio
- server -> client: WAV audio responses
- server -> client: JSON `transcript`, `state_update`, and `barge_in` events
- authentication: JWT passed as the existing WebSocket `token` query parameter

The route remains:

```text
/api/v1/ws/voice/{ticket_id}
```

## Local startup

1. Start PostgreSQL and Ollama as before.
2. Start the Piper HTTP server.
3. Install backend requirements.
4. Start FastAPI.
5. Start the frontend.
6. Create a claim voice session and connect using its ticket ID and JWT.

## Tests

The migration adds unit and pipeline-construction tests under `backend/tests/test_pipecat_voice.py` and `backend/tests/test_pipecat_voice_integration.py`.

Run:

```bash
cd backend
pytest -q
```

The tests intentionally do not download Whisper models or call a real Piper server. End-to-end audio validation should be run in an environment where the local STT model and Piper service are available.

## Migration notes

`backend/src/api/voice_ws.py` is now a compatibility shim. Existing imports from claim routes continue to resolve `process_claimant_turn`, while the WebSocket router is supplied by `pipecat_voice_ws.py`.

The old custom voice workers are no longer part of the active pipeline. Pipecat now owns the real-time voice orchestration; the insurance agent remains independent of the voice transport.
