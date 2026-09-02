import React from "react";

interface ClaimantTopBarProps {
  isRecording: boolean;
  agentState: string;
  currentIncidentTitle: string;
  onStartNewSession: () => void;
  loading: boolean;
  errorBanner?: string;
  onDismissError?: () => void;
}

export const ClaimantTopBar: React.FC<ClaimantTopBarProps> = ({
  isRecording,
  agentState,
  currentIncidentTitle,
  onStartNewSession,
  loading,
  errorBanner,
  onDismissError,
}) => {
  return (
    <>
      <div className="px-4 md:px-8 py-3.5 border-b border-[#e0e3e5] flex justify-between items-center bg-white z-10 shrink-0">
        <div>
          <div className="flex items-center gap-2 text-[#505f76] mb-0.5">
            <span className="font-label text-[11px] uppercase tracking-wider font-semibold">Active Intake</span>
            <span
              className={`w-2 h-2 rounded-full ${
                isRecording ? "bg-[#0891B2] animate-pulse" : "bg-emerald-500"
              }`}
            />
            {agentState !== "idle" && (
              <span className="text-[11px] text-[#0891B2] capitalize font-medium">
                ({agentState})
              </span>
            )}
          </div>
          <h1 className="font-headline text-lg md:text-xl font-bold text-[#191c1e]">
            {currentIncidentTitle}
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onStartNewSession}
            disabled={loading}
            className="flex items-center gap-1.5 text-[#505f76] hover:text-[#00647c] transition-colors px-3 py-1.5 rounded-lg hover:bg-[#eceef0] text-xs font-label font-medium cursor-pointer"
          >
            <span className="material-symbols-outlined text-base">refresh</span>
            <span>New Session</span>
          </button>
        </div>
      </div>

      {errorBanner && (
        <div className="px-6 py-2 bg-[#ffdad6] text-[#93000a] text-xs flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-sm">warning</span>
            <span>{errorBanner}</span>
          </div>
          {onDismissError && (
            <button onClick={onDismissError} className="text-[#93000a] hover:opacity-70">
              <span className="material-symbols-outlined text-sm">close</span>
            </button>
          )}
        </div>
      )}
    </>
  );
};
