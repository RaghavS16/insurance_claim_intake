import React, { RefObject } from "react";
import { ConversationTurn } from "./ChatTranscript";

interface TranscriptSegment {
  segment_id: string;
  sequence: number;
  speaker: "user" | "agent";
  text: string;
  is_final: boolean;
  start_ts?: number;
  confidence?: number;
  global_seq?: number;
  timestamp?: number;
}

interface ClaimantChatAreaProps {
  history: ConversationTurn[];
  partialSegments: Map<string, TranscriptSegment>;
  agentState: string;
  confirmed: boolean;
  submittedMessage: string;
  chatContainerRef: RefObject<HTMLDivElement | null>;
}

export const ClaimantChatArea: React.FC<ClaimantChatAreaProps> = ({
  history,
  partialSegments,
  agentState,
  confirmed,
  submittedMessage,
  chatContainerRef,
}) => {
  return (
    <div
      ref={chatContainerRef}
      className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scroll-smooth pb-48"
    >
      {history.map((turn, idx) => {
        if (turn.speaker === "agent") {
          return (
            <div key={`msg-${idx}`} className="flex gap-3 max-w-[85%]">
              <div className="w-8 h-8 rounded-full bg-[#eceef0] flex items-center justify-center shrink-0 border border-[#e0e3e5] text-[#00647c]">
                <span className="material-symbols-outlined text-base">robot_2</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="font-label text-xs text-[#505f76] font-medium">InsureClaimAI</span>
                <div className="bg-[#F1F5F9] p-3.5 rounded-2xl rounded-tl-none border border-[#e0e3e5] shadow-sm">
                  <p className="font-body text-sm text-[#191c1e] leading-relaxed whitespace-pre-line">
                    {turn.text}
                  </p>
                </div>
              </div>
            </div>
          );
        } else {
          return (
            <div key={`msg-${idx}`} className="flex gap-3 max-w-[85%] ml-auto justify-end">
              <div className="flex flex-col gap-1 items-end">
                <span className="font-label text-xs text-[#505f76] font-medium">You</span>
                <div className="bg-[#00647c] text-white p-3.5 rounded-2xl rounded-tr-none shadow-sm">
                  <p className="font-body text-sm leading-relaxed whitespace-pre-line">
                    {turn.text}
                  </p>
                </div>
              </div>
            </div>
          );
        }
      })}

      {/* Partial live transcript */}
      {Array.from(partialSegments.values()).map((seg) => (
        <div key={seg.segment_id} className="flex gap-3 max-w-[85%] ml-auto justify-end opacity-85">
          <div className="flex flex-col gap-1 items-end">
            <span className="font-label text-xs text-[#0891B2] font-semibold">Speaking...</span>
            <div className="bg-[#00647c]/90 text-white p-3.5 rounded-2xl rounded-tr-none border border-[#0891B2]">
              <p className="font-body text-sm italic">{seg.text}</p>
            </div>
          </div>
        </div>
      ))}

      {/* AI Processing Indicator */}
      {agentState === "thinking" && (
        <div className="flex gap-3 max-w-[85%]">
          <div className="w-8 h-8 rounded-full bg-[#eceef0] flex items-center justify-center shrink-0 border border-[#e0e3e5]">
            <span className="material-symbols-outlined text-[#0EA5E9] animate-spin text-base">
              progress_activity
            </span>
          </div>
          <div className="flex flex-col gap-1 justify-center">
            <span className="font-label text-xs text-[#505f76] italic">InsureClaimAI is processing...</span>
          </div>
        </div>
      )}

      {confirmed && (
        <div className="p-4 bg-emerald-50 border border-emerald-500/30 rounded-xl text-emerald-800 text-xs flex items-center gap-3 shadow-sm">
          <span className="material-symbols-outlined text-2xl text-emerald-600">verified</span>
          <div>
            <h4 className="font-bold text-sm">Claim Successfully Submitted</h4>
            <p className="mt-0.5">{submittedMessage || "Your claim has been assigned to an adjuster."}</p>
          </div>
        </div>
      )}

      {/* Bottom Spacer so messages are never hidden under the voice console */}
      <div className="h-48 w-full shrink-0 pointer-events-none" aria-hidden="true" />
    </div>
  );
};
