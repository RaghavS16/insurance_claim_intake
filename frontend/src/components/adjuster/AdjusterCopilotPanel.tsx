import React, { useEffect, useState } from "react";
import { CopilotChatMessage, FileData } from "./types";

interface AdjusterCopilotPanelProps {
  file: FileData;
  copilotLoading: boolean;
  updatingStatus: boolean;
  onLoadCopilot: (ticketId: string) => void;
  onUpdateStatus: (status: string) => void;
  onSendChat: (message: string) => Promise<void>;
  chatSending: boolean;
}

export const AdjusterCopilotPanel: React.FC<AdjusterCopilotPanelProps> = ({
  file,
  copilotLoading,
  updatingStatus,
  onLoadCopilot,
  onUpdateStatus,
  onSendChat,
  chatSending,
}) => {
  const [draft, setDraft] = useState("");
  const messages = file.copilot_chat || [];

  useEffect(() => {
    setDraft("");
  }, [file.claim.ticket_id]);

  const submit = async () => {
    const value = draft.trim();
    if (!value || chatSending) return;
    setDraft("");
    await onSendChat(value);
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_380px]">
      <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.07)]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#e5f3f1] text-[#0b6b72]">
                <span className="material-symbols-outlined text-[19px]">auto_awesome</span>
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Claim intelligence</p>
                <h2 className="mt-0.5 text-lg font-semibold tracking-tight text-slate-900">AI adjuster copilot</h2>
              </div>
            </div>
            <p className="mt-3 max-w-2xl text-xs leading-relaxed text-slate-500">
              Review the grounded assessment, then ask questions about this claim in the same workspace.
            </p>
          </div>
          <button
            onClick={() => onLoadCopilot(file.claim.ticket_id)}
            disabled={copilotLoading}
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-[#0b6b72] hover:text-[#0b6b72] disabled:opacity-50"
          >
            {copilotLoading ? "Analyzing..." : "Refresh analysis"}
          </button>
        </div>

        <div className="space-y-5 p-6">
          {copilotLoading ? (
            <div className="space-y-3">
              <div className="h-20 animate-pulse rounded-2xl bg-slate-100" />
              <div className="h-14 animate-pulse rounded-2xl bg-slate-100" />
              <div className="h-14 animate-pulse rounded-2xl bg-slate-100" />
            </div>
          ) : file.copilot?.summary ? (
            <div className="rounded-2xl border border-[#cfe7e4] bg-[#f4fbfa] p-5">
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#0b6b72]">Decision brief</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{file.copilot.summary}</p>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <p className="text-sm font-semibold text-slate-800">No analysis yet</p>
              <p className="mt-1 text-xs text-slate-500">Run the grounded claim analysis before discussing the file with Copilot.</p>
              <button onClick={() => onLoadCopilot(file.claim.ticket_id)} className="mt-4 rounded-xl bg-[#0b6b72] px-4 py-2 text-xs font-semibold text-white">
                Run analysis
              </button>
            </div>
          )}

          {(file.copilot?.coverage_observations || []).length > 0 && (
            <div className="grid gap-3 md:grid-cols-2">
              {(file.copilot.coverage_observations || []).map((item, index) => (
                <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Coverage observation</p>
                  <p className="mt-2 text-xs leading-5 text-slate-600">{item}</p>
                </div>
              ))}
            </div>
          )}

          {(file.copilot?.evidence_gaps || []).length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-amber-700">Evidence gaps</p>
              <ul className="mt-2 space-y-2">
                {(file.copilot.evidence_gaps || []).map((item, index) => (
                  <li key={index} className="text-xs leading-5 text-amber-950">• {item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-900">Discuss this claim</p>
                <p className="mt-0.5 text-[11px] text-slate-400">Ask about coverage, evidence, inconsistencies, or next steps.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-500">Grounded chat</span>
            </div>

            <div className="mt-4 max-h-[360px] space-y-3 overflow-y-auto pr-1">
              {messages.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-xs text-slate-400">
                  Try: “What evidence is still missing?” or “Which policy clause supports the current assessment?”
                </div>
              ) : (
                messages.map((message: CopilotChatMessage, index) => (
                  <div key={`${message.created_at || "m"}-${index}`} className={message.role === "user" ? "ml-10" : "mr-10"}>
                    <div className={`rounded-2xl px-4 py-3 text-xs leading-5 ${message.role === "user" ? "bg-[#0b6b72] text-white" : "bg-slate-100 text-slate-700"}`}>
                      {message.text}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-[#0b6b72]">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit();
                  }
                }}
                rows={2}
                placeholder="Ask Copilot about this claim..."
                className="min-h-[52px] flex-1 resize-none bg-transparent px-2 py-1.5 text-xs text-slate-800 outline-none placeholder:text-slate-400"
              />
              <button
                onClick={() => void submit()}
                disabled={!draft.trim() || chatSending}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#0b6b72] text-white transition hover:bg-[#095b61] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="material-symbols-outlined text-[18px]">{chatSending ? "progress_activity" : "arrow_upward"}</span>
              </button>
            </div>
          </div>

          {(file.knowledge_sources || []).length > 0 && (
            <div className="border-t border-slate-100 pt-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Grounding sources</p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {file.knowledge_sources.slice(0, 6).map((source, index) => (
                  <div key={index} className="rounded-xl border border-slate-200 p-3">
                    <p className="text-[10px] font-semibold text-[#0b6b72]">{source.source_name || "Policy source"}</p>
                    <p className="mt-1 line-clamp-3 text-[10px] leading-4 text-slate-500">{source.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      <aside className="h-fit rounded-[24px] border border-slate-200/80 bg-[#102f35] p-6 text-white shadow-[0_18px_55px_rgba(15,23,42,0.09)]">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-200/70">Human decision control</p>
        <h3 className="mt-2 text-xl font-semibold tracking-tight">You own the adjudication</h3>
        <p className="mt-2 text-xs leading-5 text-teal-50/70">
          Copilot surfaces evidence and reasoning. The final claim decision remains with the assigned adjuster.
        </p>
        <div className="mt-6 grid gap-2">
          <button disabled={updatingStatus} onClick={() => onUpdateStatus("pending_evidence")} className="rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-xs font-semibold text-white transition hover:bg-white/10">
            Request more evidence
          </button>
          <button disabled={updatingStatus} onClick={() => onUpdateStatus("approved")} className="rounded-xl bg-[#b8ddd7] px-4 py-3 text-xs font-bold text-[#102f35] transition hover:bg-[#c8e8e3]">
            Approve claim
          </button>
          <button disabled={updatingStatus} onClick={() => onUpdateStatus("rejected")} className="rounded-xl border border-rose-300/30 px-4 py-3 text-xs font-semibold text-rose-100 transition hover:bg-rose-400/10">
            Reject claim
          </button>
        </div>
      </aside>
    </div>
  );
};