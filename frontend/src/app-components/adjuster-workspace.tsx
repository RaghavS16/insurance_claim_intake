"use client";
import Link from "next/link";
import React, { useEffect, useState } from "react";
import { 
  AlertCircle, 
  AlertTriangle, 
  CheckCircle2, 
  ChevronRight, 
  ClipboardList, 
  Clock3, 
  ExternalLink, 
  FileCheck2, 
  Gauge, 
  MessageSquare, 
  Paperclip, 
  Send, 
  ShieldAlert, 
  ShieldCheck, 
  Sparkles, 
  Upload, 
  UserRound, 
  Users 
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, DataBadge, Empty, MarkdownRenderer, Metric, Page } from "@/app-components/ui";

const date = (v: any) => (v ? new Date(v).toLocaleDateString() : "—");
const dt = (v: any) => (v ? new Date(v).toLocaleString() : "—");
const money = (v: any) =>
  v == null || v === ""
    ? "—"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
        Number(v) || 0
      );
const human = (v: any) => String(v ?? "—").replaceAll("_", " ");

/* ==========================================================================
   Adjuster Dashboard Overview (Stripe & Ramp Benchmark)
   ========================================================================== */

function AdjusterDashboard() {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/v1/adjuster/dashboard")
      .then(setD)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <Page
      title="Adjuster overview"
      subtitle="Operational performance metrics, assigned claim queues, and SLA health indicators."
      actions={
        <Link className="btn primary" href="/adjuster/queue">
          <ClipboardList size={15} />
          <span>Open claims queue</span>
        </Link>
      }
    >
      {error && (
        <div className="error" style={{ marginBottom: 20 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <div className="metrics">
        <Metric
          label="Filed claims"
          value={d?.total_filed_claims ?? "—"}
          note="Total tenant volume"
          icon={<ClipboardList size={16} />}
        />
        <Metric
          label="Total users"
          value={d?.total_users ?? "—"}
          note="Active claimants & adjusters"
          icon={<Users size={16} />}
        />
        <Metric
          label="Assigned to me"
          value={d?.assigned_to_me ?? "—"}
          note="Current personal queue"
          icon={<UserRound size={16} />}
        />
        <Metric
          label="SLA breaches"
          value={d?.sla_breached ?? "—"}
          note={Number(d?.sla_breached) > 0 ? "Requires urgent attention" : "All within statutory window"}
          trend={Number(d?.sla_breached) > 0 ? "danger" : "success"}
          icon={<ShieldAlert size={16} />}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <div className="card-title">Operational workload breakdown</div>
          {[
            ["Under review", d?.under_review],
            ["Pending evidence", d?.pending_evidence],
            ["Queue total", d?.queue_total]
          ].map(([k, v]) => (
            <div className="list-row" key={String(k)}>
              <div className="list-main">
                <b>{k}</b>
                <span>Active claims in this state</span>
              </div>
              <b style={{ fontSize: 16 }}>{v ?? "—"}</b>
            </div>
          ))}

          <div className="chart" aria-label="Workload volume distribution">
            {[d?.under_review || 0, d?.pending_evidence || 0, d?.assigned_to_me || 0, d?.sla_breached || 0].map(
              (v: any, i) => (
                <div
                  className="bar"
                  key={i}
                  style={{
                    height: Math.max(18, Math.min(150, Number(v) * 22)),
                    background: i === 3 && Number(v) > 0 ? "var(--danger)" : undefined
                  }}
                  title={`Stage count: ${v}`}
                />
              )
            )}
          </div>
        </Card>

        <Card>
          <div className="card-title">Recently assigned claims</div>
          {d?.recent_claims?.length ? (
            d.recent_claims.slice(0, 7).map((c: any) => (
              <div className="list-row" key={c.ticket_id}>
                <div className="list-main">
                  <b>{c.ticket_id}</b>
                  <span>
                    {human(c.status)} · {c.age_hours ?? 0}h in queue
                  </span>
                </div>
                <div className="actions">
                  <DataBadge status={c.status} />
                  <Link className="btn" href={"/adjuster/claims/" + c.ticket_id + "/workbench"}>
                    <span>Review</span>
                    <ChevronRight size={13} />
                  </Link>
                </div>
              </div>
            ))
          ) : (
            <Empty
              text="No assigned claims are currently waiting in your queue."
              icon={<FileCheck2 size={28} />}
            />
          )}
        </Card>
      </div>
    </Page>
  );
}

/* ==========================================================================
   Adjuster Queue Table
   ========================================================================== */

function AdjusterQueue() {
  const [d, setD] = useState<any>(null);
  const [f, setF] = useState("all");
  const [error, setError] = useState("");

  async function load(s = f) {
    setF(s);
    try {
      setD(await api("/api/v1/adjuster/queue?status=" + s));
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load("all");
  }, []);

  return (
    <Page
      title="Claims Queue"
      subtitle="Prioritized operational queue with SLA deadline tracking and recommended next steps."
      actions={
        <Link className="btn" href="/adjuster">
          <Gauge size={14} />
          <span>Dashboard</span>
        </Link>
      }
    >
      <Card>
        <div className="tabs">
          {["all", "submitted", "under_review", "pending_evidence", "escalated"].map((s) => (
            <button className={"tab " + (f === s ? "active" : "")} key={s} onClick={() => load(s)}>
              {human(s)}
            </button>
          ))}
        </div>

        {error && (
          <div className="error" style={{ marginBottom: 14 }}>
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {d?.items?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Claim Ticket</th>
                  <th>Status</th>
                  <th>Queue Age</th>
                  <th>SLA Compliance</th>
                  <th>Recommended Action</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.items.map((c: any) => (
                  <tr key={c.ticket_id}>
                    <td>
                      <b style={{ fontFamily: "ui-monospace, monospace" }}>{c.ticket_id}</b>
                    </td>
                    <td>
                      <DataBadge status={c.status} />
                    </td>
                    <td>{c.age_hours ?? 0} hrs</td>
                    <td>
                      {c.sla_breached ? (
                        <Badge tone="danger">SLA Breached</Badge>
                      ) : (
                        <Badge tone="success">Within SLA</Badge>
                      )}
                    </td>
                    <td>{human(c.next_action)}</td>
                    <td style={{ textAlign: "right" }}>
                      <Link className="link" href={"/adjuster/claims/" + c.ticket_id + "/workbench"}>
                        <span>Review</span>
                        <ChevronRight size={13} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            text="No claims in the selected queue category."
            icon={<ClipboardList size={28} />}
          />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Human-in-the-Loop Workbench & Copilot Dossier
   ========================================================================== */

function Workbench({ ticket }: { ticket: string }) {
  const [d, setD] = useState<any>(null);
  const [cop, setCop] = useState<any>(null);
  const [requests, setRequests] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [chat, setChat] = useState("");
  const [chatRows, setChatRows] = useState<any[]>([]);
  const [request, setRequest] = useState("");
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [priority, setPriority] = useState("normal");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [a, b, c, e] = await Promise.all([
        api<any>("/api/v1/adjuster/claims/" + ticket),
        api<any>("/api/v1/adjuster/claims/" + ticket + "/copilot"),
        api<any>("/api/v1/adjuster/claims/" + ticket + "/evidence-requests"),
        api<any>("/api/v1/adjuster/claims/" + ticket + "/audit")
      ]);
      setD(a);
      setCop(b);
      setRequests(Array.isArray(c) ? c : c.items || []);
      setAudit(Array.isArray(e) ? e : e.items || []);
      setChatRows(b.chat || []);
      setPriority(a?.claim?.priority || "normal");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [ticket]);

  async function act(url: string, body?: any, method: "POST" | "PATCH" = "POST") {
    try {
      await api(url, { method, body: body ? JSON.stringify(body) : undefined });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function ask() {
    if (!chat.trim()) return;
    const v = chat;
    setChat("");
    setChatRows((x) => [...x, { speaker: "adjuster", message: v }]);
    try {
      const r = await api<any>("/api/v1/adjuster/claims/" + ticket + "/copilot/chat", {
        method: "POST",
        body: JSON.stringify({ message: v })
      });
      setChatRows((x) => [...x, { speaker: "copilot", message: r.message || r.response || "Copilot response received." }]);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function evidenceUrl(id: string) {
    try {
      const x = await api<any>("/api/v1/adjuster/claims/" + ticket + "/evidence/" + id + "/url");
      window.open(x.url, "_blank", "noopener,noreferrer");
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (loading) {
    return (
      <Page title={ticket} subtitle="Assembling claim dossier and Copilot intelligence…">
        <Card>
          <div className="chat-skeleton" style={{ width: "100%", margin: "20px 0" }}>
            <div className="skeleton-shimmer" style={{ width: "40%" }} />
            <div className="skeleton-shimmer" style={{ width: "90%" }} />
            <div className="skeleton-shimmer" style={{ width: "65%" }} />
          </div>
        </Card>
      </Page>
    );
  }

  const c = d?.claim || {};
  const facts = d?.extracted_data || {};
  const evidence = d?.evidence || d?.submission_package?.evidence || [];
  const req = d?.requirements || [];
  const missing = [...(d?.missing_requirements || []), ...(d?.missing_evidence || [])];
  const a = cop?.analysis;
  const conf = Number(a?.confidence_score || 0) * 100;

  return (
    <Page
      title={ticket}
      subtitle="Human-in-the-loop claim adjudication workbench with verified statutory coverage."
      actions={
        <>
          <DataBadge status={c.status || "under_review"} />
          <button className="btn secondary" onClick={() => act("/api/v1/adjuster/claims/" + ticket + "/assign")}>
            <UserRound size={14} />
            <span>Assign to me</span>
          </button>
        </>
      }
    >
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      {/* Metric Highlights */}
      <div className="metrics">
        <Metric
          label="Estimated amount"
          value={money(c.estimated_claim_amount)}
          note={c.insurance_type || "Claim"}
          icon={<FileCheck2 size={16} />}
        />
        <Metric
          label="Claim age"
          value={c.updated_at ? Math.round((Date.now() - new Date(c.updated_at).getTime()) / 3600000) + "h" : "—"}
          note="Since last claimant activity"
          icon={<Clock3 size={16} />}
        />
        <Metric
          label="Evidence items"
          value={evidence.length}
          note={evidence.length > 0 ? "Attached & verified" : "Pending claimant upload"}
          icon={<Upload size={16} />}
        />
        <Metric
          label="Copilot confidence"
          value={a?.confidence_score ? Math.round(conf) + "%" : "—"}
          note={a?.decision_recommendation ? human(a.decision_recommendation) : "Statutory Analysis"}
          trend={conf >= 80 ? "success" : conf >= 50 ? "warning" : "danger"}
          icon={<Sparkles size={16} />}
        />
      </div>

      {/* Main Dossier Split */}
      <div className="grid grid-2">
        {/* Left Column: Claim Overview & Facts */}
        <div style={{ display: "grid", gap: 20 }}>
          <Card>
            <div className="card-title">Claim overview</div>
            <div className="detail-grid">
              <div className="detail-item">
                <span>Insurance type</span>
                <b>{human(c.insurance_type)}</b>
              </div>
              <div className="detail-item">
                <span>Incident date</span>
                <b>{date(c.incident_date || c.event_date)}</b>
              </div>
              <div className="detail-item">
                <span>Priority</span>
                <b style={{ textTransform: "capitalize" }}>{priority}</b>
              </div>
            </div>

            <div style={{ marginTop: 20 }}>
              <div className="card-title" style={{ fontSize: 13, marginBottom: 10 }}>Linked policy coverage</div>
              {d?.policy ? (
                <div className="fact-grid">
                  <div className="fact">
                    <small>Policy Number</small>
                    <b>{d.policy.policy_number}</b>
                  </div>
                  <div className="fact">
                    <small>Total Coverage</small>
                    <b>{money(d.policy.coverage_amount)}</b>
                  </div>
                  <div className="fact">
                    <small>Standard Deductible</small>
                    <b>{money(d.policy.deductible)}</b>
                  </div>
                  <div className="fact">
                    <small>Term Validity</small>
                    <b>
                      {date(d.policy.effective_date)} – {date(d.policy.expiry_date)}
                    </b>
                  </div>
                </div>
              ) : (
                <Empty text="No linked policy record identified." />
              )}
            </div>

            <div style={{ marginTop: 20 }}>
              <div className="card-title" style={{ fontSize: 13, marginBottom: 10 }}>Extracted claimant facts</div>
              {Object.keys(facts).length ? (
                <div className="fact-grid">
                  {Object.entries(facts).slice(0, 16).map(([k, v]) => (
                    <div className="fact" key={k}>
                      <small>{human(k)}</small>
                      <b>{typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}</b>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty text="No structured facts extracted yet." />
              )}
            </div>
          </Card>

          {/* Evidence Attachments */}
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div className="card-title" style={{ margin: 0 }}>Evidence attachments</div>
              <Badge tone="info">{evidence.length} files</Badge>
            </div>
            {evidence.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Verification</th>
                      <th>Type</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.map((x: any, i: number) => (
                      <tr key={x.id || i}>
                        <td>
                          <b>{x.original_filename || x.filename || "Evidence " + (i + 1)}</b>
                        </td>
                        <td>
                          <DataBadge status={x.verification_status || x.status || "review"} />
                        </td>
                        <td>{x.content_type || x.requested_evidence_type || "Document"}</td>
                        <td style={{ textAlign: "right" }}>
                          {x.id && (
                            <button className="btn" onClick={() => evidenceUrl(String(x.id))}>
                              <ExternalLink size={12} />
                              <span>View</span>
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty text="No evidence attachments uploaded yet." />
            )}
          </Card>
        </div>

        {/* Right Column: AI Copilot Decision Report & Actions */}
        <div style={{ display: "grid", gap: 20 }}>
          <Card className="copilot-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Sparkles size={16} color="var(--blue)" />
                <div className="card-title" style={{ margin: 0 }}>AI Copilot Intelligence</div>
              </div>
              <button className="btn" onClick={load}>
                <span>Refresh</span>
              </button>
            </div>

            {a ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
                  <DataBadge status={a.decision_recommendation || "review"} />
                  <span className="score">{Math.round(conf)}%</span>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>confidence score</span>
                </div>

                <div style={{ display: "grid", gap: 12, marginBottom: 16 }}>
                  <div>
                    <b style={{ fontSize: 13, color: "var(--ink)" }}>Executive Summary</b>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--ink-secondary)", lineHeight: 1.6 }}>
                      {a.executive_summary || "—"}
                    </p>
                  </div>
                  <div>
                    <b style={{ fontSize: 13, color: "var(--ink)" }}>Decision Rationale</b>
                    <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--ink-secondary)", lineHeight: 1.6 }}>
                      {a.decision_rationale || "—"}
                    </p>
                  </div>
                </div>

                <div className="grid grid-2" style={{ marginBottom: 16 }}>
                  <div>
                    <b style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase" }}>Coverage Observations</b>
                    {(a.coverage_observations || []).slice(0, 4).map((x: string, i: number) => (
                      <div className="list-row" key={i} style={{ padding: "8px 0" }}>
                        <span style={{ fontSize: 12.5 }}>{x}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <b style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase" }}>Risk Flags</b>
                    {(a.risk_flags || []).slice(0, 4).map((x: string, i: number) => (
                      <div className="list-row" key={i} style={{ padding: "8px 0" }}>
                        <span style={{ fontSize: 12.5, color: "var(--danger)" }}>⚠ {x}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <b style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase" }}>Recommended Next Steps</b>
                  {(a.recommended_next_steps || []).slice(0, 5).map((x: string, i: number) => (
                    <div className="list-row" key={i} style={{ padding: "8px 0" }}>
                      <span style={{ fontSize: 12.5 }}>
                        {i + 1}. {x}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <Empty text={cop?.error || "Copilot intelligence is computing recommendations…"} />
            )}
          </Card>

          {/* Decision & Adjudication Controls */}
          <Card>
            <div className="card-title">Adjudication decision</div>
            <div className="form-grid">
              <label>
                Decision
                <select value={decision} onChange={(e) => setDecision(e.target.value)}>
                  <option value="">Select decision</option>
                  <option value="approve">Approve claim</option>
                  <option value="partial_approve">Partial approve</option>
                  <option value="reject">Reject claim</option>
                  <option value="request_evidence">Request additional evidence</option>
                  <option value="escalate">Escalate to Senior Adjuster</option>
                </select>
              </label>

              <label>
                Priority
                <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
            </div>

            <label style={{ marginTop: 12 }}>
              Adjudication rationale
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Document your statutory coverage determination rationale for the audit trail…"
              />
            </label>

            <div className="actions" style={{ marginTop: 12 }}>
              <button
                className="btn primary"
                onClick={() =>
                  decision &&
                  act("/api/v1/adjuster/claims/" + ticket + "/decision", {
                    decision,
                    rationale: rationale || "Decision recorded after claim package review."
                  })
                }
                disabled={!decision}
              >
                Record decision
              </button>
              <button className="btn" onClick={() => act("/api/v1/adjuster/claims/" + ticket, { priority }, "PATCH")}>
                Save priority
              </button>
            </div>

            <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
              <label>
                Private work note (Internal only)
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Record an internal observation not visible to the claimant…"
                  style={{ minHeight: 70 }}
                />
              </label>
              <button
                className="btn"
                onClick={() =>
                  note &&
                  act("/api/v1/adjuster/claims/" + ticket + "/notes", { note, visibility: "internal" }).then(() =>
                    setNote("")
                  )
                }
                disabled={!note.trim()}
                style={{ marginTop: 10 }}
              >
                Add internal note
              </button>
            </div>
          </Card>
        </div>
      </div>

      {/* Information Requests & Interactive Copilot Chat */}
      <div className="grid grid-2" style={{ marginTop: 20 }}>
        {/* Request Evidence from Claimant */}
        <Card>
          <div className="card-title">Request information from claimant</div>
          <label>
            Describe document or clarification needed
            <textarea
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder="e.g., Please provide an itemized repair estimate and the front fender damage photo."
            />
          </label>
          <button
            className="btn primary"
            onClick={() => {
              if (request.trim()) {
                act("/api/v1/adjuster/claims/" + ticket + "/evidence-requests", { request_text: request }).then(() =>
                  setRequest("")
                );
              }
            }}
            disabled={!request.trim()}
            style={{ marginTop: 10 }}
          >
            <Send size={13} />
            <span>Send formal request</span>
          </button>

          <div style={{ marginTop: 16 }}>
            <div className="card-kicker" style={{ marginBottom: 8 }}>Outstanding & answered requests</div>
            {requests.map((r: any) => (
              <div className="list-row" key={r.id}>
                <div className="list-main">
                  <b>{r.request_text}</b>
                  <span>
                    {human(r.status)}
                    {r.responded_at ? ` · Responded ${dt(r.responded_at)}` : ""}
                  </span>
                  {r.response_note && (
                    <span style={{ whiteSpace: "normal", color: "var(--ink)", marginTop: 2 }}>
                      Claimant: {r.response_note}
                    </span>
                  )}
                </div>
                <DataBadge status={r.status || "open"} />
              </div>
            ))}
          </div>
        </Card>

        {/* Copilot Chat Assistant */}
        <Card className="copilot-card">
          <div className="card-title">Copilot policy query</div>
          <div style={{ maxHeight: 300, overflowY: "auto", display: "grid", gap: 10, paddingRight: 4 }}>
            {chatRows.length ? (
              chatRows.map((m: any, i: number) => (
                <div key={i} className={"chat-turn " + ((m.speaker || m.role) === "adjuster" ? "user" : "assistant")}>
                  <div className="chat-avatar">{m.speaker === "adjuster" ? "Adj" : "AI"}</div>
                  <div className="chat-message-content">
                    {m.speaker === "adjuster" ? (
                      <div className="chat-bubble-user">{m.message || m.text}</div>
                    ) : (
                      <div className="chat-response-ai">
                        <MarkdownRenderer content={m.message || m.content || m.text} />
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <Empty text="Ask questions about clause limits, deductible exceptions, or risk flags." />
            )}
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <input
              value={chat}
              onChange={(e) => setChat(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  ask();
                }
              }}
              placeholder="Ask Copilot about this policy or claim…"
            />
            <button className="btn primary" onClick={ask} disabled={!chat.trim()}>
              <Send size={14} />
            </button>
          </div>
        </Card>
      </div>

      {/* Audit Trail */}
      <Card style={{ marginTop: 20 }}>
        <div className="card-title">Tamper-evident audit trail</div>
        {audit.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Timestamp</th>
                  <th>Reason / Details</th>
                </tr>
              </thead>
              <tbody>
                {audit.slice(0, 10).map((x: any, i: number) => (
                  <tr key={x.id || i}>
                    <td>
                      <b>{x.event_type || x.action || "Event"}</b>
                    </td>
                    <td>{dt(x.created_at)}</td>
                    <td>{x.reason || x.resource_type || "Recorded in tenant ledger"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="No audit records for this claim." />
        )}
      </Card>
    </Page>
  );
}

export { AdjusterDashboard, AdjusterQueue, Workbench };
