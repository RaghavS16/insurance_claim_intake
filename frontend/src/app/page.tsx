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

interface UploadedDocument {
  document_id: string;
  document_type: string;
  filename: string;
  uploaded_at?: string | null;
}

export default function ClaimIntakePage() {
  const [activeTab, setActiveTab] = useState<"intake" | "documents">("intake");
  const [ticketId, setTicketId] = useState<string>("");
  const [conversationStatus, setConversationStatus] = useState<string>("not_started");
  const [extractedData, setExtractedData] = useState<ExtractedData>({});
  const [fieldStatus, setFieldStatus] = useState<Record<string, string>>({});
  const [missingFields, setMissingFields] = useState<string[]>([
    "policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"
  ]);
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [textInput, setTextInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmed, setConfirmed] = useState<boolean>(false);
  const [confirmationMessage, setConfirmationMessage] = useState<string>("");

  // Documents tab state
  const [documentsList, setDocumentsList] = useState<UploadedDocument[]>([]);
  const [selectedDocType, setSelectedDocType] = useState<string>("damage_photo");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [docUploadLoading, setDocUploadLoading] = useState<boolean>(false);
  const [docUploadMessage, setDocUploadMessage] = useState<string>("");

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
      setConversationStatus("collecting");
      setConfirmed(false);
      setConfirmationMessage("");
      setExtractedData({});
      setFieldStatus({});
      setMissingFields(["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]);
      setDocumentsList([]);
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || "Please tell me what happened. You can describe the incident in your own words, and I'll collect the details I need.",
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

  // Fetch documents for the current ticket
  const fetchDocuments = useCallback(async () => {
    if (!ticketId) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocumentsList(data);
      }
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    }
  }, [ticketId]);

  useEffect(() => {
    let ignore = false;
    const loadDocs = async () => {
      if (activeTab === "documents" && ticketId && !ignore) {
        await fetchDocuments();
      }
    };
    loadDocs();
    return () => {
      ignore = true;
    };
  }, [activeTab, ticketId, fetchDocuments]);

  // Text-based fallback intake
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
      setFieldStatus(data.field_status || {});
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
          text: data.message || "Thank you for the information.",
        },
      ]);
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
            setFieldStatus(msg.field_status || {});
            setMissingFields(msg.missing_fields || []);
            if (msg.conversation_status) {
              setConversationStatus(msg.conversation_status);
            }
            if (msg.confirmed) {
              setConfirmed(true);
            }
            if (msg.agent_text) {
              setHistory((prev) => {
                const last = prev[prev.length - 1];
                if (last && last.speaker === "agent" && last.text === msg.agent_text) {
                  return prev;
                }
                return [...prev, { turn: prev.length + 1, speaker: "agent", text: msg.agent_text }];
              });
            }
          } else if (msg.type === "agent_text_fallback") {
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

  // Explicit confirmation button handler
  const handleConfirm = async () => {
    if (!ticketId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/intake`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_id: ticketId,
          claim_text: "Yes, everything is correct.",
          input_mode: "text",
        }),
      });
      const data = await res.json();
      setConfirmed(true);
      setConversationStatus("intake_complete");
      setConfirmationMessage(data.message || "Your claim intake is complete and submitted for review.");
      setHistory((prev) => [
        ...prev,
        { turn: prev.length + 1, speaker: "user", text: "Yes, everything is correct." },
        { turn: prev.length + 2, speaker: "agent", text: data.message || "Perfect! Your claim intake is complete." },
      ]);
    } catch (err) {
      console.error("Confirmation error:", err);
    } finally {
      setLoading(false);
    }
  };

  // Document upload handler
  const handleDocumentUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketId || !selectedFile || docUploadLoading) return;

    setDocUploadLoading(true);
    setDocUploadMessage("");

    const formData = new FormData();
    formData.append("document_type", selectedDocType);
    formData.append("file", selectedFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/documents`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        setDocUploadMessage("Document uploaded successfully!");
        setSelectedFile(null);
        fetchDocuments();
      } else {
        const err = await res.json();
        setDocUploadMessage(`Upload failed: ${err.detail || "Error"}`);
      }
    } catch {
      setDocUploadMessage("Upload error: Could not reach server.");
    } finally {
      setDocUploadLoading(false);
    }
  };

  const filledFieldsCount = Object.values(fieldStatus).filter((s) => s === "provided").length;
  const confidencePercent = Math.round((filledFieldsCount / 5) * 100);

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-950/60 border border-blue-800/60 rounded-full text-xs font-semibold text-blue-400 mb-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
            Review 1: Voice & Conversational Claim Intake
          </div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            Insurance Claim Intake Voice Agent
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Natural voice conversation, multi-field extraction, and real-time state confirmation
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

      {/* Tab Navigation */}
      <div className="flex gap-4 mt-6 border-b border-slate-800">
        <button
          onClick={() => setActiveTab("intake")}
          className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
            activeTab === "intake"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>🎙️</span>
          <span>Voice Claim Intake (Review 1)</span>
        </button>
        <button
          onClick={() => setActiveTab("documents")}
          className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition ${
            activeTab === "documents"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>📄</span>
          <span>Supporting Documents (Review 2/3)</span>
          {documentsList.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] text-blue-300">
              {documentsList.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab 1: Voice Claim Intake (Hero Experience) */}
      {activeTab === "intake" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
          {/* Left Column: Live Conversation & Audio Controls */}
          <section className="lg:col-span-7 flex flex-col gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col h-[540px]">
              <div className="flex justify-between items-center pb-4 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${isRecording ? "bg-red-500 animate-ping" : "bg-emerald-500"}`}></span>
                  <h2 className="text-sm font-semibold text-slate-200">Conversation Stream</h2>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-slate-400 bg-slate-800/80 px-2.5 py-1 rounded-md uppercase">
                    Status: {conversationStatus}
                  </span>
                </div>
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
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-line ${
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

              {/* Confirmation Action Box (When state is 'confirming') */}
              {conversationStatus === "confirming" && !confirmed && (
                <div className="p-3 bg-blue-950/40 border border-blue-800/50 rounded-xl mb-3 flex items-center justify-between gap-3">
                  <div className="text-xs text-blue-300">
                    <span className="font-semibold block text-blue-200">Confirmation Ready</span>
                    You can say <span className="font-mono text-white font-bold">&quot;Yes&quot;</span> or click to confirm.
                  </div>
                  <button
                    onClick={() => void handleConfirm()}
                    disabled={loading}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg transition shadow-md whitespace-nowrap"
                  >
                    ✓ Confirm Claim
                  </button>
                </div>
              )}

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
                    placeholder="Or type your reply (e.g., 'ABC12345' or 'Actually, amount is 60000')..."
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

          {/* Right Column: Live Extraction State & Collected Checklist */}
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

              {/* Extracted Mandatory Fields Checklist */}
              <div className="space-y-2.5">
                <h3 className="text-xs font-semibold text-slate-400 tracking-wider uppercase">Collected Information</h3>

                {[
                  { label: "Policy Number", key: "policy_id", val: extractedData.policy_id },
                  { label: "Incident Date", key: "incident_date", val: extractedData.incident_date },
                  {
                    label: "Insurance Type",
                    key: "claim_type",
                    val: extractedData.claim_type
                      ? {
                          motor: "Motor",
                          health: "Health",
                          senior_health: "Senior Health",
                          home: "Home",
                          travel: "Travel",
                          cyber: "Cyber",
                          auto: "Motor",
                        }[extractedData.claim_type.toLowerCase()] || extractedData.claim_type
                      : null,
                  },
                  { label: "Incident Description", key: "damage_description", val: extractedData.damage_description },
                  {
                    label: "Estimated Amount",
                    key: "claimed_amount",
                    val: extractedData.claimed_amount ? `₹${extractedData.claimed_amount.toLocaleString()}` : null,
                  },
                ].map((field) => {
                  const status = fieldStatus[field.key] || (field.val ? "provided" : "missing");
                  const isProvided = status === "provided";
                  const isDeferred = status === "deferred";

                  return (
                    <div
                      key={field.key}
                      className={`p-3 rounded-xl border flex justify-between items-start text-xs transition ${
                        isProvided
                          ? "bg-slate-950/60 border-emerald-900/40 text-slate-200"
                          : isDeferred
                          ? "bg-slate-950/40 border-amber-900/40 text-slate-300"
                          : "bg-slate-950/20 border-slate-800/80 text-slate-500"
                      }`}
                    >
                      <div>
                        <span className="font-semibold block text-slate-300">{field.label}</span>
                        <span className="font-mono text-slate-400 break-all">{field.val || (isDeferred ? "Deferred for later" : "Not provided")}</span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isProvided
                            ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                            : isDeferred
                            ? "bg-amber-950/60 text-amber-400 border border-amber-800/60"
                            : "bg-slate-800 text-slate-400 border border-slate-700"
                        }`}
                      >
                        {isProvided ? "✓ CAPTURED" : isDeferred ? "○ DEFERRED" : "○ MISSING"}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Status Box */}
              {conversationStatus === "intake_complete" ? (
                <div className="p-3.5 bg-emerald-950/40 border border-emerald-800/50 rounded-xl space-y-1.5">
                  <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold">
                    <span className="text-base">✓</span>
                    <span>Claim Intake Complete & Confirmed!</span>
                  </div>
                  <p className="text-[11px] text-emerald-200/80">
                    {confirmationMessage || `Ticket ${ticketId} is now ready for evaluation.`}
                  </p>
                </div>
              ) : conversationStatus === "confirming" ? (
                <div className="p-3.5 bg-blue-950/40 border border-blue-800/50 rounded-xl">
                  <div className="flex items-center gap-2 text-blue-400 text-xs font-semibold mb-1">
                    <span>💬</span>
                    <span>Awaiting Confirmation</span>
                  </div>
                  <p className="text-[11px] text-slate-300">
                    Please review the details in the chat. Speak &quot;Yes&quot; to seal the intake or state any corrections.
                  </p>
                </div>
              ) : (
                <div className="p-3 bg-slate-950/50 border border-slate-800 rounded-xl">
                  <span className="text-[11px] text-slate-400 block">
                    Remaining fields to collect: <span className="text-blue-400 font-mono">{missingFields.join(", ") || "None"}</span>
                  </span>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Tab 2: Supporting Documents (Cleanly Isolated) */}
      {activeTab === "documents" && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl mt-6 space-y-6">
          <div>
            <h2 className="text-lg font-bold text-white">Supporting Documentation</h2>
            <p className="text-xs text-slate-400 mt-1">
              Upload photos or damage estimates for claim ticket <span className="font-mono text-blue-400 font-semibold">{ticketId}</span>.
              (Note: Supporting documents are evaluated in Review 2/3 and do not block Review 1 voice intake.)
            </p>
          </div>

          <form onSubmit={handleDocumentUpload} className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-4 max-w-xl">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Document Type</label>
              <select
                value={selectedDocType}
                onChange={(e) => setSelectedDocType(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="damage_photo">Damage Photo (JPG, PNG)</option>
                <option value="repair_estimate">Repair Cost Estimate (PDF, JPG)</option>
                <option value="fir">Police Report / FIR (PDF, JPG)</option>
                <option value="medical_bill">Medical Bill (PDF, JPG)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Select File</label>
              <input
                type="file"
                accept=".jpg,.jpeg,.png,.pdf,.webp"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-blue-600 file:text-white hover:file:bg-blue-500"
              />
            </div>

            {docUploadMessage && (
              <p className={`text-xs ${docUploadMessage.includes("success") ? "text-emerald-400" : "text-red-400"}`}>
                {docUploadMessage}
              </p>
            )}

            <button
              type="submit"
              disabled={docUploadLoading || !selectedFile}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg transition"
            >
              {docUploadLoading ? "Uploading..." : "Upload Document"}
            </button>
          </form>

          {/* Uploaded Documents List */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Uploaded Documents</h3>
            {documentsList.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No documents uploaded for this claim ticket yet.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {documentsList.map((doc) => (
                  <div key={doc.document_id} className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between text-xs">
                    <div>
                      <span className="font-semibold text-slate-200 block">{doc.filename}</span>
                      <span className="text-[10px] text-slate-500 uppercase font-mono">{doc.document_type}</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                      UPLOADED
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
