import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ExtractedData {
  policy_id?: string | null;
  event_date?: string | null;
  insurance_type?: string | null;
  event_description?: string | null;
  estimated_claim_amount?: number | null;
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
  const { policy: queryPolicy } = router.query;

  const [token, setToken] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
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
          router.push(data.role === "ADMIN" ? "/admin" : "/adjuster");
          return;
        }
        setUserId(data.id);
        setUserName(data.full_name || "Claimant");
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
          setAgentState(isRecording ? "listening" : "idle");
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
  }, [isRecording]);

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
          utteranceRef.current = utterance;
          utterance.onstart = () => {
            isSpeakingFallbackRef.current = true;
            setAgentState("speaking");
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "tts_started" }));
            }
          };
          utterance.onend = () => {
            isSpeakingFallbackRef.current = false;
            setAgentState(isRecording ? "listening" : "idle");
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "tts_stopped" }));
            }
          };
          window.speechSynthesis.speak(utterance);
        }
      }
    } else if (event.data instanceof Blob) {
      enqueueAudio(event.data);
    }
  }, [enqueueAudio, isRecording]);

  // Connect WebSocket
  const connectWebSocket = useCallback((ticket: string, userToken: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = API_BASE.replace(/^https?:\/\//, "");
    const wsUrl = `${wsProtocol}//${host}/ws/claims/${ticket}/voice?token=${userToken}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setErrorBanner("");
    };

    ws.onmessage = handleWsMessage;

    ws.onerror = () => {
      console.warn("WebSocket status warning - falling back to API channels if disconnected.");
    };

    ws.onclose = () => {
      // ws closed
    };
  }, [handleWsMessage]);

  // Load existing session or initialize new
  const loadOrInitSession = useCallback(async () => {
    if (!token || !userId) return;
    setLoading(true);
    setErrorBanner("");

    const savedTicket = localStorage.getItem("active_claim_ticket_id");
    if (savedTicket) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/claims/${savedTicket}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const claimData = await res.json();
          const convRes = await fetch(`${API_BASE}/api/v1/claims/${savedTicket}/conversation`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          let turns: ConversationTurn[] = [];
          if (convRes.ok) {
            const convData = await convRes.json();
            turns = convData.map((t: any) => ({
              turn: t.turn,
              speaker: t.speaker,
              text: t.text,
              timestamp: t.created_at ? new Date(t.created_at).getTime() : Date.now(),
            }));
          }

          if (turns.length === 0) {
            turns = [
              {
                turn: 1,
                speaker: "agent",
                text: "Hello! I'm here to assist you in filing your insurance claim. Please describe what happened, and I will capture all the details for you.",
                global_seq: 0,
                timestamp: Date.now(),
              },
            ];
          }

          setTicketId(savedTicket);
          setConversationStatus(claimData.conversation_status || "collecting");
          const isSubmitted = claimData.status === "submitted" || claimData.conversation_status === "confirmed";
          setConfirmed(isSubmitted);
          if (isSubmitted) {
            setSubmittedMessage(`Claim #${savedTicket} has been submitted.`);
          }

          let ext = claimData.extracted_data || {};
          if (queryPolicy && typeof queryPolicy === "string") {
            ext = { ...ext, policy_id: queryPolicy.toUpperCase() };
            fetch(`${API_BASE}/api/v1/claims/${savedTicket}`, {
              method: "PATCH",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: JSON.stringify({ policy_id: queryPolicy.toUpperCase() }),
            }).catch(() => {});
          }
          setExtractedData(ext);
          setHistory(turns);
          setPartialSegments(new Map());
          connectWebSocket(savedTicket, token);
          setLoading(false);
          return;
        } else {
          localStorage.removeItem("active_claim_ticket_id");
        }
      } catch (err) {
        console.warn("Failed to restore saved claim session:", err);
        localStorage.removeItem("active_claim_ticket_id");
      }
    }

    // Initialize fresh session
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(queryPolicy ? { policy_number: queryPolicy } : {}),
      });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      const data = await res.json();
      setTicketId(data.ticket_id);
      localStorage.setItem("active_claim_ticket_id", data.ticket_id);
      setConversationStatus("collecting");
      setConfirmed(false);
      setSubmittedMessage("");
      setExtractedData(data.extracted_data || (queryPolicy ? { policy_id: queryPolicy as string } : {}));
      setPartialSegments(new Map());
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || "Hello! I'm here to assist you in filing your insurance claim. Please describe what happened, and I will capture all the details for you.",
          global_seq: 0,
          timestamp: Date.now(),
        },
      ]);

      connectWebSocket(data.ticket_id, token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Failed to initialize claim intake: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [token, userId, queryPolicy, connectWebSocket]);

  useEffect(() => {
    if (token && userId && !ticketId) {
      loadOrInitSession();
    }
  }, [token, userId, ticketId, loadOrInitSession]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        audioContextRef.current.close();
      }
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Voice recording triggers
  const startVoiceRecording = async () => {
    try {
      setErrorBanner("");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 16000,
      });
      audioContextRef.current = audioCtx;

      await audioCtx.audioWorklet.addModule("/audio-processor.js");

      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, "pcm16-processor");
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event) => {
        const pcmBuffer = event.data;
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(pcmBuffer);
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioCtx.destination);

      setIsRecording(true);
      setAgentState("listening");
    } catch (err: any) {
      setErrorBanner(`Microphone access error: ${err.message || "Please allow microphone permissions."}`);
    }
  };

  const stopVoiceRecording = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setIsRecording(false);
    setAgentState("idle");
  };

  const toggleMic = () => {
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  };

  // Text message submission fallback
  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;

    const userText = textInput.trim();
    setTextInput("");

    setHistory((prev) => [
      ...prev,
      {
        turn: prev.length + 1,
        speaker: "user",
        text: userText,
        timestamp: Date.now(),
      },
    ]);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "text_input",
          text: userText,
        })
      );
    } else {
      // Fallback via HTTP
      fetch(`${API_BASE}/api/v1/claims/message/${ticketId}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: userText }),
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.agent_message) {
            setHistory((prev) => [
              ...prev,
              {
                turn: prev.length + 1,
                speaker: "agent",
                text: data.agent_message,
                timestamp: Date.now(),
              },
            ]);
          }
          if (data.extracted_data) {
            setExtractedData(data.extracted_data);
          }
        })
        .catch(() => {});
    }
  };

  // Submit verified claim
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
      if (isRecording) {
        stopVoiceRecording();
      }
    } catch (err: any) {
      setErrorBanner(err.message || "An error occurred while submitting your claim.");
    } finally {
      setSubmittingClaim(false);
    }
  };

  // Explicit New Intake Session
  const handleStartNewSession = async () => {
    if (isRecording) stopVoiceRecording();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    localStorage.removeItem("active_claim_ticket_id");
    setTicketId("");
    setExtractedData({});
    setHistory([]);
    setConfirmed(false);
    setSubmittedMessage("");

    if (!token) return;
    try {
      setLoading(true);
      setErrorBanner("");
      const res = await fetch(`${API_BASE}/api/v1/claims/voice-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      const data = await res.json();
      setTicketId(data.ticket_id);
      localStorage.setItem("active_claim_ticket_id", data.ticket_id);
      setConversationStatus("collecting");
      setConfirmed(false);
      setSubmittedMessage("");
      setExtractedData(data.extracted_data || {});
      setPartialSegments(new Map());
      setHistory([
        {
          turn: 1,
          speaker: "agent",
          text: data.initial_message || "Hello! I'm here to assist you in filing your insurance claim. Please describe what happened, and I will capture all the details for you.",
          global_seq: 0,
          timestamp: Date.now(),
        },
      ]);
      connectWebSocket(data.ticket_id, token);
    } catch (err: any) {
      setErrorBanner(`Failed to start new session: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Manual Edit Field Handler
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

    const updated = {
      ...extractedData,
      [editingField]: parsedVal,
    };
    setExtractedData(updated);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "manual_edit",
          field: editingField,
          value: parsedVal,
        })
      );
    }

    setEditingField(null);
  };

  const handleLogout = () => {
    if (isRecording) stopVoiceRecording();
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  const pendingCount = [
    !extractedData.policy_id,
    !extractedData.insurance_type,
    !extractedData.event_date,
    !extractedData.estimated_claim_amount,
  ].filter(Boolean).length;

  const currentIncidentTitle = extractedData.insurance_type
    ? `${SUPPORTED_INSURANCE_TYPES[extractedData.insurance_type as keyof typeof SUPPORTED_INSURANCE_TYPES] || extractedData.insurance_type} Claim`
    : "New Claim Intake";

  return (
    <div className="bg-[#f7f9fb] text-[#191c1e] font-body antialiased min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Mobile TopAppBar */}
      <header className="md:hidden bg-white text-[#00647c] font-body w-full top-0 sticky flex justify-between items-center px-4 py-3 border-b border-[#e0e3e5] z-40">
        <div className="flex items-center gap-2 font-headline text-lg font-bold text-[#191c1e] tracking-tight">
          <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
          <span>InsureClaimAI</span>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/link-policy" className="text-[#505f76] hover:text-[#00647c] p-1.5 rounded-md hover:bg-[#eceef0]">
            <span className="material-symbols-outlined text-xl">settings</span>
          </Link>
          <button onClick={handleLogout} className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded-md hover:bg-[#eceef0]">
            <span className="material-symbols-outlined text-xl">logout</span>
          </button>
        </div>
      </header>

      {/* Desktop SideNavBar */}
      <nav className="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 bg-[#f7f9fb] text-[#0891B2] font-label text-xs border-r border-[#e0e3e5] py-8 px-4 z-40">
        <div className="px-2 mb-8">
          <div className="flex items-center gap-2 font-headline text-xl font-bold text-[#191c1e]">
            <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
            <span>InsureClaimAI</span>
          </div>
          <p className="font-label text-[11px] text-[#505f76] mt-0.5">Kinetic Voice Intake</p>
        </div>

        <div className="flex flex-col gap-1 flex-1">
          <Link
            href="/claimant"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#00647c] font-bold bg-[#eceef0] transition-colors"
          >
            <span className="material-symbols-outlined fill text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>
              dashboard
            </span>
            <span>Active Intake</span>
          </Link>
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] opacity-50 cursor-not-allowed">
            <span className="material-symbols-outlined text-[20px]">history</span>
            <span>Claims History</span>
          </div>
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] opacity-50 cursor-not-allowed">
            <span className="material-symbols-outlined text-[20px]">description</span>
            <span>Documents</span>
          </div>
          <Link
            href="/link-policy"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] hover:text-[#00647c] hover:bg-[#eceef0] transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">link</span>
            <span>Link Policy</span>
          </Link>
        </div>

        {/* User Card */}
        <div className="mt-auto pt-6 border-t border-[#e0e3e5]">
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="w-8 h-8 rounded-full bg-[#d0e1fb] text-[#54647a] flex items-center justify-center font-bold text-xs shrink-0">
                {userName.charAt(0) || "C"}
              </div>
              <div className="flex flex-col truncate">
                <span className="font-label text-xs text-[#191c1e] font-semibold truncate">{userName}</span>
                <span className="font-label text-[#505f76] text-[10px]">Claimant</span>
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded-md hover:bg-[#eceef0] transition-colors"
            >
              <span className="material-symbols-outlined text-lg">logout</span>
            </button>
          </div>
        </div>
      </nav>

      {/* Main Canvas */}
      <main className="flex-1 md:ml-64 flex flex-col h-[calc(100vh-57px)] md:h-screen bg-white overflow-hidden">
        {/* Canvas Header */}
        <div className="px-4 md:px-8 py-3.5 border-b border-[#e0e3e5] flex justify-between items-center bg-white z-10 shrink-0">
          <div>
            <div className="flex items-center gap-2 text-[#505f76] mb-0.5">
              <span className="font-label text-[11px] uppercase tracking-wider font-semibold">Active Intake</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  isRecording ? "bg-[#0891B2] animate-pulse" : "bg-emerald-500"
                }`}
              ></span>
              {agentState !== "idle" && (
                <span className="text-[11px] text-[#0891B2] capitalize font-medium">
                  ({agentState})
                </span>
              )}
            </div>
            <h1 className="font-headline text-lg md:text-xl font-bold text-[#191c1e]">
              {currentIncidentTitle}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleStartNewSession}
              disabled={loading}
              className="flex items-center gap-1.5 text-[#505f76] hover:text-[#00647c] transition-colors px-3 py-1.5 rounded-lg hover:bg-[#eceef0] text-xs font-label font-medium cursor-pointer"
            >
              <span className="material-symbols-outlined text-base">refresh</span>
              <span>New Session</span>
            </button>
          </div>
        </div>

        {errorBanner && (
          <div className="px-6 py-2 bg-[#ffdad6] text-[#93000a] text-xs flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">warning</span>
              <span>{errorBanner}</span>
            </div>
            <button onClick={() => setErrorBanner("")} className="text-[#93000a] hover:opacity-70">
              <span className="material-symbols-outlined text-sm">close</span>
            </button>
          </div>
        )}

        {/* Two Column Layout */}
        <div className="flex flex-1 overflow-hidden flex-col lg:flex-row h-full">
          {/* Left Column: Conversation & Voice Bar */}
          <div className="flex-1 flex flex-col h-full relative bg-white overflow-hidden">
            {/* Chat Area */}
            <div
              ref={chatContainerRef}
              className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scroll-smooth pb-48"
            >
              {history.map((turn, idx) => {
                if (turn.speaker === "agent") {
                  return (
                    <div key={`msg-${idx}`} className="flex gap-3 max-w-[85%]">
                      <div className="w-8 h-8 rounded-full bg-[#eceef0] flex items-center justify-center shrink-0 border border-[#e0e3e5] text-[#00647c]">
                        <span className="material-symbols-outlined text-base">robot_2</span>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="font-label text-xs text-[#505f76] font-medium">InsureClaimAI</span>
                        <div className="bg-[#F1F5F9] p-3.5 rounded-2xl rounded-tl-none border border-[#e0e3e5] shadow-sm">
                          <p className="font-body text-sm text-[#191c1e] leading-relaxed whitespace-pre-line">
                            {turn.text}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                } else {
                  return (
                    <div key={`msg-${idx}`} className="flex gap-3 max-w-[85%] ml-auto justify-end">
                      <div className="flex flex-col gap-1 items-end">
                        <span className="font-label text-xs text-[#505f76] font-medium">You</span>
                        <div className="bg-[#00647c] text-white p-3.5 rounded-2xl rounded-tr-none shadow-sm">
                          <p className="font-body text-sm leading-relaxed whitespace-pre-line">
                            {turn.text}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                }
              })}

              {/* Partial live transcript */}
              {Array.from(partialSegments.values()).map((seg) => (
                <div key={seg.segment_id} className="flex gap-3 max-w-[85%] ml-auto justify-end opacity-85">
                  <div className="flex flex-col gap-1 items-end">
                    <span className="font-label text-xs text-[#0891B2] font-semibold">Speaking...</span>
                    <div className="bg-[#00647c]/90 text-white p-3.5 rounded-2xl rounded-tr-none border border-[#0891B2]">
                      <p className="font-body text-sm italic">{seg.text}</p>
                    </div>
                  </div>
                </div>
              ))}

              {/* AI Processing Indicator */}
              {agentState === "thinking" && (
                <div className="flex gap-3 max-w-[85%]">
                  <div className="w-8 h-8 rounded-full bg-[#eceef0] flex items-center justify-center shrink-0 border border-[#e0e3e5]">
                    <span className="material-symbols-outlined text-[#0EA5E9] animate-spin text-base">
                      progress_activity
                    </span>
                  </div>
                  <div className="flex flex-col gap-1 justify-center">
                    <span className="font-label text-xs text-[#505f76] italic">InsureClaimAI is processing...</span>
                  </div>
                </div>
              )}

              {confirmed && (
                <div className="p-4 bg-emerald-50 border border-emerald-500/30 rounded-xl text-emerald-800 text-xs flex items-center gap-3 shadow-sm">
                  <span className="material-symbols-outlined text-2xl text-emerald-600">verified</span>
                  <div>
                    <h4 className="font-bold text-sm">Claim Successfully Submitted</h4>
                    <p className="mt-0.5">{submittedMessage || "Your claim has been assigned to an adjuster."}</p>
                  </div>
                </div>
              )}

              {/* Bottom Spacer so messages are never hidden under the voice console */}
              <div className="h-48 w-full shrink-0 pointer-events-none" aria-hidden="true" />
            </div>

            {/* Voice Input Console (Fixed Bottom) */}
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white/95 to-transparent pt-6 pb-4 px-4 md:px-8 flex flex-col items-center justify-end z-20">
              {/* Waveform Visualizer */}
              <div className="flex items-center gap-1.5 mb-2 h-7 opacity-85">
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-3 waveform-bar" : "h-2"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-6 waveform-bar delay-1" : "h-2"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-4 waveform-bar delay-2" : "h-2"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-8 waveform-bar delay-3" : "h-3"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-5 waveform-bar delay-4" : "h-2"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-7 waveform-bar delay-5" : "h-2"}`}></div>
                <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-3 waveform-bar" : "h-2"}`}></div>
              </div>

              {/* Active Speech Preview Quote */}
              <div className="text-center mb-3 min-h-[18px]">
                <p className="font-body text-xs text-[#505f76] truncate max-w-md">
                  {isRecording
                    ? "Listening... Speak naturally to describe your claim"
                    : textMode
                    ? "Type your message below and press Enter"
                    : "Tap the microphone to speak with your claims assistant"}
                </p>
              </div>

              {/* Text Input Drawer when in Text Mode */}
              {textMode && (
                <form onSubmit={handleSendText} className="w-full max-w-lg flex items-center gap-2 mb-3">
                  <input
                    type="text"
                    placeholder="Type incident details, dates, or estimates..."
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    className="input-minimal flex-1 bg-[#f7f9fb] border border-[#bdc8ce] rounded-full px-4 py-2 text-sm text-[#191c1e] placeholder:text-[#6e797e]"
                  />
                  <button
                    type="submit"
                    className="w-10 h-10 rounded-full bg-[#0891B2] hover:bg-[#007f9d] text-white flex items-center justify-center shrink-0 transition-colors cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-base">send</span>
                  </button>
                </form>
              )}

              {/* Voice Controls Row */}
              <div className="flex items-center justify-center gap-4">
                <button
                  type="button"
                  onClick={() => setTextMode(!textMode)}
                  title={textMode ? "Switch to Voice Only" : "Switch to Keyboard Input"}
                  className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors cursor-pointer border ${
                    textMode
                      ? "bg-[#0891B2] text-white border-[#0891B2]"
                      : "bg-[#f7f9fb] text-[#505f76] hover:bg-[#eceef0] border-[#bdc8ce]"
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">keyboard</span>
                </button>

                <button
                  type="button"
                  onClick={toggleMic}
                  disabled={confirmed}
                  title={isRecording ? "Mute Microphone" : "Start Speaking"}
                  className={`w-16 h-16 rounded-full text-white flex items-center justify-center relative z-10 transition-all cursor-pointer shadow-md ${
                    isRecording
                      ? "bg-[#0891B2] pulse-ring scale-105"
                      : "bg-[#0891B2] hover:bg-[#007f9d]"
                  } disabled:opacity-50`}
                >
                  <span className="material-symbols-outlined fill text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                    {isRecording ? "mic" : "mic_none"}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (isRecording) stopVoiceRecording();
                    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
                  }}
                  title="Stop Audio / Reset"
                  className="w-10 h-10 rounded-full bg-[#f7f9fb] border border-[#bdc8ce] flex items-center justify-center text-[#505f76] hover:bg-[#eceef0] transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-sm">stop</span>
                </button>
              </div>
            </div>
          </div>

          {/* Right Column: Collected Details (Review & Verify) */}
          <div className="w-full lg:w-[400px] xl:w-[460px] bg-[#f7f9fb] flex flex-col h-full border-t lg:border-t-0 lg:border-l border-[#e0e3e5] shrink-0 overflow-hidden">
            {/* Header */}
            <div className="p-4 md:p-5 border-b border-[#e0e3e5] bg-white sticky top-0 z-10 flex justify-between items-center shadow-sm shrink-0">
              <div>
                <h2 className="font-headline text-base md:text-lg font-bold text-[#191c1e]">Collected Details</h2>
                <p className="font-label text-xs text-[#505f76]">Review and verify extracted information</p>
              </div>
              <span
                className={`font-label text-[10px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wider ${
                  pendingCount === 0
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-[#d0e1fb] text-[#54647a]"
                }`}
              >
                {pendingCount === 0 ? "Ready to Submit" : `${pendingCount} Pending`}
              </span>
            </div>

            {/* Details Cards Container */}
            <div className="p-4 md:p-5 space-y-3.5 flex-1 overflow-y-auto">
              {/* Detail Card: Policy ID */}
              <div
                className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-sm ${
                  extractedData.policy_id ? "border-[#00647c]" : "border-[#bdc8ce]"
                }`}
              >
                {extractedData.policy_id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
                <div className="flex justify-between items-start pl-1">
                  <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                    Policy ID
                  </span>
                  <button
                    onClick={() => handleOpenEdit("policy_id", extractedData.policy_id)}
                    className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                </div>
                <div className="flex items-center gap-2 pl-1">
                  <span className="material-symbols-outlined text-[#505f76] text-[20px]">verified_user</span>
                  <span className="font-body text-sm text-[#191c1e] font-semibold font-mono">
                    {extractedData.policy_id || <span className="text-[#505f76] font-normal italic">Not specified yet</span>}
                  </span>
                </div>
                {extractedData.policy_id ? (
                  <div className="text-[11px] text-emerald-700 flex items-center gap-1 mt-0.5 pl-1">
                    <span className="material-symbols-outlined text-[14px]">check_circle</span> Verified
                  </div>
                ) : (
                  <Link
                    href="/link-policy"
                    className="text-[11px] text-[#0891B2] font-semibold hover:underline mt-1 pl-1 flex items-center gap-1"
                  >
                    <span>Link your policy now</span>
                    <span className="material-symbols-outlined text-[12px]">arrow_forward</span>
                  </Link>
                )}
              </div>

              {/* Detail Card: Incident Category */}
              <div
                className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-sm ${
                  extractedData.insurance_type ? "border-[#00647c]" : "border-[#bdc8ce]"
                }`}
              >
                {extractedData.insurance_type && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
                <div className="flex justify-between items-start pl-1">
                  <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                    Incident Category
                  </span>
                  <button
                    onClick={() => handleOpenEdit("insurance_type", extractedData.insurance_type)}
                    className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                </div>
                <div className="flex items-center gap-2 pl-1">
                  <span className="material-symbols-outlined text-[#00647c] text-[20px]">category</span>
                  <span className="font-body text-sm text-[#191c1e] font-semibold capitalize">
                    {extractedData.insurance_type ? (
                      SUPPORTED_INSURANCE_TYPES[extractedData.insurance_type as keyof typeof SUPPORTED_INSURANCE_TYPES] ||
                      extractedData.insurance_type
                    ) : (
                      <span className="text-[#505f76] font-normal italic">Analyzing incident...</span>
                    )}
                  </span>
                </div>
              </div>

              {/* Detail Card: Date of Incident */}
              <div
                className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-sm ${
                  extractedData.event_date ? "border-[#00647c]" : "border-[#bdc8ce]"
                }`}
              >
                {extractedData.event_date && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
                <div className="flex justify-between items-start pl-1">
                  <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                    Date of Incident
                  </span>
                  <button
                    onClick={() => handleOpenEdit("event_date", extractedData.event_date)}
                    className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                </div>
                <div className="flex items-center gap-2 pl-1">
                  <span className="material-symbols-outlined text-[#00647c] text-[20px]">calendar_today</span>
                  <span className="font-body text-sm text-[#191c1e] font-semibold">
                    {extractedData.event_date || <span className="text-[#505f76] font-normal italic">Waiting for date...</span>}
                  </span>
                </div>
              </div>

              {/* Detail Card: Estimated Amount */}
              <div
                className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-sm ${
                  extractedData.estimated_claim_amount != null ? "border-[#00647c]" : "border-[#bdc8ce]"
                }`}
              >
                {extractedData.estimated_claim_amount != null && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
                <div className="flex justify-between items-start pl-1">
                  <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                    Estimated Cost
                  </span>
                  <button
                    onClick={() => handleOpenEdit("estimated_claim_amount", extractedData.estimated_claim_amount)}
                    className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                </div>
                <div className="flex items-center gap-2 pl-1">
                  <span className="material-symbols-outlined text-[#00647c] text-[20px]">payments</span>
                  <span className="font-body text-sm text-[#191c1e] font-semibold">
                    {extractedData.estimated_claim_amount != null ? (
                      `₹${extractedData.estimated_claim_amount.toLocaleString()}`
                    ) : (
                      <span className="text-[#505f76] font-normal italic">Discussing damage cost...</span>
                    )}
                  </span>
                </div>
              </div>

              {/* Detail Card: Description Summary */}
              <div className="bg-white border border-[#bdc8ce] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
                <div className="flex justify-between items-start">
                  <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                    Description Summary
                  </span>
                  <button
                    onClick={() => handleOpenEdit("event_description", extractedData.event_description)}
                    className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                </div>
                <div className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[#505f76] text-[18px] mt-0.5">subject</span>
                  <p className="font-body text-xs text-[#191c1e] leading-relaxed">
                    {extractedData.event_description || (
                      <span className="text-[#505f76] italic">
                        Voice summaries will update automatically as you converse with the AI assistant.
                      </span>
                    )}
                  </p>
                </div>
              </div>
            </div>

            {/* Action Footer */}
            <div className="p-4 border-t border-[#e0e3e5] bg-white shrink-0 shadow-sm">
              <button
                type="button"
                onClick={handleSubmitClaim}
                disabled={submittingClaim || confirmed}
                className="w-full bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-sm"
              >
                {submittingClaim ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                    <span>Submitting Claim...</span>
                  </>
                ) : confirmed ? (
                  <>
                    <span className="material-symbols-outlined text-base">check</span>
                    <span>Claim Submitted</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-base">send</span>
                    <span>
                      Submit Claim {pendingCount > 0 ? `(${pendingCount} Items Incomplete)` : ""}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Edit Field Modal */}
      {editingField && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">
              Edit {editingField.replace(/_/g, " ").toUpperCase()}
            </h3>
            <p className="font-body text-xs text-[#505f76] mb-4">
              Update the value manually or let the voice assistant extract it during conversation.
            </p>

            {editingField === "insurance_type" ? (
              <select
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
              >
                <option value="">Select Insurance Type</option>
                {Object.entries(SUPPORTED_INSURANCE_TYPES).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            ) : editingField === "event_date" ? (
              <input
                type="date"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
              />
            ) : editingField === "event_description" ? (
              <textarea
                rows={4}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4 resize-none"
              />
            ) : (
              <input
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
              />
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingField(null)}
                className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-4 py-2 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm cursor-pointer"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
