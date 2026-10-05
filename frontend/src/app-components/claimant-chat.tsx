"use client";
import React, { useEffect, useRef, useState } from "react";
import { 
  AlertCircle, 
  BookOpen, 
  Check, 
  ChevronDown, 
  ChevronUp, 
  Copy, 
  FileText, 
  Menu, 
  MessageCircle, 
  Mic, 
  Paperclip, 
  Plus, 
  RefreshCw, 
  Send, 
  ShieldCheck, 
  Sparkles, 
  Trash2, 
  Upload, 
  Volume2, 
  X 
} from "lucide-react";
import { API_BASE, api } from "@/lib/api";
import { DataBadge, MarkdownRenderer } from "@/app-components/ui";

type Source = {
  citation_label?: string;
  source_name?: string;
  document_type?: string;
  page_number?: number;
  section_number?: string;
  clause_number?: string;
  chunk_id?: string;
  document_version?: string;
  text?: string;
};

type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  text: string;
  citations?: Source[];
  grounded?: boolean;
  attachment?: any;
  isStreaming?: boolean;
};

type Conversation = {
  ticket_id: string;
  status: string;
  insurance_type?: string;
  updated_at?: string;
  last_message?: string;
  turn_count?: number;
};

function sourceLabel(s: Source) {
  return s.citation_label || s.source_name || s.chunk_id || "Policy Source";
}

export function ClaimantChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [ticket, setTicket] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "starting" | "listening" | "thinking" | "speaking" | "error">("idle");
  const [error, setError] = useState("");
  const [showSources, setShowSources] = useState<Record<string, boolean>>({});
  const [mobileHistory, setMobileHistory] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [linkedPolicies, setLinkedPolicies] = useState<any[]>([]);
  const ticketRef = useRef(ticket);
  useEffect(() => {
    ticketRef.current = ticket;
  }, [ticket]);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const callRef = useRef("");
  const creatingRef = useRef<Promise<string> | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const isAutoScrollLockedRef = useRef(true);

  function cleanupVoice() {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    heartbeatRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    mediaRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    callRef.current = "";
    setVoiceState("idle");
  }

  useEffect(() => () => cleanupVoice(), []);

  // Smart non-disruptive autoscroll: only scrolls if the user is near bottom
  function handleScroll() {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isAutoScrollLockedRef.current = distanceToBottom < 80;
  }

  function scrollToBottom(smooth = true) {
    const el = scrollContainerRef.current;
    if (!el || !isAutoScrollLockedRef.current) return;
    if (typeof el.scrollTo === "function") {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth ? "smooth" : "auto"
      });
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }

  useEffect(() => {
    scrollToBottom(false);
  }, [messages]);

  async function loadConversations(preferred?: string) {
    const data = await api<any>("/api/v1/claims?limit=100");
    const items = (data.items || []) as Conversation[];
    setConversations(items);
    const next = preferred || ticket || items[0]?.ticket_id || "";
    if (next) {
      await openConversation(next);
      return;
    }
    setMessages([]);
    if (!items.length) await createChat();
  }

  async function openConversation(id: string) {
    if (!id) return;
    cleanupVoice();
    setTicket(id);
    setMobileHistory(false);
    try {
      const rows = await api<any[]>("/api/v1/claims/" + encodeURIComponent(id) + "/conversation");
      setMessages(
        (rows || [])
          .map(
            (m: any, idx: number): ChatMessage => ({
              id: m.id || `turn-${idx}`,
              role: m.speaker === "user" ? "user" : "assistant",
              text: m.text || "",
              attachment: m.attachment
            })
          )
          .filter((x) => x.text)
      );
      setError("");
    } catch (e: any) {
      setError(e.message || "Unable to open conversation.");
    }
  }

  async function createChat(): Promise<string> {
    if (creatingRef.current) return creatingRef.current;
    const task = (async () => {
      cleanupVoice();
      setMobileHistory(false);
      setError("");
      const data = await api<any>("/api/v1/claims/new-session", { method: "POST", body: JSON.stringify({}) });
      const welcome: ChatMessage = {
        id: "msg-welcome-" + Date.now(),
        role: "assistant",
        text:
          data.initial_message ||
          "Hello, I am your Flowa Claim Intake Assistant. Describe what happened in your own words, and I will capture all the facts, determine coverage, and file your claim."
      };
      setTicket(data.ticket_id);
      setMessages([welcome]);
      setConversations((v) => [
        {
          ticket_id: data.ticket_id,
          status: data.status || "draft",
          insurance_type: data.insurance_type,
          updated_at: new Date().toISOString(),
          last_message: welcome.text,
          turn_count: 1
        },
        ...v.filter((x) => x.ticket_id !== data.ticket_id)
      ]);
      return String(data.ticket_id);
    })();
    creatingRef.current = task;
    try {
      return await task;
    } finally {
      creatingRef.current = null;
    }
  }

  async function discardConversation(e: React.MouseEvent, t: string) {
    e.stopPropagation();
    if (!confirm("Are you sure you want to discard this draft claim session?")) return;
    try {
      await api("/api/v1/claims/" + encodeURIComponent(t), { method: "DELETE" });
      let nextFirstTicket: string | null = null;
      setConversations((prev) => {
        const remaining = prev.filter((x) => x.ticket_id !== t);
        if (remaining.length > 0) {
          nextFirstTicket = remaining[0].ticket_id;
        }
        return remaining;
      });
      if (ticketRef.current === t) {
        if (nextFirstTicket) {
          await openConversation(nextFirstTicket);
        } else {
          await createChat();
        }
      }
    } catch (err: any) {
      setError(err.message || "Unable to discard draft.");
    }
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadConversations()
      .catch((e: any) => alive && setError(e.message || "Unable to load conversations."))
      .finally(() => alive && setLoading(false));

    api<any>("/api/v1/policies/my-policies")
      .then((res) => {
        if (alive) setLinkedPolicies(Array.isArray(res) ? res : res.items || []);
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, []);

  async function sendText(customText?: string) {
    const text = (customText !== undefined ? customText : draft).trim();
    if (!text || sending) return;

    let activeTicket = ticket;
    if (!activeTicket) {
      try {
        activeTicket = await createChat();
      } catch (err: any) {
        setError(err?.message || "Failed to start a new chat session.");
        return;
      }
    }
    if (!activeTicket) return;

    if (customText === undefined) setDraft("");
    const userMsgId = "user-" + Date.now();
    setMessages((v) => [...v, { id: userMsgId, role: "user", text }]);
    setSending(true);
    setError("");

    try {
      const r = await api<any>("/api/v1/claims/" + encodeURIComponent(activeTicket) + "/text-turn", {
        method: "POST",
        body: JSON.stringify({ text })
      });

      const assistantMsg: ChatMessage = {
        id: "ai-" + Date.now(),
        role: "assistant",
        text: r.agent_message || "Received.",
        citations: r.citations || r.sources || [],
        grounded: r.grounded
      };

      setMessages((v) => [...v, assistantMsg]);
      setConversations((v) =>
        v.map((x) =>
          x.ticket_id === activeTicket
            ? {
                ...x,
                last_message: assistantMsg.text,
                updated_at: new Date().toISOString(),
                status: r.status || x.status,
                turn_count: (x.turn_count || 0) + 2
              }
            : x
        )
      );
    } catch (e: any) {
      setError(e.message || "Your message could not be processed.");
    } finally {
      setSending(false);
    }
  }

  async function copyText(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      /* ignore */
    }
  }

  async function upload(file: File) {
    if (!ticket) return;
    setUploading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api<any>("/api/v1/claims/" + encodeURIComponent(ticket) + "/evidence", {
        method: "POST",
        body: fd
      });
      setMessages((v) => [
        ...v,
        {
          id: "upload-" + Date.now(),
          role: "user",
          text: "Uploaded evidence attachment: " + file.name,
          attachment: { name: file.name }
        },
        {
          id: "ai-ack-" + Date.now(),
          role: "assistant",
          text: r.message || "Evidence received and added to this claim package. Analyzing document coverage…"
        }
      ]);
    } catch (e: any) {
      setError(e.message || "Evidence upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function startVoice() {
    let activeTicket = ticket || "";
    let reservedCallId = "";
    if (!activeTicket) {
      activeTicket = await createChat();
    }
    if (!activeTicket) return;

    cleanupVoice();
    setVoiceState("starting");
    setError("");

    try {
      const token = localStorage.getItem("access_token");
      if (!token) throw new Error("Your session has expired. Please sign in again.");
      const session = await api<any>("/api/v1/voice/realtime/session/" + encodeURIComponent(activeTicket), {
        method: "POST"
      });
      reservedCallId = String(session.call_id || "");

      if (window.isSecureContext === false) {
        throw new Error("Voice requires HTTPS or localhost. Open the secure application URL and try again.");
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser does not provide microphone access.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      const peer = new RTCPeerConnection({ iceServers: (session.ice_servers || []).map((x: any) => ({ urls: x.urls })) });
      pcRef.current = peer;
      mediaRef.current = stream;

      stream.getTracks().forEach((t) => peer.addTrack(t, stream));

      peer.ontrack = (ev) => {
        const remote = ev.streams?.[0];
        if (remote && audioRef.current) {
          audioRef.current.srcObject = remote;
          audioRef.current.play().catch(() => {});
        }
      };

      peer.onconnectionstatechange = () => {
        if (["failed", "disconnected", "closed"].includes(peer.connectionState)) {
          setVoiceState("error");
          setError("Voice connection dropped. Your conversation remains available by text.");
        }
      };

      const wsBase = API_BASE.replace(/^http/, "ws");
      const ws = new WebSocket(wsBase + "/api/v1/voice/events/" + encodeURIComponent(activeTicket));
      socketRef.current = ws;

      ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token }));
      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          if (event.event_type === "voice.state") {
            if (event.state === "listening" || event.state === "thinking" || event.state === "speaking") {
              setVoiceState(event.state);
            }
          }
          if (event.event_type === "voice.user.final" && event.text) {
            setMessages((v) => [...v, { id: "voice-u-" + Date.now(), role: "user", text: event.text }]);
          }
          if (event.event_type === "voice.agent.final" && event.text) {
            setMessages((v) => [
              ...v,
              {
                id: "voice-ai-" + Date.now(),
                role: "assistant",
                text: event.text,
                citations: event.citations || event.sources || [],
                grounded: event.grounded
              }
            ]);
          }
          if (event.event_type === "voice.error") {
            setVoiceState("error");
            setError("Voice processing failed; continue this exact conversation by typing.");
          }
        } catch {
          /* ignore */
        }
      };

      ws.onerror = () => setError("Voice event stream is unavailable; text remains fully available.");

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);

      await new Promise<void>((resolve) => {
        if (peer.iceGatheringState === "complete") {
          resolve();
          return;
        }
        const timer = window.setTimeout(() => {
          peer.removeEventListener("icegatheringstatechange", onState);
          resolve();
        }, 5000);
        const onState = () => {
          if (peer.iceGatheringState === "complete") {
            window.clearTimeout(timer);
            peer.removeEventListener("icegatheringstatechange", onState);
            resolve();
          }
        };
        peer.addEventListener("icegatheringstatechange", onState);
      });

      const local = peer.localDescription;
      if (!local?.sdp) throw new Error("WebRTC could not prepare local media candidates.");

      const answer = await api<any>("/api/v1/voice/realtime/offer/" + encodeURIComponent(session.call_id), {
        method: "POST",
        body: JSON.stringify({ ticket_id: activeTicket, sdp: local.sdp, type: local.type })
      });
      await peer.setRemoteDescription(answer);

      callRef.current = session.call_id;
      setVoiceState("listening");

      heartbeatRef.current = setInterval(() => {
        api("/api/v1/voice/heartbeat/" + encodeURIComponent(activeTicket) + "/" + encodeURIComponent(session.call_id), {
          method: "POST"
        }).catch(() => {});
      }, 30000);
    } catch (e: any) {
      if (reservedCallId && activeTicket) {
        api("/api/v1/voice/close/" + encodeURIComponent(activeTicket), { method: "POST" }).catch(() => {});
      }
      cleanupVoice();
      setVoiceState("error");
      setError(e.message || "Voice is currently unavailable. You can continue seamlessly with text.");
    }
  }

  async function stopVoice() {
    try {
      if (ticket) await api("/api/v1/voice/close/" + encodeURIComponent(ticket), { method: "POST" });
    } catch {
      /* local cleanup always runs */
    }
    cleanupVoice();
  }

  const selected = conversations.find((x) => x.ticket_id === ticket);

  return (
    <div className="claimant-chat-shell">
      {/* Conversations History Sidebar */}
      <aside className={"chat-history" + (mobileHistory ? " mobile-open" : "")} aria-label="Claim conversations">
        <div className="chat-history-head">
          <div>
            <div className="chat-brand">Claims Intake</div>
            <div className="chat-history-sub">Your conversational claims</div>
          </div>
          <button className="icon-btn" onClick={createChat} aria-label="New chat" title="Start new claim intake">
            <Plus size={16} />
          </button>
        </div>

        <button className="new-chat-btn" onClick={createChat}>
          <Plus size={15} />
          <span>New chat</span>
        </button>

        <div className="chat-history-list">
          {conversations.map((c, idx) => (
            <div
              key={c.ticket_id || `conv-${idx}`}
              className={"chat-history-item" + (c.ticket_id === ticket ? " active" : "")}
            >
              <button
                type="button"
                className="chat-history-open-btn"
                onClick={() => openConversation(c.ticket_id)}
                style={{
                  all: "unset",
                  display: "grid",
                  gap: 3,
                  cursor: "pointer",
                  textAlign: "left",
                  width: "100%",
                  paddingRight: ["draft", "pending_confirmation"].includes(c.status) ? 22 : 0
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="chat-history-title">
                    {c.insurance_type ? c.insurance_type.replaceAll("_", " ") : "Claim session"}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>
                    {c.status || "draft"}
                  </span>
                </div>
                <div className="chat-history-meta">{c.ticket_id}</div>
                <div className="chat-history-preview">{c.last_message || "No messages yet."}</div>
              </button>

              {["draft", "pending_confirmation"].includes(c.status) && (
                <button
                  type="button"
                  aria-label="Discard draft conversation"
                  onClick={(e) => discardConversation(e, c.ticket_id)}
                  title="Discard draft conversation"
                  style={{
                    position: "absolute",
                    top: 11,
                    right: 12,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--muted)",
                    display: "inline-flex",
                    padding: 2
                  }}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
          {!conversations.length && !loading && (
            <div style={{ padding: "32px 14px", textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
              No claims conversations yet.
            </div>
          )}
        </div>
      </aside>

      {/* Main Conversational Viewport */}
      <main className="claim-chat-main">
        {/* Chat Topbar */}
        <header className="claim-chat-topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              className="chat-history-toggle"
              onClick={() => setMobileHistory((v) => !v)}
              aria-label="Toggle chat history"
            >
              <Menu size={17} />
            </button>
            <div>
              <div className="claim-chat-title">
                {selected?.insurance_type ? selected.insurance_type.replaceAll("_", " ") : "Insurance Claim Copilot"}
              </div>
              <div className="claim-chat-status">
                {ticket ? `Ticket: ${ticket}` : "Start a new claim conversation"}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {voiceState !== "idle" && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 10px",
                  borderRadius: 9999,
                  background: voiceState === "listening" ? "var(--success-subtle)" : "var(--info-subtle)",
                  color: voiceState === "listening" ? "var(--success)" : "var(--info)",
                  fontSize: 11.5,
                  fontWeight: 600
                }}
              >
                <Volume2 size={13} />
                <span>Voice: {voiceState}</span>
              </span>
            )}
            {ticket && <DataBadge status={selected?.status || "draft"} />}
          </div>
        </header>

        {/* Scrollable Message Thread */}
        <div className="claim-chat-scroll" ref={scrollContainerRef} onScroll={handleScroll}>
          {loading ? (
            <div className="chat-skeleton" aria-label="Loading conversations">
              <div className="skeleton-shimmer" style={{ width: "60%" }} />
              <div className="skeleton-shimmer" style={{ width: "80%" }} />
              <div className="skeleton-shimmer" style={{ width: "45%" }} />
            </div>
          ) : (
            messages.map((m, i) => {
              const msgId = m.id || `msg-${i}`;
              return (
                <div key={msgId} className={"chat-turn " + (m.role === "user" ? "user" : "assistant")}>
                  <div className="chat-avatar">{m.role === "user" ? "You" : "AI"}</div>

                  <div className="chat-message-content">
                    {m.role === "user" ? (
                      <div className="chat-bubble-user">{m.text}</div>
                    ) : (
                      <div className="chat-response-ai">
                        <MarkdownRenderer content={m.text} />

                        {/* Inline Controls: Copy & Regenerate */}
                        <div className="chat-utilities">
                          <button
                            className="chat-util-btn"
                            onClick={() => copyText(msgId, m.text)}
                            aria-label="Copy message"
                            title="Copy response"
                          >
                            {copiedId === msgId ? <Check size={12} color="var(--success)" /> : <Copy size={12} />}
                            <span>{copiedId === msgId ? "Copied" : "Copy"}</span>
                          </button>
                        </div>

                        {/* Citations Sheet */}
                        {m.citations && m.citations.length > 0 && (
                          <div className="citation-wrap">
                            <button
                              className="citation-toggle"
                              onClick={() =>
                                setShowSources((x) => ({ ...x, [msgId]: !x[msgId] }))
                              }
                            >
                              <BookOpen size={12} />
                              <span>Verified Sources ({m.citations.length})</span>
                              {showSources[msgId] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            </button>

                            {showSources[msgId] && (
                              <div className="citation-list">
                                {m.citations.slice(0, 6).map((s, j) => (
                                  <div className="citation-item" key={j}>
                                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                                      <b>{sourceLabel(s)}</b>
                                      <span style={{ fontSize: 10, color: "var(--muted)" }}>
                                        {s.document_type ? s.document_type.replaceAll("_", " ") : "Policy"}
                                      </span>
                                    </div>
                                    <span>
                                      {s.page_number ? `p. ${s.page_number} · ` : ""}
                                      {s.clause_number ? `Clause ${s.clause_number}` : ""}
                                      {s.document_version ? ` · v${s.document_version}` : ""}
                                    </span>
                                    {s.text && (
                                      <div
                                        style={{
                                          fontSize: 11,
                                          color: "var(--ink-secondary)",
                                          fontStyle: "italic",
                                          marginTop: 3
                                        }}
                                      >
                                        “{s.text.slice(0, 160)}…”
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Empty State with Fast Suggestion Prompts */}
          {!messages.length && !loading && (
            <div style={{ margin: "auto", textAlign: "center", maxWidth: 480, padding: "40px 16px" }}>
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: "50%",
                  background: "var(--blue-subtle)",
                  color: "var(--blue)",
                  display: "grid",
                  placeItems: "center",
                  margin: "0 auto 16px"
                }}
              >
                <Sparkles size={26} />
              </div>
              <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px", color: "var(--ink)" }}>
                Start your claim conversation
              </h2>
              <p style={{ fontSize: 13.5, color: "var(--muted)", margin: "0 0 20px", lineHeight: 1.6 }}>
                Speak in your natural voice, type details at your own pace, or attach photos and documents. Our AI parses coverage and coordinates directly with adjusters.
              </p>

              {linkedPolicies.length > 0 && (
                <div style={{ marginBottom: 18, padding: "12px 14px", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--radius-md)", textAlign: "left" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: 8, letterSpacing: "0.05em" }}>
                    Your Linked Policies (Click to file)
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {linkedPolicies.map((p) => (
                      <button
                        key={p.policy_number}
                        className="btn"
                        style={{ height: 32, fontSize: 12, display: "inline-flex", alignItems: "center", gap: 6 }}
                        onClick={() => sendText(`I need to file a claim under my linked ${p.insurance_type || p.policy_type} policy ${p.policy_number}.`)}
                      >
                        <ShieldCheck size={13} color="var(--blue)" />
                        <span>{p.policy_number} ({p.insurance_type || p.policy_type})</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                <button
                  className="btn"
                  onClick={() => sendText("I was in a minor vehicle collision today and need to file an auto claim.")}
                  style={{ height: "auto", padding: "10px 12px", textAlign: "left", display: "grid", gap: 3 }}
                >
                  <b style={{ fontSize: 12 }}>Vehicle Collision</b>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Auto accident & damage</span>
                </button>
                <button
                  className="btn"
                  onClick={() => sendText("I have hospital invoices and pharmacy receipts for my health insurance.")}
                  style={{ height: "auto", padding: "10px 12px", textAlign: "left", display: "grid", gap: 3 }}
                >
                  <b style={{ fontSize: 12 }}>Medical Expenses</b>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Hospitalization & OPD</span>
                </button>
              </div>
            </div>
          )}

          {sending && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--muted)", fontSize: 12 }}>
              <div className="streaming-cursor" />
              <span>Analyzing policy requirements…</span>
            </div>
          )}
        </div>

        <audio ref={audioRef} autoPlay playsInline className="sr-only" />

        {/* Dismissable Error Toast */}
        {error && (
          <div
            style={{
              margin: "0 clamp(20px, 5vw, 80px) 10px",
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              background: "var(--danger-subtle)",
              border: "1px solid var(--danger-border)",
              color: "var(--danger)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 12
            }}
            role="alert"
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
            <button onClick={() => setError("")} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Modern Composer Bar */}
        <div className="claim-chat-composer">
          <label className="composer-attach" aria-label="Attach evidence" title="Upload damage photo or receipt">
            <Upload size={17} />
            <input
              type="file"
              hidden
              disabled={!ticket || uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
                e.currentTarget.value = "";
              }}
            />
          </label>

          <button
            className={"voice-primary " + (voiceState !== "idle" && voiceState !== "error" ? "active" : "")}
            onClick={
              voiceState === "listening" || voiceState === "thinking" || voiceState === "speaking"
                ? stopVoice
                : startVoice
            }
            disabled={voiceState === "starting"}
            aria-label={voiceState === "listening" ? "Stop voice" : "Start voice"}
            title={voiceState === "listening" ? "End voice session" : "Start conversational voice intake"}
          >
            <Mic size={20} />
          </button>

          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendText();
              }
            }}
            placeholder="Type your claim details or question… (Press Enter to send)"
            aria-label="Message claim assistant"
          />

          <button
            className="composer-send"
            onClick={() => sendText()}
            disabled={!draft.trim() || sending || !ticket}
            aria-label="Send message"
            title="Send message"
          >
            <Send size={16} />
          </button>
        </div>

        <div className="composer-hint">
          Voice and text are fully synchronized. Upload police reports, bills, or damage photos directly into this thread.
        </div>
      </main>
    </div>
  );
}
