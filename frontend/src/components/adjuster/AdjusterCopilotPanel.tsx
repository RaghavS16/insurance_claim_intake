import React from "react";
import { FileData } from "./types";

interface Props {
  file: FileData;
  copilotLoading: boolean;
  updatingStatus: boolean;
  onLoadCopilot: (ticketId: string) => void;
  onUpdateStatus: (status: string) => void;
  copilotMessage: string;
  setCopilotMessage: (value: string) => void;
  copilotChat: Array<{ speaker: string; message: string; created_at?: string }>;
  onSendCopilotMessage: () => void;
}

export const AdjusterCopilotPanel: React.FC<Props> = ({
  file, copilotLoading, updatingStatus, onLoadCopilot, onUpdateStatus,
  copilotMessage, setCopilotMessage, copilotChat, onSendCopilotMessage,
}) => {
  const report = file.copilot || {};
  const sections: Array<[string, string[] | undefined]> = [
    ["Coverage Observations", report.coverage_observations],
    ["Evidence Assessment", report.evidence_assessment || report.evidence_gaps],
    ["Risk Flags", report.risk_flags],
    ["Regulatory Considerations", report.regulatory_considerations],
    ["Decision Considerations", report.decision_considerations],
    ["Recommended Next Steps", report.recommended_next_steps],
    ["Uncertainties", report.uncertainties],
  ];
  return (
    <div className="grid xl:grid-cols-[1fr_380px] gap-5">
      <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
        <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
          <div>
            <h2 className="font-headline font-bold text-base">AI Adjuster Copilot</h2>
            <p className="text-[11px] text-[#6e797e] mt-0.5">Claim-specific advisory report plus live claim chat.</p>
          </div>
          <button onClick={() => onLoadCopilot(file.claim.ticket_id)} disabled={copilotLoading}
            className="text-xs bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white px-3 py-1.5 rounded-lg font-semibold cursor-pointer">
            {copilotLoading ? "Analyzing..." : "Re-run Analysis"}
          </button>
        </div>

        <div className="p-5 space-y-4">
          {copilotLoading ? (
            <div className="py-14 text-center text-xs text-[#6e797e]">Running grounded policy, regulatory, requirement and evidence analysis…</div>
          ) : report.executive_summary || report.summary ? (
            <>
              <div className="border-l-[3px] border-[#00647c] bg-[#f4f9fa] p-4 rounded-r-lg text-xs leading-relaxed">
                <b className="block text-[11px] uppercase tracking-wider text-[#00647c] mb-1">Decision-Support Summary</b>
                {report.executive_summary || report.summary}
              </div>

              {report.mandatory_requirements?.length ? (
                <div className="border border-[#e0e3e5] rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-[#f7f9fb] text-[11px] font-bold">Mandatory Requirement Review</div>
                  {report.mandatory_requirements.map((r, i) => (
                    <div key={i} className="px-3 py-2 border-t border-[#edf0f1] flex items-start justify-between gap-3 text-xs">
                      <div><b>{r.label || "Requirement"}</b>{r.condition ? <div className="text-[10px] text-[#778187] mt-0.5">{r.condition}</div> : null}</div>
                      <span className="text-[10px] font-bold uppercase text-[#00647c]">{r.status || "review"}</span>
                    </div>
                  ))}
                </div>
              ) : null}

              {sections.map(([label, items]) => items?.length ? (
                <div key={label} className="bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg p-3">
                  <b className="text-[11px] text-[#00647c]">{label}</b>
                  <div className="mt-1.5 space-y-1.5">{items.map((x, i) => <p key={i} className="text-xs text-[#475569] leading-relaxed">• {x}</p>)}</div>
                </div>
              ) : null)}

              {(file.knowledge_sources || []).length > 0 && (
                <div className="border-t border-[#e0e3e5] pt-4">
                  <b className="text-xs">Grounding Sources</b>
                  {(file.knowledge_sources || []).map((s, i) => (
                    <div key={i} className="mt-2 text-[10px] bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg p-3">
                      <b className="text-[#00647c]">{s.source_name || "Policy Document"}</b>
                      <p className="mt-1 text-[#657177] leading-relaxed">{s.text?.slice(0, 600)}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="py-14 text-center text-xs text-[#6e797e]">
              <p>Copilot analysis is not available yet.</p>
              <button onClick={() => onLoadCopilot(file.claim.ticket_id)} className="mt-3 bg-[#00647c] text-white px-3.5 py-1.5 rounded-lg font-semibold cursor-pointer">Run Analysis Now</button>
            </div>
          )}
        </div>
      </section>

      <div className="space-y-5">
        <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
          <div className="px-4 py-3 border-b border-[#e0e3e5]"><b className="text-sm">Discuss this claim with Copilot</b></div>
          <div className="p-4 space-y-2 max-h-[420px] overflow-y-auto">
            {copilotChat.length === 0 ? <p className="text-xs text-[#6e797e]">Ask about coverage evidence, missing requirements, inconsistencies, or what to review next.</p> :
              copilotChat.map((m, i) => (
                <div key={i} className={m.speaker === "copilot" ? "bg-[#f2f7f8] rounded-lg p-3 text-xs" : "bg-[#e9f5f8] rounded-lg p-3 text-xs"}>
                  <div className="text-[9px] uppercase tracking-wider font-bold text-[#778187] mb-1">{m.speaker}</div>
                  <div className="leading-relaxed whitespace-pre-wrap">{m.message}</div>
                </div>
              ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); onSendCopilotMessage(); }} className="p-3 border-t border-[#e0e3e5] flex gap-2">
            <input value={copilotMessage} onChange={(e) => setCopilotMessage(e.target.value)}
              placeholder="Ask about this claim…" className="flex-1 border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-[#00647c]" />
            <button disabled={!copilotMessage.trim()} className="bg-[#00647c] text-white px-3 rounded-lg text-xs font-semibold disabled:opacity-50">Send</button>
          </form>
        </section>

        <aside className="bg-white border border-[#e0e3e5] rounded-xl p-5 shadow-2xs">
          <h2 className="font-headline font-bold text-[15px]">Decision Control</h2>
          <p className="text-[11px] text-[#6e797e] leading-relaxed mt-1">Copilot is advisory; the adjuster owns the final adjudication decision.</p>
          <div className="grid gap-2.5 mt-5">
            <button disabled={updatingStatus} onClick={() => onUpdateStatus("pending_evidence")} className="border border-[#bdc8ce] rounded-lg py-2.5 text-xs font-semibold cursor-pointer">Open Evidence Review</button>
            <button disabled={updatingStatus} onClick={() => onUpdateStatus("approved")} className="bg-emerald-600 text-white rounded-lg py-2.5 text-xs font-semibold cursor-pointer">Approve Claim</button>
            <button disabled={updatingStatus} onClick={() => onUpdateStatus("rejected")} className="border border-[#d9a7a2] text-[#93000a] rounded-lg py-2.5 text-xs font-semibold cursor-pointer">Reject Claim</button>
          </div>
        </aside>
      </div>
    </div>
  );
};