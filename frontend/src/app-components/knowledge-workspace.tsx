"use client";
import Link from "next/link";
import React, { useEffect, useState } from "react";
import { 
  AlertCircle, 
  BookOpen, 
  CheckCircle2, 
  FileCheck2, 
  FilePlus2, 
  FileText, 
  Pencil, 
  RefreshCw, 
  Search, 
  ShieldCheck, 
  Sparkles, 
  Upload, 
  X 
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, DataBadge, Empty, Page } from "@/app-components/ui";

const human = (v: string) => v.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

export function Knowledge({ manage = false }: { manage?: boolean }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [docs, setDocs] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [replaceFile, setReplaceFile] = useState<Record<string, File | null>>({});
  const [id, setId] = useState("");
  const [docType, setDocType] = useState("policy_wording");
  const [insuranceType, setInsuranceType] = useState("general");
  const [policyNumber, setPolicyNumber] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [version, setVersion] = useState("");
  const [editing, setEditing] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  async function search() {
    setError("");
    try {
      const x = await api<any>(
        "/api/v1/knowledge/search?q=" + encodeURIComponent(q) + "&document_type=" + encodeURIComponent(docType || "")
      );
      setRows(x.items || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function loadDocs() {
    try {
      const x = await api<any>("/api/v1/knowledge/documents");
      setDocs(x.items || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    if (manage) loadDocs();
  }, [manage]);

  async function ingestText() {
    setBusy(true);
    setError("");
    try {
      const x = await api<any>("/api/v1/knowledge/documents", {
        method: "POST",
        body: JSON.stringify({
          text,
          source_name: name,
          document_type: docType,
          insurance_type: insuranceType,
          policy_number: policyNumber || undefined,
          policy_version: version || undefined,
          jurisdiction: jurisdiction || undefined
        })
      });
      setId(x.document_id || "");
      setMsg("Knowledge source indexed successfully into vector store.");
      setText("");
      setName("");
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("document_type", docType);
      fd.append("insurance_type", insuranceType);
      if (policyNumber) fd.append("policy_number", policyNumber);
      if (version) fd.append("policy_version", version);
      if (jurisdiction) fd.append("jurisdiction", jurisdiction);

      const x = await api<any>("/api/v1/knowledge/upload", { method: "POST", body: fd });
      setId(x.job_id || "");
      setMsg("Document upload queued for OCR & chunking pipeline.");

      if (x.job_id) {
        let done = false;
        for (let attempt = 0; attempt < 30 && !done; attempt++) {
          await new Promise((res) => setTimeout(res, 1000));
          const s = await api<any>("/api/v1/knowledge/ingestion/" + x.job_id);
          if (["processed", "completed", "dead_letter"].includes(s.status)) {
            done = true;
            setMsg(
              s.status === "dead_letter"
                ? "Indexing failed: " + (s.error || "worker rejected the document.")
                : "Document parsed and indexed into vector knowledge base."
            );
          }
        }
      }
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      setFile(null);
    }
  }

  async function publish(docId: string) {
    try {
      await api("/api/v1/knowledge/documents/" + docId + "/publish", { method: "POST" });
      setMsg("Document published for Copilot and intake retrieval.");
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function updateDoc() {
    if (!editing) return;
    setBusy(true);
    try {
      await api("/api/v1/knowledge/documents/" + editing.id, {
        method: "PUT",
        body: JSON.stringify({
          source_name: editing.source_name,
          insurance_type: editing.insurance_type,
          policy_number: editing.policy_number,
          policy_version: editing.policy_version,
          jurisdiction: editing.jurisdiction,
          publication_status: editing.publication_status
        })
      });
      setMsg("Document metadata updated.");
      setEditing(null);
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function reindex(doc: any) {
    setBusy(true);
    setError("");
    try {
      const x = await api<any>("/api/v1/knowledge/documents/" + doc.id + "/reindex", { method: "POST" });
      setMsg("Re-indexed " + (x.chunks || 0) + " semantic chunks.");
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function replaceContent(doc: any) {
    const f = replaceFile[doc.id];
    if (!f) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("document_type", doc.document_type);
      if (doc.insurance_type) fd.append("insurance_type", doc.insurance_type);
      if (doc.policy_number) fd.append("policy_number", doc.policy_number);
      if (doc.policy_version) fd.append("policy_version", doc.policy_version);
      if (doc.jurisdiction) fd.append("jurisdiction", doc.jurisdiction);

      const x = await api<any>("/api/v1/knowledge/documents/" + doc.id + "/content", { method: "PUT", body: fd });
      setMsg("Document replaced and re-indexed. ID: " + (x.replacement_document_id || "created"));
      setReplaceFile((v) => ({ ...v, [doc.id]: null }));
      await loadDocs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (manage) {
    return (
      <Page
        title="Knowledge management"
        subtitle="Maintain published policy wordings, exclusions, and statutory regulatory guidance."
        actions={
          <Link className="btn" href="/knowledge">
            <BookOpen size={14} />
            <span>Search published knowledge</span>
          </Link>
        }
      >
        {(msg || error) && (
          <div className={error ? "error" : "notice"} role={error ? "alert" : "status"} style={{ marginBottom: 16 }}>
            {error ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
            <span>{error || msg}</span>
          </div>
        )}

        <div className="grid grid-2" style={{ marginBottom: 24 }}>
          {/* Direct Text Ingestion */}
          <Card>
            <div className="card-title">Index text clause source</div>
            <div className="form-grid">
              <label>
                Document type
                <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                  <option value="policy_wording">Policy wording</option>
                  <option value="regulation">Regulation</option>
                  <option value="guideline">Regulatory guidance</option>
                  <option value="claim_requirement">Claim requirements</option>
                </select>
              </label>

              <label>
                Insurance type
                <input value={insuranceType} onChange={(e) => setInsuranceType(e.target.value)} placeholder="motor, health…" />
              </label>

              <label>
                Policy number
                <input value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} placeholder="e.g. POL-MOT-99" />
              </label>

              <label>
                Version
                <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="e.g. 2026.1" />
              </label>

              <label>
                Jurisdiction
                <input value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="e.g. California / National" />
              </label>
            </div>

            <label style={{ marginTop: 12 }}>
              Source title / reference
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Comprehensive Motor Section 4 (Own Damage)" />
            </label>

            <label style={{ marginTop: 12 }}>
              Clause text content
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the statutory clause, deductible schedule, or coverage terms…"
                style={{ minHeight: 120 }}
              />
            </label>

            <div className="actions" style={{ marginTop: 12 }}>
              <button
                className="btn primary"
                onClick={ingestText}
                disabled={busy || text.trim().length < 20 || !name.trim()}
              >
                {busy ? "Indexing chunks…" : "Index text source"}
              </button>
            </div>
          </Card>

          {/* Upload PDF/DOCX Document */}
          <Card>
            <div className="card-title">Upload policy document</div>
            <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 16px" }}>
              Uploaded files are scanned for malware, processed via OCR, divided into semantic vector embeddings, and registered in the transactional outbox.
            </p>

            <label className="btn" style={{ height: 48, justifyContent: "flex-start", width: "100%", gap: 10 }}>
              <Upload size={16} />
              <span>{file ? file.name : "Select PDF / DOCX / TXT"}</span>
              <input
                type="file"
                accept=".pdf,.doc,.docx,.txt"
                hidden
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>

            <button
              className="btn primary"
              onClick={upload}
              disabled={busy || !file}
              style={{ marginTop: 14, width: "100%", height: 42 }}
            >
              {busy ? "Processing document…" : "Upload and index"}
            </button>
          </Card>
        </div>

        {/* Source Registry Table */}
        <Card style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div className="card-title" style={{ margin: 0 }}>Registered knowledge sources</div>
            <button className="btn" onClick={loadDocs}>
              <RefreshCw size={13} />
              <span>Refresh</span>
            </button>
          </div>

          {docs.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Source Title</th>
                    <th>Document Type</th>
                    <th>Version</th>
                    <th>Publication</th>
                    <th>Chunks</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d: any) => (
                    <tr key={d.id}>
                      <td>
                        <b>{d.source_name}</b>
                        <div style={{ fontSize: 11, color: "var(--muted)" }}>
                          {d.policy_number || "General"} · {d.jurisdiction || "All jurisdictions"}
                        </div>
                      </td>
                      <td>{human(d.document_type)}</td>
                      <td>{d.policy_version || "—"}</td>
                      <td>
                        <DataBadge status={d.publication_status || "pending_review"} />
                      </td>
                      <td>
                        <b style={{ fontFamily: "ui-monospace, monospace" }}>{d.chunks || 0}</b>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div className="actions" style={{ justifyContent: "flex-end" }}>
                          <button className="btn" onClick={() => setEditing({ ...d })} title="Edit metadata">
                            <Pencil size={12} />
                          </button>
                          <button className="btn" onClick={() => reindex(d)} disabled={busy} title="Re-index vector chunks">
                            Re-index
                          </button>
                          <label className="btn" title="Replace file">
                            <span>Replace</span>
                            <input
                              type="file"
                              hidden
                              accept=".pdf,.doc,.docx,.txt"
                              onChange={(e) =>
                                setReplaceFile({ ...replaceFile, [d.id]: e.target.files?.[0] || null })
                              }
                            />
                          </label>
                          {replaceFile[d.id] && (
                            <button className="btn primary" onClick={() => replaceContent(d)} disabled={busy}>
                              Apply
                            </button>
                          )}
                          {d.publication_status !== "published" && (
                            <button className="btn primary" onClick={() => publish(d.id)}>
                              Publish
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty text="No knowledge sources indexed in the repository." />
          )}
        </Card>

        {/* Metadata Editor Modal */}
        {editing && (
          <Card style={{ marginBottom: 24, borderColor: "var(--blue)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div className="card-title" style={{ margin: 0 }}>Update source metadata</div>
              <button className="icon-btn" onClick={() => setEditing(null)}>
                <X size={15} />
              </button>
            </div>
            <div className="form-grid">
              <label>
                Source name
                <input value={editing.source_name || ""} onChange={(e) => setEditing({ ...editing, source_name: e.target.value })} />
              </label>
              <label>
                Insurance type
                <input value={editing.insurance_type || ""} onChange={(e) => setEditing({ ...editing, insurance_type: e.target.value })} />
              </label>
              <label>
                Policy number
                <input value={editing.policy_number || ""} onChange={(e) => setEditing({ ...editing, policy_number: e.target.value })} />
              </label>
              <label>
                Version
                <input value={editing.policy_version || ""} onChange={(e) => setEditing({ ...editing, policy_version: e.target.value })} />
              </label>
              <label>
                Jurisdiction
                <input value={editing.jurisdiction || ""} onChange={(e) => setEditing({ ...editing, jurisdiction: e.target.value })} />
              </label>
              <label>
                Publication status
                <select
                  value={editing.publication_status || "pending_review"}
                  onChange={(e) => setEditing({ ...editing, publication_status: e.target.value })}
                >
                  <option value="pending_review">Pending review</option>
                  <option value="published">Published</option>
                  <option value="superseded">Superseded</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
            </div>
            <div className="actions" style={{ marginTop: 14 }}>
              <button className="btn primary" onClick={updateDoc} disabled={busy}>
                {busy ? "Saving…" : "Save metadata"}
              </button>
              <button className="btn" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
          </Card>
        )}
      </Page>
    );
  }

  // Knowledge Search View
  return (
    <Page
      title="Policy & Regulations"
      subtitle="Search published insurance wording, exclusions, and regulatory precedents used by Copilot."
      actions={
        <Link className="btn primary" href="/knowledge/manage">
          <Pencil size={13} />
          <span>Manage knowledge base</span>
        </Link>
      }
    >
      <Card style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ flex: 1, position: "relative" }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="Search policy terms, exclusions, deductible rules (e.g., 'total loss depreciation')…"
            />
          </div>
          <button className="btn primary" onClick={search} style={{ height: 42 }}>
            <Search size={15} />
            <span>Search</span>
          </button>
        </div>

        {error && (
          <div className="error" style={{ marginTop: 14 }}>
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        <div style={{ marginTop: 18 }}>
          {rows.length ? (
            rows.map((x: any, i: number) => (
              <div className="list-row" key={x.id || i}>
                <div className="list-main">
                  <b>{x.title || x.document_name || x.source_name || "Knowledge Citation"}</b>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--ink-secondary)", lineHeight: 1.6 }}>
                    {x.citation_label || x.snippet || x.content || x.text || ""}
                  </p>
                </div>
                <DataBadge status={x.document_type || "policy"} />
              </div>
            ))
          ) : (
            <Empty
              text={q ? "No matching published clauses found." : "Search across all published policy wording and statutory guidelines."}
              icon={<Search size={28} />}
            />
          )}
        </div>
      </Card>
    </Page>
  );
}
