import React, { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { ClaimantSidebar, ClaimSummary } from "@/components/claimant/ClaimantSidebar";
import { ClaimantTopBar } from "@/components/claimant/ClaimantTopBar";
import { getAuthToken, clearAuthToken, verifySessionOrRedirect } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

type TrackedClaim = ClaimSummary & { extracted_data?: Record<string, unknown>; evidence_requests?: Array<any>; open_request_count?: number; };

const postSubmission = new Set(["submitted","assigned","under_review","pending_evidence","approved","partially_approved","rejected","escalated","closed"]);

export default function TrackClaimPage() {
  const router = useRouter();
  const [claims, setClaims] = useState<TrackedClaim[]>([]);
  const [selected, setSelected] = useState<TrackedClaim>();
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string | null>(null);
  const [responseNotes, setResponseNotes] = useState<Record<string,string>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async (token: string) => {
    setLoading(true);
    try {
      const d = await apiFetch<{items?: TrackedClaim[]}>("/api/v1/claims/track", { token });
      const items = (d.items || []).filter((c) => postSubmission.has(c.status));
      setClaims(items);
      const q = typeof router.query.ticket === "string" ? router.query.ticket : "";
      setSelected(items.find((c) => c.ticket_id === q) || items[0]);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not load tracked claims."); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!router.isReady) return;
    verifySessionOrRedirect(router, { requiredRole: "CLAIMANT", onSuccess: () => {
      const token = getAuthToken(); if (token) void load(token);
    }});
  }, [router.isReady]);

  const respond = async (claim: TrackedClaim, requestId: string, file: File | null) => {
    const token = getAuthToken();
    if (!token || (!file && !responseNotes[requestId]?.trim())) { setError("Attach the requested document or add a response note."); return; }
    setUploading(requestId); setError("");
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      if (responseNotes[requestId]?.trim()) form.append("response_note", responseNotes[requestId].trim());
      await apiFetch("/api/v1/claims/" + claim.ticket_id + "/requests/" + requestId + "/respond", { token, method: "POST", body: form });
      setResponseNotes((prev) => ({...prev, [requestId]: ""}));
      setSuccess("Your response has been submitted to the adjuster.");
      setTimeout(() => setSuccess(""), 3500);
      await load(token);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not submit evidence response."); }
    finally { setUploading(null); }
  };

  const statusLabel = (s: string) => s.replaceAll("_"," ").replace(/\b\w/g, (x) => x.toUpperCase());
  const logout = () => { clearAuthToken(); void router.push("/login"); };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a]">
      <ClaimantSidebar userName="Claimant" claims={claims} activeRoute="track-claim" activeTicketId={selected?.ticket_id}
        onSelectClaim={(id) => setSelected(claims.find((c) => c.ticket_id === id))}
        onNewClaim={() => router.push("/claimant")} onDeleteClaim={() => {}} onLogout={logout} loadingClaims={loading} />
      <main className="md:ml-64 min-h-screen">
        <ClaimantTopBar isRecording={false} agentState="idle" currentIncidentTitle="Track Claim" ticketId={selected?.ticket_id || ""}
          onStartNewSession={() => router.push("/claimant")} onExportTranscript={() => {}} loading={loading} errorBanner={error}
          onDismissError={() => setError("")} mobileTab="chat" onTabChange={() => {}} pendingCount={0} />
        <div className="max-w-[1200px] mx-auto p-5 md:p-8">
          {success && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{success}</div>}
          <div className="mb-6">
            <div className="text-[10px] uppercase tracking-[.12em] text-[#778187] font-bold">Post-submission</div>
            <h1 className="font-headline text-2xl font-bold mt-1">Track Claim</h1>
            <p className="text-xs text-[#64748b] mt-1">Submitted claims remain outside intake chat. Status and adjuster requests appear here.</p>
          </div>
          <div className="grid lg:grid-cols-[340px_1fr] gap-5">
            <section className="bg-white rounded-xl border border-[#e0e3e5] shadow-2xs overflow-hidden">
              <div className="px-4 py-3 border-b border-[#e0e3e5] font-semibold text-sm">Submitted claims</div>
              <div className="p-2 space-y-1">
                {loading ? <div className="p-6 text-xs text-slate-400">Loading…</div> :
                  claims.length === 0 ? <div className="p-6 text-xs text-slate-400">No submitted claims yet.</div> :
                  claims.map((claim) => <button key={claim.ticket_id} onClick={() => setSelected(claim)}
                    className={"w-full text-left p-3 rounded-lg border cursor-pointer " + (selected?.ticket_id === claim.ticket_id ? "bg-[#f2f9fb] border-[#00647c]/30" : "border-transparent hover:bg-slate-50")}>
                    <div className="flex items-center justify-between gap-2"><b className="text-xs text-[#00647c]">#{claim.ticket_id}</b>
                      <span className="text-[9px] uppercase font-bold px-2 py-1 rounded-full bg-slate-100 text-slate-600">{statusLabel(claim.status)}</span></div>
                    <div className="text-[11px] text-slate-600 mt-1">{claim.insurance_type || "Insurance"} claim</div>
                    <div className="text-[10px] text-slate-400 mt-1">{claim.updated_at ? new Date(claim.updated_at).toLocaleString() : ""}</div>
                  </button>)}
              </div>
            </section>
            <section className="bg-white rounded-xl border border-[#e0e3e5] shadow-2xs p-5">
              {!selected ? <div className="py-12 text-center text-xs text-slate-400">Select a submitted claim.</div> :
                <>
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-[#e0e3e5] pb-4">
                    <div><div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Claim reference</div>
                      <div className="text-lg font-bold text-[#00647c] mt-1">#{selected.ticket_id}</div>
                      <div className="text-xs text-slate-500 mt-1">{selected.insurance_type || "Insurance"} · {selected.event_date || "Date pending"}</div></div>
                    <span className="text-[10px] uppercase font-bold px-2.5 py-1.5 rounded-full bg-cyan-50 text-cyan-800">{statusLabel(selected.status)}</span>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-3 my-5">
                    <div className="rounded-lg bg-slate-50 p-3"><div className="text-[9px] uppercase text-slate-400 font-bold">Incident</div><div className="text-xs mt-1">{selected.event_description || "—"}</div></div>
                    <div className="rounded-lg bg-slate-50 p-3"><div className="text-[9px] uppercase text-slate-400 font-bold">Amount</div><div className="text-xs mt-1">{selected.estimated_claim_amount != null ? "₹" + Number(selected.estimated_claim_amount).toLocaleString("en-IN") : "—"}</div></div>
                    <div className="rounded-lg bg-slate-50 p-3"><div className="text-[9px] uppercase text-slate-400 font-bold">Last updated</div><div className="text-xs mt-1">{selected.updated_at ? new Date(selected.updated_at).toLocaleString() : "—"}</div></div>
                  </div>
                  <div><h2 className="font-headline font-bold text-base">Adjuster requests</h2>
                    {!selected.evidence_requests?.length ? <div className="mt-3 p-4 rounded-lg border border-dashed border-slate-200 text-xs text-slate-400">No extra evidence requests at this time.</div> :
                    <div className="mt-3 space-y-3">{selected.evidence_requests.map((req: any) =>
                      <div key={req.id} className="rounded-xl border border-[#e0e3e5] p-4">
                        <div className="flex justify-between gap-3"><div><div className="text-[9px] uppercase tracking-wider text-[#00647c] font-bold">Request</div>
                          <p className="text-xs leading-relaxed mt-1 text-slate-700">{req.request_text}</p></div>
                          <span className="text-[9px] uppercase font-bold text-slate-500">{statusLabel(req.status)}</span></div>
                        {req.status === "open" ? <div className="mt-4 border-t border-slate-100 pt-3">
                          <textarea value={responseNotes[req.id] || ""} onChange={(e) => setResponseNotes((p) => ({...p, [req.id]: e.target.value}))} rows={2}
                            placeholder="Add a note for the adjuster (optional when a file is attached)…" className="w-full border border-slate-200 rounded-lg p-2.5 text-xs" />
                          <div className="mt-2 flex flex-col sm:flex-row gap-2"><input id={"file-" + req.id} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.txt" className="text-xs flex-1" />
                            <button onClick={() => { const el = document.getElementById("file-" + req.id) as HTMLInputElement | null; void respond(selected, req.id, el?.files?.[0] || null); }}
                              disabled={uploading === req.id} className="bg-[#00647c] disabled:opacity-50 text-white rounded-lg px-4 py-2 text-xs font-semibold cursor-pointer">{uploading === req.id ? "Submitting…" : "Upload & Respond"}</button>
                          </div>
                        </div> : <div className="mt-3 text-[10px] text-slate-500">{req.response_evidence?.name ? "Response file: " + req.response_evidence.name : "Response submitted."}</div>}
                      </div>)}</div>}
                  </div>
                </>
              }
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
