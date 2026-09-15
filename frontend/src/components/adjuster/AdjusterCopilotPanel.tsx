import React from "react";
import { FileData } from "./types";

interface AdjusterCopilotPanelProps {
  file: FileData;
  copilotLoading: boolean;
  updatingStatus: boolean;
  onLoadCopilot: (ticketId: string) => void;
  onUpdateStatus: (status: string) => void;
}

export const AdjusterCopilotPanel: React.FC<AdjusterCopilotPanelProps> = ({
  file,
  copilotLoading,
  updatingStatus,
  onLoadCopilot,
  onUpdateStatus,
}) => {
  return (
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
            onClick={() => onLoadCopilot(file.claim.ticket_id)}
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
                onClick={() => onLoadCopilot(file.claim.ticket_id)}
                className="mt-3 bg-[#00647c] text-white px-3.5 py-1.5 rounded-lg font-semibold cursor-pointer"
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
            onClick={() => onUpdateStatus("pending_evidence")}
            className="border border-[#bdc8ce] hover:border-[#00647c] rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer"
          >
            Need More Evidence
          </button>
          <button
            disabled={updatingStatus}
            onClick={() => onUpdateStatus("approved")}
            className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer shadow-xs"
          >
            Approve Claim
          </button>
          <button
            disabled={updatingStatus}
            onClick={() => onUpdateStatus("rejected")}
            className="border border-[#d9a7a2] text-[#93000a] hover:bg-rose-50 rounded-lg py-2.5 text-xs font-semibold transition-colors cursor-pointer"
          >
            Reject Claim
          </button>
        </div>
      </aside>
    </div>
  );
};
