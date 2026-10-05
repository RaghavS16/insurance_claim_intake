"use client";
import Link from "next/link";
import React, { useEffect, useState } from "react";
import { 
  AlertCircle, 
  Check, 
  CheckCircle2, 
  ClipboardList, 
  Copy, 
  Download, 
  FileSpreadsheet, 
  Pencil, 
  Plus, 
  ShieldCheck, 
  Trash2, 
  Upload, 
  UserPlus, 
  UserRound, 
  Users, 
  X 
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, DataBadge, Empty, Metric, Page } from "@/app-components/ui";

const dt = (v: any) => (v ? new Date(v).toLocaleString() : "—");
const money = (v: any) =>
  v == null || v === ""
    ? "—"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
        Number(v) || 0
      );
const human = (v: any) => String(v ?? "—").replaceAll("_", " ");

/* ==========================================================================
   Admin Overview Dashboard
   ========================================================================== */

function AdminDashboard() {
  const [a, setA] = useState<any[]>([]);
  const [p, setP] = useState<any[]>([]);
  const [c, setC] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<any>("/api/v1/admin/adjusters"),
      api<any>("/api/v1/admin/policies"),
      api<any>("/api/v1/admin/claims")
    ])
      .then(([x, y, z]) => {
        setA(x.items || x);
        setP(y.items || y);
        setC(z.items || z);
      })
      .catch((e) => setError(e.message));
  }, []);

  const statusCounts = c.reduce((m, x) => {
    m[x.status] = (m[x.status] || 0) + 1;
    return m;
  }, {} as Record<string, number>);

  return (
    <Page
      title="Administration"
      subtitle="Policy inventory management, adjuster team onboarding, and statutory tenant oversight."
      actions={
        <Link className="btn primary" href="/admin">
          <Users size={14} />
          <span>Operational settings</span>
        </Link>
      }
    >
      {error && (
        <div className="error" role="alert" style={{ marginBottom: 16 }}>
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      )}

      <div className="metrics">
        <Metric
          label="Policies"
          value={p.length}
          note="Active inventory"
          icon={<ShieldCheck size={16} />}
        />
        <Metric
          label="Adjusters"
          value={a.length}
          note={`Active: ${a.filter((x) => x.is_active !== false).length}`}
          icon={<Users size={16} />}
        />
        <Metric
          label="Filed claims"
          value={c.filter((x) => x.status !== "draft").length}
          note="Total pipeline volume"
          icon={<ClipboardList size={16} />}
        />
        <Metric
          label="Unassigned"
          value={c.filter((x) => !x.assigned_adjuster_id && x.status !== "draft").length}
          note="Requires operational routing"
          trend={c.filter((x) => !x.assigned_adjuster_id && x.status !== "draft").length > 0 ? "warning" : "success"}
          icon={<UserRound size={16} />}
        />
      </div>

      <div className="grid grid-2">
        <Card>
          <div className="card-title">Claims by adjudication stage</div>
          {Object.keys(statusCounts).length ? (
            Object.entries(statusCounts)
              .sort(([, a], [, b]) => (b as number) - (a as number))
              .map(([k, v]) => (
                <div className="list-row" key={k}>
                  <div className="list-main">
                    <b>{human(k)}</b>
                    <span>Current active claims</span>
                  </div>
                  <b style={{ fontSize: 16 }}>{String(v)}</b>
                </div>
              ))
          ) : (
            <Empty text="No claims recorded in the tenant system." />
          )}
        </Card>

        <Card>
          <div className="card-title">Adjuster team workload</div>
          {a.length ? (
            a.map((x) => (
              <div className="list-row" key={x.id}>
                <div className="list-main">
                  <b>{x.name}</b>
                  <span>
                    {human(x.specialization)} · {x.is_active === false ? "Inactive" : "Active"}
                  </span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <b style={{ fontSize: 15 }}>{x.claims_assigned || 0}</b>
                  <span style={{ fontSize: 11, color: "var(--muted)", display: "block" }}>assigned</span>
                </div>
              </div>
            ))
          ) : (
            <Empty text="No adjusters onboarded yet." />
          )}
        </Card>
      </div>
    </Page>
  );
}

/* ==========================================================================
   Admin Operations (Adjuster Invites, Policies, Bulk Imports)
   ========================================================================== */

function Admin() {
  const [a, setA] = useState<any[]>([]);
  const [p, setP] = useState<any[]>([]);
  const [invites, setInvites] = useState<any[]>([]);
  const [mode, setMode] = useState<"adjuster" | "policy" | null>(null);
  const [adjusterFilter, setAdjusterFilter] = useState("all");
  const [adjusterSpecFilter, setAdjusterSpecFilter] = useState("all");
  const [policyTypeFilter, setPolicyTypeFilter] = useState("all");
  const [policyStatusFilter, setPolicyStatusFilter] = useState("all");
  const [edit, setEdit] = useState<any>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [importErrors, setImportErrors] = useState<any[]>([]);
  const [copiedLink, setCopiedLink] = useState(false);

  const [form, setForm] = useState<any>({
    name: "",
    email: "",
    phone: "",
    specialization: "motor",
    policy_number: "",
    policy_type: "motor",
    coverage_amount: "",
    deductible: "0",
    effective_date: "",
    expiry_date: "",
    policyholder_name: "",
    policyholder_dob: "",
    policyholder_phone: "",
    policyholder_email: ""
  });

  async function load() {
    const [x, y, z] = await Promise.all([
      api<any>("/api/v1/admin/adjusters"),
      api<any>("/api/v1/admin/policies"),
      api<any>("/api/v1/admin/adjusters/invitations")
    ]);
    setA(x.items || x);
    setP(y.items || y);
    setInvites(z.items || []);
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  function open(m: "adjuster" | "policy", x?: any) {
    setMode(m);
    setEdit(x || null);
    setNotice("");
    setError("");
    setInviteUrl("");
    setForm(
      x
        ? {
            ...form,
            ...x,
            policyholder_name: x.policyholder_name || "",
            policyholder_dob: x.policyholder_dob || "",
            policyholder_phone: x.policyholder_phone || "",
            policyholder_email: x.policyholder_email || ""
          }
        : {
            name: "",
            email: "",
            phone: "",
            specialization: "motor",
            policy_number: "",
            policy_type: "motor",
            coverage_amount: "",
            deductible: "0",
            effective_date: "",
            expiry_date: "",
            policyholder_name: "",
            policyholder_dob: "",
            policyholder_phone: "",
            policyholder_email: ""
          }
    );
  }

  async function invite() {
    setNotice("");
    setError("");
    try {
      const r = await api<any>("/api/v1/admin/adjusters/invite", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          email: form.email,
          phone: form.phone,
          specialization: form.specialization
        })
      });
      setInviteUrl(r.invitation_url || "");
      setNotice("Invitation queued for delivery. You can copy the onboarding link below.");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function resendInvitation(id: string) {
    setNotice("");
    setError("");
    try {
      const r = await api<any>("/api/v1/admin/adjusters/invitations/" + encodeURIComponent(id) + "/resend", {
        method: "POST"
      });
      setInviteUrl(r.invitation_url || "");
      setNotice("A fresh invitation was queued for delivery.");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function savePolicy() {
    setNotice("");
    setError("");
    try {
      if (edit) {
        await api("/api/v1/admin/policies/" + edit.id, {
          method: "PUT",
          body: JSON.stringify({
            policy_type: form.policy_type,
            coverage_amount: Number(form.coverage_amount),
            deductible: Number(form.deductible),
            effective_date: form.effective_date,
            expiry_date: form.expiry_date,
            policyholder_name: form.policyholder_name,
            policyholder_dob: form.policyholder_dob,
            policyholder_phone: form.policyholder_phone,
            policyholder_email: form.policyholder_email
          })
        });
      } else {
        await api("/api/v1/admin/policies/strict", {
          method: "POST",
          body: JSON.stringify({
            policy_number: form.policy_number,
            policy_type: form.policy_type,
            coverage_amount: Number(form.coverage_amount),
            deductible: Number(form.deductible),
            effective_date: form.effective_date,
            expiry_date: form.expiry_date,
            policyholder_name: form.policyholder_name,
            policyholder_dob: form.policyholder_dob,
            policyholder_phone: form.policyholder_phone,
            policyholder_email: form.policyholder_email || undefined
          })
        });
      }
      setNotice("Policy successfully saved.");
      setMode(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function importPolicies(e: any) {
    const f = e.target.files?.[0];
    if (!f) return;
    setNotice("");
    setError("");
    setImportErrors([]);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api<any>("/api/v1/admin/policies/import-strict", {
        method: "POST",
        body: fd
      });
      setNotice("Import processed: " + (r.total_processed ?? 0) + " policies.");
      setImportErrors(r.errors || []);
      await load();
    } catch (x: any) {
      setError(x.message);
    } finally {
      e.target.value = "";
    }
  }

  async function downloadFile(path: string, filename: string) {
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch((process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + path, {
        headers: token ? { Authorization: "Bearer " + token } : {}
      });
      if (!res.ok) throw Error("Download failed (" + res.status + ")");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function toggle(id: string, active: boolean) {
    try {
      await api("/api/v1/admin/adjusters/" + id, {
        method: "PUT",
        body: JSON.stringify({ is_active: active })
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function delPolicy(id: string) {
    if (!confirm("Are you sure you want to permanently delete this policy?")) return;
    try {
      await api("/api/v1/admin/policies/" + encodeURIComponent(id), { method: "DELETE" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function copyInviteLink() {
    if (!inviteUrl) return;
    navigator.clipboard.writeText(inviteUrl);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  }

  const filteredAdjusters = a.filter((x) => {
    if (adjusterFilter === "active" && x.is_active === false) return false;
    if (adjusterFilter === "inactive" && x.is_active !== false) return false;
    if (adjusterSpecFilter !== "all" && x.specialization !== adjusterSpecFilter) return false;
    return true;
  });

  const filteredPolicies = p.filter((x) => {
    if (policyTypeFilter !== "all" && x.policy_type !== policyTypeFilter) return false;
    if (policyStatusFilter === "active" && x.is_active === false) return false;
    if (policyStatusFilter === "inactive" && x.is_active !== false) return false;
    return true;
  });

  return (
    <Page
      title="Administration"
      subtitle="Manage team invitations, policy records, and bulk validation imports."
    >
      {(notice || error) && (
        <div className={error ? "error" : "notice"} role={error ? "alert" : "status"} style={{ marginBottom: 16 }}>
          {error ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
          <span>{error || notice}</span>
        </div>
      )}

      {inviteUrl && (
        <Card style={{ marginBottom: 20, borderColor: "var(--blue)" }}>
          <div className="card-title">Adjuster onboarding link generated</div>
          <div style={{ display: "flex", gap: 10 }}>
            <input value={inviteUrl} readOnly style={{ fontFamily: "ui-monospace, monospace", fontSize: 13 }} />
            <button className="btn primary" onClick={copyInviteLink}>
              {copiedLink ? <Check size={14} /> : <Copy size={14} />}
              <span>{copiedLink ? "Copied" : "Copy"}</span>
            </button>
          </div>
          <div className="card-kicker" style={{ marginTop: 8 }}>
            This secure token activates the privileged account and enforces FIDO2 passkey registration.
          </div>
        </Card>
      )}

      {/* Control Actions Bar */}
      <div className="actions" style={{ marginBottom: 24 }}>
        <button className="btn primary" onClick={() => open("adjuster")}>
          <UserPlus size={14} />
          <span>Invite adjuster</span>
        </button>

        <button className="btn" onClick={() => open("policy")}>
          <Plus size={14} />
          <span>Add policy</span>
        </button>

        <label className="btn">
          <Upload size={14} />
          <span>Import CSV / XLSX</span>
          <input type="file" accept=".csv,.xlsx" hidden onChange={importPolicies} />
        </label>

        <button
          className="btn"
          onClick={() => downloadFile("/api/v1/admin/policies/template?format=csv", "policy-import-template.csv")}
        >
          <FileSpreadsheet size={14} />
          <span>Download template</span>
        </button>

        <button
          className="btn"
          onClick={() =>
            downloadFile(
              "/api/v1/admin/policies/export?format=csv" +
                (policyTypeFilter !== "all" ? "&policy_type=" + policyTypeFilter : "") +
                (policyStatusFilter !== "all" ? "&is_active=" + policyStatusFilter : ""),
              "policies-export.csv"
            )
          }
        >
          <Download size={14} />
          <span>Export policies</span>
        </button>

        <button
          className="btn"
          onClick={() =>
            downloadFile(
              "/api/v1/admin/adjusters/export?format=csv" +
                (adjusterFilter !== "all" ? "&status=" + adjusterFilter : "") +
                (adjusterSpecFilter !== "all" ? "&specialization=" + adjusterSpecFilter : ""),
              "adjusters-export.csv"
            )
          }
        >
          <Download size={14} />
          <span>Export adjusters</span>
        </button>
      </div>

      {/* Import Validation Errors Table */}
      {importErrors.length > 0 && (
        <Card style={{ marginBottom: 20, borderColor: "var(--danger-border)" }}>
          <div className="card-title" style={{ color: "var(--danger)" }}>
            Import validation errors ({importErrors.length})
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Policy Number</th>
                  <th>Validation Issue</th>
                </tr>
              </thead>
              <tbody>
                {importErrors.slice(0, 50).map((x: any, i: number) => (
                  <tr key={i}>
                    <td>Row {x.row}</td>
                    <td>
                      <b>{x.policy_number || "—"}</b>
                    </td>
                    <td>
                      <span className="error" style={{ padding: "4px 8px", display: "inline-block" }}>
                        {x.error}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Adjusters & Invitations Grid */}
      <div className="grid grid-2" style={{ marginBottom: 24 }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div className="card-title" style={{ margin: 0 }}>Adjuster roster</div>
              <Badge tone="info">{filteredAdjusters.length}</Badge>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select
                aria-label="Filter adjusters by status"
                value={adjusterFilter}
                onChange={(e) => setAdjusterFilter(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-subtle)" }}
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
              <select
                aria-label="Filter adjusters by specialization"
                value={adjusterSpecFilter}
                onChange={(e) => setAdjusterSpecFilter(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-subtle)" }}
              >
                <option value="all">All lines</option>
                {["motor", "health", "senior_health", "home", "travel", "cyber"].map((s) => (
                  <option key={s} value={s}>{human(s)}</option>
                ))}
              </select>
            </div>
          </div>
          {filteredAdjusters.length ? (
            filteredAdjusters.map((x) => (
              <div className="list-row" key={x.id}>
                <div className="list-main">
                  <b>{x.name}</b>
                  <span>
                    {x.email} · {human(x.specialization)} · {x.claims_assigned || 0} claims assigned
                  </span>
                </div>
                <div className="actions">
                  <DataBadge status={x.is_active === false ? "inactive" : "active"} />
                  <button className="btn" onClick={() => toggle(x.id, x.is_active === false)}>
                    {x.is_active === false ? "Activate" : "Deactivate"}
                  </button>
                </div>
              </div>
            ))
          ) : (
            <Empty text="No adjusters matching selected filters." />
          )}
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div className="card-title" style={{ margin: 0 }}>Pending invitations</div>
            <Badge tone="info">{invites.length}</Badge>
          </div>
          {invites.length ? (
            invites.slice(0, 8).map((x) => (
              <div className="list-row" key={x.id}>
                <div className="list-main">
                  <b>{x.name}</b>
                  <span>
                    {x.email} · {human(x.specialization)}
                  </span>
                  <span>Delivery: {human(x.email_delivery_status || "queued")}</span>
                </div>
                <div className="actions">
                  <DataBadge status={x.status} />
                  {x.status !== "accepted" && (
                    <button className="btn" onClick={() => resendInvitation(x.id)}>
                      Resend
                    </button>
                  )}
                </div>
              </div>
            ))
          ) : (
            <Empty text="No active invitations." />
          )}
        </Card>
      </div>

      {/* Policy Inventory Table */}
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div className="card-title" style={{ margin: 0 }}>Policy repository</div>
            <Badge tone="info">{filteredPolicies.length} policies</Badge>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              aria-label="Filter policies by line of business"
              value={policyTypeFilter}
              onChange={(e) => setPolicyTypeFilter(e.target.value)}
              style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-subtle)" }}
            >
              <option value="all">All lines of business</option>
              {["motor", "health", "senior_health", "home", "travel", "cyber"].map((t) => (
                <option key={t} value={t}>{human(t)}</option>
              ))}
            </select>
            <select
              aria-label="Filter policies by status"
              value={policyStatusFilter}
              onChange={(e) => setPolicyStatusFilter(e.target.value)}
              style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-subtle)" }}
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>

        {filteredPolicies.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Policy Number</th>
                  <th>Type</th>
                  <th>Policyholder</th>
                  <th>Coverage</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredPolicies.slice(0, 50).map((x) => (
                  <tr key={x.id}>
                    <td>
                      <b style={{ fontFamily: "ui-monospace, monospace" }}>{x.policy_number}</b>
                    </td>
                    <td>{human(x.policy_type)}</td>
                    <td>{x.policyholder_name || "—"}</td>
                    <td>{money(x.coverage_amount)}</td>
                    <td>
                      <DataBadge status={x.is_active === false ? "inactive" : "active"} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="actions" style={{ justifyContent: "flex-end" }}>
                        <button className="btn" onClick={() => open("policy", x)} title="Edit policy">
                          <Pencil size={13} />
                        </button>
                        <button className="btn danger" onClick={() => delPolicy(x.id)} title="Delete policy">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="No policies matching selected filters." />
        )}
      </Card>

      {/* Adjuster Invite Modal/Drawer */}
      {mode === "adjuster" && (
        <Card style={{ marginBottom: 24, borderColor: "var(--blue)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div className="card-title" style={{ margin: 0 }}>Invite new adjuster</div>
            <button className="icon-btn" onClick={() => setMode(null)}>
              <X size={15} />
            </button>
          </div>
          <div className="form-grid">
            <label>
              Full name
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </label>
            <label>
              Email address
              <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
            </label>
            <label>
              Phone number
              <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
            </label>
            <label>
              Specialization
              <select value={form.specialization} onChange={(e) => setForm({ ...form, specialization: e.target.value })}>
                {["motor", "health", "senior_health", "home", "travel", "cyber"].map((x) => (
                  <option key={x} value={x}>
                    {human(x)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="actions" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={invite}>
              Send invitation
            </button>
            <button className="btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </Card>
      )}

      {/* Policy Create / Edit Modal/Drawer */}
      {mode === "policy" && (
        <Card style={{ marginBottom: 24, borderColor: "var(--blue)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div className="card-title" style={{ margin: 0 }}>{edit ? "Edit policy record" : "Add new policy"}</div>
            <button className="icon-btn" onClick={() => setMode(null)}>
              <X size={15} />
            </button>
          </div>
          <div className="form-grid">
            <label>
              Policy number
              <input
                value={form.policy_number || ""}
                onChange={(e) => setForm({ ...form, policy_number: e.target.value })}
                disabled={!!edit}
                required
              />
            </label>
            <label>
              Policy type
              <select value={form.policy_type || "motor"} onChange={(e) => setForm({ ...form, policy_type: e.target.value })}>
                {["motor", "health", "senior_health", "home", "travel", "cyber"].map((x) => (
                  <option key={x} value={x}>
                    {human(x)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Coverage amount (INR)
              <input
                type="number"
                value={form.coverage_amount || ""}
                onChange={(e) => setForm({ ...form, coverage_amount: e.target.value })}
                required
              />
            </label>
            <label>
              Deductible (INR)
              <input
                type="number"
                value={form.deductible || "0"}
                onChange={(e) => setForm({ ...form, deductible: e.target.value })}
                required
              />
            </label>
            <label>
              Effective date
              <input
                type="date"
                value={form.effective_date || ""}
                onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                required
              />
            </label>
            <label>
              Expiry date
              <input
                type="date"
                value={form.expiry_date || ""}
                onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
                required
              />
            </label>
            <label>
              Policyholder name
              <input
                value={form.policyholder_name || ""}
                onChange={(e) => setForm({ ...form, policyholder_name: e.target.value })}
                required
              />
            </label>
            <label>
              Date of birth
              <input
                type="date"
                value={form.policyholder_dob || ""}
                onChange={(e) => setForm({ ...form, policyholder_dob: e.target.value })}
                required
              />
            </label>
            <label>
              Phone number
              <input
                value={form.policyholder_phone || ""}
                onChange={(e) => setForm({ ...form, policyholder_phone: e.target.value })}
                required
              />
            </label>
            <label>
              Email (optional)
              <input
                type="email"
                value={form.policyholder_email || ""}
                onChange={(e) => setForm({ ...form, policyholder_email: e.target.value })}
              />
            </label>
          </div>
          <div className="actions" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={savePolicy}>
              Save policy record
            </button>
            <button className="btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </Card>
      )}
    </Page>
  );
}

/* ==========================================================================
   Tenant Claims Management & Reassignment
   ========================================================================== */

function AdminClaims() {
  const [rows, setRows] = useState<any[]>([]);
  const [adjusters, setAdjusters] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("Operational workload balancing");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    const [r, a] = await Promise.all([
      api<any>("/api/v1/admin/claims" + (filter !== "all" ? "?status=" + encodeURIComponent(filter) : "")),
      api<any>("/api/v1/admin/adjusters")
    ]);
    setRows(r.items || []);
    setAdjusters(a.items || a);
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [filter]);

  async function reassign(ticket: string) {
    const target = targets[ticket];
    if (!target) {
      setError("Please select an active adjuster before reassigning.");
      return;
    }
    setError("");
    setNotice("");
    try {
      await api("/api/v1/admin/claims/" + encodeURIComponent(ticket) + "/reassign", {
        method: "POST",
        body: JSON.stringify({ adjuster_id: target, reason })
      });
      setNotice("Claim " + ticket + " reassigned successfully.");
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <Page
      title="Claims Management"
      subtitle="Tenant-wide claim allocation, SLA monitoring, and operational reassignment."
    >
      {(notice || error) && (
        <div className={error ? "error" : "notice"} role={error ? "alert" : "status"} style={{ marginBottom: 16 }}>
          {error ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
          <span>{error || notice}</span>
        </div>
      )}

      <Card style={{ marginBottom: 20 }}>
        <div className="actions">
          <label>
            Filter by status
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All statuses</option>
              <option value="submitted">Submitted</option>
              <option value="pending_adjuster">Pending adjuster</option>
              <option value="under_review">Under review</option>
              <option value="pending_evidence">Pending evidence</option>
              <option value="escalated">Escalated</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="closed">Closed</option>
            </select>
          </label>

          <label style={{ minWidth: 300 }}>
            Reassignment audit reason
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
      </Card>

      <Card>
        {rows.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Claim Ticket</th>
                  <th>Status</th>
                  <th>Insurance Line</th>
                  <th>Assigned Officer</th>
                  <th>Reassign To</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((x) => (
                  <tr key={x.ticket_id}>
                    <td>
                      <b style={{ fontFamily: "ui-monospace, monospace" }}>{x.ticket_id}</b>
                    </td>
                    <td>
                      <DataBadge status={x.status} />
                    </td>
                    <td>{human(x.insurance_type)}</td>
                    <td>{x.assigned_adjuster_name || "Unassigned"}</td>
                    <td>
                      <div className="actions" style={{ flexWrap: "nowrap" }}>
                        <select
                          value={targets[x.ticket_id] || x.assigned_adjuster_id || ""}
                          onChange={(e) => setTargets({ ...targets, [x.ticket_id]: e.target.value })}
                          style={{ minWidth: 160 }}
                        >
                          <option value="">Select adjuster</option>
                          {adjusters
                            .filter((a) => a.is_active !== false)
                            .map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name} ({human(a.specialization)})
                              </option>
                            ))}
                        </select>
                        <button className="btn primary" onClick={() => reassign(x.ticket_id)}>
                          Reassign
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="No claims match this filter criteria." />
        )}
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Tenant System Audit Trail
   ========================================================================== */

function Audit() {
  const [x, setX] = useState<any[]>([]);

  useEffect(() => {
    api<any>("/api/v1/admin/audit/events").then((v) => setX(Array.isArray(v) ? v : v.items || []));
  }, []);

  return (
    <Page
      title="System Audit"
      subtitle="Immutable cryptographic log of administrative decisions, claim state transitions, and AI events."
    >
      <Card>
        {x.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event Name</th>
                  <th>Timestamp</th>
                  <th>Details & Context</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {x.slice(0, 100).map((r: any, i: number) => (
                  <tr key={r.id || i}>
                    <td>
                      <b>{r.event_type || r.action || "Audit Event"}</b>
                    </td>
                    <td>{dt(r.created_at)}</td>
                    <td>{r.reason || r.resource_type || "Recorded in tenant ledger"}</td>
                    <td>
                      <DataBadge status={r.status || "recorded"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="No audit events found in current ledger." />
        )}
      </Card>
    </Page>
  );
}

export { AdminDashboard, Admin, AdminClaims, Audit };
