import React from "react";
import Link from "next/link";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";
import { ExtractedData } from "./ExtractionPanel";

interface CollectedDetailsPanelProps {
  extractedData: ExtractedData;
  onOpenEdit: (field: string, currentVal: any) => void;
  onSubmitClaim: () => void;
  submittingClaim: boolean;
  confirmed: boolean;
  ticketId: string;
}

export const CollectedDetailsPanel: React.FC<CollectedDetailsPanelProps> = ({
  extractedData,
  onOpenEdit,
  onSubmitClaim,
  submittingClaim,
  confirmed,
  ticketId,
}) => {
  const pendingCount = [
    !extractedData.policy_id,
    !extractedData.insurance_type,
    !extractedData.event_date,
    !extractedData.estimated_claim_amount,
  ].filter(Boolean).length;

  return (
    <div className="w-full lg:w-[400px] xl:w-[460px] bg-[#f7f9fb] flex flex-col h-full border-t lg:border-t-0 lg:border-l border-[#e0e3e5] shrink-0 overflow-hidden">
      {/* Header */}
      <div className="p-4 md:p-5 border-b border-[#e0e3e5] bg-white sticky top-0 z-10 flex justify-between items-center shadow-sm shrink-0">
        <div>
          <h2 className="font-headline text-base md:text-lg font-bold text-[#191c1e]">Collected Details</h2>
          <p className="font-label text-xs text-[#505f76]">Review and verify extracted information</p>
        </div>
        <span
          className={`font-label text-[10px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wider ${
            pendingCount === 0
              ? "bg-emerald-100 text-emerald-800"
              : "bg-[#d0e1fb] text-[#54647a]"
          }`}
        >
          {pendingCount === 0 ? "Ready to Submit" : `${pendingCount} Pending`}
        </span>
      </div>

      {/* Details Cards Container */}
      <div className="p-4 md:p-5 space-y-3.5 flex-1 overflow-y-auto">
        {/* Detail Card: Policy ID */}
        <div
          className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-sm ${
            extractedData.policy_id ? "border-[#00647c]" : "border-[#bdc8ce]"
          }`}
        >
          {extractedData.policy_id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
          <div className="flex justify-between items-start pl-1">
            <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
              Policy ID
            </span>
            <button
              onClick={() => onOpenEdit("policy_id", extractedData.policy_id)}
              className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-center gap-2 pl-1">
            <span className="material-symbols-outlined text-[#505f76] text-[20px]">verified_user</span>
            <span className="font-body text-sm text-[#191c1e] font-semibold font-mono">
              {extractedData.policy_id || <span className="text-[#505f76] font-normal italic">Not specified yet</span>}
            </span>
          </div>
          {!extractedData.policy_id && (
            <Link
              href="/link-policy"
              className="text-[11px] text-[#0891B2] font-semibold hover:underline mt-1 pl-1 flex items-center gap-1"
            >
              <span>Select from linked policies</span>
              <span className="material-symbols-outlined text-xs">arrow_forward</span>
            </Link>
          )}
        </div>

        {/* Detail Card: Insurance Type */}
        <div className="bg-white border border-[#bdc8ce] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
              Insurance Type
            </span>
            <button
              onClick={() => onOpenEdit("insurance_type", extractedData.insurance_type)}
              className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-[20px]">category</span>
            <span className="font-body text-sm text-[#191c1e] font-semibold capitalize">
              {extractedData.insurance_type ? (
                (SUPPORTED_INSURANCE_TYPES as any)[extractedData.insurance_type] || extractedData.insurance_type
              ) : (
                <span className="text-[#505f76] font-normal italic">Pending classification...</span>
              )}
            </span>
          </div>
        </div>

        {/* Detail Card: Incident Date */}
        <div className="bg-white border border-[#bdc8ce] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
              Incident Date
            </span>
            <button
              onClick={() => onOpenEdit("event_date", extractedData.event_date)}
              className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-[20px]">event</span>
            <span className="font-body text-sm text-[#191c1e] font-semibold">
              {extractedData.event_date || (
                <span className="text-[#505f76] font-normal italic">Waiting for date...</span>
              )}
            </span>
          </div>
        </div>

        {/* Detail Card: Estimated Loss */}
        <div className="bg-white border border-[#bdc8ce] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
              Estimated Loss (INR)
            </span>
            <button
              onClick={() => onOpenEdit("estimated_claim_amount", extractedData.estimated_claim_amount)}
              className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-center gap-2 pl-1">
            <span className="material-symbols-outlined text-[#00647c] text-[20px]">payments</span>
            <span className="font-body text-sm text-[#191c1e] font-semibold">
              {extractedData.estimated_claim_amount != null ? (
                `₹${extractedData.estimated_claim_amount.toLocaleString()}`
              ) : (
                <span className="text-[#505f76] font-normal italic">Discussing damage cost...</span>
              )}
            </span>
          </div>
        </div>

        {/* Detail Card: Description Summary */}
        <div className="bg-white border border-[#bdc8ce] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
              Description Summary
            </span>
            <button
              onClick={() => onOpenEdit("event_description", extractedData.event_description)}
              className="text-[#00647c] hover:text-[#007f9d] p-0.5 rounded cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-[#505f76] text-[18px] mt-0.5">subject</span>
            <p className="font-body text-xs text-[#191c1e] leading-relaxed">
              {extractedData.event_description || (
                <span className="text-[#505f76] italic">
                  Voice summaries will update automatically as you converse with the AI assistant.
                </span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Action Footer */}
      <div className="p-4 border-t border-[#e0e3e5] bg-white shrink-0 shadow-sm">
        <button
          type="button"
          onClick={onSubmitClaim}
          disabled={submittingClaim || confirmed || !ticketId}
          className="w-full bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shadow-sm"
        >
          {submittingClaim ? (
            <>
              <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
              <span>Submitting Claim...</span>
            </>
          ) : confirmed ? (
            <>
              <span className="material-symbols-outlined text-base">check</span>
              <span>Claim Submitted</span>
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-base">send</span>
              <span>
                Submit Claim {pendingCount > 0 ? `(${pendingCount} Items Incomplete)` : ""}
              </span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
