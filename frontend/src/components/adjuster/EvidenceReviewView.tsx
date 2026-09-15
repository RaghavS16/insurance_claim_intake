import React from "react";
import { FileData, EvidenceItem } from "./types";

interface EvidenceReviewViewProps {
  file: FileData;
  onRefresh: () => void;
  onOpenEvidence: (e: EvidenceItem) => void;
  onUpdateStatus: (status: string) => void;
}

export const EvidenceReviewView: React.FC<EvidenceReviewViewProps> = ({
  file,
  onRefresh,
  onOpenEvidence,
  onUpdateStatus,
}) => {
  return (
    <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-2xs">
      <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
        <div>
          <h2 className="font-headline font-bold text-base">Evidence Review</h2>
          <p className="text-[11px] text-[#6e797e] mt-0.5">
            Required documents and claimant uploads.
          </p>
        </div>
        <button
          onClick={onRefresh}
          className="text-xs text-[#00647c] font-semibold hover:underline flex items-center gap-1 cursor-pointer"
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
                  onClick={() => onOpenEvidence(e)}
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
              onClick={() => onUpdateStatus("pending_evidence")}
              className="mt-3 text-xs text-[#00647c] font-bold hover:underline cursor-pointer"
            >
              Mark claim as Pending Evidence
            </button>
          </div>
        )}
      </div>
    </section>
  );
};
