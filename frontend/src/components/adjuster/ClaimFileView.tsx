import React from "react";
import { FileData, title, money } from "./types";

interface ClaimFileViewProps {
  file: FileData;
  onAssignClaim: () => void;
  updatingStatus: boolean;
  onUpdateStatus: (status: string) => void;
  newNote: string;
  setNewNote: (note: string) => void;
  addingNote: boolean;
  onAddNote: () => void;
}

const SectionTitle: React.FC<{ eyebrow: string; title: string; detail?: string }> = ({ eyebrow, title, detail }) => (
  <div className="border-b border-slate-100 px-6 py-5">
    <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400">{eyebrow}</p>
    <h2 className="mt-1 text-base font-semibold tracking-tight text-slate-900">{title}</h2>
    {detail && <p className="mt-1 text-[11px] leading-5 text-slate-500">{detail}</p>}
  </div>
);

export const ClaimFileView: React.FC<ClaimFileViewProps> = ({
  file,
  onAssignClaim,
  updatingStatus,
  onUpdateStatus,
  newNote,
  setNewNote,
  addingNote,
  onAddNote,
}) => {
  const pkg = file.submission_package;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
      <div className="space-y-5">
        <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
          <div className="bg-[#10373d] px-6 py-6 text-white">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-200/70">Adjuster dossier</p>
                <h2 className="mt-2 text-xl font-semibold tracking-tight">Claim file overview</h2>
                <p className="mt-2 max-w-2xl text-xs leading-5 text-teal-50/70">
                  One structured view of the claimant story, verified policy facts, evidence state, and investigation notes.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-[9px] uppercase tracking-[0.14em] text-teal-100/60">Reference</p>
                <p className="mt-1 font-mono text-sm font-semibold">#{file.claim.ticket_id}</p>
              </div>
            </div>
            {pkg?.executive_summary && (
              <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-teal-100/60">Executive summary</p>
                <p className="mt-2 text-xs leading-5 text-white/85">{pkg.executive_summary}</p>
              </div>
            )}
          </div>

          <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Policy", String(file.extracted_data?.policy_id || "Not linked")],
              ["Incident date", file.claim.event_date || "Pending"],
              ["Insurance", title(file.claim.insurance_type)],
              ["Location", file.claim.event_location || "Pending"],
              ["Estimated loss", money(file.claim.estimated_claim_amount)],
              ["Assigned to", file.claim.assigned_adjuster_name || "Unassigned"],
            ].map(([label, value]) => (
              <div key={label} className="bg-white px-5 py-4">
                <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{label}</p>
                <p className="mt-1.5 text-xs font-semibold text-slate-800">{value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white">
          <SectionTitle eyebrow="Claimant account" title="Incident narrative" detail="The facts captured during conversational intake." />
          <div className="px-6 py-5">
            <p className="text-sm leading-7 text-slate-700">{file.claim.event_description || "No incident narrative recorded yet."}</p>
          </div>
        </section>

        <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white">
          <SectionTitle eyebrow="Investigation context" title="Chronology" detail="Key events synthesized from the claim conversation." />
          <div className="px-6 py-5">
            {pkg?.chronological_narrative?.length ? (
              <div className="space-y-5">
                {pkg.chronological_narrative.map((item, index) => (
                  <div key={index} className="grid grid-cols-[28px_1fr] gap-3">
                    <div className="relative flex justify-center">
                      <span className="grid h-6 w-6 place-items-center rounded-full bg-[#e5f3f1] text-[10px] font-bold text-[#0b6b72]">{index + 1}</span>
                      {index < pkg.chronological_narrative!.length - 1 && <span className="absolute top-7 h-full w-px bg-slate-200" />}
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-xs font-semibold text-slate-800">{item.event || "Claim event"}</p>
                        {item.timestamp && <span className="font-mono text-[9px] text-slate-400">{item.timestamp}</span>}
                      </div>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{item.details}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No chronology has been synthesized yet.</p>
            )}
          </div>
        </section>

        <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white">
          <SectionTitle eyebrow="Conversation record" title="Claimant transcript" detail={`${file.conversation.length} turns recorded`} />
          <div className="max-h-[520px] space-y-4 overflow-y-auto px-6 py-5">
            {file.conversation.length ? file.conversation.map((turn, index) => (
              <div key={index} className={`flex ${turn.speaker === "Claimant" ? "justify-start" : "justify-end"}`}>
                <div className={`max-w-[86%] rounded-2xl px-4 py-3 ${turn.speaker === "Claimant" ? "bg-slate-100 text-slate-700" : "bg-[#edf7f5] text-[#21474b]"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[9px] font-bold uppercase tracking-[0.12em] opacity-60">{turn.speaker}</p>
                    {turn.timestamp && <span className="font-mono text-[9px] opacity-50">{turn.timestamp.replace("T", " ").slice(0, 16)}</span>}
                  </div>
                  <p className="mt-1.5 text-xs leading-5">{turn.text}</p>
                </div>
              </div>
            )) : <p className="text-xs text-slate-400">No transcript recorded for this claim.</p>}
          </div>
        </section>
      </div>

      <aside className="space-y-5">
        <section className="rounded-[24px] border border-slate-200/80 bg-white p-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Workflow</p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">Claim progress</h3>
          <div className="mt-4 space-y-1">
            {[
              ["Claimant confirmed", Boolean(file.claim.claimant_confirmed)],
              ["Policy verified", Boolean(file.claim.policy_verified)],
              ["Claim-specific intake", Boolean(file.claim.dynamic_requirements_complete)],
              ["Evidence reviewed", (file.evidence || []).length > 0 && !(file.missing_evidence || []).length],
            ].map(([label, done]) => (
              <div key={String(label)} className="flex items-center justify-between border-b border-slate-100 py-3 last:border-0">
                <span className="text-xs text-slate-600">{String(label)}</span>
                <span className={`rounded-full px-2 py-1 text-[9px] font-bold uppercase ${done ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{done ? "Complete" : "Open"}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[24px] border border-slate-200/80 bg-white p-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Actions</p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">Move the claim forward</h3>
          {!file.claim.assigned_adjuster_id && (
            <button onClick={onAssignClaim} className="mt-4 w-full rounded-xl border border-[#b9d8d4] bg-[#f2faf9] px-4 py-2.5 text-xs font-semibold text-[#0b6b72]">Assign to me</button>
          )}
          <div className="mt-2 grid gap-2">
            <button disabled={updatingStatus} onClick={() => onUpdateStatus("under_review")} className="rounded-xl bg-[#0b6b72] px-4 py-3 text-xs font-semibold text-white hover:bg-[#095b61] disabled:opacity-40">Start review</button>
            <button disabled={updatingStatus} onClick={() => onUpdateStatus("pending_evidence")} className="rounded-xl border border-slate-200 px-4 py-3 text-xs font-semibold text-slate-700 hover:border-[#0b6b72] hover:text-[#0b6b72] disabled:opacity-40">Open evidence review</button>
          </div>
        </section>

        <section className="rounded-[24px] border border-slate-200/80 bg-white p-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Private notes</p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">Investigation note</h3>
          <textarea value={newNote} onChange={(event) => setNewNote(event.target.value)} rows={5} placeholder="Record an investigation observation or next step..." className="mt-3 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 outline-none focus:border-[#0b6b72] focus:bg-white" />
          <button disabled={addingNote || !newNote.trim()} onClick={onAddNote} className="mt-2 w-full rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-40">{addingNote ? "Saving..." : "Save private note"}</button>
        </section>
      </aside>
    </div>
  );
};