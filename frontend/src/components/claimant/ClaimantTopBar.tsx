import React, { useState } from "react";

interface ClaimantTopBarProps {
  isRecording: boolean;
  agentState: string;
  currentIncidentTitle: string;
  ticketId?: string;
  onStartNewSession: () => void;
  onExportTranscript?: () => void;
  loading: boolean;
  errorBanner?: string;
  onDismissError?: () => void;
  mobileTab?: "chat" | "details";
  onTabChange?: (tab: "chat" | "details") => void;
  pendingCount?: number;
}

export const ClaimantTopBar: React.FC<ClaimantTopBarProps> = ({
  isRecording,
  agentState,
  currentIncidentTitle,
  ticketId,
  onStartNewSession,
  onExportTranscript,
  loading,
  errorBanner,
  onDismissError,
  mobileTab = "chat",
  onTabChange,
  pendingCount = 0,
}) => {
  const [copiedTicket, setCopiedTicket] = useState(false);

  const handleCopyTicket = () => {
    if (!ticketId) return;
    navigator.clipboard.writeText(ticketId);
    setCopiedTicket(true);
    setTimeout(() => setCopiedTicket(false), 2000);
  };

  return (
    <>
      <div className="px-4 md:px-8 py-3.5 border-b border-[#e2e8f0] flex flex-wrap justify-between items-center bg-white z-10 shrink-0 gap-3">
        {/* Title & Live Status */}
        <div className="flex items-center gap-3 min-w-0">
          <div>
            <div className="flex items-center gap-2 text-slate-500 mb-0.5">
              <span className="font-label text-[11px] uppercase tracking-wider font-bold text-slate-600">
                Claim Conversation
              </span>
              <span
                className={`w-2 h-2 rounded-full ${isRecording ? "bg-cyan-500 animate-ping" : "bg-emerald-500"
                  }`}
              />
              {agentState !== "idle" && (
                <span className="text-[11px] text-cyan-600 font-semibold capitalize">
                  ({agentState})
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <h1 className="font-headline text-base md:text-lg font-bold text-[#0f172a] truncate">
                {currentIncidentTitle}
              </h1>
              {ticketId && (
                <button
                  onClick={handleCopyTicket}
                  title="Click to copy Ticket ID"
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 text-[11px] font-mono font-medium text-slate-600 transition-colors cursor-pointer"
                >
                  <span>#{ticketId.slice(0, 14)}</span>
                  <span className="material-symbols-outlined text-[13px] text-slate-400">
                    {copiedTicket ? "check" : "content_copy"}
                  </span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Action Controls & Responsive Tab Switcher */}
        <div className="flex items-center gap-2">
          {/* Mobile/Tablet Screen View Switcher (< lg) */}
          {onTabChange && (
            <div className="flex lg:hidden items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200">
              <button
                type="button"
                onClick={() => onTabChange("chat")}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${mobileTab === "chat"
                  ? "bg-white text-[#00647c] shadow-2xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
                  }`}
              >
                <span className="material-symbols-outlined text-[15px]">forum</span>
                <span>Chat</span>
              </button>
              <button
                type="button"
                onClick={() => onTabChange("details")}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${mobileTab === "details"
                  ? "bg-white text-[#00647c] shadow-2xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
                  }`}
              >
                <span className="material-symbols-outlined text-[15px]">fact_check</span>
                <span>Details</span>
                {pendingCount > 0 && (
                  <span className="bg-[#00647c]/10 text-[#00647c] text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                    {pendingCount}
                  </span>
                )}
              </button>
            </div>
          )}

          {onExportTranscript && ticketId && (
            <button
              onClick={onExportTranscript}
              title="Export claim conversation dossier"
              className="flex items-center gap-1.5 text-slate-600 hover:text-[#00647c] transition-colors px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-xs font-label font-medium cursor-pointer shadow-2xs"
            >
              <span className="material-symbols-outlined text-base">download</span>
              <span className="hidden sm:inline">Export</span>
            </button>
          )}
        </div>
      </div>

      {/* Error / Warning Alert Banner */}
      {errorBanner && (
        <div className="px-6 py-2.5 bg-rose-50 border-b border-rose-200 text-rose-800 text-xs flex items-center justify-between shrink-0 animate-fade-in">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-base text-rose-600">error</span>
            <span className="font-medium">{errorBanner}</span>
          </div>
          {onDismissError && (
            <button
              onClick={onDismissError}
              className="text-rose-600 hover:text-rose-900 p-1 rounded hover:bg-rose-100"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          )}
        </div>
      )}
    </>
  );
};
