"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface ExtractedData {
  policy_id?: string | null;
  incident_date?: string | null;
  claim_type?: string | null;
  damage_description?: string | null;
  claimed_amount?: number | null;
}

/**
 * A transcript segment as modeled on the client.
 * Partials are updated in-place (same segment_id, same position in history).
 * Finals freeze the segment.
 */
interface TranscriptSegment {
  segment_id: string;
  sequence: number;
  speaker: "user" | "agent";
  text: string;
  is_final: boolean;
  start_ts?: number;
  confidence?: number;
}

/** Conversation history item (finalized segments + initial agent message) */
interface ConversationTurn {
  turn: number;
  speaker: "user" | "agent";
  text: string;
  /** Tracks whether this entry originated from a streaming segment */
  segment_id?: string;
}

const SUPPORTED_INSURANCE_TYPES = [
  { id: "motor", name: "Motor", icon: "🚗", desc: "Vehicle accident, collision, or damage" },
  { id: "health", name: "Health", icon: "🏥", desc: "Hospitalization, surgery, or medical care" },
  { id: "senior_health", name: "Senior Health", icon: "🩺", desc: "Elderly parent / senior citizen medical care" },
  { id: "home", name: "Home", icon: "🏠", desc: "Fire, roof leak, plumbing, or property damage" },
  { id: "travel", name: "Travel", icon: "✈️", desc: "Lost luggage, trip cancellation, flight delay" },
  { id: "cyber", name: "Cyber", icon: "🔒", desc: "Ransomware, malware, hacking, or online fraud" },
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function ClaimIntakePage() {
  const [ticketId, setTicketId] = useState<string>("");
  const [conversationStatus, setConversationStatus] = useState<string>("not_started");
  const [extractedData, setExtractedData] = useState<ExtractedData>({});
  const [missingFields, setMissingFields] = useState<string[]>([
    "policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"
  ]);
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [textInput, setTextInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmed, setConfirmed] = useState<boolean>(false);
  const [submittedMessage, setSubmittedMessage] = useState<string>("");
  /** Visible error banner — shown instead of silent console.error */
  const [errorBanner, setErrorBanner] = useState<string>("");

  // Active partial segments (keyed by segment_id) — updated in real time
  const [partialSegments, setPartialSegments] = useState<Map<string, TranscriptSegment>>(new Map());

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const isPlayingRef = useRef<boolean>(false);

  // Auto-scroll chat to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, partialSegments]);

  // ---------------------------------------------------------------------------
  // Session initialization
  // ---------------------------------------------------------------------------
  const initSession = useCallback(async () => {
    try {
      setLoading(true);
      setErrorBanner("");
      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      const data = await res.json();
      setTicketId(data.ticket_id);
      setConversationStatus("collecting");
      setConfirmed(false);
      setSubmittedMessage("");
      setExtractedData({});
      setPartialSegments(new Map());
      setMissingFields(["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]);
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || "Please tell me what happened. You can describe the incident in your own words, and I'll collect the details I need.",
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Failed to start claim session: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    const load = async () => {
      if (!ignore) {
        await initSession();
      }
    };
    load();
    return () => {
      ignore = true;
    };
  }, [initSession]);

  // ---------------------------------------------------------------------------
  // Audio queue playback — plays TTS responses sequentially
  // ---------------------------------------------------------------------------
  const enqueueAudio = useCallback((blob: Blob) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audioQueueRef.current.push(audio);

    const playNext = () => {
      if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
      const next = audioQueueRef.current.shift();
      if (!next) return;
      isPlayingRef.current = true;

      // Signal to server that TTS is playing (for echo suppression)
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "tts_playing", duration_s: 5 }));
      }

      next.play().catch((e) => {
        console.warn("Audio autoplay prevented:", e);
        isPlayingRef.current = false;
        playNext();
      });
      next.onended = () => {
        URL.revokeObjectURL(url);
        isPlayingRef.current = false;
        // Signal that TTS finished (echo suppression can end)
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "tts_stopped" }));
        }
        playNext();
      };
    };

    playNext();
  }, []);

  // ---------------------------------------------------------------------------
  // WebSocket message handler
  // ---------------------------------------------------------------------------
  const handleWsMessage = useCallback((event: MessageEvent) => {
    if (typeof event.data === "string") {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      if (msg.type === "transcript") {
        const speaker = msg.speaker as string;
        const segmentId = msg.segment_id as string;
        const sequence = msg.sequence as number;
        const text = msg.text as string;
        const isFinal = msg.is_final as boolean;
        const confidence = msg.confidence as number | undefined;
        const startTs = msg.start_ts as number | undefined;

        if (speaker === "claimant") {
          if (!isFinal) {
            // Update partial segment in-place (does not create new history item)
            setPartialSegments((prev) => {
              const next = new Map(prev);
              next.set(segmentId, {
                segment_id: segmentId,
                sequence,
                speaker: "user",
                text,
                is_final: false,
                start_ts: startTs,
                confidence,
              });
              return next;
            });
          } else {
            // Final: remove from partials, add to history (or update if already there)
            setPartialSegments((prev) => {
              const next = new Map(prev);
              next.delete(segmentId);
              return next;
            });
            if (text && text.trim()) {
              setHistory((prev) => {
                // Check if there's already a history entry for this segment_id
                const existing = prev.findIndex((t) => t.segment_id === segmentId);
                if (existing !== -1) {
                  const updated = [...prev];
                  updated[existing] = { ...updated[existing], text, segment_id: segmentId };
                  return updated;
                }
                return [...prev, {
                  turn: prev.length + 1,
                  speaker: "user",
                  text,
                  segment_id: segmentId,
                }];
              });
            }
          }
        } else if (speaker === "agent") {
          // Agent transcript arrives from LLM text — add directly to history
          setHistory((prev) => {
            const existing = prev.findIndex((t) => t.segment_id === segmentId);
            if (existing !== -1) {
              return prev; // already present (no duplicates)
            }
            return [...prev, {
              turn: prev.length + 1,
              speaker: "agent",
              text,
              segment_id: segmentId,
            }];
          });
        }

      } else if (msg.type === "state_update") {
        setExtractedData((msg.extracted_data as ExtractedData) || {});
        setMissingFields((msg.missing_fields as string[]) || []);
        if (msg.conversation_status) {
          setConversationStatus(msg.conversation_status as string);
        }
        if (msg.confirmed) {
          setConfirmed(true);
        }

      } else if (msg.type === "agent_text_fallback") {
        const text = msg.text as string;
        // Display in history if not already there (via transcript event)
        setHistory((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.speaker === "agent" && last.text === text) {
            return prev;
          }
          return [...prev, { turn: prev.length + 1, speaker: "agent", text }];
        });
        // Play via Web Speech API
        if ("speechSynthesis" in window) {
          const utterance = new SpeechSynthesisUtterance(text);
          window.speechSynthesis.speak(utterance);
        }

      } else if (msg.type === "error") {
        const detail = msg.detail as string;
        // Show visible error (not just console.error)
        setErrorBanner(detail || "An unexpected error occurred.");

      } else if (msg.type === "session_end") {
        setIsRecording(false);
      }

    } else if (event.data instanceof Blob) {
      enqueueAudio(event.data);
    }
  }, [enqueueAudio]);

  // ---------------------------------------------------------------------------
  // Voice recording — AudioWorklet path
  // ---------------------------------------------------------------------------
  const startVoiceRecording = async () => {
    if (!ticketId) return;
    setErrorBanner("");

    try {
      const wsUrl = API_BASE.replace(/^http/, "ws") + `/ws/claims/${ticketId}/voice`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = handleWsMessage;
      ws.onclose = () => {
        setIsRecording(false);
        setPartialSegments(new Map());
      };
      ws.onerror = () => {
        setErrorBanner("WebSocket connection error. Please check your network and try again.");
        setIsRecording(false);
      };

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        setTimeout(() => reject(new Error("WebSocket connection timeout")), 8000);
      });

      // Request microphone with echo cancellation and noise suppression
      // Echo cancellation (AEC) prevents agent TTS from being captured by the mic
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,     // AEC: primary defence against TTS echo
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioContext = new AudioCtx({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      // Load AudioWorklet processor module
      try {
        await audioContext.audioWorklet.addModule("/audio-processor.js");
      } catch (workletErr) {
        // AudioWorklet not supported (very old browser) — fall back to ScriptProcessorNode
        console.warn("AudioWorklet not supported, falling back to ScriptProcessorNode:", workletErr);
        _startScriptProcessorFallback(audioContext, stream, ws);
        setIsRecording(true);
        return;
      }

      const source = audioContext.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioContext, "pcm16-processor");
      workletNodeRef.current = workletNode;

      // Receive PCM16 chunks from the AudioWorklet thread
      workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
        }
      };

      source.connect(workletNode);
      // Do NOT connect workletNode to destination — we don't want to hear ourselves
      setIsRecording(true);

    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Voice initialization failed: ${msg}`);
      setIsRecording(false);
    }
  };

  /**
   * Fallback to ScriptProcessorNode for browsers without AudioWorklet support.
   * Deprecated but retained for compatibility.
   */
  function _startScriptProcessorFallback(
    audioContext: AudioContext,
    stream: MediaStream,
    ws: WebSocket,
  ) {
    const source = audioContext.createMediaStreamSource(stream);
    // ScriptProcessorNode is deprecated but retained as fallback for browsers without AudioWorklet
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      if (ws.readyState === WebSocket.OPEN) {
        const inputData = e.inputBuffer.getChannelData(0);
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        ws.send(pcm16.buffer);
      }
    };
    source.connect(processor);
    processor.connect(audioContext.destination);
  }

  const stopVoiceRecording = () => {
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      // Send end_session to trigger the backend to flush ASR and respond,
      // but do NOT close the WebSocket here. The backend will close it cleanly
      // after sending the final agent response, or ws.onclose will handle it.
      wsRef.current.send(JSON.stringify({ type: "end_session" }));
    }
    setIsRecording(false);
  };

  // ---------------------------------------------------------------------------
  // Text-based fallback intake
  // ---------------------------------------------------------------------------
  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || !ticketId || loading) return;

    const userText = textInput.trim();
    setTextInput("");
    setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text: userText }]);
    setLoading(true);
    setErrorBanner("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/intake`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_id: ticketId,
          claim_text: userText,
          input_mode: "text",
        }),
      });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      const data = await res.json();
      setExtractedData(data.extracted_data || {});
      setMissingFields(data.missing_fields || []);
      if (data.conversation_status) {
        setConversationStatus(data.conversation_status);
      }
      if (data.confirmed) {
        setConfirmed(true);
      }
      setHistory((prev) => [
        ...prev,
        {
          turn: prev.length + 1,
          speaker: "agent",
          text: data.message || "Thank you for providing those details.",
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Text intake failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Confirm claim
  // ---------------------------------------------------------------------------
  const handleConfirmSubmit = async () => {
    if (!ticketId || loading) return;
    setErrorBanner("");
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setConfirmed(true);
      setConversationStatus("intake_complete");
      setSubmittedMessage(data.response_message || "Claim submitted and recorded successfully!");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Confirm failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const completedFieldsCount = 5 - missingFields.length;
  const progressPercent = Math.round((completedFieldsCount / 5) * 100);

  // Merge history + active partial segments for rendering
  const activePartials = Array.from(partialSegments.values()).sort((a, b) => a.sequence - b.sequence);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-30 px-6 py-4 flex items-center justify-between shadow-lg shadow-black/40">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center text-xl shadow-md shadow-cyan-500/20">
            🎙️
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              Voice Claim Intake
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 font-medium">
                Phase 1 Active
              </span>
            </h1>
            <p className="text-xs text-slate-400">Speech-driven insurance FNOL &amp; structured data gathering</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs">
            <span className="text-slate-400">Ticket:</span>
            <span className="font-mono font-semibold text-cyan-300">{ticketId || "Connecting..."}</span>
          </div>
          <button
            onClick={initSession}
            disabled={loading}
            className="px-3.5 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-200 border border-slate-700 rounded-lg transition"
          >
            New Session
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {errorBanner && (
        <div className="mx-4 mt-3 flex items-start gap-3 bg-rose-950/70 border border-rose-600/50 rounded-xl px-4 py-3 text-sm text-rose-200 shadow-md">
          <span className="text-rose-400 shrink-0 mt-0.5">⚠️</span>
          <span className="flex-1">{errorBanner}</span>
          <button
            onClick={() => setErrorBanner("")}
            className="text-rose-400 hover:text-rose-200 shrink-0 text-lg leading-none"
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Grid */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Left Column: Supported Categories & Live Conversation */}
        <section className="lg:col-span-7 flex flex-col gap-4">

          {/* Supported 6 Insurance Types Banner */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-sm">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2.5 flex items-center justify-between">
              <span>Supported Insurance Types (Strict 6)</span>
              <span className="text-[10px] text-cyan-400 lowercase">voice-classified</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {SUPPORTED_INSURANCE_TYPES.map((type) => {
                const isSelected = extractedData.claim_type === type.id;
                return (
                  <div
                    key={type.id}
                    className={`p-2.5 rounded-xl border transition-all flex items-start gap-2.5 ${
                      isSelected
                        ? "bg-cyan-950/60 border-cyan-500 text-cyan-100 shadow-md shadow-cyan-500/10 scale-[1.02]"
                        : "bg-slate-950/40 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <span className="text-xl">{type.icon}</span>
                    <div className="min-w-0">
                      <div className="font-medium text-xs truncate flex items-center gap-1">
                        {type.name}
                        {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate">{type.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Conversation Chat Log */}
          <div className="flex-1 min-h-[380px] max-h-[500px] bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col overflow-hidden shadow-inner">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center justify-between border-b border-slate-800/80 pb-2">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Live Intake Dialogue
              </span>
              <span className="text-xs text-slate-500">{history.length} turns</span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {/* Finalized conversation history */}
              {history.map((turn, idx) => {
                const isAgent = turn.speaker === "agent";
                return (
                  <div
                    key={`hist-${idx}-${turn.segment_id ?? idx}`}
                    className={`flex items-start gap-3 ${isAgent ? "justify-start" : "justify-end"}`}
                  >
                    {isAgent && (
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-sm shadow-md shrink-0">
                        🤖
                      </div>
                    )}
                    <div
                      className={`max-w-[82%] rounded-2xl px-4 py-2.5 text-sm shadow-sm leading-relaxed whitespace-pre-line ${
                        isAgent
                          ? "bg-slate-800/90 text-slate-100 border border-slate-700/80 rounded-tl-sm"
                          : "bg-cyan-600 text-white rounded-tr-sm shadow-cyan-900/30"
                      }`}
                    >
                      {turn.text}
                    </div>
                    {!isAgent && (
                      <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-sm shrink-0">
                        👤
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Active partial transcript segments (streaming, in-place update) */}
              {activePartials.map((seg) => (
                <div
                  key={`partial-${seg.segment_id}`}
                  className="flex items-start gap-3 justify-end"
                >
                  <div className="max-w-[82%] rounded-2xl px-4 py-2.5 text-sm shadow-sm leading-relaxed whitespace-pre-line bg-cyan-700/60 text-white rounded-tr-sm border border-cyan-500/30 italic">
                    {seg.text}
                    <span className="inline-block ml-1 w-1.5 h-3.5 bg-cyan-300 animate-pulse rounded-sm align-middle" />
                  </div>
                  <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-sm shrink-0">
                    👤
                  </div>
                </div>
              ))}

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Voice & Text Input Controls */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  id="voice-toggle-btn"
                  onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
                  disabled={loading || confirmed}
                  className={`px-5 py-2.5 rounded-xl font-medium text-sm flex items-center gap-2 transition-all shadow-lg active:scale-95 ${
                    isRecording
                      ? "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30 animate-pulse"
                      : "bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-cyan-600/20"
                  }`}
                >
                  <span className="text-lg">{isRecording ? "⏹️" : "🎙️"}</span>
                  <span>{isRecording ? "Stop Speaking" : "Speak to Agent"}</span>
                </button>
                {isRecording && (
                  <span className="text-xs text-rose-400 flex items-center gap-1.5 font-medium animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                    Listening...
                  </span>
                )}
              </div>

              {conversationStatus === "confirming" && !confirmed && (
                <button
                  id="confirm-submit-btn"
                  onClick={handleConfirmSubmit}
                  disabled={loading}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded-xl shadow-md shadow-emerald-900/30 active:scale-95 transition"
                >
                  ✓ Confirm &amp; Submit Claim
                </button>
              )}
            </div>

            {/* Text Fallback Form */}
            <form onSubmit={handleTextSubmit} className="flex gap-2">
              <input
                id="text-input"
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder={isRecording ? "Listening via microphone..." : "Or type your response here..."}
                disabled={isRecording || loading || confirmed}
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition"
              />
              <button
                id="text-submit-btn"
                type="submit"
                disabled={!textInput.trim() || isRecording || loading || confirmed}
                className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-200 text-sm font-medium rounded-xl border border-slate-700 transition"
              >
                Send
              </button>
            </form>
          </div>

        </section>

        {/* Right Column: Structured Extracted Claim Data & Checklist */}
        <aside className="lg:col-span-5 flex flex-col gap-4">

          {/* Progress Card */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Intake Progress</span>
              <span className="text-xs font-bold text-cyan-400">{progressPercent}% Completed</span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-cyan-500 to-emerald-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              ></div>
            </div>
          </div>

          {/* Structured Claim Object Details */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-sm flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <span>📋</span> Structured Claim State
              </h2>
              <span
                className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold uppercase tracking-wider border ${
                  confirmed
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : conversationStatus === "confirming"
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse"
                    : "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
                }`}
              >
                {confirmed ? "Submitted" : conversationStatus}
              </span>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Policy ID</span>
                <span className="font-mono font-semibold text-slate-100">
                  {extractedData.policy_id || <span className="text-slate-600 font-normal italic">Waiting for voice/text...</span>}
                </span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Insurance Type</span>
                <span className="font-semibold text-cyan-300 capitalize">
                  {extractedData.claim_type || <span className="text-slate-600 font-normal italic">Pending classification</span>}
                </span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Incident Date</span>
                <span className="font-medium text-slate-100">
                  {extractedData.incident_date || <span className="text-slate-600 font-normal italic">Not recorded</span>}
                </span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Estimated Amount</span>
                <span className="font-bold text-emerald-400">
                  {extractedData.claimed_amount != null
                    ? `₹${Number(extractedData.claimed_amount).toLocaleString("en-IN")}`
                    : <span className="text-slate-600 font-normal italic">Pending estimate</span>}
                </span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col gap-1">
                <span className="text-slate-400 font-medium">Incident Description</span>
                <p className="text-slate-200 leading-relaxed text-[11px]">
                  {extractedData.damage_description || <span className="text-slate-600 italic">No description provided yet.</span>}
                </p>
              </div>
            </div>
          </div>

          {/* Mandatory Fields Checklist */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Intake Field Checklist
            </h3>
            <div className="space-y-2 text-xs">
              {[
                { id: "claim_type", label: "Insurance Type (Strict 6)" },
                { id: "damage_description", label: "Incident Details / Narrative" },
                { id: "incident_date", label: "Date of Incident" },
                { id: "policy_id", label: "Policy Number" },
                { id: "claimed_amount", label: "Estimated Loss Amount" },
              ].map((f) => {
                const isProvided = !missingFields.includes(f.id);
                return (
                  <div
                    key={f.id}
                    className={`flex items-center justify-between p-2 rounded-lg border ${
                      isProvided
                        ? "bg-emerald-950/30 border-emerald-800/40 text-emerald-200"
                        : "bg-slate-950/30 border-slate-800 text-slate-400"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className={isProvided ? "text-emerald-400" : "text-slate-600"}>
                        {isProvided ? "✓" : "○"}
                      </span>
                      {f.label}
                    </span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-md font-semibold uppercase ${
                        isProvided ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {isProvided ? "Collected" : "Required"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Confirmation Banner */}
          {confirmed && (
            <div className="bg-emerald-950/60 border border-emerald-500/60 rounded-2xl p-4 text-emerald-100 flex flex-col gap-2 shadow-lg shadow-emerald-950/40">
              <div className="flex items-center gap-2 font-bold text-sm text-emerald-300">
                <span>🎉</span> Claim Confirmed &amp; Saved
              </div>
              <p className="text-xs text-emerald-200/90 leading-relaxed">
                {submittedMessage || "Your structured claim intake is complete. Ticket ID: " + ticketId}
              </p>
            </div>
          )}

        </aside>

      </main>
    </div>
  );
}
