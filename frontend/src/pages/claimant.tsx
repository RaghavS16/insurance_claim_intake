import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/router";
import { ClaimantSidebar } from "@/components/claimant/ClaimantSidebar";
import { ClaimantTopBar } from "@/components/claimant/ClaimantTopBar";
import { ClaimantChatArea } from "@/components/claimant/ClaimantChatArea";
import { VoiceConsole } from "@/components/claimant/VoiceConsole";
import { CollectedDetailsPanel } from "@/components/claimant/CollectedDetailsPanel";
import { ManualEditModal } from "@/components/claimant/ManualEditModal";
import { ExtractedData } from "@/components/claimant/ExtractionPanel";
import { ConversationTurn } from "@/components/claimant/ChatTranscript";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export default function ClaimantPage() {
  const router = useRouter();

  const [token, setToken] = useState<string>("");
  const [userName, setUserName] = useState<string>("");
  const [ticketId, setTicketId] = useState<string>("");
  const [conversationStatus, setConversationStatus] = useState<string>("not_started");
  const [agentState, setAgentState] = useState<string>("idle"); // idle, listening, thinking, speaking
  const [extractedData, setExtractedData] = useState<ExtractedData>({});
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [textMode, setTextMode] = useState<boolean>(false);
  const [textInput, setTextInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmed, setConfirmed] = useState<boolean>(false);
  const [submittingClaim, setSubmittingClaim] = useState<boolean>(false);
  const [submittedMessage, setSubmittedMessage] = useState<string>("");
  const [errorBanner, setErrorBanner] = useState<string>("");

  // Edit Modal State
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");

  const [partialSegments, setPartialSegments] = useState<Map<string, TranscriptSegment>>(new Map());

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef<boolean>(false);
  const isRecordingRef = useRef<boolean>(false);
  isRecordingRef.current = isRecording;
  const hasInitializedRef = useRef<boolean>(false);

  // Auto-scroll to bottom
  const scrollToBottom = useCallback((force = false) => {
    const container = chatContainerRef.current;
    if (!container) return;
    const threshold = 300;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
    if (force || isNearBottom) {
      setTimeout(() => {
        if (container) {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: "smooth",
          });
        }
      }, 50);
    }
  }, []);

  useEffect(() => {
    scrollToBottom(true);
  }, [history.length, partialSegments.size, scrollToBottom]);

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
        setAgentState("speaking");
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
        if (audioQueueRef.current.length === 0) {
          setAgentState(isRecordingRef.current ? "listening" : "idle");
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
        if (activeAudioRef.current) {
          activeAudioRef.current.pause();
          activeAudioRef.current = null;
        }
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
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
        const globalSeq = msg.global_seq as number | undefined;
        const timestamp = msg.timestamp as number | undefined;

        if (speaker === "claimant" || speaker === "user") {
          if (!isFinal) {
            setPartialSegments((prev) => {
              const next = new Map(prev);
              next.set(segmentId, {
                segment_id: segmentId,
                sequence,
                speaker: "user",
                text,
                is_final: false,
                global_seq: globalSeq,
                timestamp,
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
              setHistory((prev) => [
                ...prev,
                {
                  turn: prev.length + 1,
                  speaker: "user",
                  text,
                  segment_id: segmentId,
                  global_seq: globalSeq,
                  timestamp,
                },
              ]);
            }
          }
        } else if (speaker === "agent") {
          setHistory((prev) => [
            ...prev,
            {
              turn: prev.length + 1,
              speaker: "agent",
              text,
              segment_id: segmentId,
              global_seq: globalSeq,
              timestamp,
            },
          ]);
        }
      } else if (msg.type === "state_update") {
        setExtractedData((msg.extracted_data as ExtractedData) || {});
        if (msg.conversation_status) {
          setConversationStatus(msg.conversation_status as string);
        }
        if (msg.confirmed) {
          setConfirmed(true);
        }
      } else if (msg.type === "agent_text_fallback") {
        const text = msg.text as string;
        setHistory((prev) => [
          ...prev,
          {
            turn: prev.length + 1,
            speaker: "agent",
            text,
            timestamp: Date.now(),
          },
        ]);
        if ("speechSynthesis" in window && text) {
          try {
            const utter = new SpeechSynthesisUtterance(text);
            utter.rate = 1.0;
            window.speechSynthesis.speak(utter);
          } catch {}
        }
      }
    } else if (event.data instanceof Blob) {
      enqueueAudio(event.data);
    } else if (event.data instanceof ArrayBuffer) {
      enqueueAudio(new Blob([event.data], { type: "audio/wav" }));
    }
  }, [enqueueAudio]);

  const stopVoiceRecording = useCallback(() => {
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.postMessage({ command: "stop" });
        workletNodeRef.current.disconnect();
      } catch {}
      workletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setIsRecording(false);
    setAgentState("idle");
  }, []);

  const connectWebSocket = useCallback((currentTicketId: string, currentToken: string) => {
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {}
    }
    const wsUrl = `${API_BASE.replace(/^http/, "ws")}/api/v1/ws/voice/${currentTicketId}?token=${currentToken}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "blob";
    ws.onmessage = handleWsMessage;
    ws.onclose = () => {
      if (isRecordingRef.current) stopVoiceRecording();
    };
    wsRef.current = ws;
  }, [handleWsMessage, stopVoiceRecording]);

  const startSession = useCallback(async (authToken: string, policyNum?: string) => {
    if (isRecordingRef.current) stopVoiceRecording();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    localStorage.removeItem("active_claim_ticket_id");
    setTicketId("");
    setExtractedData({});
    setHistory([]);
    setConfirmed(false);
    setSubmittedMessage("");

    if (!authToken) return;
    try {
      setLoading(true);
      setErrorBanner("");
      const payload: any = {};
      if (policyNum) {
        payload.policy_number = policyNum.trim().toUpperCase();
      }

      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setTicketId(data.ticket_id);
      localStorage.setItem("active_claim_ticket_id", data.ticket_id);
      setConversationStatus("collecting");
      setExtractedData(data.extracted_data || (policyNum ? { policy_id: policyNum } : {}));
      setPartialSegments(new Map());
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || (policyNum 
            ? `Hello! I see you are filing a claim for policy ${policyNum}. Please describe what happened, and I will capture all the details for you.`
            : "Hello! I'm here to assist you in filing your insurance claim. Please describe what happened, and I will capture all the details for you."),
          global_seq: 0,
          timestamp: Date.now(),
        },
      ]);
      connectWebSocket(data.ticket_id, authToken);
    } catch (err: any) {
      setErrorBanner(`Failed to start session: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [connectWebSocket, stopVoiceRecording]);

  // Authenticate user on load and start session exactly once
  useEffect(() => {
    if (!router.isReady) return;
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
          router.push(data.role === "ADMIN" ? "/admin" : "/adjuster");
          return;
        }
        setUserName(data.full_name || "Claimant");
        if (!hasInitializedRef.current) {
          hasInitializedRef.current = true;
          const initialPolicy = (router.query.policy || router.query.policy_id) as string | undefined;
          startSession(savedToken, initialPolicy);
        }
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router.isReady, router.query, startSession, router]);

  const startVoiceRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 16000,
      });
      audioContextRef.current = audioCtx;

      await audioCtx.audioWorklet.addModule("/audio-processor.js");
      const source = audioCtx.createMediaStreamSource(stream);
      let worklet: AudioWorkletNode;
      try {
        worklet = new AudioWorkletNode(audioCtx, "audio-processor");
      } catch {
        worklet = new AudioWorkletNode(audioCtx, "pcm16-processor");
      }
      workletNodeRef.current = worklet;

      worklet.port.onmessage = (event) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          if (event.data instanceof ArrayBuffer) {
            wsRef.current.send(event.data);
          } else if (event.data?.buffer instanceof ArrayBuffer) {
            wsRef.current.send(event.data.buffer);
          }
        }
      };

      source.connect(worklet);
      worklet.connect(audioCtx.destination);
      setIsRecording(true);
      setAgentState("listening");
    } catch (err: any) {
      setErrorBanner(`Microphone access error: ${err.message}`);
    }
  };

  const toggleMic = () => {
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  };

  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || !ticketId || !token) return;
    const text = textInput.trim();
    setTextInput("");

    setHistory((prev) => [
      ...prev,
      { turn: prev.length + 1, speaker: "user", text, timestamp: Date.now() },
    ]);

    fetch(`${API_BASE}/api/v1/claims/${ticketId}/text-turn`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
    })
      .then((res) => res.json())
      .then((data) => {
        const agentText = data.agent_message || data.message;
        if (agentText) {
          setHistory((prev) => [
            ...prev,
            { turn: prev.length + 1, speaker: "agent", text: agentText, timestamp: Date.now() },
          ]);
        }
        if (data.extracted_data) {
          setExtractedData(data.extracted_data);
        }
        if (data.conversation_status) {
          setConversationStatus(data.conversation_status);
        }
      })
      .catch(() => {});
  };

  const handleSubmitClaim = async () => {
    if (!ticketId || !token) return;
    setSubmittingClaim(true);
    setErrorBanner("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/confirm`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ confirmed: true }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to submit claim.");
      }
      const resData = await res.json();
      setSubmittedMessage(resData.message || `Claim successfully submitted! Reference ID: #${ticketId.slice(0, 8).toUpperCase()}`);
      setConfirmed(true);
      localStorage.removeItem("active_claim_ticket_id");
      if (isRecording) stopVoiceRecording();
    } catch (err: any) {
      setErrorBanner(err.message || "An error occurred while submitting your claim.");
    } finally {
      setSubmittingClaim(false);
    }
  };

  const handleOpenEdit = (field: string, currentVal: any) => {
    setEditingField(field);
    setEditValue(currentVal != null ? String(currentVal) : "");
  };

  const handleSaveEdit = () => {
    if (!editingField) return;
    let parsedVal: any = editValue.trim();
    if (editingField === "estimated_claim_amount") {
      parsedVal = parseFloat(editValue.replace(/[^0-9.]/g, "")) || null;
    }
    const updated = { ...extractedData, [editingField]: parsedVal };
    setExtractedData(updated);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "manual_edit", field: editingField, value: parsedVal }));
    }
    setEditingField(null);
  };

  const handleLogout = () => {
    if (isRecording) stopVoiceRecording();
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  const currentIncidentTitle = extractedData.insurance_type
    ? `${(SUPPORTED_INSURANCE_TYPES as any)[extractedData.insurance_type] || extractedData.insurance_type} Claim`
    : "New Claim Intake";

  return (
    <div className="bg-[#f7f9fb] text-[#191c1e] font-body antialiased min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Modular Sidebar Component */}
      <ClaimantSidebar userName={userName} onLogout={handleLogout} />

      {/* Main Canvas */}
      <main className="flex-1 md:ml-64 flex flex-col h-[calc(100vh-57px)] md:h-screen bg-white overflow-hidden">
        {/* Modular TopBar Component */}
        <ClaimantTopBar
          isRecording={isRecording}
          agentState={agentState}
          currentIncidentTitle={currentIncidentTitle}
          onStartNewSession={() => startSession(token)}
          loading={loading}
          errorBanner={errorBanner}
          onDismissError={() => setErrorBanner("")}
        />

        {/* Two Column Layout */}
        <div className="flex flex-1 overflow-hidden flex-col lg:flex-row h-full">
          {/* Left Column: Conversation & Voice Bar */}
          <div className="flex-1 flex flex-col h-full relative bg-white overflow-hidden">
            {/* Modular Chat Area Component */}
            <ClaimantChatArea
              history={history}
              partialSegments={partialSegments}
              agentState={agentState}
              confirmed={confirmed}
              submittedMessage={submittedMessage}
              chatContainerRef={chatContainerRef}
            />

            {/* Modular Voice Console Component */}
            <VoiceConsole
              isRecording={isRecording}
              textMode={textMode}
              setTextMode={setTextMode}
              textInput={textInput}
              setTextInput={setTextInput}
              onSendText={handleSendText}
              onToggleMic={toggleMic}
              onStopAudio={() => {
                if (isRecording) stopVoiceRecording();
                if ("speechSynthesis" in window) window.speechSynthesis.cancel();
              }}
              confirmed={confirmed}
            />
          </div>

          {/* Right Column: Collected Details Panel Component */}
          <CollectedDetailsPanel
            extractedData={extractedData}
            onOpenEdit={handleOpenEdit}
            onSubmitClaim={handleSubmitClaim}
            submittingClaim={submittingClaim}
            confirmed={confirmed}
            ticketId={ticketId}
          />
        </div>
      </main>

      {/* Modular Manual Edit Modal Component */}
      <ManualEditModal
        editingField={editingField}
        editValue={editValue}
        setEditValue={setEditValue}
        onClose={() => setEditingField(null)}
        onSave={handleSaveEdit}
      />
    </div>
  );
}
