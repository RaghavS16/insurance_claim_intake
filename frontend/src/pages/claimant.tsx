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
import { getAuthToken, clearAuthToken, verifySessionOrRedirect } from "@/lib/auth";
import { apiFetch, normalizeList } from "@/lib/api";
import { RealtimeVoiceSession, RealtimeVoiceState } from "@/lib/realtimeVoice";

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
  [key: string]: unknown;
  ticket_id: string;
  agent_message?: string;
  status?: string;
  conversation_status?: string;
  insurance_type?: string;
  event_description?: string;
  event_location?: string;
  event_date?: string;
  estimated_claim_amount?: number;
  extracted_data?: ExtractedData;
  missing_fields?: string[];
  dynamic_requirements?: Array<Record<string, unknown>>;
  dynamic_missing?: Array<Record<string, unknown>>;
  missing_evidence?: Array<Record<string, unknown>>;
  pending_evidence_review?: Array<Record<string, unknown>>;
  evidence?: Array<Record<string, unknown>>;
  field_status?: Record<string, string>;
  awaiting_confirmation?: boolean;
  confirmed?: boolean;
  conversation_phase?: string;
  gap_analysis?: Record<string, unknown>;
  submission_readiness?: { ready?: boolean; blocking_requirements?: Array<Record<string, unknown>>; exceptions?: Array<Record<string, unknown>>; verification?: Record<string, unknown> };
  conversation?: Array<{ turn: number; speaker: "user" | "agent"; text: string; attachment?: { name: string; size?: number; type?: string } | null; created_at?: string | null }>;
  initial_message?: string;
  resumed?: boolean;
}

export interface LinkedPolicyItem {
  policy_number: string;
  policy_type: string;
  coverage_amount?: number;
  [key: string]: unknown;
}

export default function ClaimantPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>(() => (typeof window !== "undefined" ? getAuthToken() || "" : ""));
  const [userName, setUserName] = useState("");
  const [ticketId, setTicketId] = useState("");
  const [, setConversationStatus] = useState("not_started");
  const [agentState, setAgentState] = useState("idle");
  const [extractedData, setExtractedData] = useState<ExtractedData>({});
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [claimsList, setClaimsList] = useState<ClaimSummary[]>([]);
  const [linkedPolicies, setLinkedPolicies] = useState<LinkedPolicyItem[]>([]);
  const [loadingClaims, setLoadingClaims] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [textMode, setTextMode] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [claimSubmitted, setClaimSubmitted] = useState(false);
  const [submittingClaim, setSubmittingClaim] = useState(false);
  const [submittedMessage, setSubmittedMessage] = useState("");
  const [evidenceUploading, setEvidenceUploading] = useState(false);
  const [missingEvidence, setMissingEvidence] = useState<Array<Record<string, unknown>>>([]);
  const [pendingEvidenceReview, setPendingEvidenceReview] = useState<Array<Record<string, unknown>>>([]);
  const [evidenceItems, setEvidenceItems] = useState<Array<Record<string, unknown>>>([]);
  const [pendingEvidenceName, setPendingEvidenceName] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState("");
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [partialSegments, setPartialSegments] = useState<Map<string, TranscriptSegment>>(new Map());
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [mobileTab, setMobileTab] = useState<"chat" | "details">("chat");
  const [conversationPhase, setConversationPhase] = useState("1_baseline");
  const [gapAnalysis, setGapAnalysis] = useState<Record<string, unknown>>({});
  const [submissionReadiness, setSubmissionReadiness] = useState<SessionPayload["submission_readiness"]>({});

  const voiceSessionRef = useRef<RealtimeVoiceSession | null>(null);
  const isRecordingRef = useRef(false);
  const hasInitializedRef = useRef(false);
  const autoScrollEnabledRef = useRef(true);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const textTurnInFlightRef = useRef(false);

  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  const scrollToBottom = useCallback((force = false) => {
    const container = chatContainerRef.current;
    if (!container) return;
    if (force) {
      autoScrollEnabledRef.current = true;
      setShowScrollBottom(false);
    }
    if (!force && !autoScrollEnabledRef.current) return;

    // Do not use smooth scrolling for the live transcript. Smooth scrolling can
    // fight with VAD/interim transcript updates and visibly pull the user away
    // from the latest message. Pin the viewport after React paints the new DOM.
    requestAnimationFrame(() => {
      const current = chatContainerRef.current;
      if (!current || (!force && !autoScrollEnabledRef.current)) return;
      current.scrollTop = current.scrollHeight;
      requestAnimationFrame(() => {
        const latest = chatContainerRef.current;
        if (latest && (force || autoScrollEnabledRef.current)) {
          latest.scrollTop = latest.scrollHeight;
        }
      });
    });
  }, []);

  const handleScrollToBottom = useCallback(() => {
    scrollToBottom(true);
  }, [scrollToBottom]);

  useEffect(() => {
    scrollToBottom(false);
  }, [history.length, partialSegments.size, scrollToBottom]);

  const fetchClaimsList = useCallback(async (authToken: string) => {
    if (!authToken) return;
    setLoadingClaims(true);
    try {
      const data = await apiFetch<ClaimSummary[] | { items?: ClaimSummary[] }>(
        "/api/v1/claims",
        { token: authToken },
      );
      setClaimsList(normalizeList(data));
    } catch {} finally {
      setLoadingClaims(false);
    }
  }, []);

  const fetchLinkedPolicies = useCallback(async (authToken: string) => {
    if (!authToken) return;
    try {
      const data = await apiFetch<LinkedPolicyItem[]>("/api/v1/policies/my-policies", { token: authToken });
      setLinkedPolicies(Array.isArray(data) ? data : []);
    } catch {}
  }, []);

  const stopVoiceRecording = useCallback(() => {
    voiceSessionRef.current?.close();
    voiceSessionRef.current = null;
    isRecordingRef.current = false;
    setIsRecording(false);
    setAgentState("idle");
    setPartialSegments(new Map());
  }, []);

  const stopAssistantAudio = useCallback(() => {
    voiceSessionRef.current?.stopAssistant();
    setAgentState(isRecordingRef.current ? "listening" : "idle");
  }, []);

  const connectVoiceSession = useCallback(
    async (activeTicketId: string, authToken: string) => {
      const session = new RealtimeVoiceSession();
      voiceSessionRef.current = session;

      await session.connect(activeTicketId, authToken, {
        onState: (state: RealtimeVoiceState) => {
          if (state !== "error") setAgentState(state);
        },
        onConnected: () => {
          isRecordingRef.current = true;
          setIsRecording(true);
        },
        onDisconnected: () => {
          isRecordingRef.current = false;
          setIsRecording(false);
          setAgentState("idle");
        },
        onUserPartial: (text) => {
          if (!text) {
            setPartialSegments((prev) => {
              const next = new Map(prev);
              next.delete("realtime-user");
              return next;
            });
            return;
          }
          setPartialSegments(
            new Map([
              [
                "realtime-user",
                {
                  segment_id: "realtime-user",
                  sequence: 0,
                  speaker: "user",
                  text,
                  is_final: false,
                  timestamp: Date.now(),
                },
              ],
            ]),
          );
        },
        onUserFinal: (text, itemId) => {
          setPartialSegments((prev) => {
            const next = new Map(prev);
            next.delete("realtime-user");
            return next;
          });
          setHistory((prev) => [
            ...prev,
            {
              turn: prev.length + 1,
              speaker: "user",
              text,
              segment_id: itemId || "voice-user-" + Date.now(),
              timestamp: Date.now(),
            },
          ]);
        },
        onAgentPartial: (text) => {
          setPartialSegments(
            new Map([
              [
                "realtime-agent",
                {
                  segment_id: "realtime-agent",
                  sequence: 0,
                  speaker: "agent",
                  text,
                  is_final: false,
                  timestamp: Date.now(),
                },
              ],
            ]),
          );
        },
        onAgentFinal: (text) => {
          setPartialSegments((prev) => {
            const next = new Map(prev);
            next.delete("realtime-agent");
            return next;
          });
          const normalized = text.trim();
          if (!normalized) return;
          setHistory((prev) => {
            const alreadyPresent = prev.some(
              (item) => item.speaker === "agent" && item.text === normalized,
            );
            return alreadyPresent
              ? prev
              : [
                  ...prev,
                  {
                    turn: prev.length + 1,
                    speaker: "agent",
                    text: normalized,
                    segment_id: "voice-agent-" + Date.now(),
                    timestamp: Date.now(),
                  },
                ];
          });
        },
        onClaimState: (payload) => {
          setExtractedData((payload.extracted_data as ExtractedData) || {});
          setConfirmed(Boolean(payload.confirmed));
          setClaimSubmitted(String(payload.status || "") === "submitted");
          setMissingEvidence(
            (payload.missing_evidence as Array<Record<string, unknown>>) || [],
          );
          setEvidenceItems(
            (payload.evidence as Array<Record<string, unknown>>) || [],
          );
          if (payload.conversation_phase) {
            setConversationPhase(String(payload.conversation_phase));
          }
          if (payload.submission_readiness) {
            setSubmissionReadiness(
              payload.submission_readiness as SessionPayload["submission_readiness"],
            );
          }
        },
        onError: (message) => {
          setErrorBanner(message);
          setTextMode(true);
          stopVoiceRecording();
        },
      });

      isRecordingRef.current = true;
      setIsRecording(true);
      setAgentState("listening");
    },
    [stopVoiceRecording],
  );

  const ensureClaimSession = useCallback(async (authToken: string): Promise<string> => {
    const data = await apiFetch<SessionPayload>("/api/v1/claims/voice-session", {
      method: "POST",
      token: authToken,
    });
    const tid = String(data.ticket_id || "");
    if (!tid) throw new Error("Unable to create a claim session.");
    setTicketId(tid);
    setConversationPhase(String(data.conversation_phase || "1_baseline"));
    setExtractedData(data.extracted_data || {});
    setConfirmed(Boolean(data.confirmed));
    setClaimSubmitted(String(data.status || "") === "submitted");
    setMissingEvidence(data.missing_evidence || []);
    setPendingEvidenceReview(data.pending_evidence_review || []);
    setEvidenceItems(data.evidence || []);
    const conversation = Array.isArray(data.conversation) ? data.conversation : [];
    setHistory(conversation.map((item) => ({
      turn: item.turn, speaker: item.speaker, text: item.text,
      timestamp: item.created_at ? Date.parse(item.created_at) : Date.now(),
      attachment: item.attachment || undefined,
    })));
    if (data.initial_message && conversation.length === 0) {
      setHistory([{ turn: 1, speaker: "agent", text: data.initial_message, timestamp: Date.now() }]);
    }
    fetchClaimsList(authToken);
    return tid;
  }, [fetchClaimsList]);

  const loadClaimByTicket = useCallback(async (tid: string, authToken: string) => {
    setLoading(true);
    setErrorBanner("");
    try {
      const data = await apiFetch<SessionPayload>(`/api/v1/claims/${encodeURIComponent(tid)}`, { token: authToken });
      setTicketId(data.ticket_id);
      setConversationPhase(String(data.conversation_phase || "1_baseline"));
      setExtractedData(data.extracted_data || {});
      setConfirmed(Boolean(data.confirmed));
      setClaimSubmitted(String(data.status || "") === "submitted");
      setMissingEvidence(data.missing_evidence || []);
      setPendingEvidenceReview(data.pending_evidence_review || []);
      setEvidenceItems(data.evidence || []);
      setSubmissionReadiness(data.submission_readiness || {});
      setGapAnalysis(data.gap_analysis || {});
      const conversation = Array.isArray(data.conversation) ? data.conversation : [];
      setHistory(conversation.map((item) => ({
        turn: item.turn, speaker: item.speaker, text: item.text,
        timestamp: item.created_at ? Date.parse(item.created_at) : Date.now(),
        attachment: item.attachment || undefined,
      })));
      await router.replace({ pathname: "/claimant", query: { ticket_id: data.ticket_id } }, undefined, { shallow: true });
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not load the claim.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!router.isReady) return;
    verifySessionOrRedirect(router, {
      requiredRole: "CLAIMANT",
      onSuccess: (userData) => {
        const name = (userData.full_name as string) || (userData.email as string) || "Claimant";
        setUserName(name);
        const currentToken = getAuthToken() || "";
        if (currentToken) {
          setToken(currentToken);
          fetchClaimsList(currentToken);
          fetchLinkedPolicies(currentToken);

          const qTicket = (router.query.ticket || router.query.ticket_id) as string | undefined;
          if (qTicket) {
            loadClaimByTicket(qTicket, currentToken);
          }
        }
      },
    });
  }, [router.isReady, router, fetchClaimsList, fetchLinkedPolicies, loadClaimByTicket]);

  useEffect(() => {
    if (!router.isReady) return;
    const qTicket = (router.query.ticket || router.query.ticket_id) as string | undefined;
    if (qTicket && qTicket !== ticketId && token) {
      loadClaimByTicket(qTicket, token);
    }
  }, [router.isReady, router.query.ticket, router.query.ticket_id, ticketId, token, loadClaimByTicket]);

  const initBlankChat = useCallback(async () => {
    if (!token) return;
    stopVoiceRecording();
    setErrorBanner("");
    setSubmittedMessage("");
    setClaimSubmitted(false);
    setConfirmed(false);
    setExtractedData({});
    setMissingEvidence([]);
    setPendingEvidenceReview([]);
    setEvidenceItems([]);
    setSubmissionReadiness({});
    setGapAnalysis({});
    setConversationPhase("1_baseline");
    setHistory([]);
    try {
      const data = await apiFetch<SessionPayload>("/api/v1/claims/new-session", {
        method: "POST", token, headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
      });
      setTicketId(data.ticket_id);
      if (data.initial_message) {
        setHistory([{ turn: 1, speaker: "agent", text: data.initial_message, timestamp: Date.now() }]);
      }
      fetchClaimsList(token);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not start a new claim.");
    }
  }, [fetchClaimsList, stopVoiceRecording, token]);

  const handleDeleteClaim = useCallback(async (tid: string) => {
    if (!token) return;
    try {
      await apiFetch(`/api/v1/claims/${encodeURIComponent(tid)}`, { method: "DELETE", token });
      if (ticketId === tid) {
        setTicketId(""); setHistory([]); setExtractedData({}); setConfirmed(false);
        setClaimSubmitted(false); setConversationPhase("1_baseline");
      }
      fetchClaimsList(token);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not delete the claim.");
    }
  }, [fetchClaimsList, ticketId, token]);

  const handleExportTranscript = useCallback(async () => {
    if (!ticketId || !token) return;
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${base}/api/v1/claims/${encodeURIComponent(ticketId)}/export`, {
        headers: { Authorization: "Bearer " + token },
      });
      if (!response.ok) throw new Error("Could not export transcript.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${ticketId}-transcript.txt`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not export transcript.");
    }
  }, [ticketId, token]);
  const startVoiceRecording = async () => {
    if (!token) return;
    setErrorBanner("");
    setIsRecording(true);
    isRecordingRef.current = true;
    setAgentState("connecting");
    try {
      const activeTid = ticketId || (await ensureClaimSession(token));
      stopAssistantAudio();
      await connectVoiceSession(activeTid, token);
    } catch (err: unknown) {
      voiceSessionRef.current?.close();
      voiceSessionRef.current = null;
      isRecordingRef.current = false;
      setIsRecording(false);
      setAgentState("idle");
      setErrorBanner(
        err instanceof Error
          ? err.message + " You can continue by typing."
          : "Voice service is unavailable. You can continue by typing.",
      );
    }
  };

  const toggleMic = () => (isRecording ? stopVoiceRecording() : startVoiceRecording());

  const handleSendText = async (e?: React.FormEvent, customText?: string) => {
    if (e) e.preventDefault();
    if (textTurnInFlightRef.current) return;
    const rawText = customText || textInput;
    if (!rawText.trim() || !token) return;
    const text = rawText.trim();
    textTurnInFlightRef.current = true;
    if (isRecordingRef.current) stopVoiceRecording();
    stopAssistantAudio();
    voiceSessionRef.current?.stopAssistant();
    setTextInput("");
    setHistory((prev) => [...prev, { turn: prev.length + 1, speaker: "user", text, timestamp: Date.now() }]);
    setAgentState("thinking");
    try {
      const activeTid = ticketId || await ensureClaimSession(token);
      const data = await apiFetch<SessionPayload>(
        `/api/v1/claims/${activeTid}/text-turn`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
      );
      if (data.agent_message) {
        setHistory((prev) => [
          ...prev,
          { turn: prev.length + 1, speaker: "agent", text: data.agent_message!, timestamp: Date.now() },
        ]);
      }
      setExtractedData(data.extracted_data || {});
      setConfirmed(Boolean(data.confirmed));
      setClaimSubmitted(Boolean(data.status === "submitted"));
      setSubmissionReadiness(data.submission_readiness || {});
      setMissingEvidence(data.missing_evidence || []);
      setEvidenceItems(data.evidence || []);
      if ((data as Record<string, unknown>).conversation_phase) {
        setConversationPhase(String((data as Record<string, unknown>).conversation_phase));
      }
      if ((data as Record<string, unknown>).gap_analysis) {
        setGapAnalysis((data as Record<string, unknown>).gap_analysis as Record<string, unknown>);
      }
      fetchClaimsList(token);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Unable to process message.");
    } finally {
      textTurnInFlightRef.current = false;
      setAgentState("idle");
    }
  };

  const handleUploadEvidence = async (file: File) => {
    if (!ticketId || !token) {
      setErrorBanner("Start your claim conversation before uploading evidence.");
      return;
    }
    setEvidenceUploading(true);
    setPendingEvidenceName(file.name);
    setErrorBanner("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await apiFetch<{
        missing_evidence?: Array<Record<string, unknown>>;
        pending_evidence_review?: Array<Record<string, unknown>>;
        evidence_items?: Array<Record<string, unknown>>;
        message?: string;
        agent_message?: string;
      }>(
        `/api/v1/claims/${ticketId}/evidence`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        },
      );
      setMissingEvidence(result.missing_evidence || []);
      setPendingEvidenceReview(result.pending_evidence_review || []);
      setEvidenceItems(result.evidence_items || []);

      // Evidence belongs to the claimant turn. Render it on the user's side,
      // then render the AI verification/follow-up as a separate assistant turn.
      // This mirrors normal ChatGPT attachment semantics and prevents the upload
      // from looking like something the assistant sent.
      setHistory((prev) => [
        ...prev,
        {
          turn: prev.length + 1,
          speaker: "user",
          text: "",
          timestamp: Date.now(),
          attachment: { name: file.name, size: file.size, type: file.type },
        } as ConversationTurn,
        ...(result.message
          ? [{
              turn: prev.length + 2,
              speaker: "agent",
              text: result.message,
              timestamp: Date.now(),
            } as ConversationTurn]
          : []),
      ]);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not upload evidence.");
    } finally {
      setEvidenceUploading(false);
      setPendingEvidenceName(null);
    }
  };

  const handleSubmitClaim = async () => {
    if (!ticketId || !token) return;
    setSubmittingClaim(true);
    setErrorBanner("");
    try {
      const data = await apiFetch<{ message?: string }>(
        `/api/v1/claims/${ticketId}/confirm`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ confirmed: true }),
        },
      );
      setSubmittedMessage(
        data.message || `Claim successfully submitted. Reference ID: #${ticketId.slice(0, 8).toUpperCase()}`
      );
      setConfirmed(true);
      setClaimSubmitted(true);
      fetchClaimsList(token);
      voiceSessionRef.current?.close();
      voiceSessionRef.current = null;
      await router.push("/claimant/track-claim");

    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "An error occurred while submitting your claim.");
    } finally {
      setSubmittingClaim(false);
    }
  };

  const handleOpenEdit = (field: string, currentVal: unknown) => {
    setEditingField(field);
    setEditValue(currentVal != null ? String(currentVal) : "");
  };

  const handleSaveEdit = async () => {
    if (!editingField || !ticketId || !token) return;
    let parsedVal: string | number | null = editValue.trim();
    if (editingField === "estimated_claim_amount") {
      parsedVal = parseFloat(editValue.replace(/[^0-9.]/g, "")) || null;
    }
    try {
      const data = await apiFetch<{ extracted_data?: ExtractedData; confirmed?: boolean; agent_message?: string; conversation_phase?: string }>(
        `/api/v1/claims/${ticketId}`,
        {
          method: "PATCH",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ [editingField]: parsedVal }),
        },
      );
      setExtractedData(data.extracted_data || { ...extractedData, [editingField]: parsedVal });
      setConfirmed(Boolean(data.confirmed));
      if (data.conversation_phase) setConversationPhase(data.conversation_phase);
      if (data.agent_message) {
        setHistory((prev) => [
          ...prev,
          { turn: prev.length + 1, speaker: "agent", text: data.agent_message!, timestamp: Date.now() },
        ]);
      }
      setEditingField(null);
      fetchClaimsList(token);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Could not save correction.");
    }
  };

  const handleLogout = () => {
    if (isRecording) stopVoiceRecording();
    stopAssistantAudio();
    try {
      voiceSessionRef.current?.close();
    } catch {}
    clearAuthToken();
    router.push("/login");
  };

  const currentIncidentTitle = extractedData.insurance_type
    ? `${(SUPPORTED_INSURANCE_TYPES as Record<string, string>)[extractedData.insurance_type] || extractedData.insurance_type} Claim`
    : "New Claim Intake";

  const pendingCount = [
    !extractedData.policy_id,
    !extractedData.insurance_type,
    !extractedData.event_date,
    !extractedData.estimated_claim_amount,
    ...missingEvidence.map(() => true),
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
              onScrollChange={(isUp) => {
                autoScrollEnabledRef.current = !isUp;
                setShowScrollBottom(isUp);
              }}
              pendingEvidenceName={pendingEvidenceName}
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
              onUploadEvidence={handleUploadEvidence}
              evidenceUploading={evidenceUploading}
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
              submitted={claimSubmitted}
              missingEvidence={missingEvidence}
              pendingEvidenceReview={pendingEvidenceReview}
              evidenceItems={evidenceItems}
              ticketId={ticketId}
              conversationPhase={conversationPhase}
              gapAnalysis={gapAnalysis}
              submissionReadiness={submissionReadiness}
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

