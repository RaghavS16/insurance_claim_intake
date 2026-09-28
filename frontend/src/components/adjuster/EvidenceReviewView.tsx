import React, { useState } from "react";
import { FileData, EvidenceItem } from "./types";

interface EvidenceReviewViewProps {
  file: FileData;
  onRefresh: () => void;
  onOpenEvidence: (e: EvidenceItem) => void;
  onUpdateStatus: (status: string) => void;
  onRequestEvidence: (message: string, requestedEvidence: string[]) => Promise<void>;
  requestSending: boolean;
}

export const EvidenceReviewView: React.FC<EvidenceReviewViewProps> = ({
  file,
  onRefresh,
  onOpenEvidence,
  onUpdateStatus,
  onRequestEvidence,
  requestSending,
}) => {
  const [message, setMessage] = useState("");
  const [requestedEvidence, setRequestedEvidence] = useState<string[]>([]);

  const toggleEvidence = (label: string) => {
    setRequestedEvidence((current) =>
      current.includes(label) ? current.filter((item) => item !== label) : [...current, label],
    );
  };

  const submitRequest = async () => {
    if (!message.trim()) return;
    await onRequestEvidence(message.trim(), requestedEvidence);
    setMessage("");
    setRequestedEvidence([]);
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Documents & proof</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">Evidence review</h2>
            <p className="mt-1 text-xs text-slate-500">See what is required, what has arrived, and what still needs attention.</p>
          </div>
          <button onClick={onRefresh} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:border-[#0b6b72] hover:text-[#0b6b72]">
            Refresh
          </button>
        </div>

        <div className="p-6">
          {(file.missing_evidence || []).length > 0 ? (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-amber-700">Still required</p>
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-bold text-amber-700">{file.missing_evidence.length} open</span>
              </div>
              <div className="grid gap-2">
                {file.missing_evidence.map((item, index) => (
                  <button
                    key={String(item.key || index)}
                    onClick={() => toggleEvidence(String(item.label || item.key || "Supporting evidence"))}
                    className={`w-full rounded-2xl border p-4 text-left transition ${requestedEvidence.includes(String(item.label || item.key || "Supporting evidence")) ? "border-[#0b6b72] bg-[#f2faf9]" : "border-amber-200 bg-amber-50/60 hover:border-amber-300"}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-slate-900">{String(item.label || item.key || "Supporting evidence")}</p>
                        <p className="mt-1 text-[11px] leading-5 text-slate-600">{String(item.description || item.question_hint || "Supporting document requested by the policy requirements.")}</p>
                      </div>
                      <span className="text-[10px] font-bold uppercase text-slate-400">
                        {requestedEvidence.includes(String(item.label || item.key || "Supporting evidence")) ? "Selected" : "Select"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4 text-xs text-emerald-900">
              No policy-derived evidence gaps are currently open.
            </div>
          )}

          <div className="mt-7">
            <div className="flex items-end justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Claimant communication</p>
                <h3 className="mt-1 text-sm font-semibold text-slate-900">Request specific evidence</h3>
              </div>
              <span className="text-[10px] text-slate-400">Sent to claimant dashboard</span>
            </div>
            <textarea
              rows={5}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Example: Please upload the final hospital discharge summary showing the admission and discharge dates."
              className="mt-3 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-800 outline-none transition focus:border-[#0b6b72] focus:bg-white"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-[10px] leading-4 text-slate-400">The request is recorded in the claim timeline so the claimant can see exactly what is needed.</p>
              <button
                onClick={() => void submitRequest()}
                disabled={!message.trim() || requestSending}
                className="shrink-0 rounded-xl bg-[#0b6b72] px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-[#095b61] disabled:cursor-not-allowed disabled:opacity-40"
              >
                {requestSending ? "Sending..." : "Send request"}
              </button>
            </div>
          </div>

          <div className="mt-7 border-t border-slate-100 pt-6">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Received evidence</p>
            {file.evidence?.length ? (
              <div className="mt-3 divide-y divide-slate-100">
                {file.evidence.map((item, index) => (
                  <div key={String(item.id || index)} className="flex items-center justify-between gap-3 py-3.5">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500">
                        <span className="material-symbols-outlined text-[18px]">description</span>
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-slate-800">{item.name || item.type || "Evidence document"}</p>
                        <p className="mt-0.5 text-[10px] text-slate-400">
                          {item.type || "Document"} · {String(item.verification_status || item.status || "Uploaded").replaceAll("_", " ")}
                        </p>
                      </div>
                    </div>
                    <button onClick={() => onOpenEvidence(item)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-[10px] font-semibold text-slate-600 hover:border-[#0b6b72] hover:text-[#0b6b72]">
                      View
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 rounded-2xl border border-dashed border-slate-200 p-8 text-center">
                <p className="text-xs font-semibold text-slate-600">No files uploaded yet</p>
                <p className="mt-1 text-[11px] text-slate-400">Use the request field above when a specific document is needed.</p>
              </div>
            )}
          </div>
        </div>
      </section>

      <aside className="h-fit rounded-[24px] border border-slate-200/80 bg-slate-50 p-5">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Workflow</p>
        <h3 className="mt-1 text-base font-semibold text-slate-900">Evidence status</h3>
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between rounded-xl bg-white p-3">
            <span className="text-xs text-slate-500">Missing</span>
            <span className="text-sm font-semibold text-amber-700">{file.missing_evidence?.length || 0}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl bg-white p-3">
            <span className="text-xs text-slate-500">Uploaded</span>
            <span className="text-sm font-semibold text-slate-900">{file.evidence?.length || 0}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl bg-white p-3">
            <span className="text-xs text-slate-500">Open requests</span>
            <span className="text-sm font-semibold text-[#0b6b72]">{file.adjuster_requests?.filter((item) => item.status !== "resolved").length || 0}</span>
          </div>
        </div>
        <button onClick={() => onUpdateStatus("under_review")} className="mt-4 w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:border-[#0b6b72] hover:text-[#0b6b72]">
          Continue review
        </button>
      </aside>
    </div>
  );
};