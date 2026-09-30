import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import { getAuthToken, clearAuthToken } from "@/lib/auth";
import { useAuthApi } from "@/lib/useAuthApi";
import { apiFetch } from "@/lib/api";
import {
  AdjusterTopBar,
  AdjusterSidebar,
  ClaimsQueueView,
  AdjusterKnowledgePanel,
  ClaimFileView,
  EvidenceReviewView,
  AdjusterCopilotPanel,
  AdjusterUser,
  Claim,
  FileData,
  KnowledgeItem,
  EvidenceItem,
  CopilotAnalysis,
  AdjusterViewType,
  title,
  money,
} from "@/components/adjuster";


export default function AdjusterPage() {
  const router = useRouter();
  const [user, setUser] = useState<AdjusterUser | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [selected, setSelected] = useState<string>();
  const [file, setFile] = useState<FileData>();
  const [view, setView] = useState<AdjusterViewType>("queue");
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotMessage, setCopilotMessage] = useState("");
  const [copilotChat, setCopilotChat] = useState<Array<{ speaker: string; message: string; created_at?: string }>>([]);
  const [newNote, setNewNote] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  const [evidenceRequestText, setEvidenceRequestText] = useState("");
  const [sendingEvidenceRequest, setSendingEvidenceRequest] = useState(false);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeType, setKnowledgeType] = useState("policy_wording");
  const [knowledgeInsurance, setKnowledgeInsurance] = useState("");
  const [knowledgePolicy, setKnowledgePolicy] = useState("");
  const [knowledgeUploading, setKnowledgeUploading] = useState(false);

  const api = useAuthApi();

  const loadQueue = useCallback(async () => {
    try {
      const d = (await api("/api/v1/adjuster/queue")) as { items?: Claim[] };
      setClaims(d.items || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load claims queue.");
    }
  }, [api]);

  const openClaim = useCallback(
    async (id: string, nextView: AdjusterViewType = "file") => {
      setSelected(id);
      setView(nextView);
      setError("");
      try {
        const data = (await api("/api/v1/adjuster/claims/" + id)) as FileData;
        setFile(data);
        if (data.copilot_chat) setCopilotChat(data.copilot_chat);
        else setCopilotChat([]);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load claim file.");
      }
    },
    [api]
  );

  const loadCopilot = useCallback(
    async (id = selected) => {
      if (!id) return;
      setCopilotLoading(true);
      setError("");
      try {
        const d = (await api("/api/v1/adjuster/claims/" + id + "/copilot")) as {
          analysis?: CopilotAnalysis;
          sources?: KnowledgeItem[];
          chat?: Array<{ speaker: string; message: string; created_at?: string }>;
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
        if (d.chat) setCopilotChat(d.chat);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load Copilot analysis.");
      } finally {
        setCopilotLoading(false);
      }
    },
    [api, selected]
  );

  useEffect(() => {
    if (view === "copilot" && selected && file && (!file.copilot || (!file.copilot.executive_summary && !file.copilot.summary)) && !copilotLoading) {
      void loadCopilot(selected);
    }
  }, [view, selected, file, copilotLoading, loadCopilot]);

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

  const requestEvidence = useCallback(async () => {
    if (!selected || evidenceRequestText.trim().length < 5) return;
    setSendingEvidenceRequest(true);
    try {
      await api("/api/v1/adjuster/claims/" + selected + "/evidence-requests", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({request_text:evidenceRequestText.trim()})
      });
      setEvidenceRequestText("");
      setSuccessMessage("Evidence request sent to claimant.");
      setTimeout(()=>setSuccessMessage(""),3000);
      await loadQueue(); await openClaim(selected);
    } catch(e:unknown){setError(e instanceof Error?e.message:"Failed to send evidence request.");}
    finally{setSendingEvidenceRequest(false);}
  },[api,selected,evidenceRequestText,loadQueue,openClaim]);

  const searchKnowledge = useCallback(async () => {
    try{
      const d=await api("/api/v1/knowledge/search?q="+encodeURIComponent(knowledgeQuery.trim()||"policy coverage claim requirements")) as {items?:KnowledgeItem[]};
      setKnowledgeItems(d.items||[]);
    }catch(e:unknown){setError(e instanceof Error?e.message:"Knowledge search failed.");}
  },[api,knowledgeQuery]);

  const uploadKnowledge = useCallback(async () => {
    if(!knowledgeFile)return;
    setKnowledgeUploading(true);
    try{
      const form=new FormData();
      form.append("file",knowledgeFile); form.append("document_type",knowledgeType);
      if(knowledgeInsurance)form.append("insurance_type",knowledgeInsurance);
      if(knowledgePolicy)form.append("policy_number",knowledgePolicy);
      const d=await apiFetch<{source_name?:string}>("/api/v1/knowledge/upload",{method:"POST",headers:{Authorization:"Bearer "+(getAuthToken()||"")},body:form});
      setKnowledgeFile(null); setKnowledgeQuery(d.source_name||""); await searchKnowledge();
    }catch(e:unknown){setError(e instanceof Error?e.message:"Knowledge upload failed.");}
    finally{setKnowledgeUploading(false);}
  },[apiFetch,knowledgeFile,knowledgeType,knowledgeInsurance,knowledgePolicy,searchKnowledge]);

  const sendCopilotMessage = useCallback(
    async (customText?: string) => {
      const text = (typeof customText === "string" ? customText : copilotMessage).trim();
      if (!selected || !text) return;
      setCopilotMessage("");
      setCopilotLoading(true);
      setCopilotChat((prev) => [
        ...prev,
        { speaker: "adjuster", message: text, created_at: new Date().toISOString() },
      ]);
      try {
        const d = (await api("/api/v1/adjuster/claims/" + selected + "/copilot/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        })) as { chat?: Array<{ speaker: string; message: string; created_at?: string }> };
        if (d.chat) setCopilotChat(d.chat);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Copilot chat is unavailable.");
      } finally {
        setCopilotLoading(false);
      }
    },
    [api, selected, copilotMessage]
  );

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
    if (view === "copilot" && selected && !file?.copilot?.summary && !file?.copilot?.executive_summary) {
      setCopilotLoading(true);
      api<{ analysis?: CopilotAnalysis; sources?: KnowledgeItem[]; chat?: any[] }>("/api/v1/adjuster/claims/" + selected + "/copilot")
        .then((d) => {
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
            if (d.chat) setCopilotChat(d.chat);
          }
        })
        .catch((e: unknown) => {
          if (!ignore) {
            setError(e instanceof Error ? e.message : "Failed to load Copilot analysis.");
          }
        })
        .finally(() => {
          if (!ignore) setCopilotLoading(false);
        });
    }
    return () => {
      ignore = true;
    };
  }, [view, selected, api, file?.copilot?.summary, file?.copilot?.executive_summary]);

  useEffect(() => {
    const t = getAuthToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    api<AdjusterUser>("/api/v1/auth/me")
      .then((u) => {
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

  const handleSignOut = () => {
    clearAuthToken();
    router.push("/login");
  };

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
      <AdjusterTopBar user={user} onSignOut={handleSignOut} />

      <div className="flex min-h-[calc(100vh-64px)]">
        <AdjusterSidebar
          view={view}
          setView={setView}
          user={user}
          selected={selected}
          claims={claims}
          onOpenClaim={openClaim}
        />

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
                  className="text-xs text-[#ba1a1a] hover:underline font-bold cursor-pointer"
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
                  className="text-xs text-emerald-800 hover:underline font-bold cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            <div className="flex gap-1.5 mb-5 md:hidden overflow-x-auto pb-1">
              {[["queue","Claims Queue"],["knowledge","Policy & Regulations"],["file","Claim Details"],["evidence","Evidence Review"],["copilot","AI Copilot"]].map(([v,lbl])=><button key={v} onClick={()=>{if((v==="file"||v==="evidence"||v==="copilot")&&!selected&&claims.length)void openClaim(claims[0].ticket_id);setView(v as AdjusterViewType)}} className={"px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap "+(view===v?"bg-[#00647c] text-white":"bg-white border border-[#e0e3e5] text-[#526066]")}>{lbl}</button>)}
            </div>

            {view === "queue" && <ClaimsQueueView claims={claims} selected={selected} onOpenClaim={openClaim} onRefresh={loadQueue} />}

            {view === "knowledge" && <AdjusterKnowledgePanel
              knowledgeType={knowledgeType} setKnowledgeType={setKnowledgeType}
              knowledgeInsurance={knowledgeInsurance} setKnowledgeInsurance={setKnowledgeInsurance}
              knowledgePolicy={knowledgePolicy} setKnowledgePolicy={setKnowledgePolicy}
              knowledgeFile={knowledgeFile} setKnowledgeFile={setKnowledgeFile}
              knowledgeUploading={knowledgeUploading} onUploadKnowledge={uploadKnowledge}
              knowledgeQuery={knowledgeQuery} setKnowledgeQuery={setKnowledgeQuery}
              knowledgeItems={knowledgeItems} onSearchKnowledge={searchKnowledge}
            />}

            {file && view !== "queue" && view !== "knowledge" && (
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
                  <ClaimFileView
                    file={file}
                    onAssignClaim={handleAssignClaim}
                    updatingStatus={updatingStatus}
                    onUpdateStatus={update}
                    newNote={newNote}
                    setNewNote={setNewNote}
                    addingNote={addingNote}
                    onAddNote={handleAddNote}
                    evidenceRequestText={evidenceRequestText}
                    setEvidenceRequestText={setEvidenceRequestText}
                    sendingEvidenceRequest={sendingEvidenceRequest}
                    onRequestEvidence={requestEvidence}
                  />
                )}

                {view === "evidence" && (
                  <EvidenceReviewView
                    file={file}
                    onRefresh={() => openClaim(file.claim.ticket_id)}
                    onOpenEvidence={openEvidence}
                    onUpdateStatus={update}
                  />
                )}

                {view === "copilot" && (
                  <AdjusterCopilotPanel
                    file={file}
                    copilotLoading={copilotLoading}
                    updatingStatus={updatingStatus}
                    onLoadCopilot={loadCopilot}
                    onUpdateStatus={update}
                    copilotMessage={copilotMessage}
                    setCopilotMessage={setCopilotMessage}
                    copilotChat={copilotChat}
                    onSendCopilotMessage={sendCopilotMessage}
                  />
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
