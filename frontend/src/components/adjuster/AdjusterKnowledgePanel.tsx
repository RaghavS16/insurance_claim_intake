import React from "react";
import { KnowledgeItem } from "./types";

interface AdjusterKnowledgePanelProps {
  knowledgeType: string;
  setKnowledgeType: (val: string) => void;
  knowledgeInsurance: string;
  setKnowledgeInsurance: (val: string) => void;
  knowledgePolicy: string;
  setKnowledgePolicy: (val: string) => void;
  knowledgeFile: File | null;
  setKnowledgeFile: (file: File | null) => void;
  knowledgeUploading: boolean;
  onUploadKnowledge: () => void;
  knowledgeQuery: string;
  setKnowledgeQuery: (val: string) => void;
  knowledgeItems: KnowledgeItem[];
  onSearchKnowledge: () => void;
}

export const AdjusterKnowledgePanel: React.FC<AdjusterKnowledgePanelProps> = ({
  knowledgeType,
  setKnowledgeType,
  knowledgeInsurance,
  setKnowledgeInsurance,
  knowledgePolicy,
  setKnowledgePolicy,
  knowledgeFile,
  setKnowledgeFile,
  knowledgeUploading,
  onUploadKnowledge,
  knowledgeQuery,
  setKnowledgeQuery,
  knowledgeItems,
  onSearchKnowledge,
}) => {
  return (
    <section className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-[#e0e3e5]">
        <h2 className="font-headline font-bold text-lg">Policy & Regulatory Knowledge</h2>
        <p className="text-[11px] text-[#6e797e] mt-0.5">
          Upload policy wording, guidelines, and claim rules. Retrieved during claimant intake and AI Copilot.
        </p>
      </div>
      <div className="p-5 grid xl:grid-cols-[1fr_1fr] gap-5">
        <div className="border border-[#e0e3e5] rounded-xl p-5 bg-[#fcfdfe]">
          <h3 className="font-headline font-bold text-sm">Update Knowledge Base</h3>
          <p className="text-[11px] text-[#6e797e] mt-0.5">
            Upload PDF or text documents to embed into vector storage.
          </p>
          <div className="grid gap-3 mt-4">
            <div>
              <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                Document Type
              </label>
              <select
                value={knowledgeType}
                onChange={(e) => setKnowledgeType(e.target.value)}
                className="w-full border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs bg-white cursor-pointer"
              >
                <option value="policy_wording">Policy wording</option>
                <option value="regulatory ">Regulatory</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                Insurance Type (optional)
              </label>
              <input
                value={knowledgeInsurance}
                onChange={(e) => setKnowledgeInsurance(e.target.value)}
                placeholder="e.g. motor, health, home"
                className="w-full border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs bg-white"
              />
            </div>

            <div>
              <label className="text-[10px] uppercase font-bold text-[#6e797e] block mb-1">
                File (.pdf, .txt, .md, .csv)
              </label>
              <input
                type="file"
                accept=".pdf,.txt,.md,.csv"
                onChange={(e) => setKnowledgeFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-[#505f76] file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-[#00647c] file:text-white hover:file:bg-[#004e61] cursor-pointer"
              />
            </div>

            <button
              disabled={!knowledgeFile || knowledgeUploading}
              onClick={onUploadKnowledge}
              className="bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white rounded-lg py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer mt-2"
            >
              {knowledgeUploading ? (
                <>
                  <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                  <span>Uploading & Indexing...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-base">upload</span>
                  <span>Upload & Index</span>
                </>
              )}
            </button>
          </div>
        </div>

        <div className="border border-[#e0e3e5] rounded-xl p-5 bg-[#fcfdfe] flex flex-col">
          <h3 className="font-headline font-bold text-sm">Search Retrieved Knowledge</h3>
          <p className="text-[11px] text-[#6e797e] mt-0.5">
            Test pgvector / BM25 semantic retrieval over ingested policy clauses.
          </p>
          <div className="flex gap-2 mt-4">
            <input
              value={knowledgeQuery}
              onChange={(e) => setKnowledgeQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSearchKnowledge()}
              placeholder="e.g. water damage exclusions, deductible limits"
              className="border border-[#cbd5e1] rounded-lg px-3 py-2 text-xs flex-1 bg-white"
            />
            <button
              onClick={onSearchKnowledge}
              className="bg-[#00647c] hover:bg-[#004e61] text-white rounded-lg px-4 text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">search</span>
              <span>Search</span>
            </button>
          </div>
          <div className="mt-4 max-h-[380px] overflow-y-auto space-y-3 flex-1 pr-1">
            {knowledgeItems.length ? (
              knowledgeItems.map((x, i) => (
                <div key={i} className="bg-white border border-[#e0e3e5] rounded-lg p-3 shadow-2xs">
                  <div className="flex justify-between items-start gap-2">
                    <b className="text-xs text-[#00647c]">{x.source_name || "Document"}</b>
                    <span className="text-[9px] uppercase font-bold px-2 py-0.5 rounded bg-slate-100 text-[#6e797e]">
                      {x.document_type || "policy"}
                    </span>
                  </div>
                  <p className="text-[11px] leading-5 mt-2 text-[#526066]">{x.text}</p>
                </div>
              ))
            ) : (
              <p className="text-xs text-[#6e797e] py-12 text-center">
                No retrieval results. Enter a query or upload documents above.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
