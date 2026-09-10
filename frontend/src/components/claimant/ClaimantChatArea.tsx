import React, { RefObject, useState, useEffect, useRef } from "react";
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
  textMode?: boolean;
  linkedPolicies?: Array<{ policy_number: string; policy_type: string; coverage_amount?: number }>;
  onSelectPromptSuggestion?: (text: string) => void;
  onExportTranscript?: () => void;
  onScrollChange?: (isScrolledUp: boolean) => void;
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
  onScrollChange,
}) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Monitor scroll position to notify parent
  useEffect(() => {
    const el = chatContainerRef.current;
    if (!el) return;

    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      onScrollChange?.(distanceFromBottom > 100);
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [chatContainerRef, onScrollChange]);

  // Auto-scroll when new messages arrive if user is near bottom
  useEffect(() => {
    const el = chatContainerRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 280;
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [history.length, partialSegments.size, agentState, chatContainerRef]);

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
      className={`flex-1 p-4 md:p-8 space-y-5 scroll-smooth pb-44 relative bg-gradient-to-b from-[#f8fafc]/50 to-white ${isConversationEmpty
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
            <div key={`msg-${idx}`} className="flex gap-3 max-w-[88%] md:max-w-[80%] group animate-fade-in">
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
                  <p className="font-body text-xs md:text-sm leading-relaxed whitespace-pre-line">
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
              className="flex gap-3 max-w-[88%] md:max-w-[80%] ml-auto justify-end group animate-fade-in"
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
                  <p className="font-body text-xs md:text-sm leading-relaxed whitespace-pre-line">
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
          className="flex gap-3 max-w-[88%] md:max-w-[80%] ml-auto justify-end opacity-90 animate-pulse"
        >
          <div className="flex flex-col gap-1 items-end">
            <span className="font-label text-xs text-[#0891B2] font-semibold flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-[#0891B2] animate-ping" />
              Transcribing audio...
            </span>
            <div className="bg-[#00647c]/90 text-white p-3.5 rounded-2xl rounded-tr-xs border border-[#0891B2] shadow-sm">
              <p className="font-body text-xs md:text-sm italic">{seg.text}</p>
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


      {/* Explicit Anchor for smooth and accurate scroll to latest */}
      <div ref={messagesEndRef} className="h-1 w-full shrink-0" aria-hidden="true" />

      {/* Bottom Spacer for fixed VoiceConsole */}
      <div className="h-44 w-full shrink-0 pointer-events-none" aria-hidden="true" />
    </div>
  );
};

