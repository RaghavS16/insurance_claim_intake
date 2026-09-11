import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/router";
import { ClaimantSidebar, ClaimSummary } from "@/components/claimant/ClaimantSidebar";
import { ClaimantTopBar } from "@/components/claimant/ClaimantTopBar";
import { ClaimantChatArea } from "@/components/claimant/ClaimantChatArea";
import { VoiceConsole } from "@/components/claimant/VoiceConsole";
import { CollectedDetailsPanel } from "@/components/claimant/CollectedDetailsPanel";
import { ManualEditModal } from "@/components/claimant/ManualEditModal";
import { ExtractedData } from "@/components/claimant/ExtractionPanel";
import { ConversationTurn } from "@/components/claimant/ChatTranscript";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";
import { getAuthToken, clearAuthToken } from "@/lib/auth";

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

interface SessionPayload {
  ticket_id: string;
  status?: string;
  conversation_status?: string;
  insurance_type?: string;
  event_description?: string;
  event_location?: string;
  event_date?: string;
  estimated_claim_amount?: number;
  extracted_data?: ExtractedData;
  missing_fields?: string[];
  field_status?: Record<string, string>;
  awaiting_confirmation?: boolean;
  confirmed?: boolean;
  conversation?: Array<{ turn: number; speaker: "user" | "agent"; text: string; created_at?: string | null }>;
  initial_message?: string;
  resumed?: boolean;
}

export default function ClaimantPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [userName, setUserName] = useState("");
  const [ticketId, setTicketId] = useState("");
  const [conversationStatus, setConversationStatus] = useState("not_started");
  const [agentState, setAgentState] = useState("idle");
  const [extractedData, setExtractedData] = useState<ExtractedData>({});
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [claimsList, setClaimsList] = useState<ClaimSummary[]>([]);
  const [linkedPolicies, setLinkedPolicies] = useState<any[]>([]);
  const [loadingClaims, setLoadingClaims] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [textMode, setTextMode] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submittingClaim, setSubmittingClaim] = useState(false);
  const [submittedMessage, setSubmittedMessage] = useState("");
  const [errorBanner, setErrorBanner] = useState("");
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [partialSegments, setPartialSegments] = useState<Map<string, TranscriptSegment>>(new Map());
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [mobileTab, setMobileTab] = useState<"chat" | "details">("chat");

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const activeSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const audioBlobQueueRef = useRef<Blob[]>([]);
  const isPlayingRef = useRef(false);
  const isRecordingRef = useRef(false);
  const hasInitializedRef = useRef(false);
  isRecordingRef.current = isRecording;

  const scrollToBottom = useCallback((force = false) => {
    const container = chatContainerRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= 350;
    if (force || nearBottom) {
      setTimeout(() => {
        container.scrollTo({ top: container.scrollHeight + 500, behavior: "smooth" });
      }, 50);
    }
  }, []);

  const handleScrollToBottom = useCallback(() => {
    setShowScrollBottom(false);
    scrollToBottom(true);
  }, [scrollToBottom]);

  useEffect(() => {
    scrollToBottom(true);
  }, [history.length, partialSegments.size, scrollToBottom]);

  const getPlaybackContext = useCallback(() => {
    if (!playbackContextRef.current || playbackContextRef.current.state === "closed") {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      playbackContextRef.current = new AudioCtx();
    }
    if (playbackContextRef.current.state === "suspended") {
      playbackContextRef.current.resume().catch(() => {});
    }
    return playbackContextRef.current;
  }, []);

  const enqueueAudio = useCallback((blob: Blob) => {
    audioBlobQueueRef.current.push(blob);
    const playNext = async () => {
      if (isPlayingRef.current || !audioBlobQueueRef.current.length) return;
      const next = audioBlobQueueRef.current.shift();
      if (!next) return;
      isPlayingRef.current = true;
      try {
        const ctx = getPlaybackContext();
        const buffer = await ctx.decodeAudioData(await next.arrayBuffer());
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        activeSourceRef.current = source;
        setAgentState("speaking");
        source.onended = () => {
          isPlayingRef.current = false;
          if (activeSourceRef.current === source) activeSourceRef.current = null;
          if (!audioBlobQueueRef.current.length) {
            setAgentState(isRecordingRef.current ? "listening" : "idle");
          }
          playNext();
        };
        source.start(0);
      } catch {
        isPlayingRef.current = false;
        activeSourceRef.current = null;
        playNext();
      }
    };
    playNext();
  }, [getPlaybackContext]);

  const fetchClaimsList = useCallback(async (authToken: string) => {
    if (!authToken) return;
    setLoadingClaims(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setClaimsList(Array.isArray(data) ? data : (data.items || []));
      }
    } catch {} finally {
      setLoadingClaims(false);
    }
  }, []);

  const fetchLinkedPolicies = useCallback(async (authToken: string) => {
    if (!authToken) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/policies/my-policies`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setLinkedPolicies(Array.isArray(data) ? data : []);
      }
    } catch {}
  }, []);

  const handleWsMessage = useCallback((event: MessageEvent) => {
    if (typeof event.data !== "string") {
      if (event.data instanceof Blob) enqueueAudio(event.data);
      else if (event.data instanceof ArrayBuffer) enqueueAudio(new Blob([event.data], { type: "audio/wav" }));
      return;
    }
    let msg: Record<string, any>;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type === "barge_in") {
      try {
        activeSourceRef.current?.stop();
      } catch {}
      activeSourceRef.current = null;
      audioBlobQueueRef.current = [];
      isPlayingRef.current = false;
      setAgentState(isRecordingRef.current ? "listening" : "idle");
      setPartialSegments(new Map());
      return;
    }
    if (msg.type === "agent_state") {
      setAgentState(msg.state);
      return;
    }
    if (msg.type === "transcript") {
      const speaker = msg.speaker as string,
        segmentId = msg.segment_id as string,
        text = msg.text as string,
        isFinal = msg.is_final as boolean;
      if (!text) return;
      if (!isFinal) {
        setPartialSegments((prev) => {
          const next = new Map(prev);
          next.set(segmentId, {
            segment_id: segmentId,
            sequence: msg.sequence || 0,
            speaker: speaker === "agent" ? "agent" : "user",
            text,
            is_final: false,
            global_seq: msg.global_seq,
            timestamp: msg.timestamp,
          });
          return next;
        });
      } else {
        setPartialSegments((prev) => {
          const next = new Map(prev);
          next.delete(segmentId);
          return next;
        });
        setHistory((prev) => [
          ...prev,
          {
            turn: prev.length + 1,
            speaker: speaker === "agent" ? "agent" : "user",
            text,
            segment_id: segmentId,
            global_seq: msg.global_seq,
            timestamp: msg.timestamp || Date.now(),
          },
        ]);
      }
      return;
    }
    if (msg.type === "state_update") {
      setExtractedData(msg.extracted_data || {});
      setConversationStatus(msg.conversation_status || "collecting");
      setConfirmed(Boolean(msg.confirmed));
      return;
    }
  }, [enqueueAudio]);

  const stopVoiceRecording = useCallback(() => {
    try {
      workletNodeRef.current?.port.postMessage({ command: "stop" });
      workletNodeRef.current?.disconnect();
    } catch {}
    workletNodeRef.current = null;
    try {
      audioContextRef.current?.close();
    } catch {}
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setIsRecording(false);
    setAgentState("idle");
  }, []);

  const stopAssistantAudio = useCallback(() => {
    try {
      activeSourceRef.current?.stop();
    } catch {}
    activeSourceRef.current = null;
    audioBlobQueueRef.current = [];
    isPlayingRef.current = false;
    setAgentState(isRecordingRef.current ? "listening" : "idle");
  }, []);

  const connectWebSocket = useCallback((currentTicketId: string, currentToken: string) => {
    try {
      wsRef.current?.close();
    } catch {}
    const ws = new WebSocket(
      `${API_BASE.replace(/^http/, "ws")}/api/v1/ws/voice/${currentTicketId}?token=${encodeURIComponent(currentToken)}`
    );
    ws.binaryType = "blob";
    ws.onmessage = handleWsMessage;
    ws.onclose = () => {
      if (isRecordingRef.current) stopVoiceRecording();
    };
    wsRef.current = ws;
  }, [handleWsMessage, stopVoiceRecording]);

  const initBlankChat = useCallback(() => {
    if (isRecordingRef.current) stopVoiceRecording();
    stopAssistantAudio();
    try {
      wsRef.current?.close();
    } catch {}
    wsRef.current = null;
    setTicketId("");
    localStorage.removeItem("active_claim_ticket_id");
    setConversationStatus("not_started");
    setExtractedData({});
    setHistory([]);
    setConfirmed(false);
    setSubmittedMessage("");
    setPartialSegments(new Map());
    setErrorBanner("");
    if (router.query.ticket || router.query.ticket_id) {
      router.replace({ pathname: "/claimant" }, undefined, { shallow: true });
    }
  }, [router, stopAssistantAudio, stopVoiceRecording]);

  const applySession = useCallback((data: SessionPayload, authToken: string, fallbackMessage?: string) => {
    setTicketId(data.ticket_id);
    localStorage.setItem("active_claim_ticket_id", data.ticket_id);
    setConversationStatus(data.conversation_status || data.status || "collecting");
    setExtractedData(data.extracted_data || {});
    setConfirmed(Boolean(data.confirmed || data.status === "submitted"));
    setPartialSegments(new Map());
    const saved = (data.conversation || []).map((t) => ({
      turn: t.turn,
      speaker: t.speaker,
      text: t.text,
      timestamp: t.created_at ? Date.parse(t.created_at) : Date.now(),
    }));
    if (saved.length) {
      setHistory(saved);
    } else if (fallbackMessage || data.initial_message) {
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || fallbackMessage || "Tell me what happened, in your own words. I'll collect the details as we go.",
          timestamp: Date.now(),
        },
      ]);
    } else {
      setHistory([]);
    }
    connectWebSocket(data.ticket_id, authToken);
    fetchClaimsList(authToken);
  }, [connectWebSocket, fetchClaimsList]);

  const loadClaimByTicket = useCallback(async (selectedTicketId: string, authToken: string) => {
    if (!authToken || !selectedTicketId) return;
    if (isRecordingRef.current) stopVoiceRecording();
    setLoading(true);
    setErrorBanner("");
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${selectedTicketId}`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) throw new Error(`Could not load claim #${selectedTicketId}`);
      const data = await res.json();
      applySession(data, authToken);
      router.replace({ pathname: "/claimant", query: { ticket: selectedTicketId } }, undefined, { shallow: true });
    } catch (err: any) {
      setErrorBanner(err.message || "Failed to load claim.");
    } finally {
      setLoading(false);
    }
  }, [applySession, router, stopVoiceRecording]);

  const ensureClaimSession = useCallback(async (authToken: string, policyNum?: string): Promise<string> => {
    if (ticketId) return ticketId;
    const payload = policyNum ? { policy_number: policyNum.trim().toUpperCase() } : {};
    const res = await fetch(`${API_BASE}/api/v1/claims/new-session`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${authToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Could not initialize claim intake.");
    const data = await res.json();
    setTicketId(data.ticket_id);
    localStorage.setItem("active_claim_ticket_id", data.ticket_id);
    connectWebSocket(data.ticket_id, authToken);
    router.replace({ pathname: "/claimant", query: { ticket: data.ticket_id } }, undefined, { shallow: true });
    return data.ticket_id;
  }, [connectWebSocket, router, ticketId]);

  const handleDeleteClaim = useCallback(async (targetTicketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token || !targetTicketId) return;
    if (!window.confirm(`Discard draft for claim #${targetTicketId}?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${targetTicketId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Unable to delete claim.");
      }
      fetchClaimsList(token);
      if (targetTicketId === ticketId) initBlankChat();
    } catch (err: any) {
      setErrorBanner(err.message || "Could not delete claim.");
    }
  }, [fetchClaimsList, initBlankChat, ticketId, token]);

  const handleExportTranscript = useCallback(async () => {
    if (!ticketId || !token) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}/export`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Could not export transcript.");
      const data = await res.json();
      const textContent = data.formatted_text || JSON.stringify(data, null, 2);
      const blob = new Blob([textContent], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `Claim_${ticketId}_Dossier.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setErrorBanner(err.message || "Failed to download export.");
    }
  }, [ticketId, token]);

  useEffect(() => {
    if (!router.isReady || hasInitializedRef.current) return;
    const savedToken = getAuthToken();
    if (!savedToken) {
      router.push("/login");
      return;
    }
    setToken(savedToken);
    hasInitializedRef.current = true;
    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${savedToken}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error("Session expired");
        return r.json();
      })
      .then((data) => {
        if (data.role !== "CLAIMANT") {
          router.push(data.role === "ADMIN" ? "/admin" : "/adjuster");
          return;
        }
        setUserName(data.full_name || "Claimant");
        const initialTicket = (router.query.ticket || router.query.ticket_id) as string | undefined;
        fetchClaimsList(savedToken);
        fetchLinkedPolicies(savedToken);
        if (initialTicket) return loadClaimByTicket(initialTicket, savedToken);
        else initBlankChat();
      })
      .catch(() => {
        clearAuthToken();
        router.push("/login");
      });
  }, [router.isReady, router.query.ticket, router.query.ticket_id, loadClaimByTicket, initBlankChat, router, fetchClaimsList, fetchLinkedPolicies]);

  useEffect(() => () => {
    try {
      wsRef.current?.close();
    } catch {}
    stopVoiceRecording();
    stopAssistantAudio();
  }, [stopVoiceRecording, stopAssistantAudio]);

  const startVoiceRecording = async () => {
    if (!token) return;
    try {
      let activeTid = ticketId;
      if (!activeTid) activeTid = await ensureClaimSession(token);
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
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
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
          wsRef.current.send(event.data instanceof ArrayBuffer ? event.data : event.data?.buffer);
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

  const toggleMic = () => (isRecording ? stopVoiceRecording() : startVoiceRecording());

  const handleSendText = async (e?: React.FormEvent, customText?: string) => {
    if (e) e.preventDefault();
    const rawText = customText || textInput;
    if (!rawText.trim() || !token) return;
    const text = rawText.trim();
    setTextInput("");
    setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text, timestamp: Date.now() }]);
    setAgentState("thinking");
    try {
      let activeTid = ticketId;
      if (!activeTid) activeTid = await ensureClaimSession(token);
      const res = await fetch(`${API_BASE}/api/v1/claims/${activeTid}/text-turn`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Unable to process message.");
      if (data.agent_message) {
        setHistory((prev) => [
          ...prev,
          { turn: prev.length + 1, speaker: "agent", text: data.agent_message, timestamp: Date.now() },
        ]);
      }
      setExtractedData(data.extracted_data || {});
      setConversationStatus(data.conversation_status || "collecting");
      setConfirmed(Boolean(data.confirmed || data.status === "submitted"));
      fetchClaimsList(token);
    } catch (err: any) {
      setErrorBanner(err.message || "Unable to process message.");
    } finally {
      setAgentState("idle");
    }
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
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to submit claim.");
      setSubmittedMessage(
        data.message || `Claim successfully submitted. Reference ID: #${ticketId.slice(0, 8).toUpperCase()}`
      );
      setConfirmed(true);
      fetchClaimsList(token);
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

  const handleSaveEdit = async () => {
    if (!editingField || !ticketId || !token) return;
    let parsedVal: any = editValue.trim();
    if (editingField === "estimated_claim_amount") {
      parsedVal = parseFloat(editValue.replace(/[^0-9.]/g, "")) || null;
    }
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/${ticketId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ [editingField]: parsedVal }),
      });
      if (!res.ok) throw new Error("Could not save this correction.");
      const data = await res.json();
      setExtractedData(data.extracted_data || { ...extractedData, [editingField]: parsedVal });
      setEditingField(null);
      fetchClaimsList(token);
    } catch (err: any) {
      setErrorBanner(err.message || "Could not save correction.");
    }
  };

  const handleLogout = () => {
    if (isRecording) stopVoiceRecording();
    stopAssistantAudio();
    try {
      wsRef.current?.close();
    } catch {}
    clearAuthToken();
    router.push("/login");
  };

  const currentIncidentTitle = extractedData.insurance_type
    ? `${(SUPPORTED_INSURANCE_TYPES as any)[extractedData.insurance_type] || extractedData.insurance_type} Claim`
    : "New Claim Intake";

  const pendingCount = [
    !extractedData.policy_id,
    !extractedData.insurance_type,
    !extractedData.event_date,
    !extractedData.estimated_claim_amount,
  ].filter(Boolean).length;

  return (
    <div className="bg-[#f8fafc] text-[#0f172a] font-body antialiased min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      <ClaimantSidebar
        userName={userName}
        claims={claimsList}
        activeTicketId={ticketId}
        activeRoute="claimant"
        loadingClaims={loadingClaims}
        onSelectClaim={(id) => {
          setMobileTab("chat");
          loadClaimByTicket(id, token);
        }}
        onNewClaim={() => {
          setMobileTab("chat");
          initBlankChat();
        }}
        onDeleteClaim={handleDeleteClaim}
        onLogout={handleLogout}
      />

      <main className="flex-1 md:ml-64 flex flex-col h-[calc(100vh-57px)] md:h-screen bg-white overflow-hidden">
        <ClaimantTopBar
          isRecording={isRecording}
          agentState={agentState}
          currentIncidentTitle={currentIncidentTitle}
          ticketId={ticketId}
          onStartNewSession={() => {
            setMobileTab("chat");
            initBlankChat();
          }}
          onExportTranscript={handleExportTranscript}
          loading={loading}
          errorBanner={errorBanner}
          onDismissError={() => setErrorBanner("")}
          mobileTab={mobileTab}
          onTabChange={setMobileTab}
          pendingCount={pendingCount}
        />

        <div className="flex flex-1 overflow-hidden flex-col lg:flex-row h-full">
          {/* Chat & Voice Console Area */}
          <div
            className={`flex-1 flex-col h-full relative bg-white overflow-hidden ${
              mobileTab === "chat" ? "flex" : "hidden lg:flex"
            }`}
          >
            <ClaimantChatArea
              history={history}
              partialSegments={partialSegments}
              agentState={agentState}
              confirmed={confirmed}
              submittedMessage={submittedMessage}
              chatContainerRef={chatContainerRef}
              linkedPolicies={linkedPolicies}
              onSelectPromptSuggestion={(txt) => handleSendText(undefined, txt)}
              onExportTranscript={handleExportTranscript}
              onScrollChange={(isUp) => setShowScrollBottom(isUp)}
            />

            <VoiceConsole
              isRecording={isRecording}
              textMode={textMode}
              setTextMode={setTextMode}
              textInput={textInput}
              setTextInput={setTextInput}
              onSendText={(e) => handleSendText(e)}
              onToggleMic={toggleMic}
              onStopAudio={stopAssistantAudio}
              confirmed={confirmed}
              showScrollBottom={showScrollBottom}
              onScrollToBottom={handleScrollToBottom}
            />
          </div>

          {/* Collected Details Panel */}
          <div
            className={`h-full overflow-hidden ${
              mobileTab === "details" ? "flex flex-col flex-1" : "hidden lg:flex lg:flex-col"
            }`}
          >
            <CollectedDetailsPanel
              extractedData={extractedData}
              linkedPolicies={linkedPolicies}
              onOpenEdit={handleOpenEdit}
              onSelectPolicy={() => {}}
              onSubmitClaim={handleSubmitClaim}
              submittingClaim={submittingClaim}
              confirmed={confirmed}
              ticketId={ticketId}
            />
          </div>
        </div>
      </main>

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

