import React from "react";

interface HumanEscalationBannerProps {
  onDismiss?: () => void;
  reason?: string;
}

export const HumanEscalationBanner: React.FC<HumanEscalationBannerProps> = ({
  onDismiss,
  reason,
}) => {
  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start justify-between gap-3 text-amber-900 shadow-sm animate-fade-in">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined text-amber-600 text-2xl mt-0.5">
          support_agent
        </span>
        <div>
          <h4 className="font-headline text-sm font-bold text-amber-800">
            Human Specialist Requested
          </h4>
          <p className="text-xs text-amber-700/90 mt-1 leading-relaxed">
            Your claim intake is being transferred to a human claims specialist. All information
            collected so far has been saved and will be reviewed by your assigned adjuster.
          </p>
          {reason && (
            <span className="inline-block mt-2 text-[10px] font-semibold px-2 py-0.5 rounded bg-amber-500/20 text-amber-800">
              Reason: {reason.replace(/_/g, " ")}
            </span>
          )}
        </div>
      </div>

      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-amber-700 hover:text-amber-900 p-1 rounded hover:bg-amber-500/20 transition-colors"
        >
          <span className="material-symbols-outlined text-base">close</span>
        </button>
      )}
    </div>
  );
};
