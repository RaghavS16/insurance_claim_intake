"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ExtractedData {
  policy_id?: string | null;
  incident_date?: string | null;
  claim_type?: string | null;
  damage_description?: string | null;
  claimed_amount?: number | null;
}

interface TranscriptSegment {
  segment_id: string;
  sequence: number;
  speaker: "user" | "agent";
  text: string;
  is_final: boolean;
  start_ts?: number;
  confidence?: number;
  global_seq?: number;
  timestamp?: number;
}

interface ConversationTurn {
  turn: number;
  speaker: "user" | "agent";
  text: string;
  segment_id?: string;
  global_seq?: number;
  timestamp?: number;
}

export default function ClaimantPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
  const [userName, setUserName] = useState<string>("");
  const [ticketId, setTicketId] = useState<string>("");
  const [conversationStatus, setConversationStatus] = useState<string>("not_started");
  const [agentState, setAgentState] = useState<string>("listening"); // listening, thinking, speaking
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
  const [errorBanner, setErrorBanner] = useState<string>("");

  const [partialSegments, setPartialSegments] = useState<Map<string, TranscriptSegment>>(new Map());

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef<boolean>(false);
  const isSpeakingFallbackRef = useRef<boolean>(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  // Authenticate user on load
  useEffect(() => {
    const savedToken = localStorage.getItem("access_token");
    if (!savedToken) {
      router.push("/login");
      return;
    }
    setToken(savedToken);

    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${savedToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Session expired");
        return res.json();
      })
      .then((data) => {
        if (data.role !== "CLAIMANT") {
          router.push("/login");
          return;
        }
        setUserId(data.id);
        setUserName(data.full_name);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router]);

  // Auto-scroll to bottom
  const scrollToBottom = useCallback((force = false) => {
    const container = chatContainerRef.current;
    if (!container) return;
    const threshold = 150;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
    if (force || isNearBottom) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, []);

  useEffect(() => {
    scrollToBottom(true);
  }, [history.length, scrollToBottom]);

  // Handle Logout
  const handleLogout = () => {
    if (isRecording) {
      stopVoiceRecording();
    }
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  // Initialize Session
  const initSession = useCallback(async () => {
    if (!token || !userId) return;
    try {
      setLoading(true);
      setErrorBanner("");
      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
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
          global_seq: 0,
          timestamp: Date.now() - 1000,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Failed to start claim session: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [token, userId]);

  useEffect(() => {
    if (token && userId) {
      initSession();
    }
  }, [token, userId, initSession]);

  // Audio queue playback
  const enqueueAudio = useCallback((blob: Blob) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audioQueueRef.current.push(audio);

    const playNext = () => {
      if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
      const next = audioQueueRef.current.shift();
      if (!next) return;

      isPlayingRef.current = true;
      activeAudioRef.current = next;

      next.onplay = () => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "tts_started" }));
        }
      };

      const onStopPlayback = () => {
        URL.revokeObjectURL(url);
        isPlayingRef.current = false;
        if (activeAudioRef.current === next) {
          activeAudioRef.current = null;
        }
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "tts_stopped" }));
        }
        playNext();
      };

      next.onended = onStopPlayback;
      next.onpause = onStopPlayback;

      next.play().catch((e) => {
        console.warn("Audio autoplay prevented:", e);
        isPlayingRef.current = false;
        activeAudioRef.current = null;
        playNext();
      });
    };

    playNext();
  }, []);

  // WebSocket message handler
  const handleWsMessage = useCallback((event: MessageEvent) => {
    if (typeof event.data === "string") {
      let msg: Record<string, any>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      if (msg.type === "barge_in") {
        console.log("Interruption detected: stopping agent playback");
        if (activeAudioRef.current) {
          activeAudioRef.current.pause();
          activeAudioRef.current = null;
        }
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          isSpeakingFallbackRef.current = false;
        }
        audioQueueRef.current = [];
        isPlayingRef.current = false;
        setPartialSegments(new Map());

      } else if (msg.type === "agent_state") {
        setAgentState(msg.state as string);

      } else if (msg.type === "transcript") {
        const speaker = msg.speaker as string;
        const segmentId = msg.segment_id as string;
        const sequence = msg.sequence as number;
        const text = msg.text as string;
        const isFinal = msg.is_final as boolean;
        const confidence = msg.confidence as number | undefined;
        const startTs = msg.start_ts as number | undefined;
        const globalSeq = msg.global_seq as number | undefined;
        const timestamp = msg.timestamp as number | undefined;

        if (speaker === "claimant") {
          if (!isFinal) {
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
                global_seq: globalSeq,
                timestamp: timestamp,
              });
              return next;
            });
          } else {
            setPartialSegments((prev) => {
              const next = new Map(prev);
              next.delete(segmentId);
              return next;
            });
            if (text && text.trim()) {
              setHistory((prev) => {
                const existing = prev.findIndex((t) => t.segment_id === segmentId);
                if (existing !== -1) {
                  const updated = [...prev];
                  updated[existing] = {
                    ...updated[existing],
                    text,
                    segment_id: segmentId,
                    global_seq: globalSeq,
                    timestamp: timestamp,
                  };
                  return updated;
                }
                return [...prev, {
                  turn: prev.length + 1,
                  speaker: "user",
                  text,
                  segment_id: segmentId,
                  global_seq: globalSeq,
                  timestamp: timestamp,
                }];
              });
            }
          }
        } else if (speaker === "agent") {
          setHistory((prev) => {
            const existing = prev.findIndex((t) => t.segment_id === segmentId);
            if (existing !== -1) {
              return prev;
            }
            return [...prev, {
              turn: prev.length + 1,
              speaker: "agent",
              text,
              segment_id: segmentId,
              global_seq: globalSeq,
              timestamp: timestamp,
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
        const globalSeq = msg.global_seq as number | undefined;
        setHistory((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.speaker === "agent" && last.text === text) {
            return prev;
          }
          return [...prev, {
            turn: prev.length + 1,
            speaker: "agent",
            text,
            global_seq: globalSeq,
            timestamp: Date.now(),
          }];
        });
        if ("speechSynthesis" in window) {
          const utterance = new SpeechSynthesisUtterance(text);
          utteranceRef.current = utterance; // Prevent Chrome garbage collection
          
          utterance.onstart = () => {
            isSpeakingFallbackRef.current = true;
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "tts_started" }));
            }
          };
          utterance.onend = () => {
            isSpeakingFallbackRef.current = false;
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "tts_stopped" }));
            }
          };
          utterance.onerror = () => {
            isSpeakingFallbackRef.current = false;
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "tts_stopped" }));
            }
          };
          window.speechSynthesis.speak(utterance);
        }

      } else if (msg.type === "error") {
        setErrorBanner((msg.detail as string) || "An unexpected error occurred.");

      } else if (msg.type === "session_end") {
        setIsRecording(false);
      }
    } else if (event.data instanceof Blob) {
      enqueueAudio(event.data);
    }
  }, [enqueueAudio]);

  // Voice recording
  const startVoiceRecording = async () => {
    if (!ticketId || !token) return;
    setErrorBanner("");

    try {
      const wsUrl = API_BASE.replace(/^http/, "ws") + `/ws/claims/${ticketId}/voice?token=${token}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = handleWsMessage;
      ws.onclose = () => {
        setIsRecording(false);
        setPartialSegments(new Map());
      };
      ws.onerror = () => {
        setErrorBanner("WebSocket connection error. Please reconnect.");
        setIsRecording(false);
      };

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        setTimeout(() => reject(new Error("WebSocket connection timeout")), 8000);
      });

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioCtx({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      await audioContext.audioWorklet.addModule("/audio-processor.js");

      const source = audioContext.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioContext, "pcm16-processor");
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState === WebSocket.OPEN && !isSpeakingFallbackRef.current) {
          ws.send(e.data);
        }
      };

      source.connect(workletNode);
      setIsRecording(true);

    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Voice initialization failed: ${msg}`);
      setIsRecording(false);
    }
  };

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
      wsRef.current.send(JSON.stringify({ type: "end_session" }));
    }
    setIsRecording(false);
  };

  // Text Submission
  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || textInput.length > 1000 || !ticketId || loading) return;

    const userText = textInput.trim().substring(0, 1000);
    setTextInput("");

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "text_input",
        text: userText,
      }));
      return;
    }

    setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text: userText, timestamp: Date.now() }]);
    setLoading(true);
    setErrorBanner("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/intake`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
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
          timestamp: Date.now(),
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Text intake failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  // Confirm Claim
  const handleConfirmSubmit = async () => {
    if (!ticketId || loading) return;
    setErrorBanner("");
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ confirmed: true }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setConfirmed(true);
      setConversationStatus("completed");
      setSubmittedMessage(data.message || "Claim submitted and recorded successfully!");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Confirm failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  if (!userId) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-500"></div>
      </div>
    );
  }

  const completedFieldsCount = 5 - missingFields.length;
  const progressPercent = Math.round((completedFieldsCount / 5) * 100);
  const activePartials = Array.from(partialSegments.values()).sort((a, b) => a.sequence - b.sequence);
  const liveClaimantText = activePartials.length > 0 ? activePartials[0].text : "";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-white">
      {/* Claimant Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md sticky top-0 z-30 px-6 py-4 flex items-center justify-between shadow-lg shadow-black/20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center text-xl shadow-md shadow-cyan-500/20">
            🎙️
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Insurance Assistant
            </h1>
            <p className="text-[11px] text-slate-400">Claimant Voice Intake FNOL</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex flex-col text-right">
            <span className="text-xs font-semibold text-slate-200">{userName}</span>
            <span className="text-[9px] text-slate-500">Claimant Session</span>
          </div>
          <button
            onClick={handleLogout}
            className="px-3.5 py-1.5 text-[11px] font-medium bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-300 border border-slate-700 rounded-xl transition"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {errorBanner && (
        <div className="mx-6 mt-4 flex items-start gap-3 bg-rose-950/70 border border-rose-600/50 rounded-2xl px-4 py-3.5 text-xs text-rose-200 shadow-md">
          <span className="text-rose-400 shrink-0">⚠️</span>
          <span className="flex-1 leading-normal">{errorBanner}</span>
          <button
            onClick={() => setErrorBanner("")}
            className="text-rose-400 hover:text-rose-200 shrink-0 text-base leading-none"
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Grid */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 overflow-hidden">
        {/* Left Column: Dialogue Chat Interface */}
        <section className="lg:col-span-7 flex flex-col gap-4 overflow-hidden h-[calc(100vh-140px)] min-h-[500px]">
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-4 flex items-center justify-between shadow-sm">
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-2.5 w-2.5">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  agentState === "speaking" ? "bg-cyan-400" : agentState === "thinking" ? "bg-amber-400" : "bg-emerald-400"
                }`}></span>
                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                  agentState === "speaking" ? "bg-cyan-500" : agentState === "thinking" ? "bg-amber-500" : "bg-emerald-500"
                }`}></span>
              </span>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                {agentState === "speaking" ? "Assistant is speaking" : agentState === "thinking" ? "Assistant is thinking..." : isRecording ? "Listening..." : "Silent"}
              </span>
            </div>
          </div>

          {/* Conversation Chat Log */}
          <div className="flex-1 bg-slate-900/30 border border-slate-800/80 rounded-3xl p-5 flex flex-col overflow-hidden shadow-inner">
            <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
              {history.map((turn, idx) => {
                const isAgent = turn.speaker === "agent";
                return (
                  <div
                    key={`hist-${idx}`}
                    className={`flex items-start gap-3 ${isAgent ? "justify-start" : "justify-end"}`}
                  >
                    {isAgent && (
                      <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm shrink-0">
                        🤖
                      </div>
                    )}
                    <div
                      className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm shadow-sm leading-relaxed whitespace-pre-line ${
                        isAgent
                          ? "bg-slate-900/80 text-slate-100 border border-slate-800 rounded-tl-sm"
                          : "bg-gradient-to-tr from-cyan-600 to-blue-600 text-white rounded-tr-sm shadow-md shadow-cyan-500/5"
                      }`}
                    >
                      {turn.text}
                    </div>
                  </div>
                );
              })}

              {liveClaimantText && (
                <div className="flex items-start gap-3 justify-end">
                  <div className="max-w-[78%] rounded-2xl px-4 py-3 text-sm shadow-sm leading-relaxed bg-cyan-950/60 text-cyan-100 border border-cyan-500/25 rounded-tr-sm italic">
                    {liveClaimantText}
                    <span className="inline-block ml-1 w-1.5 h-3.5 bg-cyan-400 animate-pulse rounded-sm align-middle" />
                  </div>
                </div>
              )}

              {agentState === "thinking" && (
                <div className="flex items-start gap-3 justify-start animate-fade-in">
                  <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm shrink-0">
                    🤖
                  </div>
                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl px-4 py-3.5 text-sm flex gap-1 items-center shadow-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.2s]"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce [animation-delay:0.4s]"></span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Input Controls */}
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-5 shadow-sm flex flex-col gap-4">
            {(conversationStatus === "completed" || conversationStatus === "submitted") ? (
              <div className="flex flex-col items-center justify-center py-4 text-slate-400">
                <span className="text-2xl mb-2">✅</span>
                <p className="text-sm font-medium text-slate-300">Claim intake is complete.</p>
                <p className="text-xs mt-1 text-slate-500">The assistant is no longer accepting input.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      id="voice-toggle-btn"
                      onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
                      disabled={loading || confirmed}
                      className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 relative ${
                        isRecording
                          ? "bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/30 scale-105"
                          : "bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 hover:border-cyan-500 hover:text-white"
                      }`}
                    >
                      {isRecording && (
                        <span className="absolute inset-0 rounded-full bg-rose-600 animate-ping opacity-25"></span>
                      )}
                      <span className="text-xl">{isRecording ? "⏹️" : "🎙️"}</span>
                    </button>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-slate-200">
                        {isRecording ? "Microphone active" : "Speak to file claim"}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {isRecording ? "Click to stop recording" : "Uses voice activity detection"}
                      </span>
                    </div>
                  </div>

                  {(conversationStatus === "confirming" || conversationStatus === "claimant_confirmed") && (
                    <button
                      id="confirm-submit-btn"
                      onClick={handleConfirmSubmit}
                      disabled={loading}
                      className="px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-medium text-xs rounded-2xl shadow-md shadow-emerald-950/20 active:scale-95 transition"
                    >
                      ✓ Confirm &amp; Submit Claim
                    </button>
                  )}
                </div>

                <form onSubmit={handleTextSubmit} className="flex gap-2">
                  <input
                    id="text-input"
                    type="text"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    maxLength={1000}
                    placeholder={isRecording ? "Speak now or type here to interrupt..." : "Type your response here..."}
                    disabled={loading || confirmed}
                    className="flex-1 bg-slate-950/50 border border-slate-800/80 rounded-2xl px-4.5 py-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500/80 focus:ring-1 focus:ring-cyan-500/30 transition duration-300"
                  />
                  <button
                    id="text-submit-btn"
                    type="submit"
                    disabled={!textInput.trim() || loading || confirmed}
                    className="px-5 py-3 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-200 text-xs font-semibold rounded-2xl border border-slate-700 transition"
                  >
                    Send
                  </button>
                </form>
              </>
            )}
          </div>
        </section>

        {/* Right Column: Structured Extracted Claim Data & Progress */}
        <aside className="lg:col-span-5 flex flex-col gap-4 h-[calc(100vh-140px)] min-h-[500px] overflow-y-auto pr-1">
          {/* Slim Progress Bar */}
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl px-5 py-3 shadow-sm flex flex-col gap-2">
            <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-800">
              <div
                className="bg-gradient-to-r from-cyan-500 to-emerald-400 h-full rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              ></div>
            </div>
          </div>

          <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-5.5 shadow-sm flex flex-col gap-4.5">
            <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
              <h2 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <span>📋</span> Collected Details
              </h2>
              <span
                className={`text-[9px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border ${
                  conversationStatus === "completed" || conversationStatus === "submitted"
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : conversationStatus === "confirming" || conversationStatus === "claimant_confirmed"
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/20 animate-pulse"
                    : "bg-cyan-500/10 text-cyan-400 border-cyan-500/20"
                }`}
              >
                {conversationStatus === "completed"
                  ? "Completed"
                  : conversationStatus === "submitted"
                  ? "Submitted"
                  : conversationStatus === "claimant_confirmed"
                  ? "Claimant Confirmed"
                  : conversationStatus === "confirming"
                  ? "Confirming"
                  : conversationStatus === "collecting"
                  ? "Collecting Info"
                  : conversationStatus}
              </span>
            </div>

            <div className="space-y-3.5 text-xs">
              <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/60 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Policy ID</span>
                <span className="font-mono font-semibold text-slate-200">
                  {extractedData.policy_id || <span className="text-slate-600 font-normal italic">Pending...</span>}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/60 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Insurance Category</span>
                <span className="font-semibold text-cyan-300 capitalize">
                  {extractedData.claim_type || <span className="text-slate-600 font-normal italic">Unclassified</span>}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/60 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Incident Date</span>
                <span className="font-medium text-slate-200">
                  {extractedData.incident_date || <span className="text-slate-600 font-normal italic text-slate-500">Not detected</span>}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/60 flex items-center justify-between">
                <span className="text-slate-400 font-medium">Claim Estimate</span>
                <span className="font-bold text-emerald-400">
                  {extractedData.claimed_amount != null
                    ? `₹${Number(extractedData.claimed_amount).toLocaleString("en-IN")}`
                    : <span className="text-slate-600 font-normal italic">Calculating...</span>}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/60 flex flex-col gap-1.5">
                <span className="text-slate-400 font-medium">Incident Description</span>
                <p className="text-slate-300 leading-relaxed text-[11px]">
                  {extractedData.damage_description || <span className="text-slate-600 italic">Please describe the accident or incident details.</span>}
                </p>
              </div>
            </div>
          </div>

          {conversationStatus === "completed" && (
            <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-3xl p-5 text-emerald-100 flex flex-col gap-2 shadow-lg shadow-emerald-950/20 animate-scale-up">
              <div className="flex items-center gap-2 font-bold text-xs uppercase tracking-wider text-emerald-400">
                Verified ✅
              </div>
              <p className="text-xs text-emerald-300 leading-relaxed mt-1">
                {submittedMessage || "Your structured claim intake has been finalized. Ticket reference: " + ticketId}
              </p>
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
