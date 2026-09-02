import React from "react";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

export interface ExtractedData {
  policy_id?: string | null;
  event_date?: string | null;
  insurance_type?: string | null;
  event_description?: string | null;
  estimated_claim_amount?: number | null;
}

interface ExtractionPanelProps {
  extractedData: ExtractedData;
  onEditField?: (fieldKey: string, currentValue: any) => void;
  confidence?: number;
}

export const ExtractionPanel: React.FC<ExtractionPanelProps> = ({
  extractedData,
  onEditField,
  confidence = 0,
}) => {
  const fields = [
    {
      key: "insurance_type",
      label: "Insurance Type",
      icon: "category",
      value: extractedData.insurance_type
        ? (SUPPORTED_INSURANCE_TYPES as any)[extractedData.insurance_type] || extractedData.insurance_type
        : null,
    },
    {
      key: "policy_id",
      label: "Policy Number",
      icon: "policy",
      value: extractedData.policy_id,
    },
    {
      key: "event_date",
      label: "Incident Date",
      icon: "calendar_today",
      value: extractedData.event_date,
    },
    {
      key: "estimated_claim_amount",
      label: "Estimated Loss",
      icon: "payments",
      value:
        extractedData.estimated_claim_amount != null
          ? `₹${Number(extractedData.estimated_claim_amount).toLocaleString()}`
          : null,
    },
    {
      key: "event_description",
      label: "Description",
      icon: "description",
      value: extractedData.event_description,
    },
  ];

  return (
    <div className="bg-surface border border-surface-container-highest rounded-2xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between border-b border-surface-container-highest pb-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-xl">fact_check</span>
          <h3 className="font-headline text-sm font-bold text-on-surface">Extracted Information</h3>
        </div>
        {confidence > 0 && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
            {Math.round(confidence * 100)}% Complete
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2.5">
        {fields.map(({ key, label, icon, value }) => {
          const isCollected = value != null && value !== "";
          return (
            <div
              key={key}
              className={`p-3 rounded-xl border transition-all flex items-start justify-between gap-3 ${
                isCollected
                  ? "bg-surface-container-lowest border-surface-container-highest"
                  : "bg-surface-container-lowest/40 border-dashed border-outline-variant/50 opacity-60"
              }`}
            >
              <div className="flex items-start gap-2.5 flex-1 min-w-0">
                <span
                  className={`material-symbols-outlined text-base mt-0.5 ${
                    isCollected ? "text-primary" : "text-secondary"
                  }`}
                >
                  {icon}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-secondary block">
                    {label}
                  </span>
                  <span className="text-xs font-medium text-on-surface break-words block mt-0.5">
                    {value || "Not collected yet"}
                  </span>
                </div>
              </div>

              {isCollected && onEditField && (
                <button
                  onClick={() => onEditField(key, extractedData[key as keyof ExtractedData])}
                  className="text-secondary hover:text-primary p-1 rounded hover:bg-surface-container transition-colors"
                  title="Edit field"
                >
                  <span className="material-symbols-outlined text-sm">edit</span>
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
