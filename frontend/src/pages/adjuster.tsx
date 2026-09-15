import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import { getAuthToken, clearAuthToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const title = (v?: string) =>
  (v || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const money = (v?: number) =>
  v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN");

export interface AdjusterUser {
  id?: string;
  email?: string;
  full_name?: string;
  role?: string;
  specialization?: string;
  [key: string]: unknown;
}

export interface Claim {
  ticket_id: string;
  status: string;
  insurance_type?: string;
  event_date?: string;
  event_location?: string;
  estimated_claim_amount?: number;
  event_description?: string;
  priority?: string;
  assigned_adjuster_id?: string;
  assigned_adjuster_name?: string;
  claimant_confirmed?: boolean;
  policy_verified?: boolean;
  dynamic_requirements_complete?: boolean;
  updated_at?: string;
}

export interface KnowledgeItem {
  source_name?: string;
  document_type?: string;
  text?: string;
  score?: number;
  [key: string]: unknown;
}

export interface EvidenceItem {
  id?: string;
  evidence_id?: string;
  name?: string;
  type?: string;
  status?: string;
  url?: string;
  [key: string]: unknown;
}

export interface RequirementItem {
  label?: string;
  key?: string;
  evidence_type?: string;
  description?: string;
  [key: string]: unknown;
}

export interface CopilotAnalysis {
  summary?: string;
  coverage_observations?: string[];
  evidence_gaps?: string[];
  [key: string]: unknown;
}

export interface FileData {
  claim: Claim;
  extracted_data: Record<string, unknown>;
  conversation: { speaker: string; text: string; turn: number }[];
  requirements: RequirementItem[];
  missing_requirements: RequirementItem[];
  missing_evidence: RequirementItem[];
  evidence: EvidenceItem[];
  policy_verification: Record<string, unknown>;
  knowledge_sources: KnowledgeItem[];
  copilot: CopilotAnalysis;
}

export default function AdjusterPage() {
  const router = useRouter();
  const [user, setUser] = useState<AdjusterUser | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [selected, setSelected] = useState<string>();
  const [file, setFile] = useState<FileData>();
  const [view, setView] = useState<"queue" | "file" | "evidence" | "knowledge" | "copilot">("queue");
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeType, setKnowledgeType] = useState("policy_wording");
  const [knowledgeInsurance, setKnowledgeInsurance] = useState("");
  const [knowledgePolicy, setKnowledgePolicy] = useState("");
  const [knowledgeUploading, setKnowledgeUploading] = useState(false);
  const [newNote, setNewNote] = useState("");
  const [addingNote, setAddingNote] = useState(false);

  const headers = useCallback((): Record<string, string> => {
    const t = getAuthToken();
    return t ? { Authorization: "Bearer " + t } : {};
  }, []);

  const api = useCallback(async (path: string, opts: RequestInit = {}) => {
    const merged = new Headers(opts.headers);
    const t = getAuthToken();
    if (t) merged.set("Authorization", "Bearer " + t);
    const r = await fetch(API + path, { ...opts, headers: merged });
    if (r.status === 401) {
      clearAuthToken();
      router.push("/login");
      throw new Error("Authentication expired.");
    }
    if (!r.ok) {
      const b = (await r.json().catch(() => ({}))) as { detail?: string };
      throw new Error(b.detail || "Request failed.");
    }
    return r.json();
  }, [router]);

  const loadQueue = useCallback(async () => {
    try {
      const d = (await api("/api/v1/adjuster/queue")) as { items?: Claim[] };
      setClaims(d.items || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load claims queue.");
    }
  }, [api]);

  const openClaim = useCallback(async (id: string) => {
    setSelected(id);
    setView("file");
    setError("");
    try {
      const data = (await api("/api/v1/adjuster/claims/" + id)) as FileData;
      setFile(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load claim file.");
    }
  }, [api]);

  const loadCopilot = useCallback(async (id = selected) => {
    if (!id) return;
    setCopilotLoading(true);
    setError("");
    try {
      const d = (await api("/api/v1/adjuster/claims/" + id + "/copilot")) as {
        analysis?: CopilotAnalysis;
        sources?: KnowledgeItem[];
      };
      setFile((prev) =>
        prev
          ? {
              ...prev,
              copilot: d.analysis || {},
              knowledge_sources: d.sources || prev.knowledge_sources,
            }
          : prev
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load Copilot analysis.");
    } finally {
      setCopilotLoading(false);
    }
  }, [api, selected]);

  const searchKnowledge = async () => {
    setError("");
    try {
      const q = knowledgeQuery.trim() || "policy coverage claim requirements";
      const d = (await api(
        "/api/v1/knowledge/search?q=" +
          encodeURIComponent(q) +
          (knowledgeInsurance ? "&insurance_type=" + encodeURIComponent(knowledgeInsurance) : "") +
          (knowledgePolicy ? "&policy_number=" + encodeURIComponent(knowledgePolicy) : "")
      )) as { items?: KnowledgeItem[] };
      setKnowledgeItems(d.items || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Knowledge search failed.");
    }
  };

  const openEvidence = async (e: EvidenceItem) => {
    if (!selected) return;
    setError("");
    try {
      const evId = e.id || e.evidence_id || "";
      if (!evId) {
        if (e.url) {
          window.open(e.url, "_blank", "noopener,noreferrer");
          return;
        }
        throw new Error("Invalid evidence identifier.");
      }
      const d = (await api(
        "/api/v1/adjuster/claims/" + selected + "/evidence/" + encodeURIComponent(evId) + "/url"
      )) as { url: string };
      window.open(d.url, "_blank", "noopener,noreferrer");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to open evidence.");
    }
  };

  const uploadKnowledge = async () => {
    if (!knowledgeFile) return;
    setKnowledgeUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", knowledgeFile);
      form.append("document_type", knowledgeType);
      if (knowledgeInsurance) form.append("insurance_type", knowledgeInsurance);
      if (knowledgePolicy) form.append("policy_number", knowledgePolicy);
      const d = await fetch(API + "/api/v1/knowledge/upload", {
        method: "POST",
        headers: headers(),
        body: form,
      });
      const b = (await d.json()) as { detail?: string; source_name?: string };
      if (!d.ok) throw new Error(b.detail || "Upload failed");
      setKnowledgeFile(null);
      setSuccessMessage("Knowledge document uploaded and indexed successfully!");
      setTimeout(() => setSuccessMessage(""), 3000);
      setKnowledgeQuery(b.source_name || knowledgeQuery);
      await searchKnowledge();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to upload knowledge document.");
    } finally {
      setKnowledgeUploading(false);
    }
  };

  const update = async (status: string) => {
    if (!selected) return;
    setUpdatingStatus(true);
    setError("");
    try {
      await api("/api/v1/adjuster/claims/" + selected, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      setSuccessMessage(`Claim status updated to ${title(status)}.`);
      setTimeout(() => setSuccessMessage(""), 3000);
      await loadQueue();
      await openClaim(selected);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update claim status.");
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleAddNote = async () => {
    if (!selected || !newNote.trim()) return;
    setAddingNote(true);
    setError("");
    try {
      await api("/api/v1/adjuster/claims/" + selected, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: newNote.trim() }),
      });
      setNewNote("");
      setSuccessMessage("Adjuster note added to claim record.");
      setTimeout(() => setSuccessMessage(""), 3000);
      await openClaim(selected);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add note.");
    } finally {
      setAddingNote(false);
    }
  };

  const handleAssignClaim = async () => {
    if (!selected) return;
    setError("");
    try {
      await api("/api/v1/adjuster/claims/" + selected + "/assign", {
        method: "POST",
      });
      setSuccessMessage("Claim successfully assigned.");
      setTimeout(() => setSuccessMessage(""), 3000);
      await loadQueue();
      await openClaim(selected);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to assign claim.");
    }
  };

  useEffect(() => {
    let ignore = false;
    if (view === "copilot" && selected && !file?.copilot?.summary) {
      api("/api/v1/adjuster/claims/" + selected + "/copilot")
        .then((d: { analysis?: CopilotAnalysis; sources?: KnowledgeItem[] }) => {
          if (!ignore) {
            setFile((prev) =>
              prev
                ? {
                    ...prev,
                    copilot: d.analysis || {},
                    knowledge_sources: d.sources || prev.knowledge_sources,
                  }
                : prev
            );
          }
        })
        .catch((e: unknown) => {
          if (!ignore) {
            setError(e instanceof Error ? e.message : "Failed to load Copilot analysis.");
          }
        });
    }
    return () => {
      ignore = true;
    };
  }, [view, selected, api, file?.copilot?.summary]);

  useEffect(() => {
    const t = getAuthToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    api("/api/v1/auth/me")
      .then((u: AdjusterUser) => {
        if (u.role !== "ADJUSTER" && u.role !== "ADMIN") {
          router.replace("/claimant");
          return;
        }
        setUser(u);
        return loadQueue();
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Session error"))
      .finally(() => setLoading(false));
  }, [router, api, loadQueue]);

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-[#f7f9fb] text-sm text-[#505f76]">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined animate-spin text-xl text-[#00647c]">
            progress_activity
          </span>
          <span>Loading Adjuster Portal…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f7f9fb] text-[#191c1e] font-body">
      <header className="h-16 bg-white border-b border-[#e0e3e5] px-6 flex items-center justify-between sticky top-0 z-20 shadow-xs">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
          <div>
            <b className="font-headline text-[17px]">InsureClaimAI</b>
            <div className="text-[9px] uppercase tracking-[.12em] text-[#778187]">Adjuster Portal</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="hidden sm:block text-[11px] text-[#505f76]">{user?.email}</span>
          <button
            onClick={() => {
              clearAuthToken();
              router.push("/login");
            }}
            className="border border-[#bdc8ce] hover:border-[#00647c] rounded-lg px-3 py-1.5 text-xs font-semibold bg-white flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">logout</span>
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-64px)]">
        <aside className="hidden md:flex w-60 bg-white border-r border-[#e0e3e5] p-4 flex-col shrink-0">
          <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] px-2 py-3 font-bold">
            Operations Core
          </div>
          {[
            ["queue", "inbox", "Claims Queue"],
            ["file", "folder_open", "Claim File"],
            ["evidence", "description", "Evidence Review"],
            ["knowledge", "menu_book", "Policy & Regulations"],
            ["copilot", "auto_awesome", "AI Copilot"],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              onClick={() => {
                if ((id === "file" || id === "evidence" || id === "copilot") && !selected && claims.length > 0) {
                  openClaim(claims[0].ticket_id);
                }
                setView(id as typeof view);
              }}
              className={
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-xs font-semibold mb-1 cursor-pointer transition-colors " +
                (view === id
                  ? "bg-[#d0e1fb] text-[#254b59] font-bold shadow-2xs"
                  : "text-[#526066] hover:bg-[#f2f4f6]")
              }
            >
              <span className="material-symbols-outlined text-[18px]">{icon}</span>
              <span>{label}</span>
            </button>
          ))}
          <div className="mt-auto border-t border-[#e0e3e5] pt-4 px-2 text-xs">
            <b>{user?.full_name || "Adjuster"}</b>
            <div className="text-[10px] text-[#6e797e] mt-0.5">Claims Operations</div>
          </div>
        </aside>

        <main className="flex-1 min-w-0">
          <div className="max-w-[1450px] mx-auto p-5 md:p-7">
            {error && (
              <div className="mb-5 p-3.5 rounded-xl bg-[#ffefed] border border-[#f1b7b1] text-xs text-[#93000a] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
                  <span>{error}</span>
                </div>
                <button
                  onClick={() => setError("")}
                  className="text-xs text-[#ba1a1a] hover:underline font-bold"
                >
                  Dismiss
                </button>
              </div>
            )}

            {successMessage && (
              <div className="mb-5 p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-xs text-emerald-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base text-emerald-600">check_circle</span>
                  <span>{successMessage}</span>
                </div>
                <button
                  onClick={() => setSuccessMessage("")}
                  className="text-xs text-emerald-800 hover:underline font-bold"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Mobile Tab Navigation */}
            <div className="flex gap-1.5 mb-5 md:hidden overflow-x-auto pb-1">
              {[
                ["queue", "Queue"],
                ["file", "Claim File"],
                ["evidence", "Evidence"],
                ["copilot", "Copilot"],
                ["knowledge", "Policies"],
              ].map(([v, lbl]) => (
                <button
                  key={v}
                  onClick={() => {
                    if ((v === "file" || v === "evidence" || v === "copilot") && !selected && claims.length > 0) {
                      openClaim(claims[0].ticket_id);
                    }
                    setView(v as typeof view);
                  }}
                  className={
                    "px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap cursor-pointer transition-colors " +
                    (view === v ? "bg-[#00647c] text-white" : "bg-white border border-[#e0e3e5] text-[#526066]")
                  }
                >
                  {lbl}
                </button>
              ))}
            </div>

            {view === "queue" && (
              <>
                <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
                  <div>
                    <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] mb-1 font-bold">
                      Operations / Intake
                    </div>
                    <h1 className="font-headline text-2xl font-bold">Claims Queue</h1>
                    <p className="text-xs text-[#657177] mt-0.5">
                      Claims that completed conversational intake, verification, and assignment.
                    </p>
                  </div>
                  <button
                    onClick={() => loadQueue()}
                    className="border border-[#bdc8ce] hover:border-[#00647c] bg-white rounded-lg px-3 py-2 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto"
                  >
                    <span className="material-symbols-outlined text-[16px]">refresh</span>
                    <span>Refresh</span>
                  </button>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
                  {[
                    ["Total claims", claims.length, "inbox"],
                    ["Assigned", claims.filter((c) => c.assigned_adjuster_id).length, "person_check"],
                    ["Evidence pending", claims.filter((c) => c.status === "pending_evidence").length, "assignment_late"],
                    ["Policy verified", claims.filter((c) => c.policy_verified).length, "verified"],
                  ].map(([label, count, icon]) => (
                    <div key={label as string} className="bg-white border border-[#e0e3e5] rounded-xl p-4 shadow-2xs">
                      <div className="flex justify-between text-[10px] uppercase tracking-[.08em] text-[#778187] font-semibold">
                        <span>{label}</span>
                        <span className="material-symbols-outlined text-[#00647c] text-[18px]">{icon}</span>
                      </div>
                      <div className="font-headline text-2xl font-bold mt-2">{count}</div>
                    </div>
                  ))}
                </div>

                <div className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-sm">
                  <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
                    <div>
                      <h2 className="font-headline font-bold">Review Queue</h2>
                      <p className="text-[11px] text-[#6e797e] mt-0.5">
                        Automatically assigned claims requiring adjuster action.
                      </p>
                    </div>
                    <span className="text-[10px] text-[#6e797e] font-semibold">{claims.length} records</span>
                  </div>

                  <div className="hidden md:grid grid-cols-5 gap-4 px-5 py-3 bg-[#f7f9fb] text-[9px] uppercase tracking-[.1em] font-semibold text-[#778187] border-b border-[#e0e3e5]">
                    <span>Claim</span>
                    <span>Type</span>
                    <span>Status</span>
                    <span>Amount</span>
                    <span>Assigned</span>
                  </div>

                  {claims.length === 0 ? (
                    <div className="py-16 text-center">
                      <span className="material-symbols-outlined text-[#9aa5aa] text-4xl">inbox</span>
                      <h3 className="font-headline font-semibold mt-3">No claims in queue</h3>
                      <p className="text-xs text-[#6e797e] mt-1">
                        Verified claims will appear here after automatic assignment.
                      </p>
                    </div>
                  ) : (
                    claims.map((c) => (
                      <button
                        key={c.ticket_id}
                        onClick={() => openClaim(c.ticket_id)}
                        className={
                          "w-full text-left grid grid-cols-1 md:grid-cols-5 gap-2 md:gap-4 px-5 py-4 border-t border-[#edf0f1] hover:bg-[#f8fbfc] transition-colors cursor-pointer " +
                          (selected === c.ticket_id ? "bg-[#eef7fa] border-l-4 border-l-[#00647c]" : "")
                        }
                      >
                        <div>
                          <b className="text-[13px] text-[#00647c]">#{c.ticket_id}</b>
                          <div className="text-[10px] text-[#6e797e] mt-0.5">
                            {c.event_date || "Date pending"} · {c.event_location || "Location pending"}
                          </div>
                        </div>
                        <div className="text-xs capitalize">{title(c.insurance_type)}</div>
                        <div>
                          <span
                            className={
                              "px-2.5 py-1 rounded-full text-[9px] uppercase font-bold " +
                              (c.status === "pending_evidence"
                                ? "bg-[#fff0d8] text-[#895900]"
                                : c.status === "under_review"
                                ? "bg-cyan-100 text-cyan-800"
                                : c.status === "approved"
                                ? "bg-emerald-100 text-emerald-800"
                                : c.status === "rejected"
                                ? "bg-rose-100 text-rose-800"
                                : "bg-[#dfeafc] text-[#345a72]")
                            }
                          >
                            {title(c.status)}
                          </span>
                        </div>
                        <div className="text-xs font-semibold">{money(c.estimated_claim_amount)}</div>
                        <div className="text-xs text-[#526066]">
                          {c.assigned_adjuster_name || (
                            <span className="text-[#00647c] italic">Auto-assigned</span>
                          )}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </>
            )}

            {view !== "queue" && view !== "knowledge" && !file && (
              <div className="bg-white border border-[#e0e3e5] rounded-xl p-12 text-center shadow-sm">
                <span className="material-symbols-outlined text-4xl text-[#bdc8ce] mb-2">folder_open</span>
                <h2 className="font-headline font-bold text-lg text-[#191c1e]">Select a claim</h2>
                <p className="text-xs text-[#6e797e] mt-1">Open a claim from the queue to review its file.</p>
                <button
                  onClick={() => setView("queue")}
                  className="mt-5 bg-[#00647c] hover:bg-[#004e61] text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors cursor-pointer"
                >
                  Open Claims Queue
                </button>
              </div>
            )}

            {view === "knowledge" && (
              <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-sm">
                <div className="px-5 py-4 border-b border-[#e0e3e5]">
                  <h2 className="font-headline font-bold text-lg">Policy & Regulatory Knowledge</h2>
                  <p className="text-[11px] text-[#6e797e] mt-0.5">
                    Upload policy wording, guidelines, and claim rules. Retrieved during claimant intake and AI Copilot.
                  </p>
                </div>
                <div className="p-5 grid xl:grid-cols-[1fr_1fr] gap-5">
                  <div className="border border-[#e0e3e5] rounded-xl p-5 bg-[#fcfdfe]">
                    <h3 className="font-headline font-bold text-sm">Update Knowledge Base</h3>
                    <p className="text-[11px] text-[#6e797e] mt-0.5">
                      Upload PDF or text documents to embed into vector storage.
                    </p>
                    <div className="grid gap-3 mt-4">
                      <div>
                        <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                          Document Type
                        </label>
                        <select
                          value={knowledgeType}
                          onChange={(e) => setKnowledgeType(e.target.value)}
                          className="w-full border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs bg-white cursor-pointer"
                        >
                          <option value="policy_wording">Policy wording</option>
                          <option value="regulation">Regulation</option>
                          <option value="guideline">Guideline</option>
                          <option value="claim_requirement">Claim requirement</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                          Insurance Type (optional)
                        </label>
                        <input
                          value={knowledgeInsurance}
                          onChange={(e) => setKnowledgeInsurance(e.target.value)}
                          placeholder="e.g. motor, health, home"
                          className="w-full border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs bg-white"
                        />
                      </div>

                      <div>
                        <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                          Policy Number (optional)
                        </label>
                        <input
                          value={knowledgePolicy}
                          onChange={(e) => setKnowledgePolicy(e.target.value)}
                          placeholder="e.g. POL-8492-AX"
                          className="w-full border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs bg-white"
                        />
                      </div>

                      <div>
                        <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                          File (.pdf, .txt, .md, .csv)
                        </label>
                        <input
                          type="file"
                          accept=".pdf,.txt,.md,.csv"
                          onChange={(e) => setKnowledgeFile(e.target.files?.[0] || null)}
                          className="w-full text-xs text-[#505f76] file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-[#00647c] file:text-white hover:file:bg-[#004e61] cursor-pointer"
                        />
                      </div>

                      <button
                        disabled={!knowledgeFile || knowledgeUploading}
                        onClick={uploadKnowledge}
                        className="bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white rounded-lg py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer mt-2"
                      >
                        {knowledgeUploading ? (
                          <>
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            <span>Uploading & Indexing...</span>
                          </>
                        ) : (
                          <>
                            <span className="material-symbols-outlined text-base">upload</span>
                            <span>Upload & Index</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="border border-[#e0e3e5] rounded-xl p-5 bg-[#fcfdfe] flex flex-col">
                    <h3 className="font-headline font-bold text-sm">Search Retrieved Knowledge</h3>
                    <p className="text-[11px] text-[#6e797e] mt-0.5">
                      Test pgvector / BM25 semantic retrieval over ingested policy clauses.
                    </p>
                    <div className="flex gap-2 mt-4">
                      <input
                        value={knowledgeQuery}
                        onChange={(e) => setKnowledgeQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && searchKnowledge()}
                        placeholder="e.g. water damage exclusions, deductible limits"
                        className="border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs flex-1 bg-white"
                      />
                      <button
                        onClick={searchKnowledge}
                        className="bg-[#00647c] hover:bg-[#004e61] text-white rounded-lg px-4 text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-sm">search</span>
                        <span>Search</span>
                      </button>
                    </div>
                    <div className="mt-4 max-h-[380px] overflow-y-auto space-y-3 flex-1 pr-1">
                      {knowledgeItems.length ? (
                        knowledgeItems.map((x, i) => (
                          <div key={i} className="bg-white border border-[#e0e3e5] rounded-lg p-3 shadow-2xs">
                            <div className="flex justify-between items-start gap-2">
                              <b className="text-xs text-[#00647c]">{x.source_name || "Document"}</b>
                              <span className="text-[9px] uppercase font-bold px-2 py-0.5 rounded bg-slate-100 text-[#6e797e]">
                                {x.document_type || "policy"}
                              </span>
                            </div>
                            <p className="text-[11px] leading-5 mt-2 text-[#526066]">{x.text}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-[#6e797e] py-12 text-center">
                          No retrieval results. Enter a query or upload documents above.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </section>
            )}

            {file && (
              <>
                <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-5">
                  <div>
                    <button
                      onClick={() => setView("queue")}
                      className="text-[11px] text-[#00647c] hover:text-[#004e61] font-semibold flex items-center gap-1 mb-1.5 cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[15px]">arrow_back</span>
                      <span>Back to Queue</span>
                    </button>
                    <h1 className="font-headline text-2xl font-bold">#{file.claim.ticket_id}</h1>
                    <p className="text-xs text-[#657177] mt-0.5">
                      {title(file.claim.insurance_type)} · {file.claim.event_location || "Location pending"} ·{" "}
                      {money(file.claim.estimated_claim_amount)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        "px-3 py-1.5 rounded-full text-[10px] font-bold uppercase " +
                        (file.claim.policy_verified
                          ? "bg-[#d9efe4] text-[#2f6b4f]"
                          : "bg-amber-100 text-amber-800")
                      }
                    >
                      {file.claim.policy_verified ? "Policy Verified" : "Verification Pending"}
                    </span>
                    <span
                      className={
                        "px-3 py-1.5 rounded-full text-[10px] font-bold uppercase " +
                        (file.claim.status === "approved"
                          ? "bg-emerald-100 text-emerald-800"
                          : file.claim.status === "rejected"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-cyan-100 text-cyan-800")
                      }
                    >
                      Status: {title(file.claim.status)}
                    </span>
                  </div>
                </div>

                {view === "file" && (
                  <div className="grid xl:grid-cols-[1fr_360px] gap-5">
                    <div className="space-y-5">
                      <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
                        <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
                          <div>
                            <h2 className="font-headline font-bold text-base">Claim File Details</h2>
                            <p className="text-[11px] text-[#6e797e] mt-0.5">
                              Structured facts extracted from the claimant conversation.
                            </p>
                          </div>
                          {!file.claim.assigned_adjuster_id && (
                            <button
                              onClick={handleAssignClaim}
                              className="bg-[#00647c] hover:bg-[#004e61] text-white text-xs px-3 py-1.5 rounded-lg font-semibold cursor-pointer"
                            >
                              Assign Claim
                            </button>
                          )}
                        </div>
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[#e0e3e5]">
                          {[
                            ["Policy", String(file.extracted_data?.policy_id || "—")],
                            ["Incident date", file.claim.event_date || "—"],
                            ["Insurance", title(file.claim.insurance_type)],
                            ["Location", file.claim.event_location || "—"],
                            ["Estimated loss", money(file.claim.estimated_claim_amount)],
                            ["Assigned to", file.claim.assigned_adjuster_name || "Unassigned"],
                          ].map(([lbl, val]) => (
                            <div key={lbl} className="bg-white p-4">
                              <div className="text-[9px] uppercase tracking-[.08em] text-[#778187] font-bold">
                                {lbl}
                              </div>
                              <div className="text-[13px] font-semibold mt-1 text-[#191c1e]">{val}</div>
                            </div>
                          ))}
                        </div>
                        <div className="p-5">
                          <div className="text-[9px] uppercase tracking-[.08em] text-[#778187] font-bold">
                            Incident narrative
                          </div>
                          <p className="text-sm leading-relaxed mt-2 text-[#334155]">
                            {file.claim.event_description || "No incident narrative recorded."}
                          </p>
                        </div>
                      </section>

                      <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
                        <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
                          <h2 className="font-headline font-bold text-base">Voice Transcript</h2>
                          <span className="text-[10px] text-[#6e797e] font-semibold">
                            {file.conversation.length} turns recorded
                          </span>
                        </div>
                        <div className="p-5 space-y-3.5 max-h-[480px] overflow-y-auto">
                          {file.conversation.length ? (
                            file.conversation.map((t, i) => (
                              <div key={i}>
                                <div className="text-[9px] uppercase tracking-[.08em] text-[#778187] mb-1 font-bold">
                                  {t.speaker}
                                </div>
                                <div
                                  className={
                                    "max-w-[90%] rounded-xl px-4 py-2.5 text-[13px] leading-5 " +
                                    (t.speaker === "Claimant"
                                      ? "bg-[#e9f5f8] text-[#0f3d4a] border border-[#d0eaf1]"
                                      : "bg-[#f2f4f6] text-[#334155]")
                                  }
                                >
                                  {t.text}
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-[#6e797e]">No transcript recorded for this claim.</p>
                          )}
                        </div>
                      </section>
                    </div>

                    <aside className="space-y-5">
                      <section className="bg-white border border-[#e0e3e5] rounded-xl p-5 shadow-2xs">
                        <h2 className="font-headline font-bold text-[15px]">Claim Progress</h2>
                        {(
                          [
                            ["Claimant confirmed", Boolean(file.claim.claimant_confirmed)],
                            ["Policy verified", Boolean(file.claim.policy_verified)],
                            ["Dynamic intake", Boolean(file.claim.dynamic_requirements_complete)],
                            ["Evidence uploaded", (file.evidence || []).length > 0],
                          ] as [string, boolean][]
                        ).map(([label, done]) => (
                          <div
                            key={label}
                            className="flex justify-between items-center text-xs py-2.5 border-b border-[#f0f2f4] last:border-0"
                          >
                            <span className="font-medium">{label}</span>
                            <span
                              className={
                                "font-bold text-[11px] px-2 py-0.5 rounded-full " +
                                (done
                                  ? "bg-emerald-100 text-[#2f6b4f]"
                                  : "bg-amber-100 text-[#a86516]")
                              }
                            >
                              {done ? "Complete" : "Pending"}
                            </span>
                          </div>
                        ))}
                      </section>

                      <section className="bg-white border border-[#e0e3e5] rounded-xl p-5 shadow-2xs">
                        <h2 className="font-headline font-bold text-[15px]">Adjuster Actions</h2>
                        <p className="text-[11px] text-[#6e797e] leading-relaxed mt-1">
                          Review evidence and Copilot guidance before modifying claim workflow state.
                        </p>
                        <div className="grid gap-2.5 mt-4">
                          <button
                            disabled={updatingStatus}
                            onClick={() => update("under_review")}
                            className="bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer flex items-center justify-center gap-1.5"
                          >
                            {updatingStatus ? (
                              <span className="material-symbols-outlined text-sm animate-spin">
                                progress_activity
                              </span>
                            ) : (
                              <span className="material-symbols-outlined text-base">rate_review</span>
                            )}
                            <span>Start Review</span>
                          </button>
                          <button
                            disabled={updatingStatus}
                            onClick={() => update("pending_evidence")}
                            className="border border-[#bdc8ce] hover:border-[#00647c] bg-white rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer flex items-center justify-center gap-1.5"
                          >
                            <span className="material-symbols-outlined text-base">attach_file</span>
                            <span>Request Evidence</span>
                          </button>
                        </div>
                      </section>

                      <section className="bg-white border border-[#e0e3e5] rounded-xl p-5 shadow-2xs">
                        <h2 className="font-headline font-bold text-[15px]">Add Internal Note</h2>
                        <textarea
                          rows={3}
                          value={newNote}
                          onChange={(e) => setNewNote(e.target.value)}
                          placeholder="Log notes about investigation, customer calls, or next steps..."
                          className="w-full border border-[#cbd5e1] rounded-lg p-2.5 text-xs mt-2 bg-white"
                        />
                        <button
                          disabled={addingNote || !newNote.trim()}
                          onClick={handleAddNote}
                          className="w-full mt-2 bg-slate-800 hover:bg-slate-900 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          {addingNote ? "Saving Note..." : "Save Adjuster Note"}
                        </button>
                      </section>
                    </aside>
                  </div>
                )}

                {view === "evidence" && (
                  <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
                    <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
                      <div>
                        <h2 className="font-headline font-bold text-base">Evidence Review</h2>
                        <p className="text-[11px] text-[#6e797e] mt-0.5">
                          Required documents and claimant uploads.
                        </p>
                      </div>
                      <button
                        onClick={() => openClaim(file.claim.ticket_id)}
                        className="text-xs text-[#00647c] font-semibold hover:underline flex items-center gap-1"
                      >
                        <span className="material-symbols-outlined text-sm">refresh</span>
                        <span>Refresh Evidence</span>
                      </button>
                    </div>
                    <div className="p-5">
                      {(file.missing_evidence || []).length > 0 && (
                        <div className="mb-6">
                          <div className="text-[9px] uppercase tracking-[.08em] text-[#778187] font-bold mb-2">
                            Missing Required Evidence
                          </div>
                          <div className="grid gap-2">
                            {(file.missing_evidence || []).map((r, i) => (
                              <div
                                key={i}
                                className="text-xs bg-[#fff8ec] border border-[#fce6c5] rounded-lg px-3.5 py-2.5 text-[#895900] flex items-center gap-2"
                              >
                                <span className="material-symbols-outlined text-base">warning</span>
                                <span>
                                  <b>{r.label || r.key}</b> — Evidence type: {r.evidence_type || "Document"}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="text-[9px] uppercase tracking-[.08em] text-[#778187] font-bold mb-2">
                        Uploaded Documents & Media
                      </div>

                      {file.evidence && file.evidence.length > 0 ? (
                        <div className="divide-y divide-[#edf0f1]">
                          {file.evidence.map((e, i) => (
                            <div key={i} className="py-3.5 flex items-center justify-between gap-3">
                              <div className="flex items-center gap-3">
                                <span className="material-symbols-outlined text-[#00647c] text-2xl">
                                  description
                                </span>
                                <div>
                                  <b className="text-sm text-[#191c1e]">{e.name || e.type || "Evidence Document"}</b>
                                  <p className="text-[11px] text-[#6e797e] mt-0.5">
                                    {e.type || "Document"} · {e.status || "Uploaded"}
                                  </p>
                                </div>
                              </div>
                              <button
                                onClick={() => openEvidence(e)}
                                className="text-xs bg-[#00647c] hover:bg-[#004e61] text-white px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer flex items-center gap-1"
                              >
                                <span className="material-symbols-outlined text-sm">open_in_new</span>
                                <span>View File</span>
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="py-14 text-center text-xs text-[#6e797e] bg-[#fcfdfe] border border-dashed border-[#cbd5e1] rounded-xl">
                          <span className="material-symbols-outlined text-3xl text-[#cbd5e1] mb-1">
                            folder_open
                          </span>
                          <p>No evidence uploaded for this claim yet.</p>
                          <button
                            onClick={() => update("pending_evidence")}
                            className="mt-3 text-xs text-[#00647c] font-bold hover:underline"
                          >
                            Mark claim as Pending Evidence
                          </button>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                {view === "copilot" && (
                  <div className="grid xl:grid-cols-[1fr_360px] gap-5">
                    <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
                      <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
                        <div>
                          <h2 className="font-headline font-bold text-base">AI Adjuster Copilot</h2>
                          <p className="text-[11px] text-[#6e797e] mt-0.5">
                            Advisory analysis grounded in policy clauses and claim facts.
                          </p>
                        </div>
                        <button
                          onClick={() => loadCopilot(file.claim.ticket_id)}
                          disabled={copilotLoading}
                          className="text-xs bg-[#00647c] hover:bg-[#004e61] text-white px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-sm">
                            {copilotLoading ? "progress_activity" : "refresh"}
                          </span>
                          <span>{copilotLoading ? "Analyzing..." : "Re-run Analysis"}</span>
                        </button>
                      </div>

                      <div className="p-5 space-y-4">
                        {copilotLoading ? (
                          <div className="py-14 text-center text-xs text-[#6e797e]">
                            <span className="material-symbols-outlined animate-spin text-2xl text-[#00647c] mb-2">
                              progress_activity
                            </span>
                            <p>Running grounded Copilot analysis with pgvector retrieval...</p>
                          </div>
                        ) : file.copilot?.summary ? (
                          <>
                            <div className="border-l-[3px] border-[#00647c] bg-[#f4f9fa] p-4 text-xs leading-relaxed text-[#0f3d4a] rounded-r-lg">
                              <b className="block text-[11px] uppercase tracking-wider text-[#00647c] mb-1 font-bold">
                                Executive Summary
                              </b>
                              {file.copilot.summary}
                            </div>

                            {(file.copilot.coverage_observations || []).map((x, i) => (
                              <div key={i} className="bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg p-3 text-xs">
                                <b className="text-[#00647c]">Coverage Observation</b>
                                <p className="mt-1 leading-relaxed text-[#526066]">{x}</p>
                              </div>
                            ))}

                            {(file.copilot.evidence_gaps || []).map((x, i) => (
                              <div key={i} className="bg-[#fff8ec] border border-[#fce6c5] rounded-lg p-3 text-xs">
                                <b className="text-[#895900]">Evidence Gap</b>
                                <p className="mt-1 leading-relaxed text-[#895900]">{x}</p>
                              </div>
                            ))}

                            {(file.knowledge_sources || []).length > 0 && (
                              <div className="border-t border-[#e0e3e5] pt-4 mt-4">
                                <b className="text-xs text-[#191c1e]">Retrieved Grounding Sources</b>
                                {(file.knowledge_sources || []).map((s, i) => (
                                  <div
                                    key={i}
                                    className="mt-2 text-[10px] bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg p-3"
                                  >
                                    <b className="text-[#00647c]">{s.source_name || "Policy Document"}</b>
                                    <p className="mt-1 text-[#657177] leading-relaxed">
                                      {s.text?.slice(0, 500)}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        ) : (
                          <div className="py-14 text-center text-xs text-[#6e797e]">
                            <span className="material-symbols-outlined text-3xl text-[#cbd5e1] mb-1">
                              auto_awesome
                            </span>
                            <p>Copilot analysis is not available yet.</p>
                            <button
                              onClick={() => loadCopilot(file.claim.ticket_id)}
                              className="mt-3 bg-[#00647c] text-white px-3.5 py-1.5 rounded-lg font-semibold"
                            >
                              Run Analysis Now
                            </button>
                          </div>
                        )}
                      </div>
                    </section>

                    <aside className="bg-white border border-[#e0e3e5] rounded-xl p-5 h-fit shadow-2xs">
                      <h2 className="font-headline font-bold text-[15px]">Decision Control</h2>
                      <p className="text-[11px] text-[#6e797e] leading-relaxed mt-1">
                        AI analysis is purely advisory. The adjuster owns the final adjudication decision.
                      </p>
                      <div className="grid gap-2.5 mt-5">
                        <button
                          disabled={updatingStatus}
                          onClick={() => update("pending_evidence")}
                          className="border border-[#bdc8ce] hover:border-[#00647c] rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          Need More Evidence
                        </button>
                        <button
                          disabled={updatingStatus}
                          onClick={() => update("approved")}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer shadow-xs"
                        >
                          Approve Claim
                        </button>
                        <button
                          disabled={updatingStatus}
                          onClick={() => update("rejected")}
                          className="border border-[#d9a7a2] text-[#93000a] hover:bg-rose-50 rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          Reject Claim
                        </button>
                      </div>
                    </aside>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
