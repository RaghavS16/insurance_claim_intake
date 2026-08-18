"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ClaimRecord {
  id: string;
  ticket_id: string;
  claim_type: string | null;
  status: string;
  conversation_status: string;
  final_decision: string | null;
  closure_status: string | null;
  extracted_data: Record<string, any>;
  created_at: string | null;
  claimant_id: string | null;
}

interface KnowledgeDoc {
  id: string;
  document_type: "POLICY_WORDING" | "IRDAI_REGULATION";
  title: string;
  version: string;
  file_reference: string;
  status: string;
  effective_date: string;
  uploaded_by: string;
  created_at: string;
}

export default function AdjusterPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
  const [userName, setUserName] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"claims" | "knowledge">("claims");

  // Claims state
  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const [selectedClaim, setSelectedClaim] = useState<ClaimRecord | null>(null);
  const [claimHistory, setClaimHistory] = useState<any[]>([]);
  const [claimDocs, setClaimDocs] = useState<any[]>([]);
  const [finalDecision, setFinalDecision] = useState("");
  const [closureStatus, setClosureStatus] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);

  // Knowledge docs state
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadVersion, setUploadVersion] = useState("");
  const [uploadDocType, setUploadDocType] = useState("POLICY_WORDING");
  const [uploadEffDate, setUploadEffDate] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

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
        if (data.role !== "ADJUSTER") {
          router.push("/login");
          return;
        }
        setUserId(data.id);
        setUserName(data.full_name);
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router]);

  // Load claims
  const loadClaims = async (savedToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/adjuster/claims`, {
        headers: { Authorization: `Bearer ${savedToken}` },
      });
      if (!res.ok) throw new Error("Failed to load claims");
      const data = await res.json();
      setClaims(data);
    } catch (err: any) {
      setErrorMsg(err.message || "Could not load claims.");
    }
  };

  // Load knowledge documents
  const loadKnowledgeDocs = async (savedToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge`, {
        headers: { Authorization: `Bearer ${savedToken}` },
      });
      if (!res.ok) throw new Error("Failed to load knowledge documents");
      const data = await res.json();
      setDocs(data);
    } catch (err: any) {
      setErrorMsg(err.message || "Could not load knowledge base.");
    }
  };

  useEffect(() => {
    if (token) {
      if (activeTab === "claims") {
        loadClaims(token);
      } else {
        loadKnowledgeDocs(token);
      }
    }
  }, [activeTab, token]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  // Select a claim for detailed review
  const handleSelectClaim = async (claim: ClaimRecord) => {
    setSelectedClaim(claim);
    setFinalDecision(claim.final_decision || "approved");
    setClosureStatus(claim.closure_status || "closed");
    setClaimHistory([]);
    setClaimDocs([]);

    try {
      // Fetch conversation turns history
      const turnsRes = await fetch(`${API_BASE}/api/v1/claims/${claim.ticket_id}/conversation`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (turnsRes.ok) {
        const turnsData = await turnsRes.json();
        setClaimHistory(turnsData);
      }

      // Fetch uploaded documents
      const docsRes = await fetch(`${API_BASE}/api/v1/claims/${claim.ticket_id}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setClaimDocs(docsData);
      }
    } catch (err) {
      console.error("Failed to load claim detail details:", err);
    }
  };

  // Submit claim review decision
  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClaim) return;
    setReviewLoading(true);
    setErrorMsg("");
    setSuccessMsg("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/adjuster/claims/${selectedClaim.ticket_id}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          final_decision: finalDecision,
          closure_status: closureStatus,
        }),
      });

      if (!res.ok) throw new Error("Failed to submit review");
      setSuccessMsg(`Review for ${selectedClaim.ticket_id} submitted successfully!`);
      
      // Update local state
      const updatedClaims = claims.map((c) =>
        c.ticket_id === selectedClaim.ticket_id
          ? { ...c, final_decision: finalDecision, closure_status: closureStatus }
          : c
      );
      setClaims(updatedClaims);
      setSelectedClaim({ ...selectedClaim, final_decision: finalDecision, closure_status: closureStatus });
    } catch (err: any) {
      setErrorMsg(err.message || "An error occurred submitting the review.");
    } finally {
      setReviewLoading(false);
    }
  };

  // Knowledge Document upload
  const handleDocUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadTitle.trim() || !uploadVersion.trim() || !uploadEffDate.trim() || !uploadFile) {
      setErrorMsg("Please fill in all upload fields.");
      return;
    }
    
    // 10MB limit
    if (uploadFile && uploadFile.size > 10 * 1024 * 1024) {
      setErrorMsg("File size must be under 10MB.");
      return;
    }

    setUploadLoading(true);
    setErrorMsg("");
    setSuccessMsg("");

    const formData = new FormData();
    formData.append("title", uploadTitle);
    formData.append("version", uploadVersion);
    formData.append("document_type", uploadDocType);
    formData.append("effective_date", uploadEffDate);
    formData.append("file", uploadFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Document upload failed");
      }

      setSuccessMsg("Document uploaded and versioned successfully!");
      // Reset form
      setUploadTitle("");
      setUploadVersion("");
      setUploadEffDate("");
      setUploadFile(null);
      
      // Reload documents list
      loadKnowledgeDocs(token);
    } catch (err: any) {
      setErrorMsg(err.message || "Could not upload document.");
    } finally {
      setUploadLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-white">
      {/* Adjuster Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md sticky top-0 z-30 px-6 py-4 flex items-center justify-between shadow-lg shadow-black/20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center text-xl shadow-md shadow-cyan-500/20">
            🕵️‍♂️
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Adjuster Operations Dashboard
            </h1>
            <p className="text-[11px] text-slate-400">Claims Intake &amp; Knowledge Management</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex flex-col text-right">
            <span className="text-xs font-semibold text-slate-200">{userName}</span>
            <span className="text-[9px] text-slate-500">Authorized Adjuster</span>
          </div>
          <button
            onClick={handleLogout}
            className="px-3.5 py-1.5 text-[11px] font-medium bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-300 border border-slate-700 rounded-xl transition"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Notifications banner */}
      {(errorMsg || successMsg) && (
        <div className="mx-6 mt-4 flex flex-col gap-2">
          {errorMsg && (
            <div className="flex items-start gap-3 bg-rose-950/70 border border-rose-600/50 rounded-2xl px-4 py-3.5 text-xs text-rose-200 shadow-md">
              <span className="text-rose-400 shrink-0">⚠️</span>
              <span className="flex-1 leading-normal">{errorMsg}</span>
              <button onClick={() => setErrorMsg("")} className="text-rose-400 hover:text-rose-200">×</button>
            </div>
          )}
          {successMsg && (
            <div className="flex items-start gap-3 bg-emerald-950/70 border border-emerald-600/50 rounded-2xl px-4 py-3.5 text-xs text-emerald-200 shadow-md animate-fade-in">
              <span className="text-emerald-400 shrink-0">✓</span>
              <span className="flex-1 leading-normal">{successMsg}</span>
              <button onClick={() => setSuccessMsg("")} className="text-emerald-400 hover:text-emerald-200">×</button>
            </div>
          )}
        </div>
      )}

      {/* Tabs Layout */}
      <div className="flex border-b border-slate-800/60 bg-slate-900/20 px-6">
        <button
          onClick={() => setActiveTab("claims")}
          className={`px-5 py-4 text-xs font-semibold border-b-2 transition duration-200 ${
            activeTab === "claims" ? "border-cyan-500 text-cyan-400" : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Claims Review Pipeline
        </button>
        <button
          onClick={() => setActiveTab("knowledge")}
          className={`px-5 py-4 text-xs font-semibold border-b-2 transition duration-200 ${
            activeTab === "knowledge" ? "border-cyan-500 text-cyan-400" : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Versioned Document Wording Store
        </button>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 overflow-hidden">
        {activeTab === "claims" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-210px)] overflow-hidden">
            {/* Claims Table / List */}
            <div className="lg:col-span-6 bg-slate-900/40 border border-slate-800 rounded-3xl p-5 overflow-y-auto flex flex-col gap-4">
              <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Submitted Claims ({claims.length})</h2>
              
              {claims.length === 0 ? (
                <div className="text-center py-10 text-slate-600 text-xs italic">
                  No claims found in database.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {claims.map((claim) => (
                    <button
                      key={claim.id}
                      onClick={() => handleSelectClaim(claim)}
                      className={`p-4.5 rounded-2xl text-left border transition duration-200 flex flex-col gap-2.5 ${
                        selectedClaim?.id === claim.id
                          ? "bg-cyan-950/20 border-cyan-500/60 shadow-lg shadow-cyan-500/5"
                          : "bg-slate-950/50 hover:bg-slate-800 border-slate-800/80"
                      }`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-mono text-xs text-slate-300 font-bold">{claim.ticket_id}</span>
                        <span className={`text-[9px] px-2 py-0.5 rounded-full font-extrabold uppercase border ${
                          claim.status === "evaluated"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                        }`}>
                          {claim.status}
                        </span>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                        <div>Type: <span className="text-slate-200 capitalize font-medium">{claim.claim_type || "unspecified"}</span></div>
                        <div className="text-right">Amount: <span className="text-emerald-400 font-bold">
                          {claim.extracted_data?.claimed_amount != null
                            ? `₹${Number(claim.extracted_data.claimed_amount).toLocaleString("en-IN")}`
                            : "Pending"}
                        </span></div>
                      </div>

                      {claim.final_decision && (
                        <div className="mt-1 pt-2 border-t border-slate-800/60 flex justify-between items-center text-[10px]">
                          <span className="text-slate-500">Decision:</span>
                          <span className="text-cyan-400 uppercase font-bold">{claim.final_decision}</span>
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Claims Detail & Action Panel */}
            <div className="lg:col-span-6 bg-slate-900/40 border border-slate-800 rounded-3xl p-5 overflow-y-auto flex flex-col gap-5">
              {selectedClaim ? (
                <>
                  <div className="border-b border-slate-800 pb-3 flex justify-between items-center">
                    <div>
                      <h3 className="font-mono text-sm text-white font-bold">{selectedClaim.ticket_id}</h3>
                      <p className="text-[10px] text-slate-500 mt-0.5">Claimant ID: {selectedClaim.claimant_id}</p>
                    </div>
                    <span className="text-xs font-semibold text-cyan-400 capitalize">{selectedClaim.claim_type} Insurance</span>
                  </div>

                  {/* Incident Details Card */}
                  <div className="bg-slate-950/40 border border-slate-800/60 p-4.5 rounded-2xl flex flex-col gap-3 text-xs">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-800/60 pb-1.5">Extracted Claims State</h4>
                    <div className="grid grid-cols-2 gap-2 text-slate-400">
                      <div>Incident Date: <span className="text-slate-200 font-medium">{selectedClaim.extracted_data?.incident_date || "Not set"}</span></div>
                      <div>Deductible: <span className="text-slate-200 font-medium">{selectedClaim.extracted_data?.deductible_amount ? `₹${selectedClaim.extracted_data.deductible_amount}` : "Not set"}</span></div>
                      <div>Estimated loss: <span className="text-slate-200 font-medium">{selectedClaim.extracted_data?.claimed_amount ? `₹${selectedClaim.extracted_data.claimed_amount}` : "Not set"}</span></div>
                      <div>Fraud Score: <span className="text-rose-400 font-medium">{selectedClaim.extracted_data?.fraud_score != null ? `${selectedClaim.extracted_data.fraud_score}` : "Not set"}</span></div>
                    </div>
                    <div className="flex flex-col gap-1 mt-1 text-slate-400">
                      <div>Damage description:</div>
                      <p className="p-3 bg-slate-950/80 rounded-xl border border-slate-900 text-slate-300 text-[11px] leading-relaxed">
                        {selectedClaim.extracted_data?.damage_description || "No description provided."}
                      </p>
                    </div>
                  </div>

                  {/* Documents uploaded */}
                  <div className="flex flex-col gap-3 text-xs">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Claimant-Provided Documents ({claimDocs.length})</h4>
                    {claimDocs.length === 0 ? (
                      <p className="text-slate-600 italic">No files uploaded yet.</p>
                    ) : (
                      <div className="grid grid-cols-1 gap-2">
                        {claimDocs.map((doc) => (
                          <div key={doc.document_id} className="p-3 bg-slate-950/40 border border-slate-800 rounded-xl flex items-center justify-between">
                            <div>
                              <div className="font-semibold text-slate-200">{doc.filename}</div>
                              <div className="text-[9px] text-slate-500 uppercase mt-0.5">{doc.document_type} • {(doc.file_size_bytes / 1024).toFixed(1)} KB</div>
                            </div>
                            <span className="text-[10px] text-slate-500">{new Date(doc.uploaded_at).toLocaleDateString()}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Conversation History */}
                  <div className="flex flex-col gap-3 text-xs">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Intake Dialogue Transcript</h4>
                    <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-2xl max-h-48 overflow-y-auto space-y-3">
                      {claimHistory.map((turn, tIdx) => (
                        <div key={tIdx} className={`flex flex-col gap-1 text-[11px] ${turn.speaker === "agent" ? "text-cyan-300" : "text-slate-300"}`}>
                          <div className="font-bold text-[9px] uppercase">{turn.speaker} (Turn {turn.turn})</div>
                          <p className="leading-relaxed bg-slate-950/50 p-2.5 rounded-xl border border-slate-900">{turn.text}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Form to submit review */}
                  <form onSubmit={handleReviewSubmit} className="border-t border-slate-800 pt-4 flex flex-col gap-4">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Evaluate claim decision</h4>
                    
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-slate-400 font-medium">Final Decision</label>
                        <select
                          value={finalDecision}
                          onChange={(e) => setFinalDecision(e.target.value)}
                          className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs focus:outline-none focus:border-cyan-500"
                        >
                          <option value="approved">Approved</option>
                          <option value="denied">Denied</option>
                          <option value="need_more_info">Need More Info</option>
                          <option value="need_documents">Need Documents</option>
                          <option value="flagged_for_review">Flagged for Review</option>
                          <option value="manual_review">Manual Review</option>
                        </select>
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-slate-400 font-medium">Closure Status</label>
                        <select
                          value={closureStatus}
                          onChange={(e) => setClosureStatus(e.target.value)}
                          className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs focus:outline-none focus:border-cyan-500"
                        >
                          <option value="awaiting_user">Awaiting User Response</option>
                          <option value="pending_review">Pending Review</option>
                          <option value="closed">Closed / Solved</option>
                        </select>
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={reviewLoading}
                      className="w-full p-3.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs rounded-2xl active:scale-95 transition disabled:opacity-50"
                    >
                      {reviewLoading ? "Submitting review..." : "Submit Claim Decision"}
                    </button>
                  </form>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-slate-500 text-xs italic py-20">
                  Select a claim from the pipeline list to inspect and review.
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-210px)] overflow-hidden">
            {/* Knowledge Document List */}
            <div className="lg:col-span-8 bg-slate-900/40 border border-slate-800 rounded-3xl p-5 overflow-y-auto flex flex-col gap-4">
              <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Versioned Policy/Regulatory Documents ({docs.length})</h2>

              {docs.length === 0 ? (
                <div className="text-center py-10 text-slate-600 text-xs italic">
                  No knowledge base documents found. Upload policies below to begin.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {docs.map((doc) => (
                    <div
                      key={doc.id}
                      className="p-4 bg-slate-950/50 border border-slate-800/80 rounded-2xl flex flex-col gap-2.5"
                    >
                      <div className="flex items-center justify-between w-full">
                        <div className="flex items-center gap-2">
                          <span className={`text-[8px] px-2 py-0.5 rounded font-extrabold uppercase ${
                            doc.document_type === "POLICY_WORDING"
                              ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                              : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                          }`}>
                            {doc.document_type.replace("_", " ")}
                          </span>
                          <span className="font-bold text-xs text-white">{doc.title}</span>
                        </div>
                        <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded-md font-mono text-slate-300">
                          Version: {doc.version}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[10px] text-slate-400 border-t border-slate-900 pt-2">
                        <div>Effective Date: <span className="text-slate-200 font-semibold">{doc.effective_date}</span></div>
                        <div>Uploaded By: <span className="text-slate-200 font-semibold">{doc.uploaded_by}</span></div>
                        <div className="sm:text-right">
                          <a
                            href={`${API_BASE}/api/v1/knowledge/${doc.id}/download?token=${token}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-cyan-400 hover:text-cyan-300 font-bold"
                          >
                            Download Document
                          </a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Document Upload Form */}
            <div className="lg:col-span-4 bg-slate-900/40 border border-slate-800 rounded-3xl p-5 overflow-y-auto">
              <form onSubmit={handleDocUpload} className="flex flex-col gap-4">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider border-b border-slate-850 pb-2">
                  Upload Policy wording / IRDAI Regulation
                </h3>

                <div className="flex flex-col gap-1.5 text-xs">
                  <label className="text-slate-400 font-medium">Document Title</label>
                  <input
                    type="text"
                    placeholder="e.g. Motor Policy Wording"
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex flex-col gap-1.5 text-xs">
                  <label className="text-slate-400 font-medium">Document Version</label>
                  <input
                    type="text"
                    placeholder="e.g. 1.0 or 2026-01"
                    value={uploadVersion}
                    onChange={(e) => setUploadVersion(e.target.value)}
                    className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex flex-col gap-1.5 text-xs">
                  <label className="text-slate-400 font-medium">Document Type</label>
                  <select
                    value={uploadDocType}
                    onChange={(e) => setUploadDocType(e.target.value)}
                    className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs focus:outline-none focus:border-cyan-500"
                  >
                    <option value="POLICY_WORDING">Policy Wording</option>
                    <option value="IRDAI_REGULATION">IRDAI Regulation</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1.5 text-xs">
                  <label className="text-slate-400 font-medium">Effective Date</label>
                  <input
                    type="date"
                    value={uploadEffDate}
                    onChange={(e) => setUploadEffDate(e.target.value)}
                    className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex flex-col gap-1.5 text-xs">
                  <label className="text-slate-400 font-medium">Upload File</label>
                  <input
                    type="file"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={uploadLoading}
                  className="w-full mt-2 p-3.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs rounded-2xl active:scale-95 transition disabled:opacity-50"
                >
                  {uploadLoading ? "Uploading & Versioning..." : "Upload Document"}
                </button>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
