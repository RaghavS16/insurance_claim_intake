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
  return (
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
                onClick={onAssignClaim}
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
              onClick={() => onUpdateStatus("under_review")}
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
              onClick={() => onUpdateStatus("pending_evidence")}
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
            onClick={onAddNote}
            className="w-full mt-2 bg-slate-800 hover:bg-slate-900 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-semibold transition-colors cursor-pointer"
          >
            {addingNote ? "Saving Note..." : "Save Adjuster Note"}
          </button>
        </section>
      </aside>
    </div>
  );
};
