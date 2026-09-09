import React, { RefObject, useState, useEffect } from "react";
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
  linkedPolicies?: Array<{ policy_number: string; policy_type: string; coverage_amount?: number }>;
  onSelectPromptSuggestion?: (text: string) => void;
  onExportTranscript?: () => void;
}

const formatMessageTime = (ts?: number | string | null) => {
  if (!ts) return "";
  try {
    const date = typeof ts === "string" ? new Date(ts) : new Date(ts);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
};

export const ClaimantChatArea: React.FC<ClaimantChatAreaProps> = ({
  history,
  partialSegments,
  agentState,
  confirmed,
  submittedMessage,
  chatContainerRef,
  linkedPolicies = [],
  onSelectPromptSuggestion,
  onExportTranscript,
}) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  // Monitor scroll position to show/hide scroll-to-bottom button
  useEffect(() => {
    const el = chatContainerRef.current;
    if (!el) return;

    const handleScroll = () => {
      const isUp = el.scrollHeight - el.scrollTop - el.clientHeight > 200;
      setShowScrollBottom(isUp);
    };

    el.addEventListener("scroll", handleScroll);
    return () => el.removeEventListener("scroll", handleScroll);
  }, [chatContainerRef]);

  const scrollToBottom = () => {
    const el = chatContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  const handleCopyText = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleSpeakText = (text: string, idx: number) => {
    if (!("speechSynthesis" in window)) return;
    if (speakingIndex === idx) {
      window.speechSynthesis.cancel();
      setSpeakingIndex(null);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.onend = () => setSpeakingIndex(null);
    utterance.onerror = () => setSpeakingIndex(null);
    setSpeakingIndex(idx);
    window.speechSynthesis.speak(utterance);
  };

  const isConversationEmpty = history.length === 0 && partialSegments.size === 0;

  return (
    <div
      ref={chatContainerRef}
      className={`flex-1 p-4 md:p-8 space-y-5 scroll-smooth pb-48 relative bg-gradient-to-b from-[#f8fafc]/50 to-white ${
        isConversationEmpty
          ? "flex flex-col items-center justify-center min-h-full overflow-hidden"
          : "overflow-y-auto"
      }`}
    >
      {/* Empty State / Welcome Screen */}
      {isConversationEmpty && (
        <div className="max-w-xl mx-auto text-center space-y-5 animate-fade-in -mt-8 md:-mt-12">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-[#00647c] to-[#0891B2] flex items-center justify-center text-white mx-auto shadow-md">
            <span className="material-symbols-outlined text-3xl">smart_toy</span>
          </div>
          <div>
            <h2 className="font-headline text-xl md:text-2xl font-bold text-[#0f172a] tracking-tight">
              Start Your Insurance Claim Intake
            </h2>
            <p className="text-xs md:text-sm text-slate-500 mt-2 max-w-md mx-auto leading-relaxed">
              Speak naturally or type your incident description. Our AI will automatically extract
              the necessary details, verify policy coverage, and prepare your claim.
            </p>
          </div>
        </div>
      )}

      {/* Message History */}
      {history.map((turn, idx) => {
        const isAgent = turn.speaker === "agent";
        const timeStr = formatMessageTime(turn.timestamp);

        if (isAgent) {
          return (
            <div key={`msg-${idx}`} className="flex gap-3 max-w-[85%] group animate-fade-in">
              {/* Agent Avatar */}
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#00647c] to-[#0891B2] text-white flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                <span className="material-symbols-outlined text-base">smart_toy</span>
              </div>

              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-label text-xs font-semibold text-[#00647c]">
                    InsureClaimAI
                  </span>
                  {timeStr && (
                    <span className="text-[10px] text-slate-400 font-medium">{timeStr}</span>
                  )}
                </div>

                {/* Agent Bubble */}
                <div className="relative bg-[#f1f5f9] text-[#0f172a] p-4 rounded-2xl rounded-tl-xs border border-slate-200/80 shadow-xs">
                  <p className="font-body text-sm leading-relaxed whitespace-pre-line">
                    {turn.text}
                  </p>

                  {/* Bubble Action Bar on Hover */}
                  <div className="absolute right-2 -bottom-3 hidden group-hover:flex items-center gap-1 bg-white border border-slate-200 shadow-sm rounded-lg px-1 py-0.5 z-10">
                    <button
                      onClick={() => handleCopyText(turn.text, idx)}
                      title="Copy text"
                      className="p-1 hover:text-[#00647c] text-slate-400 rounded hover:bg-slate-50 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[14px]">
                        {copiedIndex === idx ? "check" : "content_copy"}
                      </span>
                    </button>
                    <button
                      onClick={() => handleSpeakText(turn.text, idx)}
                      title={speakingIndex === idx ? "Stop reading" : "Read aloud"}
                      className={`p-1 rounded hover:bg-slate-50 transition-colors ${speakingIndex === idx ? "text-[#00647c] animate-pulse" : "text-slate-400 hover:text-[#00647c]"
                        }`}
                    >
                      <span className="material-symbols-outlined text-[14px]">
                        {speakingIndex === idx ? "volume_off" : "volume_up"}
                      </span>
                    </button>
                  </div>
                </div>

                {/* Quick Policy Chips if assistant asked for policy */}
                {idx === history.length - 1 &&
                  turn.text.toLowerCase().includes("policy") &&
                  linkedPolicies &&
                  linkedPolicies.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1 animate-fade-in">
                      <span className="text-[11px] text-slate-400 self-center font-medium">
                        Your policies:
                      </span>
                      {linkedPolicies.map((p) => (
                        <button
                          key={p.policy_number}
                          onClick={() => onSelectPromptSuggestion?.(p.policy_number)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-cyan-50 border border-[#00647c]/30 hover:border-[#00647c] text-xs font-semibold text-[#00647c] shadow-xs cursor-pointer transition-all hover:scale-[1.02] active:scale-[0.98]"
                        >
                          <span className="material-symbols-outlined text-sm">verified_user</span>
                          <span className="font-mono">{p.policy_number}</span>
                          <span className="text-[10px] text-slate-500 font-normal capitalize">
                            ({p.policy_type})
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
              </div>
            </div>
          );
        } else {
          return (
            <div
              key={`msg-${idx}`}
              className="flex gap-3 max-w-[85%] ml-auto justify-end group animate-fade-in"
            >
              <div className="flex flex-col gap-1 items-end min-w-0">
                <div className="flex items-center gap-2">
                  {timeStr && (
                    <span className="text-[10px] text-slate-400 font-medium">{timeStr}</span>
                  )}
                  <span className="font-label text-xs font-semibold text-slate-700">You</span>
                </div>

                {/* User Bubble */}
                <div className="relative bg-gradient-to-r from-[#00647c] to-[#004e61] text-white p-4 rounded-2xl rounded-tr-xs shadow-xs">
                  <p className="font-body text-sm leading-relaxed whitespace-pre-line">
                    {turn.text}
                  </p>

                  {/* Copy Button */}
                  <div className="absolute left-2 -bottom-3 hidden group-hover:flex items-center gap-1 bg-white text-slate-600 border border-slate-200 shadow-sm rounded-lg px-1 py-0.5 z-10">
                    <button
                      onClick={() => handleCopyText(turn.text, idx)}
                      title="Copy text"
                      className="p-1 hover:text-[#00647c] text-slate-400 rounded hover:bg-slate-50 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[14px]">
                        {copiedIndex === idx ? "check" : "content_copy"}
                      </span>
                    </button>
                  </div>
                </div>
              </div>

              {/* User Avatar */}
              <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                <span className="material-symbols-outlined text-base">person</span>
              </div>
            </div>
          );
        }
      })}

      {/* Partial live voice transcript */}
      {Array.from(partialSegments.values()).map((seg) => (
        <div
          key={seg.segment_id}
          className="flex gap-3 max-w-[85%] ml-auto justify-end opacity-90 animate-pulse"
        >
          <div className="flex flex-col gap-1 items-end">
            <span className="font-label text-xs text-[#0891B2] font-semibold flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-[#0891B2] animate-ping" />
              Transcribing audio...
            </span>
            <div className="bg-[#00647c]/90 text-white p-3.5 rounded-2xl rounded-tr-xs border border-[#0891B2] shadow-sm">
              <p className="font-body text-sm italic">{seg.text}</p>
            </div>
          </div>
        </div>
      ))}

      {/* AI Processing / Thinking Indicator */}
      {agentState === "thinking" && (
        <div className="flex gap-3 max-w-[85%] animate-fade-in">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#00647c] to-[#0891B2] text-white flex items-center justify-center shrink-0 shadow-xs">
            <span className="material-symbols-outlined text-base animate-spin">
              progress_activity
            </span>
          </div>
          <div className="bg-slate-100 border border-slate-200 rounded-2xl rounded-tl-xs px-4 py-2.5 flex items-center gap-2">
            <span className="flex space-x-1">
              <span className="w-1.5 h-1.5 bg-[#00647c] rounded-full animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 bg-[#00647c] rounded-full animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 bg-[#00647c] rounded-full animate-bounce" />
            </span>
            <span className="text-xs text-slate-500 font-medium">Analyzing details...</span>
          </div>
        </div>
      )}

      {/* Claim Submission Success Banner */}
      {confirmed && (
        <div className="p-4 bg-emerald-50 border border-emerald-500/30 rounded-2xl text-emerald-900 text-xs flex items-center justify-between gap-4 shadow-sm animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow-xs">
              <span className="material-symbols-outlined text-2xl">verified</span>
            </div>
            <div>
              <h4 className="font-bold text-sm text-emerald-900">Claim Successfully Submitted</h4>
              <p className="mt-0.5 text-emerald-700">
                {submittedMessage || "Your claim has been verified and registered for adjuster review."}
              </p>
            </div>
          </div>
          {onExportTranscript && (
            <button
              onClick={onExportTranscript}
              className="flex items-center gap-1 px-3 py-1.5 bg-white border border-emerald-300 text-emerald-800 hover:bg-emerald-100/50 rounded-lg text-xs font-semibold shadow-2xs transition-colors shrink-0 cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">download</span>
              <span>Export Dossier</span>
            </button>
          )}
        </div>
      )}

      {/* Floating Scroll to Bottom Button */}
      {showScrollBottom && (
        <button
          onClick={scrollToBottom}
          className="fixed bottom-28 left-1/2 -translate-x-1/2 md:left-[calc(50%+8rem)] z-20 flex items-center gap-1.5 bg-white text-slate-700 hover:text-[#00647c] border border-slate-200 shadow-md hover:shadow-lg rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all duration-200 animate-bounce cursor-pointer"
        >
          <span className="material-symbols-outlined text-sm">arrow_downward</span>
          <span>Scroll to latest</span>
        </button>
      )}

      {/* Bottom Spacer */}
      <div className="h-44 w-full shrink-0 pointer-events-none" aria-hidden="true" />
    </div>
  );
};
