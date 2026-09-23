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
  const pkg = file.submission_package;

  return (
    <div className="grid xl:grid-cols-[1fr_360px] gap-5">
      <div className="space-y-5">
        {/* Standardized Adjuster-Ready Claims Package */}
        {pkg && (
          <section className="bg-white border-2 border-[#00647c]/30 rounded-xl overflow-hidden shadow-sm">
            <div className="bg-gradient-to-r from-[#00647c] to-[#004e61] px-5 py-4 text-white flex justify-between items-center">
              <div>
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-xl text-sky-200">verified</span>
                  <h2 className="font-headline font-bold text-base">Adjuster-Ready Claims Package</h2>
                </div>
                <p className="text-[11px] text-sky-100 mt-0.5">
                  Synthesized dossier with incident chronology, verified policy details, and risk flags.
                </p>
              </div>
              <span className="bg-emerald-500/20 text-emerald-200 border border-emerald-400/40 text-[10px] uppercase font-bold px-2.5 py-1 rounded-full tracking-wider">
                {pkg.status || "Adjuster Ready"}
              </span>
            </div>

            {/* Executive Summary */}
            {pkg.executive_summary && (
              <div className="p-5 bg-sky-50/50 border-b border-[#e0e3e5]">
                <div className="text-[10px] uppercase tracking-wider text-[#00647c] font-bold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm">summarize</span>
                  Executive Summary
                </div>
                <p className="text-xs leading-relaxed mt-2 text-[#0f3d4a] font-medium">
                  {pkg.executive_summary}
                </p>
              </div>
            )}

            <div className="p-5 grid md:grid-cols-2 gap-5 border-b border-[#e0e3e5]">
              {/* Risk Assessment & Discrepancy Flags */}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[#778187] font-bold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-amber-600">shield_with_heart</span>
                  Risk Assessment & Fraud Flags
                </div>
                <div className="mt-2.5 space-y-2">
                  {pkg.risk_assessment_flags?.length ? (
                    pkg.risk_assessment_flags.map((flag, i) => (
                      <div
                        key={i}
                        className={`text-xs px-3 py-2 rounded-lg flex items-start gap-2 ${
                          flag.includes("High") || flag.includes("Multi-party")
                            ? "bg-amber-50 text-amber-900 border border-amber-200"
                            : "bg-emerald-50 text-emerald-900 border border-emerald-200"
                        }`}
                      >
                        <span className="material-symbols-outlined text-sm mt-0.5">
                          {flag.includes("High") ? "warning" : "check_circle"}
                        </span>
                        <span className="leading-snug">{flag}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-[#6e797e]">No elevated risk flags detected.</p>
                  )}
                </div>
              </div>

              {/* Recommended Next Steps */}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[#778187] font-bold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-[#00647c]">forward</span>
                  Recommended Next Steps
                </div>
                <ul className="mt-2.5 space-y-2">
                  {pkg.recommended_next_steps?.length ? (
                    pkg.recommended_next_steps.map((step, i) => (
                      <li
                        key={i}
                        className="text-xs text-[#1e293b] bg-[#f8fafc] border border-[#e2e8f0] px-3 py-2 rounded-lg flex items-start gap-2"
                      >
                        <span className="text-[#00647c] font-bold mt-0.5">•</span>
                        <span className="leading-snug">{step}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-xs text-[#6e797e]">Review facts and proceed with triage.</li>
                  )}
                </ul>
              </div>
            </div>

            {/* Chronological Incident Narrative */}
            {pkg.chronological_narrative && pkg.chronological_narrative.length > 0 && (
              <div className="p-5 bg-white">
                <div className="text-[10px] uppercase tracking-wider text-[#778187] font-bold flex items-center gap-1.5 mb-3">
                  <span className="material-symbols-outlined text-sm">schedule</span>
                  Chronological Incident Timeline
                </div>
                <div className="space-y-3 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-[#e2e8f0]">
                  {pkg.chronological_narrative.map((item, i) => (
                    <div key={i} className="flex items-start gap-3 pl-1 relative">
                      <div className="w-4 h-4 rounded-full bg-[#00647c] text-white flex items-center justify-center text-[9px] font-bold shrink-0 mt-0.5 z-10">
                        {i + 1}
                      </div>
                      <div className="flex-1 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-[#0f172a]">{item.event}</span>
                          {item.timestamp && (
                            <span className="text-[10px] text-[#94a3b8] font-mono">
                              {item.timestamp.replace("T", " ").replace("Z", " UTC")}
                            </span>
                          )}
                        </div>
                        <p className="text-[#475569] mt-0.5 leading-relaxed">{item.details}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

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
            <h2 className="font-headline font-bold text-base">Voice & Dialogue Transcript</h2>
            <span className="text-[10px] text-[#6e797e] font-semibold">
              {file.conversation.length} turns recorded
            </span>
          </div>
          <div className="p-5 space-y-3.5 max-h-[480px] overflow-y-auto">
            {file.conversation.length ? (
              file.conversation.map((t, i) => (
                <div key={i}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[9px] uppercase tracking-[.08em] text-[#778187] font-bold">
                      {t.speaker}
                    </span>
                    {t.timestamp && (
                      <span className="text-[9px] text-[#94a3b8] font-mono">
                        {t.timestamp.replace("T", " ").substring(0, 19)}
                      </span>
                    )}
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
