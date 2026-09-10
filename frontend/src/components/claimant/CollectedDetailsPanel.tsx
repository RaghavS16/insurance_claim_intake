import React from "react";
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
    <div className="w-full lg:w-[400px] xl:w-[460px] bg-[#f8fafc] flex flex-col h-full border-t lg:border-t-0 lg:border-l border-[#e2e8f0] shrink-0 overflow-hidden">
      <div className="p-4 md:p-5 border-b border-[#e2e8f0] bg-white sticky top-0 z-10 flex justify-between items-center shadow-xs shrink-0">
        <div>
          <h2 className="font-headline text-base md:text-lg font-bold text-[#0f172a]">Collected Details</h2>
          <p className="font-label text-xs text-[#64748b]">Review and verify extracted information</p>
        </div>
        <span className={`font-label text-[10px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wider ${pendingCount === 0 ? "bg-emerald-100 text-emerald-800 border border-emerald-200" : "bg-slate-100 text-slate-600 border border-slate-200"}`}>
          {pendingCount === 0 ? "Ready to Submit" : `${pendingCount} Pending`}
        </span>
      </div>

      <div className="p-4 md:p-5 space-y-3.5 flex-1 overflow-y-auto">
        <div className={`bg-white border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden shadow-xs ${extractedData.policy_id ? "border-[#00647c] ring-1 ring-[#00647c]/10" : "border-[#cbd5e1]"}`}>
          {extractedData.policy_id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#00647c]"></div>}
          <div className="flex justify-between items-start pl-1">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Policy ID</span>
            <button onClick={() => onOpenEdit("policy_id", extractedData.policy_id)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer">
              <span className="material-symbols-outlined text-[16px]">edit</span>
            </button>
          </div>
          <div className="flex items-center gap-2 pl-1">
            <span className="material-symbols-outlined text-[#64748b] text-[20px]">verified_user</span>
            <span className="font-body text-sm text-[#0f172a] font-semibold font-mono">
              {extractedData.policy_id || <span className="text-[#94a3b8] font-normal italic">Not specified yet</span>}
            </span>
          </div>
        </div>

        <div className="bg-white border border-[#cbd5e1] rounded-xl p-4 flex flex-col gap-2 shadow-xs">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Insurance Type</span>
            <button onClick={() => onOpenEdit("insurance_type", extractedData.insurance_type)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer"><span className="material-symbols-outlined text-[16px]">edit</span></button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-[20px]">category</span>
            <span className="font-body text-sm text-[#0f172a] font-semibold capitalize">
              {extractedData.insurance_type ? ((SUPPORTED_INSURANCE_TYPES as any)[extractedData.insurance_type] || extractedData.insurance_type) : <span className="text-[#94a3b8] font-normal italic">Pending classification...</span>}
            </span>
          </div>
        </div>

        <div className="bg-white border border-[#cbd5e1] rounded-xl p-4 flex flex-col gap-2 shadow-xs">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Incident Date</span>
            <button onClick={() => onOpenEdit("event_date", extractedData.event_date)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer"><span className="material-symbols-outlined text-[16px]">edit</span></button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#64748b] text-[20px]">calendar_today</span>
            <span className="font-body text-sm text-[#0f172a] font-semibold">{extractedData.event_date || <span className="text-[#94a3b8] font-normal italic">Waiting for date...</span>}</span>
          </div>
        </div>

        <div className="bg-white border border-[#cbd5e1] rounded-xl p-4 flex flex-col gap-2 shadow-xs">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Incident Location</span>
            <button onClick={() => onOpenEdit("event_location", extractedData.event_location)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer"><span className="material-symbols-outlined text-[16px]">edit</span></button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#64748b] text-[20px]">location_on</span>
            <span className="font-body text-sm text-[#0f172a] font-semibold">{extractedData.event_location || <span className="text-[#94a3b8] font-normal italic">Collecting location...</span>}</span>
          </div>
        </div>

        <div className="bg-white border border-[#cbd5e1] rounded-xl p-4 flex flex-col gap-2 shadow-xs">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Estimated Loss (INR)</span>
            <button onClick={() => onOpenEdit("estimated_claim_amount", extractedData.estimated_claim_amount)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer"><span className="material-symbols-outlined text-[16px]">edit</span></button>
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-[20px]">payments</span>
            <span className="font-body text-sm text-[#0f172a] font-semibold">{extractedData.estimated_claim_amount != null ? `₹${Number(extractedData.estimated_claim_amount).toLocaleString("en-IN")}` : <span className="text-[#94a3b8] font-normal italic">Discussing damage cost...</span>}</span>
          </div>
        </div>

        <div className="bg-white border border-[#cbd5e1] rounded-xl p-4 flex flex-col gap-2 shadow-xs">
          <div className="flex justify-between items-start">
            <span className="font-label text-[11px] text-[#64748b] font-bold uppercase tracking-wider">Description Summary</span>
            <button onClick={() => onOpenEdit("event_description", extractedData.event_description)} className="text-[#00647c] hover:text-[#004e61] p-0.5 rounded cursor-pointer"><span className="material-symbols-outlined text-[16px]">edit</span></button>
          </div>
          <p className="font-body text-xs text-[#334155] leading-relaxed line-clamp-3">{extractedData.event_description || <span className="text-[#94a3b8] italic">No description recorded yet</span>}</p>
        </div>
      </div>

      <div className="p-4 md:p-5 border-t border-[#e2e8f0] bg-white shrink-0">
        <button onClick={onSubmitClaim} disabled={submittingClaim || confirmed} className={`w-full py-3 px-4 rounded-xl font-label text-xs font-bold tracking-wider uppercase transition-all duration-200 flex items-center justify-center gap-2 shadow-xs ${confirmed ? "bg-emerald-600 text-white cursor-default" : "bg-[#00647c] hover:bg-[#004e61] text-white cursor-pointer active:scale-[0.99]"} ${submittingClaim ? "opacity-75 cursor-wait" : ""}`}>
          <span className="material-symbols-outlined text-base">{confirmed ? "check_circle" : "send"}</span>
          <span>{confirmed ? "Claim Submitted" : submittingClaim ? "Submitting Claim..." : pendingCount > 0 ? `Submit Claim (${pendingCount} Items Incomplete)` : "Submit Verified Claim"}</span>
        </button>
      </div>
    </div>
  );
};
