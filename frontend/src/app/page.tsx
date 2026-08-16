"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ExtractedData {
  policy_id?: string | null;
  incident_date?: string | null;
  claim_type?: string | null;
  damage_description?: string | null;
  claimed_amount?: number | null;
}

interface ConversationTurn {
  turn: number;
  speaker: "user" | "agent";
  text: string;
}

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
  const [confirmationMessage, setConfirmationMessage] = useState<string>("");

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Initialize a new claim session
  const initSession = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, { method: "POST" });
      const data = await res.json();
      setTicketId(data.ticket_id);
      setConversationStatus("in_progress");
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: `Hello! I am your AI Claim Intake Assistant. I will help you file your claim today. (Ticket: ${data.ticket_id}). What is your policy number or what happened?`,
        },
      ]);
    } catch (err) {
      console.error("Failed to start claim session:", err);
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

  // Text-based fallback / alternative intake
  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || !ticketId || loading) return;

    const userText = textInput.trim();
    setTextInput("");
    setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text: userText }]);
    setLoading(true);

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
      const data = await res.json();
      setExtractedData(data.extracted_data || {});
      setMissingFields(data.missing_fields || []);

      if (data.awaiting_confirmation) {
        setConversationStatus("intake_complete");
        setHistory((prev) => [
          ...prev,
          {
            turn: prev.length + 1,
            speaker: "agent",
            text: "All required details captured! Please review your claim details below and confirm to complete intake.",
          },
        ]);
      } else {
        setHistory((prev) => [
          ...prev,
          { turn: prev.length + 1, speaker: "agent", text: data.message || "Thank you. What is the next detail?" },
        ]);
      }
    } catch (err) {
      console.error("Text intake failed:", err);
    } finally {
      setLoading(false);
    }
  };

  // Start Streaming Audio over WebSocket
  const startVoiceRecording = async () => {
    if (!ticketId) return;

    try {
      const wsUrl = API_BASE.replace(/^http/, "ws") + `/ws/claims/${ticketId}/voice`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = async () => {
        setIsRecording(true);
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } });
        streamRef.current = stream;

        const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const audioContext = new AudioCtx({ sampleRate: 16000 });
        audioContextRef.current = audioContext;

        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

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
      };

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          const msg = JSON.parse(event.data);
          if (msg.type === "transcript") {
            setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text: msg.text }]);
          } else if (msg.type === "state_update") {
            setExtractedData(msg.extracted_data || {});
            setMissingFields(msg.missing_fields || []);
            if (msg.conversation_status) {
              setConversationStatus(msg.conversation_status);
            }
          } else if (msg.type === "agent_text_fallback") {
            setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "agent", text: msg.text }]);
            if ("speechSynthesis" in window) {
              const utterance = new SpeechSynthesisUtterance(msg.text);
              window.speechSynthesis.speak(utterance);
            }
          }
        } else if (event.data instanceof Blob) {
          const audioUrl = URL.createObjectURL(event.data);
          const audio = new Audio(audioUrl);
          audio.play().catch((e) => console.warn("Audio autoplay blocked:", e));
        }
      };

      ws.onclose = () => {
        setIsRecording(false);
      };
    } catch (err) {
      console.error("Voice streaming failed:", err);
      setIsRecording(false);
    }
  };

  const stopVoiceRecording = () => {
    if (processorRef.current && audioContextRef.current) {
      processorRef.current.disconnect();
      audioContextRef.current.close();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
    setIsRecording(false);
  };

  const handleConfirm = async () => {
    if (!ticketId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      });
      const data = await res.json();
      setConfirmed(true);
      setConfirmationMessage(data.response_message || "Claim submitted and confirmed successfully!");
    } catch (err) {
      console.error("Confirmation error:", err);
    } finally {
      setLoading(false);
    }
  };

  const filledFieldsCount = 5 - missingFields.length;
  const confidencePercent = Math.round((filledFieldsCount / 5) * 100);

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-950/60 border border-blue-800/60 rounded-full text-xs font-semibold text-blue-400 mb-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
            Review 1: Voice & Data Collection Intake
          </div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Insurance Claim Intake Agent
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Voice-enabled LangGraph pipeline with real-time field extraction and state management
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-xs text-slate-500 block font-mono">TICKET ID</span>
            <span className="text-sm font-mono font-semibold text-blue-400 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 inline-block">
              {ticketId || "GENERATING..."}
            </span>
          </div>
          <button
            onClick={() => void initSession()}
            className="px-3 py-2 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-lg transition"
          >
            New Session
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        {/* Left Column: Live Conversation & Voice Controller */}
        <section className="lg:col-span-7 flex flex-col gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col h-[520px]">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <h2 className="text-sm font-semibold text-slate-200">Conversation Stream</h2>
              </div>
              <span className="text-xs font-mono text-slate-400 bg-slate-800/80 px-2.5 py-1 rounded-md">
                Status: {conversationStatus}
              </span>
            </div>

            {/* Conversation Turn Messages */}
            <div className="flex-1 overflow-y-auto py-4 space-y-3.5 pr-1">
              {history.map((item, idx) => (
                <div
                  key={idx}
                  className={`flex gap-3 ${item.speaker === "user" ? "justify-end" : "justify-start"}`}
                >
                  {item.speaker === "agent" && (
                    <div className="w-8 h-8 rounded-full bg-blue-600/30 border border-blue-500/50 flex items-center justify-center text-xs font-bold text-blue-300 shrink-0">
                      AI
                    </div>
                  )}
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                      item.speaker === "user"
                        ? "bg-blue-600 text-white rounded-tr-none shadow-md"
                        : "bg-slate-800 border border-slate-700/60 text-slate-200 rounded-tl-none"
                    }`}
                  >
                    <p className="leading-relaxed">{item.text}</p>
                  </div>
                  {item.speaker === "user" && (
                    <div className="w-8 h-8 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center text-xs font-bold text-slate-200 shrink-0">
                      YOU
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex gap-2 items-center text-xs text-slate-400 animate-pulse pl-11">
                  <span>Assistant is thinking...</span>
                </div>
              )}
            </div>

            {/* Voice & Text Input Controls */}
            <div className="pt-4 border-t border-slate-800 space-y-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
                  className={`flex-1 py-3 px-4 rounded-xl font-medium text-sm flex items-center justify-center gap-2.5 transition shadow-lg ${
                    isRecording
                      ? "bg-red-600 hover:bg-red-700 text-white animate-pulse"
                      : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white"
                  }`}
                >
                  <span className="text-lg">🎙️</span>
                  <span>{isRecording ? "Listening... Click to Stop" : "Start Voice Intake"}</span>
                </button>
              </div>

              {/* Text Fallback Form */}
              <form onSubmit={handleTextSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="Or type claim details (e.g., 'Policy XYZ123, car damage 50000')..."
                  className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
                <button
                  type="submit"
                  disabled={loading || !textInput.trim()}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-sm font-medium rounded-xl transition"
                >
                  Send
                </button>
              </form>
            </div>
          </div>
        </section>

        {/* Right Column: Live Extraction State & Validation */}
        <section className="lg:col-span-5 flex flex-col gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-5">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <h2 className="text-sm font-semibold text-slate-200">Extraction Progress</h2>
                <span className="text-xs font-mono font-bold text-blue-400">{confidencePercent}% Complete</span>
              </div>
              <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                <div
                  className="bg-gradient-to-r from-blue-500 to-emerald-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${confidencePercent}%` }}
                ></div>
              </div>
            </div>

            {/* Extracted Fields Table */}
            <div className="space-y-2.5">
              <h3 className="text-xs font-semibold text-slate-400 tracking-wider uppercase">Mandatory Fields</h3>

              {[
                { label: "Policy Number", key: "policy_id", val: extractedData.policy_id },
                { label: "Incident Date", key: "incident_date", val: extractedData.incident_date },
                { label: "Claim Type", key: "claim_type", val: extractedData.claim_type },
                { label: "Damage Description", key: "damage_description", val: extractedData.damage_description },
                {
                  label: "Claimed Amount",
                  key: "claimed_amount",
                  val: extractedData.claimed_amount ? `₹${extractedData.claimed_amount.toLocaleString()}` : null,
                },
              ].map((field) => {
                const isPresent = Boolean(field.val);
                return (
                  <div
                    key={field.key}
                    className={`p-3 rounded-xl border flex justify-between items-start text-xs transition ${
                      isPresent
                        ? "bg-slate-950/60 border-emerald-900/40 text-slate-200"
                        : "bg-slate-950/30 border-slate-800/80 text-slate-500"
                    }`}
                  >
                    <div>
                      <span className="font-semibold block text-slate-300">{field.label}</span>
                      <span className="font-mono text-slate-400 break-all">{field.val || "Not provided"}</span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isPresent
                          ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                          : "bg-amber-950/60 text-amber-400 border border-amber-800/60"
                      }`}
                    >
                      {isPresent ? "CAPTURED" : "MISSING"}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Missing Fields Summary */}
            {missingFields.length > 0 ? (
              <div className="p-3 bg-amber-950/30 border border-amber-800/40 rounded-xl">
                <span className="text-xs font-semibold text-amber-400 block mb-1">Awaiting Information</span>
                <div className="flex flex-wrap gap-1.5">
                  {missingFields.map((f) => (
                    <span key={f} className="px-2 py-0.5 bg-amber-900/40 text-amber-300 rounded text-[11px] font-mono">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-3 bg-emerald-950/40 border border-emerald-800/50 rounded-xl space-y-2">
                <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold">
                  <span>✓</span>
                  <span>All 5 mandatory fields captured!</span>
                </div>
                {!confirmed ? (
                  <button
                    onClick={() => void handleConfirm()}
                    disabled={loading}
                    className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded-lg transition shadow-md"
                  >
                    Confirm & Complete Intake
                  </button>
                ) : (
                  <div className="p-2 bg-emerald-900/50 rounded text-xs text-emerald-200 font-medium">
                    {confirmationMessage}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
