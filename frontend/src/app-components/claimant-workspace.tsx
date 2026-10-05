"use client";
import Link from "next/link";
import React, { useEffect, useState, type FormEvent } from "react";
import { 
  AlertCircle, 
  CheckCircle2, 
  ChevronRight, 
  Clock3, 
  FileText, 
  MessageSquare, 
  Paperclip, 
  Plus, 
  Send, 
  ShieldCheck, 
  Trash2, 
  Upload 
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, DataBadge, Empty, Page } from "@/app-components/ui";

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
   Policies Directory & Claimant Policies View
   ========================================================================== */

function Policies({ user }: { user?: { role?: string; email?: string } }) {
  const isStaff = user?.role === "ADJUSTER" || user?.role === "ADMIN";
  const [x, setX] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [policyType, setPolicyType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  async function loadData() {
    setLoading(true);
    try {
      if (isStaff) {
        let url = "/api/v1/policies?page_size=100";
        if (search.trim()) url += "&q=" + encodeURIComponent(search.trim());
        if (policyType !== "all") url += "&policy_type=" + encodeURIComponent(policyType);
        if (statusFilter !== "all") url += "&is_active=" + (statusFilter === "active");
        const res = await api<any>(url);
        setX(res.items || []);
      } else {
        const res = await api<any>("/api/v1/policies/my-policies");
        setX(Array.isArray(res) ? res : res.items || []);
      }
    } catch {
      setX([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [isStaff, policyType, statusFilter]);

  if (isStaff) {
    return (
      <Page
        title="Policy Verification Directory"
        subtitle="Complete verified policy inventory to audit policyholder names, numbers, coverage schedules, and validity."
      >
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ flex: "1 1 240px", minWidth: 200 }}>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadData()}
                placeholder="Search by policy number or policyholder name…"
                aria-label="Search policies"
              />
            </div>
            <select
              value={policyType}
              onChange={(e) => setPolicyType(e.target.value)}
              aria-label="Filter by policy type"
              style={{ width: "auto", minWidth: 140 }}
            >
              <option value="all">All Types</option>
              <option value="motor">Motor</option>
              <option value="health">Health</option>
              <option value="senior_health">Senior Health</option>
              <option value="home">Home</option>
              <option value="travel">Travel</option>
              <option value="cyber">Cyber</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Filter by status"
              style={{ width: "auto", minWidth: 130 }}
            >
              <option value="all">All Statuses</option>
              <option value="active">Active In-Force</option>
              <option value="inactive">Expired / Inactive</option>
            </select>
            <button className="btn primary" onClick={() => loadData()}>
              <span>Search</span>
            </button>
          </div>
        </Card>

        <Card>
          {loading ? (
            <div className="chat-skeleton" style={{ width: "100%", margin: "16px 0" }}>
              <div className="skeleton-shimmer" style={{ width: "50%" }} />
              <div className="skeleton-shimmer" style={{ width: "80%" }} />
            </div>
          ) : x.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Policy Number</th>
                    <th>Policyholder Name</th>
                    <th>Contact & DOB</th>
                    <th>Type</th>
                    <th>Coverage / Deductible</th>
                    <th>Insured Date</th>
                    <th>Validity Date</th>
                    <th>Status</th>
                    <th>Claimant Link</th>
                  </tr>
                </thead>
                <tbody>
                  {x.map((p) => (
                    <tr key={p.id || p.policy_number}>
                      <td>
                        <b style={{ fontFamily: "ui-monospace, monospace" }}>{p.policy_number}</b>
                      </td>
                      <td>
                        <b>{p.policyholder_name || "—"}</b>
                      </td>
                      <td style={{ fontSize: 12 }}>
                        <div>{p.policyholder_phone || "—"}</div>
                        {p.policyholder_dob && <div style={{ color: "var(--muted)" }}>DOB: {p.policyholder_dob}</div>}
                        {p.policyholder_email && <div style={{ color: "var(--muted)" }}>{p.policyholder_email}</div>}
                      </td>
                      <td>{human(p.policy_type || "General")}</td>
                      <td>
                        <b>{money(p.coverage_amount)}</b>
                        <div style={{ fontSize: 11, color: "var(--muted)" }}>Ded: {money(p.deductible)}</div>
                      </td>
                      <td>{date(p.effective_date)}</td>
                      <td>{date(p.expiry_date)}</td>
                      <td>
                        <Badge tone={p.is_active ? "success" : "neutral"}>
                          {p.is_active ? "Active" : "Expired / Inactive"}
                        </Badge>
                      </td>
                      <td>
                        <Badge tone={p.linked ? "info" : "neutral"}>
                          {p.linked ? "Linked" : "Unlinked"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              text="No policies match the selected filters."
              icon={<ShieldCheck size={32} />}
            />
          )}
        </Card>
      </Page>
    );
  }

  return (
    <Page
      title="Policies"
      subtitle="Insurance policies currently linked to your verified account."
      actions={
        <Link className="btn primary" href="/policies/link">
          <Plus size={14} />
          <span>Link policy</span>
        </Link>
      }
    >
      <Card>
        {loading ? (
          <div className="chat-skeleton" style={{ width: "100%", margin: "16px 0" }}>
            <div className="skeleton-shimmer" style={{ width: "50%" }} />
            <div className="skeleton-shimmer" style={{ width: "80%" }} />
          </div>
        ) : x.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Policy Number</th>
                  <th>Coverage Type</th>
                  <th>Status</th>
                  <th>Effective Date</th>
                  <th>Expiry Date</th>
                </tr>
              </thead>
              <tbody>
                {x.map((p) => (
                  <tr key={p.id || p.policy_number}>
                    <td>
                      <b style={{ fontFamily: "ui-monospace, monospace" }}>{p.policy_number}</b>
                    </td>
                    <td>{human(p.insurance_type || p.policy_type || "General")}</td>
                    <td>
                      <Badge tone={p.is_active === false ? "neutral" : "success"}>
                        {p.is_active === false ? "Inactive" : "Active"}
                      </Badge>
                    </td>
                    <td>{date(p.effective_date)}</td>
                    <td>{date(p.expiry_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            text="No insurance policies linked yet. Link your policy number to enable automatic claim verification."
            icon={<ShieldCheck size={32} />}
            action={
              <Link className="btn primary" href="/policies/link">
                <Plus size={14} />
                <span>Link your first policy</span>
              </Link>
            }
          />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Link Policy Form
   ========================================================================== */

function LinkPolicy() {
  const [f, setF] = useState({ policy_number: "", policyholder_name: "", date_of_birth: "", phone_last4: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await api("/api/v1/policies/link", {
        method: "POST",
        body: JSON.stringify({ ...f, policyholder_name: f.policyholder_name || undefined })
      });
      setMsg("Policy verified and linked successfully to your account!");
    } catch (e: any) {
      setError(e.message || "Policy verification failed. Ensure the birth date and phone digits match your records.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page
      title="Link a policy"
      subtitle="Verify policyholder identity using statutory KYC verification parameters."
      actions={
        <Link className="btn" href="/policies">
          <span>Back to policies</span>
        </Link>
      }
    >
      <Card style={{ maxWidth: 640 }}>
        <form className="form" onSubmit={submit}>
          <div className="form-grid">
            <label>
              Policy number
              <input
                value={f.policy_number}
                onChange={(e) => setF({ ...f, policy_number: e.target.value })}
                placeholder="e.g. POL-MOT-2026-904"
                required
              />
            </label>

            <label>
              Policyholder full name (optional)
              <input
                value={f.policyholder_name}
                onChange={(e) => setF({ ...f, policyholder_name: e.target.value })}
                placeholder="As printed on certificate"
              />
            </label>

            <label>
              Date of birth
              <input
                type="date"
                value={f.date_of_birth}
                onChange={(e) => setF({ ...f, date_of_birth: e.target.value })}
                required
              />
            </label>

            <label>
              Last 4 digits of phone
              <input
                maxLength={4}
                value={f.phone_last4}
                onChange={(e) => setF({ ...f, phone_last4: e.target.value })}
                placeholder="e.g. 4821"
                required
              />
            </label>
          </div>

          {error && (
            <div className="error" role="alert">
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          {msg && (
            <div className="notice" role="status">
              <CheckCircle2 size={15} />
              <span>{msg}</span>
            </div>
          )}

          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Verifying policy ownership…" : "Verify and link policy"}
            </button>
          </div>
        </form>
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Claims Overview List
   ========================================================================== */

function Claims() {
  const [x, setX] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<any>("/api/v1/claims")
      .then((v) => setX(Array.isArray(v) ? v : v.items || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Page
      title="Claims"
      subtitle="Filed, pending, and resolved insurance claims associated with your account."
      actions={
        <Link className="btn" href="/track">
          <Clock3 size={14} />
          <span>Track claim workflows</span>
        </Link>
      }
    >
      <Card>
        {loading ? (
          <div className="chat-skeleton" style={{ width: "100%", margin: "16px 0" }}>
            <div className="skeleton-shimmer" style={{ width: "60%" }} />
            <div className="skeleton-shimmer" style={{ width: "90%" }} />
          </div>
        ) : x.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Claim Ticket</th>
                  <th>Status</th>
                  <th>Incident Date</th>
                  <th>Last Update</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {x.map((c) => (
                  <tr key={c.ticket_id}>
                    <td>
                      <b style={{ fontFamily: "ui-monospace, monospace" }}>{c.ticket_id}</b>
                    </td>
                    <td>
                      <DataBadge status={c.status} />
                    </td>
                    <td>{date(c.incident_date || c.event_date)}</td>
                    <td>{dt(c.updated_at)}</td>
                    <td style={{ textAlign: "right" }}>
                      <Link className="link" href={"/claims/" + c.ticket_id}>
                        <span>Open details</span>
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
            text="No claims have been initiated yet."
            icon={<FileText size={32} />}
            action={
              <Link className="btn primary" href="/chat">
                <Plus size={14} />
                <span>File a new claim in chat</span>
              </Link>
            }
          />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Track Claims Workflow
   ========================================================================== */

function Track() {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/v1/claims/track")
      .then(setD)
      .catch((e) => setError(e.message));
  }, []);

  async function discard(t: string) {
    if (!confirm("Are you sure you want to discard this draft claim session?")) return;
    try {
      await api("/api/v1/claims/" + t, { method: "DELETE" });
      setD((v: any) => ({ ...v, items: (v.items || []).filter((x: any) => x.ticket_id !== t) }));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <Page
      title="Track claims"
      subtitle="Monitor real-time adjudication status, active evidence requests, and adjuster updates."
      actions={
        <Link className="btn primary" href="/chat">
          <Plus size={14} />
          <span>New claim</span>
        </Link>
      }
    >
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <Card>
        {d?.items?.length ? (
          d.items.map((c: any) => (
            <div className="list-row" key={c.ticket_id}>
              <div className="list-main">
                <b style={{ fontFamily: "ui-monospace, monospace" }}>{c.ticket_id}</b>
                <span>
                  {c.open_request_count || 0} open evidence request(s) · Updated {dt(c.updated_at)}
                </span>
              </div>
              <div className="actions">
                <DataBadge status={c.status} />
                <Link className="btn" href={"/claims/" + c.ticket_id}>
                  <span>Details</span>
                  <ChevronRight size={13} />
                </Link>
                {!["submitted", "closed", "rejected"].includes(c.status) && (
                  <Button className="danger" onClick={() => discard(c.ticket_id)} title="Discard draft">
                    <Trash2 size={13} />
                    <span>Discard</span>
                  </Button>
                )}
              </div>
            </div>
          ))
        ) : (
          <Empty text="No tracked claims currently in progress." />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Claim Detail View
   ========================================================================== */

function ClaimDetail({ ticket }: { ticket: string }) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/v1/claims/" + ticket)
      .then(setD)
      .catch((e) => setError(e.message));
  }, [ticket]);

  if (!d) {
    return (
      <Page title={ticket} subtitle="Retrieving claim package details…">
        <Card>
          <div className="chat-skeleton" style={{ width: "100%", margin: "20px 0" }}>
            <div className="skeleton-shimmer" style={{ width: "40%" }} />
            <div className="skeleton-shimmer" style={{ width: "70%" }} />
          </div>
        </Card>
      </Page>
    );
  }

  const c = d.claim || d;
  const p = d.pipeline_state || {};
  const req = p.evidence_requests || d.evidence_requests || [];
  const facts = d.extracted_data || p.extracted_data || {};

  return (
    <Page
      title={ticket}
      subtitle="Claim lifecycle status, structured incident data, and adjuster requests."
      actions={
        <Link className="btn primary" href={"/claims/" + ticket + "/evidence"}>
          <Upload size={14} />
          <span>Upload evidence</span>
        </Link>
      }
    >
      <div className="detail-grid">
        <div className="detail-item">
          <span>Current Status</span>
          <b>
            <DataBadge status={c.status || "unknown"} />
          </b>
        </div>
        <div className="detail-item">
          <span>Insurance Type</span>
          <b>{human(c.insurance_type)}</b>
        </div>
        <div className="detail-item">
          <span>Incident Date</span>
          <b>{date(c.incident_date || c.event_date)}</b>
        </div>
      </div>

      {error && (
        <div className="error" style={{ margin: "16px 0" }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-2" style={{ marginTop: 20 }}>
        <Card>
          <div className="card-title">Captured claim facts</div>
          <div className="fact-grid">
            {Object.entries(facts).slice(0, 18).map(([k, v]) => (
              <div className="fact" key={k}>
                <small>{human(k)}</small>
                <b>{typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}</b>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="card-title">Adjuster documentation requests</div>
          {req.length ? (
            req.map((r: any) => (
              <div className="list-row" key={r.id || r.request_id}>
                <div className="list-main">
                  <b>{r.request_text || r.description || "Information requested"}</b>
                  <span>
                    {human(r.status || "open")} {r.due_at ? `· Due ${date(r.due_at)}` : ""}
                  </span>
                </div>
                <Link className="btn primary" href={"/claims/" + ticket + "/messages"}>
                  <span>Respond</span>
                </Link>
              </div>
            ))
          ) : (
            <Empty text="No outstanding requests from the adjuster." icon={<CheckCircle2 size={24} />} />
          )}
        </Card>
      </div>

      <Card style={{ marginTop: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div className="card-title" style={{ margin: 0 }}>Intake conversation turns</div>
          <Link className="link" href={"/claims/" + ticket + "/messages"}>
            <span>View requests & messages</span>
            <ChevronRight size={13} />
          </Link>
        </div>

        {d.conversation?.length ? (
          <div className="timeline">
            {d.conversation.slice(-10).map((m: any, i: number) => (
              <div className="timeline-item" key={i}>
                <span className="timeline-dot" />
                <div className="timeline-card">
                  <small style={{ fontWeight: 600, color: "var(--ink-secondary)" }}>
                    {m.speaker.toUpperCase()} · {dt(m.timestamp)}
                  </small>
                  <p>{m.text || m.message}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty text="No conversation turns recorded." />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Evidence Upload View
   ========================================================================== */

function Evidence({ ticket }: { ticket: string }) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<Record<string, File | null>>({});

  useEffect(() => {
    api("/api/v1/claims/" + ticket)
      .then(setD)
      .catch((e) => setError(e.message));
  }, [ticket]);

  const req = (d?.pipeline_state?.evidence_requests || d?.evidence_requests || []).filter(
    (x: any) => x.status === "open"
  );

  async function send(r: any) {
    const fd = new FormData();
    if (note.trim()) fd.append("response_note", note);
    const file = files[String(r.id || r.request_id)];
    if (file) fd.append("file", file);
    try {
      await api("/api/v1/claims/" + ticket + "/requests/" + (r.id || r.request_id) + "/respond", {
        method: "POST",
        body: fd
      });
      setNote("");
      setD(await api("/api/v1/claims/" + ticket));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <Page
      title="Claim evidence"
      subtitle="Respond with verified attachments to evidence requests submitted by your assigned adjuster."
      actions={
        <Link className="btn" href={"/claims/" + ticket}>
          <span>Claim overview</span>
        </Link>
      }
    >
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <Card>
        {req.length ? (
          req.map((r: any) => (
            <div key={r.id || r.request_id} style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div className="list-main">
                  <b>{r.request_text || r.description || "Information requested"}</b>
                  <span>{r.due_at ? `Due ${date(r.due_at)}` : "No strict deadline"}</span>
                </div>
                <Badge tone="warning">Pending Your Submission</Badge>
              </div>

              <label>
                Response clarification note
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Provide any context or notes for the adjuster…"
                />
              </label>

              <div className="actions" style={{ marginTop: 12 }}>
                <label className="btn">
                  <Paperclip size={14} />
                  <span>{files[String(r.id || r.request_id)]?.name || "Choose file to attach"}</span>
                  <input
                    type="file"
                    hidden
                    onChange={(e) =>
                      setFiles({ ...files, [String(r.id || r.request_id)]: e.target.files?.[0] || null })
                    }
                  />
                </label>

                <button
                  className="btn primary"
                  onClick={() => send(r)}
                  disabled={!note.trim() && !files[String(r.id || r.request_id)]}
                >
                  <Send size={14} />
                  <span>Submit response</span>
                </button>
              </div>
            </div>
          ))
        ) : (
          <Empty
            text="All requested evidence items have been received. No open requests pending."
            icon={<CheckCircle2 size={32} />}
          />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Messages & Requests View
   ========================================================================== */

function Messages({ ticket }: { ticket: string }) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, File | null>>({});

  useEffect(() => {
    api("/api/v1/claims/" + ticket)
      .then(setD)
      .catch((e) => setError(e.message));
  }, [ticket]);

  const req = d?.pipeline_state?.evidence_requests || d?.evidence_requests || [];

  async function respond(r: any) {
    const key = String(r.id || r.request_id);
    const fd = new FormData();
    const n = notes[key] || "";
    const f = files[key];
    if (n.trim()) fd.append("response_note", n);
    if (f) fd.append("file", f);
    try {
      await api("/api/v1/claims/" + ticket + "/requests/" + key + "/respond", { method: "POST", body: fd });
      setD(await api("/api/v1/claims/" + ticket));
      setNotes({ ...notes, [key]: "" });
      setFiles({ ...files, [key]: null });
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <Page
      title="Adjuster requests & messages"
      subtitle="Direct communications and clarification exchanges with the assigned claims officer."
      actions={
        <Link className="btn" href={"/claims/" + ticket}>
          <span>Claim overview</span>
        </Link>
      }
    >
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <Card>
        {req.length ? (
          req.map((r: any) => {
            const k = String(r.id || r.request_id);
            return (
              <div key={k} style={{ padding: "16px 0", borderBottom: "1px solid var(--line)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <div className="list-main">
                    <b style={{ fontSize: 14 }}>{r.request_text || r.description || "Clarification requested"}</b>
                    <span>
                      {human(r.status || "open")}
                      {r.responded_at ? ` · Answered ${dt(r.responded_at)}` : ""}
                    </span>
                  </div>
                  <DataBadge status={r.status || "open"} />
                </div>

                {r.status === "open" && (
                  <div style={{ marginTop: 10 }}>
                    <textarea
                      value={notes[k] || ""}
                      onChange={(e) => setNotes({ ...notes, [k]: e.target.value })}
                      placeholder="Type your explanation or response to the adjuster…"
                    />
                    <div className="actions" style={{ marginTop: 10 }}>
                      <label className="btn">
                        <Paperclip size={14} />
                        <span>{files[k]?.name || "Attach document"}</span>
                        <input
                          type="file"
                          hidden
                          onChange={(e) => setFiles({ ...files, [k]: e.target.files?.[0] || null })}
                        />
                      </label>
                      <button
                        className="btn primary"
                        onClick={() => respond(r)}
                        disabled={!notes[k]?.trim() && !files[k]}
                      >
                        <Send size={14} />
                        <span>Send to adjuster</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <Empty text="No adjuster requests recorded for this claim." icon={<MessageSquare size={28} />} />
        )}
      </Card>
    </Page>
  );
}

export { Policies, LinkPolicy, Claims, Track, ClaimDetail, Evidence, Messages };
