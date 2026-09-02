import React, { RefObject } from "react";

export interface ConversationTurn {
  turn: number;
  speaker: "user" | "agent";
  text: string;
  segment_id?: string;
  global_seq?: number;
  timestamp?: number;
}

interface ChatTranscriptProps {
  history: ConversationTurn[];
  containerRef: RefObject<HTMLDivElement | null>;
  liveClaimantText?: string;
  isAgentThinking?: boolean;
}

export const ChatTranscript: React.FC<ChatTranscriptProps> = ({
  history,
  containerRef,
  liveClaimantText,
  isAgentThinking,
}) => {
  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto p-4 space-y-4 max-h-[500px] border border-surface-container-highest rounded-2xl bg-surface/50 scroll-smooth"
    >
      {history.length === 0 && !liveClaimantText && (
        <div className="flex flex-col items-center justify-center h-48 text-center text-secondary">
          <span className="material-symbols-outlined text-4xl mb-2 text-outline">forum</span>
          <p className="text-sm font-medium">Your conversation will appear here.</p>
          <p className="text-xs text-secondary/70">Speak or type your incident details to begin.</p>
        </div>
      )}

      {history.map((turn, idx) => {
        const isUser = turn.speaker === "user";
        return (
          <div
            key={idx}
            className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
          >
            <div className="flex items-center gap-1.5 mb-1 px-1">
              <span className="text-[10px] font-semibold tracking-wider text-secondary uppercase">
                {isUser ? "You" : "InsureClaim Agent"}
              </span>
            </div>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                isUser
                  ? "bg-primary text-on-primary rounded-tr-none"
                  : "bg-surface-container-highest text-on-surface rounded-tl-none border border-outline-variant/30"
              }`}
            >
              {turn.text}
            </div>
          </div>
        );
      })}

      {liveClaimantText && (
        <div className="flex flex-col items-end opacity-70">
          <div className="flex items-center gap-1.5 mb-1 px-1">
            <span className="text-[10px] font-semibold tracking-wider text-secondary uppercase">
              You (Speaking...)
            </span>
          </div>
          <div className="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed bg-primary/60 text-on-primary rounded-tr-none italic">
            {liveClaimantText}
          </div>
        </div>
      )}

      {isAgentThinking && (
        <div className="flex flex-col items-start">
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-surface-container-high text-secondary text-xs rounded-tl-none border border-outline-variant/30">
            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
            <span>Thinking...</span>
          </div>
        </div>
      )}
    </div>
  );
};
