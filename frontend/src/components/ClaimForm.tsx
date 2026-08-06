"use client";

import { useState, useRef } from "react";
import {
  submitIntake,
  confirmClaim,
  uploadDocument,
  IntakeResponse,
  ConfirmResponse,
} from "@/services/claims";

type Step = "intake" | "documents" | "confirm" | "result";

const DECISION_META: Record<string, { label: string; icon: string; color: string; bg: string; border: string }> = {
  approved:          { label: "Approved",          icon: "✓", color: "#059669", bg: "#ecfdf5", border: "#a7f3d0" },
  denied:            { label: "Denied",             icon: "✕", color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
  manual_review:     { label: "Manual Review",      icon: "⚖", color: "#d97706", bg: "#fffbeb", border: "#fcd34d" },
  flagged_for_review:{ label: "Flagged for Review", icon: "⚑", color: "#ea580c", bg: "#fff7ed", border: "#fdba74" },
  need_documents:    { label: "Documents Required", icon: "📄", color: "#0284c7", bg: "#f0f9ff", border: "#7dd3fc" },
  need_more_info:    { label: "More Info Needed",   icon: "?", color: "#7c3aed", bg: "#f5f3ff", border: "#c4b5fd" },
};

const EXAMPLE_CLAIMS = [
  { label: "Auto Accident", text: "My car was hit by a truck on 2025-07-15 in Mumbai. Policy XYZ123. Repair cost is 50000 rupees." },
  { label: "Fraud Test",    text: "My car was damaged on 2027-01-01. Policy XYZ123. Repair cost is 480000 rupees." },
  { label: "Invalid Policy",text: "My car had an accident on 2025-01-10. Policy AUTO789. Damage cost 20000 rupees." },
  { label: "Business Loss", text: "My business was damaged on 2025-06-01. Policy XYZ123. Business loss is 900000 rupees. Claim type is business." },
];

export default function ClaimForm() {
  const [claimText, setClaimText] = useState("");
  const [ticketId, setTicketId] = useState<string | null>(null);
  const [intakeData, setIntakeData] = useState<IntakeResponse | null>(null);
  const [result, setResult] = useState<ConfirmResponse | null>(null);
  const [step, setStep] = useState<Step>("intake");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Document upload state
  const [docType, setDocType] = useState("damage_photo");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<{ type: string; name: string }[]>([]);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleIntakeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await submitIntake(claimText, "text", ticketId ?? undefined);
      setIntakeData(data);
      setTicketId(data.ticket_id);

      if (data.awaiting_confirmation) {
        const claimType = (data.extracted_data?.claim_type as string) ?? "";
        if (claimType === "auto" || claimType === "home") {
          setStep("documents");
        } else {
          setStep("confirm");
        }
      }
      // else: stay on intake to show missing fields prompt
    } catch {
      setError("Backend not reachable. Make sure it's running on http://localhost:8000");
    } finally {
      setLoading(false);
    }
  };

  const handleDocUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docFile || !ticketId) return;
    setLoading(true);
    setUploadMsg(null);
    setError(null);
    try {
      await uploadDocument(ticketId, docType, docFile);
      setUploadedDocs((prev) => [...prev, { type: docType, name: docFile.name }]);
      setUploadMsg(`Uploaded "${docFile.name}" as ${docType.replace("_", " ")}`);
      setDocFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch {
      setError("Upload failed. Check file and try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!ticketId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await confirmClaim(ticketId, true);
      setResult(data);
      setStep("result");
    } catch {
      setError("Evaluation failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setClaimText("");
    setTicketId(null);
    setIntakeData(null);
    setResult(null);
    setStep("intake");
    setError(null);
    setUploadedDocs([]);
    setUploadMsg(null);
  };

  const meta = result ? (DECISION_META[result.final_decision] ?? DECISION_META["manual_review"]) : null;

  const stepNum = { intake: 1, documents: 2, confirm: 3, result: 4 }[step];

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0f0f23 0%, #1a1035 50%, #0f1628 100%)" }}>

      {/* Header */}
      <header style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", padding: "20px 32px", display: "flex", alignItems: "center", gap: 16, backdropFilter: "blur(10px)", background: "rgba(255,255,255,0.03)" }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>🛡</div>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0", letterSpacing: "-0.3px" }}>InsureClaim AI</h1>
          <p style={{ fontSize: 12, color: "#64748b", marginTop: 1 }}>Intelligent Claim Processing</p>
        </div>
        {ticketId && (
          <div style={{ marginLeft: "auto", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)", borderRadius: 8, padding: "6px 14px", fontSize: 13, color: "#a5b4fc" }}>
            🎫 {ticketId}
          </div>
        )}
      </header>

      <main style={{ maxWidth: 760, margin: "0 auto", padding: "40px 24px" }}>

        {/* Progress Steps */}
        <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 40 }}>
          {["Describe Claim", "Upload Docs", "Review", "Decision"].map((label, i) => {
            const num = i + 1;
            const isActive = stepNum === num;
            const isDone = stepNum > num;
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", flex: i < 3 ? 1 : "none" }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                    fontWeight: 700, fontSize: 14, transition: "all 0.3s",
                    background: isDone ? "#6366f1" : isActive ? "linear-gradient(135deg, #6366f1, #8b5cf6)" : "rgba(255,255,255,0.06)",
                    border: isActive ? "2px solid #a5b4fc" : isDone ? "2px solid #6366f1" : "2px solid rgba(255,255,255,0.12)",
                    color: isActive || isDone ? "white" : "#64748b",
                    boxShadow: isActive ? "0 0 20px rgba(99,102,241,0.4)" : "none",
                  }}>
                    {isDone ? "✓" : num}
                  </div>
                  <span style={{ fontSize: 11, color: isActive ? "#a5b4fc" : isDone ? "#6366f1" : "#475569", fontWeight: isActive ? 600 : 400, whiteSpace: "nowrap" }}>{label}</span>
                </div>
                {i < 3 && <div style={{ flex: 1, height: 2, background: isDone ? "#6366f1" : "rgba(255,255,255,0.08)", margin: "0 8px", marginBottom: 22, transition: "background 0.3s" }} />}
              </div>
            );
          })}
        </div>

        {/* ─── STEP 1: INTAKE ─── */}
        {step === "intake" && (
          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, padding: 32, backdropFilter: "blur(10px)" }}>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>Describe Your Claim</h2>
            <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>Provide your policy number, incident date, type, and estimated amount.</p>

            {/* Example Chips */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
              <span style={{ fontSize: 12, color: "#64748b", alignSelf: "center" }}>Try an example:</span>
              {EXAMPLE_CLAIMS.map((ex) => (
                <button key={ex.label} onClick={() => setClaimText(ex.text)} style={{
                  background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 20,
                  color: "#a5b4fc", fontSize: 12, padding: "5px 12px", cursor: "pointer", transition: "all 0.2s",
                }} onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.25)")}
                   onMouseLeave={e => (e.currentTarget.style.background = "rgba(99,102,241,0.12)")}>
                  {ex.label}
                </button>
              ))}
            </div>

            <form onSubmit={handleIntakeSubmit}>
              <textarea
                id="claim-text-input"
                value={claimText}
                onChange={(e) => setClaimText(e.target.value)}
                required
                placeholder="e.g. My car was hit by a truck on 2025-07-15. Policy XYZ123. Repair cost is 50000 rupees."
                style={{
                  width: "100%", minHeight: 140, background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10,
                  color: "#e2e8f0", fontSize: 15, padding: "14px 16px", resize: "vertical",
                  outline: "none", fontFamily: "inherit", lineHeight: 1.6,
                  transition: "border-color 0.2s",
                }}
                onFocus={e => (e.target.style.borderColor = "rgba(99,102,241,0.6)")}
                onBlur={e => (e.target.style.borderColor = "rgba(255,255,255,0.12)")}
              />

              {/* Missing fields banner */}
              {intakeData?.missing_fields && intakeData.missing_fields.length > 0 && (
                <div style={{ marginTop: 16, background: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.3)", borderRadius: 10, padding: 16 }}>
                  <p style={{ color: "#c4b5fd", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>⚠️ More information needed:</p>
                  <p style={{ color: "#a78bfa", fontSize: 13 }}>{intakeData.message}</p>
                  <p style={{ color: "#64748b", fontSize: 11, marginTop: 8 }}>Add the missing details above and click Continue →</p>
                </div>
              )}

              <button id="submit-claim-btn" type="submit" disabled={loading} style={{
                marginTop: 20, padding: "13px 32px", borderRadius: 10, border: "none", cursor: loading ? "not-allowed" : "pointer",
                background: loading ? "rgba(99,102,241,0.4)" : "linear-gradient(135deg, #6366f1, #8b5cf6)",
                color: "white", fontWeight: 600, fontSize: 15, width: "100%",
                boxShadow: loading ? "none" : "0 4px 20px rgba(99,102,241,0.4)",
                transition: "all 0.2s", letterSpacing: "0.2px",
              }}>
                {loading ? "⏳ Processing with AI..." : intakeData?.missing_fields?.length ? "Continue →" : "Submit Claim →"}
              </button>
            </form>
          </div>
        )}

        {/* ─── STEP 2: DOCUMENTS ─── */}
        {step === "documents" && (
          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, padding: 32 }}>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>Upload Documents</h2>
            <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>
              Auto and home claims require supporting documents. Upload all required files before proceeding.
            </p>

            <div style={{ background: "rgba(2,132,199,0.1)", border: "1px solid rgba(2,132,199,0.25)", borderRadius: 10, padding: "12px 16px", marginBottom: 24, fontSize: 13, color: "#7dd3fc" }}>
              📋 <strong>Required for auto:</strong> Damage Photo + Repair Estimate
            </div>

            <form onSubmit={handleDocUpload} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", color: "#94a3b8", fontSize: 13, fontWeight: 500, marginBottom: 8 }}>Document Type</label>
                <select id="doc-type-select" value={docType} onChange={(e) => setDocType(e.target.value)} style={{
                  width: "100%", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 8, color: "#e2e8f0", fontSize: 14, padding: "10px 14px", outline: "none",
                }}>
                  <option value="damage_photo" style={{ background: "#1a1a35" }}>📸 Damage Photo</option>
                  <option value="repair_estimate" style={{ background: "#1a1a35" }}>🔧 Repair Estimate</option>
                </select>
              </div>

              <div>
                <label style={{ display: "block", color: "#94a3b8", fontSize: 13, fontWeight: 500, marginBottom: 8 }}>Select File</label>
                <input ref={fileRef} id="doc-file-input" type="file" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)}
                  style={{ width: "100%", color: "#94a3b8", fontSize: 13, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "10px 14px" }} />
              </div>

              <button id="upload-doc-btn" type="submit" disabled={loading || !docFile} style={{
                padding: "12px", borderRadius: 10, border: "none",
                background: !docFile ? "rgba(255,255,255,0.06)" : "linear-gradient(135deg, #0ea5e9, #6366f1)",
                color: !docFile ? "#475569" : "white", fontWeight: 600, fontSize: 14, cursor: !docFile ? "not-allowed" : "pointer",
                boxShadow: docFile ? "0 4px 16px rgba(14,165,233,0.3)" : "none",
              }}>
                {loading ? "Uploading..." : "Upload Document"}
              </button>
            </form>

            {uploadMsg && (
              <div style={{ marginTop: 16, background: "rgba(5,150,105,0.12)", border: "1px solid rgba(5,150,105,0.3)", borderRadius: 8, padding: "10px 14px", color: "#6ee7b7", fontSize: 13 }}>
                ✓ {uploadMsg}
              </div>
            )}

            {uploadedDocs.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <p style={{ color: "#64748b", fontSize: 12, marginBottom: 8 }}>UPLOADED ({uploadedDocs.length})</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {uploadedDocs.map((d, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: "8px 12px" }}>
                      <span style={{ color: "#6ee7b7" }}>✓</span>
                      <span style={{ color: "#e2e8f0", fontSize: 13 }}>{d.name}</span>
                      <span style={{ marginLeft: "auto", color: "#64748b", fontSize: 12, background: "rgba(255,255,255,0.06)", borderRadius: 4, padding: "2px 8px" }}>{d.type.replace("_", " ")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button id="proceed-confirm-btn" onClick={() => setStep("confirm")} disabled={loading} style={{
              marginTop: 24, width: "100%", padding: "13px", borderRadius: 10, border: "none",
              background: "linear-gradient(135deg, #059669, #0ea5e9)", color: "white", fontWeight: 600, fontSize: 15, cursor: "pointer",
              boxShadow: "0 4px 20px rgba(5,150,105,0.3)",
            }}>
              Proceed to Review →
            </button>
          </div>
        )}

        {/* ─── STEP 3: CONFIRM ─── */}
        {step === "confirm" && intakeData && (
          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, padding: 32 }}>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>Review & Confirm</h2>
            <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>Please verify the extracted details before we evaluate your claim.</p>

            <div style={{ display: "grid", gap: 12, marginBottom: 28 }}>
              {Object.entries(intakeData.extracted_data ?? {}).map(([key, val]) => (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "rgba(255,255,255,0.04)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.07)" }}>
                  <span style={{ color: "#64748b", fontSize: 13, textTransform: "capitalize" }}>{key.replace(/_/g, " ")}</span>
                  <span style={{ color: "#e2e8f0", fontWeight: 500, fontSize: 14 }}>{String(val ?? "—")}</span>
                </div>
              ))}
            </div>

            {uploadedDocs.length > 0 && (
              <div style={{ marginBottom: 24, padding: "12px 16px", background: "rgba(5,150,105,0.1)", borderRadius: 8, border: "1px solid rgba(5,150,105,0.2)", color: "#6ee7b7", fontSize: 13 }}>
                ✓ {uploadedDocs.length} document(s) uploaded
              </div>
            )}

            <button id="confirm-btn" onClick={handleConfirm} disabled={loading} style={{
              width: "100%", padding: "14px", borderRadius: 10, border: "none",
              background: loading ? "rgba(99,102,241,0.4)" : "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: "white", fontWeight: 700, fontSize: 16, cursor: loading ? "not-allowed" : "pointer",
              boxShadow: "0 4px 24px rgba(99,102,241,0.4)", letterSpacing: "0.3px",
            }}>
              {loading ? "⏳ AI is evaluating your claim..." : "Confirm & Get Decision →"}
            </button>
          </div>
        )}

        {/* ─── STEP 4: RESULT ─── */}
        {step === "result" && result && meta && (
          <div>
            {/* Decision Card */}
            <div style={{
              borderRadius: 16, padding: 32, marginBottom: 24, textAlign: "center",
              background: `linear-gradient(135deg, ${meta.bg}, white)`,
              border: `2px solid ${meta.border}`,
              boxShadow: `0 8px 32px ${meta.color}22`,
            }}>
              <div style={{ width: 64, height: 64, borderRadius: "50%", background: meta.color, color: "white", fontSize: 28, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                {meta.icon}
              </div>
              <h2 style={{ fontSize: 26, fontWeight: 800, color: meta.color, marginBottom: 8 }}>{meta.label}</h2>
              <p style={{ color: "#374151", fontSize: 15, lineHeight: 1.7, maxWidth: 520, margin: "0 auto" }}>{result.response_message}</p>
              {ticketId && <p style={{ marginTop: 12, fontSize: 13, color: "#9ca3af" }}>Ticket: {ticketId}</p>}
            </div>

            {/* Stats Row */}
            {(result.payout_amount != null || result.fraud_score != null) && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 24 }}>
                {result.payout_amount != null && (
                  <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: 20, textAlign: "center" }}>
                    <p style={{ color: "#64748b", fontSize: 12, marginBottom: 6 }}>PAYOUT AMOUNT</p>
                    <p style={{ color: "#34d399", fontSize: 22, fontWeight: 700 }}>₹{result.payout_amount?.toLocaleString()}</p>
                  </div>
                )}
                {result.deductible_amount != null && (
                  <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: 20, textAlign: "center" }}>
                    <p style={{ color: "#64748b", fontSize: 12, marginBottom: 6 }}>DEDUCTIBLE</p>
                    <p style={{ color: "#fbbf24", fontSize: 22, fontWeight: 700 }}>₹{result.deductible_amount?.toLocaleString()}</p>
                  </div>
                )}
                {result.fraud_score != null && (
                  <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: 20, textAlign: "center" }}>
                    <p style={{ color: "#64748b", fontSize: 12, marginBottom: 6 }}>FRAUD SCORE</p>
                    <p style={{ color: result.fraud_score >= 0.7 ? "#f87171" : "#34d399", fontSize: 22, fontWeight: 700 }}>{(result.fraud_score * 100).toFixed(0)}%</p>
                  </div>
                )}
                {result.assigned_adjuster && Object.keys(result.assigned_adjuster).length > 0 && (
                  <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: 20, textAlign: "center" }}>
                    <p style={{ color: "#64748b", fontSize: 12, marginBottom: 6 }}>ADJUSTER</p>
                    <p style={{ color: "#e2e8f0", fontSize: 14, fontWeight: 600 }}>{String(result.assigned_adjuster.name)}</p>
                  </div>
                )}
              </div>
            )}

            {/* Fraud Flags */}
            {result.fraud_flags && result.fraud_flags.length > 0 && (
              <div style={{ background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 12, padding: 20, marginBottom: 24 }}>
                <p style={{ color: "#f87171", fontWeight: 600, fontSize: 13, marginBottom: 12 }}>⚠ Fraud Flags Detected</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {result.fraud_flags.map((flag, i) => (
                    <span key={i} style={{ background: "rgba(220,38,38,0.15)", border: "1px solid rgba(220,38,38,0.3)", borderRadius: 20, color: "#fca5a5", fontSize: 12, padding: "4px 12px" }}>
                      {flag.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Collapsibles */}
            <details style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: "14px 18px", marginBottom: 12 }}>
              <summary style={{ color: "#94a3b8", fontSize: 13, cursor: "pointer", fontWeight: 500 }}>📊 Extracted Data</summary>
              <pre style={{ marginTop: 12, color: "#94a3b8", fontSize: 12, overflowX: "auto", lineHeight: 1.6 }}>{JSON.stringify(result.extracted_data, null, 2)}</pre>
            </details>

            <details style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: "14px 18px", marginBottom: 24 }}>
              <summary style={{ color: "#94a3b8", fontSize: 13, cursor: "pointer", fontWeight: 500 }}>📋 Full Pipeline Result</summary>
              <pre style={{ marginTop: 12, color: "#94a3b8", fontSize: 12, overflowX: "auto", lineHeight: 1.6 }}>{JSON.stringify(result, null, 2)}</pre>
            </details>

            <button id="new-claim-btn" onClick={reset} style={{
              width: "100%", padding: "13px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.06)", color: "#e2e8f0", fontWeight: 600, fontSize: 15, cursor: "pointer",
            }}>
              ← Start New Claim
            </button>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div id="error-msg" style={{ marginTop: 20, background: "rgba(220,38,38,0.1)", border: "1px solid rgba(220,38,38,0.3)", borderRadius: 10, padding: "14px 18px", color: "#f87171", fontSize: 14 }}>
            ⚠ {error}
          </div>
        )}
      </main>
    </div>
  );
}