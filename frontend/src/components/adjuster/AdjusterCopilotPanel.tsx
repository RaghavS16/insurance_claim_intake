import React, { useRef, useEffect, useState } from "react";
import { FileData, CopilotAnalysis } from "./types";
import { MarkdownRenderer } from "../common/MarkdownRenderer";

interface Props {
  file: FileData;
  copilotLoading: boolean;
  updatingStatus: boolean;
  onLoadCopilot: (ticketId: string) => void;
  onUpdateStatus: (status: string) => void;
  copilotMessage: string;
  setCopilotMessage: (value: string) => void;
  copilotChat: Array<{ speaker: string; message: string; created_at?: string }>;
  onSendCopilotMessage: (msg?: string) => void;
  copilotChatLoading?: boolean;
}

const getRecommendationBadge = (rec?: string) => {
  const norm = (rec || "").toUpperCase();
  if (norm.includes("APPROVE") && !norm.includes("PARTIAL")) {
    return {
      label: "Full Approval Recommended",
      bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-700",
      icon: "check_circle",
    };
  }
  if (norm.includes("PARTIAL")) {
    return {
      label: "Partial Approval Recommended",
      bg: "bg-cyan-500/10 border-cyan-500/30 text-cyan-700",
      icon: "published_with_changes",
    };
  }
  if (norm.includes("EVIDENCE") || norm.includes("REQUEST")) {
    return {
      label: "Evidence Request Required",
      bg: "bg-amber-500/10 border-amber-500/30 text-amber-700",
      icon: "rule",
    };
  }
  if (norm.includes("REJECT")) {
    return {
      label: "Rejection Recommended",
      bg: "bg-rose-500/10 border-rose-500/30 text-rose-700",
      icon: "cancel",
    };
  }
  if (norm.includes("ESCALATE")) {
    return {
      label: "Escalation / SIU Review",
      bg: "bg-purple-500/10 border-purple-500/30 text-purple-700",
      icon: "report",
    };
  }
  return {
    label: "Under Adjudication Review",
    bg: "bg-slate-100 border-slate-300 text-slate-700",
    icon: "info",
  };
};

export const AdjusterCopilotPanel: React.FC<Props> = ({
  file,
  copilotLoading,
  updatingStatus,
  onLoadCopilot,
  onUpdateStatus,
  copilotMessage,
  setCopilotMessage,
  copilotChat,
  onSendCopilotMessage,
  copilotChatLoading = false,
}) => {
  const report: CopilotAnalysis = file.copilot || {};
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<"analysis" | "evidence" | "risks" | "sources">("analysis");
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [copilotChat, copilotChatLoading]);

  const badge = getRecommendationBadge(report.decision_recommendation);

  const quickPrompts = [
    "What additional evidence should I request from claimant?",
    "Check if repair cost is consistent with incident facts",
    "Explain policy exclusions and deductible rules",
    "Draft evidence request message for the claimant",
  ];

  return (
    <div className="grid xl:grid-cols-[1.1fr_420px] gap-6 items-start">
      {/* LEFT: Decision-Making Report & Deep Dive */}
      <div className="space-y-5">
        <section className="bg-white border border-[#e0e3e5] rounded-2xl overflow-hidden shadow-xs">
          {/* Header */}
          <div className="px-6 py-4 border-b border-[#e0e3e5] flex flex-wrap gap-3 items-center justify-between bg-gradient-to-r from-slate-50 to-white">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#00647c] flex items-center justify-center text-white shadow-xs">
                <span className="material-symbols-outlined text-2xl">smart_toy</span>
              </div>
              <div>
                <h2 className="font-headline font-bold text-lg text-slate-900 leading-tight">
                  AI Decision Copilot
                </h2>
                <p className="text-xs text-slate-500">
                  Comprehensive Claim Dossier Analysis &amp; Suggestions
                </p>
              </div>
            </div>
            <button
              onClick={() => onLoadCopilot(file.claim.ticket_id)}
              disabled={copilotLoading}
              className="flex items-center gap-1.5 text-xs bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white px-3.5 py-2 rounded-xl font-semibold transition shadow-xs cursor-pointer"
            >
              <span className={`material-symbols-outlined text-sm ${copilotLoading ? "animate-spin" : ""}`}>
                sync
              </span>
              <span>{copilotLoading ? "Analyzing Dossier..." : "Re-run Analysis"}</span>
            </button>
          </div>

          {copilotLoading ? (
            <div className="py-20 text-center px-4">
              <div className="w-10 h-10 border-3 border-[#00647c] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm font-semibold text-slate-800">
                Synthesizing claim facts, evidence &amp; coverage rules…
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Evaluating policy limits, damage consistency, fraud indicators, and settlement suggestions
              </p>
            </div>
          ) : report.executive_summary || report.summary ? (
            <div className="p-6 space-y-6">
              {/* Decision Recommendation Highlight Box */}
              <div className={`p-4 rounded-xl border ${badge.bg} flex flex-col md:flex-row md:items-center justify-between gap-4`}>
                <div className="flex items-start gap-3">
                  <span className="material-symbols-outlined text-2xl mt-0.5">{badge.icon}</span>
                  <div>
                    <div className="text-[10px] uppercase font-bold tracking-wider opacity-80">
                      AI Advisory Recommendation
                    </div>
                    <div className="text-base font-bold mt-0.5">{badge.label}</div>
                    {report.decision_rationale && (
                      <p className="text-xs mt-1 leading-relaxed opacity-90">{report.decision_rationale}</p>
                    )}
                  </div>
                </div>
                {report.recommended_payout_amount != null && (
                  <div className="bg-white/80 backdrop-blur-xs border border-current/20 px-4 py-2.5 rounded-xl shrink-0 text-right">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                      Suggested Settlement
                    </div>
                    <div className="text-lg font-bold text-slate-900 font-mono">
                      ₹{Number(report.recommended_payout_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                    {report.confidence_score != null && (
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {Math.round(report.confidence_score * 100)}% Confidence
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Actionable Suggestions for Adjuster */}
              {report.actionable_suggestions && report.actionable_suggestions.length > 0 && (
                <div className="bg-[#f0f9ff] border border-[#bae6fd] rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className="material-symbols-outlined text-[#0284c7] text-lg">lightbulb</span>
                    <h3 className="text-xs font-bold text-[#0369a1] uppercase tracking-wider">
                      Actionable Suggestions for Adjuster
                    </h3>
                  </div>
                  <div className="space-y-2">
                    {report.actionable_suggestions.map((suggestion, idx) => (
                      <div
                        key={idx}
                        className="bg-white border border-[#e0f2fe] rounded-lg p-2.5 text-xs text-slate-700 flex items-start justify-between gap-2 shadow-2xs"
                      >
                        <p className="leading-relaxed flex-1">
                          <b className="text-[#0284c7] mr-1.5">{idx + 1}.</b>
                          {suggestion}
                        </p>
                        <button
                          type="button"
                          onClick={() => onSendCopilotMessage(`Can you explain more about suggestion: "${suggestion}"?`)}
                          className="shrink-0 text-[10px] text-[#0284c7] hover:underline font-semibold flex items-center gap-1 cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-xs">chat</span>
                          Discuss
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Executive Summary */}
              <div className="border-l-4 border-[#00647c] bg-slate-50 p-4 rounded-r-xl">
                <b className="block text-[11px] uppercase tracking-wider text-[#00647c] font-bold mb-1">
                  Incident &amp; Claim Overview
                </b>
                <p className="text-xs text-slate-700 leading-relaxed">
                  {report.executive_summary || report.summary}
                </p>
              </div>

              {/* Sub-Tabs for Deep Dive */}
              <div>
                <div className="flex border-b border-[#e2e8f0] gap-4 text-xs font-semibold text-slate-500 mb-4">
                  <button
                    onClick={() => setActiveTab("analysis")}
                    className={`pb-2 transition cursor-pointer border-b-2 ${
                      activeTab === "analysis"
                        ? "border-[#00647c] text-[#00647c] font-bold"
                        : "border-transparent hover:text-slate-700"
                    }`}
                  >
                    Coverage &amp; Requirements
                  </button>
                  <button
                    onClick={() => setActiveTab("evidence")}
                    className={`pb-2 transition cursor-pointer border-b-2 ${
                      activeTab === "evidence"
                        ? "border-[#00647c] text-[#00647c] font-bold"
                        : "border-transparent hover:text-slate-700"
                    }`}
                  >
                    Evidence Assessment
                  </button>
                  <button
                    onClick={() => setActiveTab("risks")}
                    className={`pb-2 transition cursor-pointer border-b-2 ${
                      activeTab === "risks"
                        ? "border-[#00647c] text-[#00647c] font-bold"
                        : "border-transparent hover:text-slate-700"
                    }`}
                  >
                    Risk Flags ({report.risk_flags?.length || 0})
                  </button>
                  <button
                    onClick={() => setActiveTab("sources")}
                    className={`pb-2 transition cursor-pointer border-b-2 ${
                      activeTab === "sources"
                        ? "border-[#00647c] text-[#00647c] font-bold"
                        : "border-transparent hover:text-slate-700"
                    }`}
                  >
                    Grounding Sources ({file.knowledge_sources?.length || 0})
                  </button>
                </div>

                {activeTab === "analysis" && (
                  <div className="space-y-4">
                    {report.mandatory_requirements && report.mandatory_requirements.length > 0 && (
                      <div className="border border-slate-200 rounded-xl overflow-hidden">
                        <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-700">
                          Mandatory Requirements Audit
                        </div>
                        <div className="divide-y divide-slate-100">
                          {report.mandatory_requirements.map((r, i) => (
                            <div key={i} className="px-4 py-2.5 flex items-center justify-between gap-3 text-xs">
                              <div>
                                <span className="font-semibold text-slate-800">{r.label || "Requirement"}</span>
                                {r.condition && (
                                  <div className="text-[11px] text-slate-500 mt-0.5">{r.condition}</div>
                                )}
                              </div>
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                                  r.status === "complete"
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                    : r.status === "missing"
                                    ? "bg-rose-50 text-rose-700 border border-rose-200"
                                    : "bg-amber-50 text-amber-700 border border-amber-200"
                                }`}
                              >
                                {r.status || "review"}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {report.coverage_observations && report.coverage_observations.length > 0 && (
                      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5">
                        <b className="text-xs font-bold text-slate-800">Coverage Observations</b>
                        <ul className="mt-2 space-y-1.5 text-xs text-slate-600">
                          {report.coverage_observations.map((obs, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-[#00647c]">•</span>
                              <span>{obs}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "evidence" && (
                  <div className="space-y-3">
                    {report.evidence_assessment && report.evidence_assessment.length > 0 ? (
                      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5">
                        <b className="text-xs font-bold text-slate-800">Evidence Assessment Findings</b>
                        <ul className="mt-2 space-y-1.5 text-xs text-slate-600">
                          {report.evidence_assessment.map((e, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-emerald-600 font-bold">✓</span>
                              <span>{e}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 p-4">No specific evidence findings reported.</p>
                    )}

                    {report.recommended_next_steps && report.recommended_next_steps.length > 0 && (
                      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5">
                        <b className="text-xs font-bold text-slate-800">Recommended Next Steps</b>
                        <ul className="mt-2 space-y-1.5 text-xs text-slate-600">
                          {report.recommended_next_steps.map((step, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="text-[#00647c] font-bold">{i + 1}.</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "risks" && (
                  <div className="space-y-3">
                    {report.risk_flags && report.risk_flags.length > 0 ? (
                      report.risk_flags.map((rf, i) => (
                        <div key={i} className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900 flex items-start gap-2">
                          <span className="material-symbols-outlined text-amber-600 text-sm mt-0.5">warning</span>
                          <span className="leading-relaxed">{rf}</span>
                        </div>
                      ))
                    ) : (
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-xs text-emerald-800">
                        No high-priority risk or fraud flags detected for this claim.
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "sources" && (
                  <div className="space-y-3">
                    {(file.knowledge_sources || []).length > 0 ? (
                      (file.knowledge_sources || []).map((s, i) => (
                        <div key={i} className="text-[11px] bg-slate-50 border border-slate-200 rounded-xl p-3">
                          <b className="text-[#00647c]">{s.source_name || "Policy Document"}</b>
                          <p className="mt-1 text-slate-600 leading-relaxed">{s.text?.slice(0, 500)}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500 p-4">
                        Standard insurance adjudication rules applied. Upload policy documents in Knowledge Base to anchor specific clauses.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="py-20 text-center px-4">
              <span className="material-symbols-outlined text-4xl text-slate-300 mb-2 block">
                psychology
              </span>
              <p className="text-sm font-semibold text-slate-800">Copilot Analysis Not Run Yet</p>
              <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                Generate a comprehensive decision-support report with coverage evaluation, settlement calculation, and actionable suggestions.
              </p>
              <button
                onClick={() => onLoadCopilot(file.claim.ticket_id)}
                className="mt-4 bg-[#00647c] hover:bg-[#004e61] text-white px-5 py-2.5 rounded-xl font-semibold text-xs shadow-xs transition cursor-pointer"
              >
                Run Claim Analysis Now
              </button>
            </div>
          )}
        </section>

        {/* Quick Decision Action Panel */}
        <section className="bg-white border border-[#e0e3e5] rounded-2xl p-5 shadow-xs">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-headline font-bold text-sm text-slate-900">Adjudication Decision</h3>
              <p className="text-xs text-slate-500">Apply human decision based on Copilot review</p>
            </div>
            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
              Current: {file.claim.status.replace("_", " ")}
            </span>
          </div>
          <div className="grid sm:grid-cols-3 gap-2.5">
            <button
              disabled={updatingStatus}
              onClick={() => onUpdateStatus("approved")}
              className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">check</span>
              Approve Claim
            </button>
            <button
              disabled={updatingStatus}
              onClick={() => onUpdateStatus("pending_evidence")}
              className="border border-[#00647c] text-[#00647c] hover:bg-[#00647c]/5 disabled:opacity-50 rounded-xl py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">rule</span>
              Request Evidence
            </button>
            <button
              disabled={updatingStatus}
              onClick={() => onUpdateStatus("rejected")}
              className="border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-50 rounded-xl py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">close</span>
              Reject Claim
            </button>
          </div>
        </section>
      </div>

      {/* RIGHT: AI Copilot Chatbot */}
      <section className="bg-white border border-[#e0e3e5] rounded-2xl overflow-hidden shadow-xs flex flex-col h-[750px] sticky top-6">
        {/* Chatbot Header */}
        <div className="px-5 py-4 border-b border-[#e0e3e5] bg-gradient-to-r from-[#f8fafc] to-white flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white">
              <span className="material-symbols-outlined text-lg">forum</span>
            </div>
            <div>
              <h3 className="font-headline font-bold text-sm text-slate-900 leading-tight">
                Discuss with Copilot
              </h3>
              <p className="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Active on #{file.claim.ticket_id}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onSendCopilotMessage("Summarize the main factors influencing the decision recommendation.")}
            className="text-[10px] text-[#00647c] font-semibold hover:underline cursor-pointer"
          >
            Ask Summary
          </button>
        </div>

        {/* Quick Suggestion Chips */}
        <div className="p-2.5 border-b border-slate-100 bg-slate-50/50 flex flex-wrap gap-1.5 shrink-0">
          {quickPrompts.map((prompt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onSendCopilotMessage(prompt)}
              className="text-[11px] bg-white hover:bg-[#e0f2fe] border border-slate-200 text-slate-700 hover:text-[#0369a1] rounded-full px-2.5 py-1 text-left transition cursor-pointer shadow-2xs"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin">
          {copilotChat.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
              <span className="material-symbols-outlined text-3xl text-slate-300 mb-2">chat_bubble</span>
              <p className="text-xs font-semibold text-slate-600">No chat history yet</p>
              <p className="text-[11px] text-slate-400 mt-1 max-w-xs">
                Ask about coverage clauses, evidence gaps, damage consistency, or draft messages for the claimant.
              </p>
            </div>
          ) : (
            copilotChat.map((m, i) => {
              const isCopilot = m.speaker === "copilot";
              return (
                <div
                  key={i}
                  className={`flex flex-col ${isCopilot ? "items-start" : "items-end"}`}
                >
                  <div className="text-[9px] uppercase tracking-wider font-bold text-slate-400 mb-1 px-1 flex items-center gap-1">
                    <span className="material-symbols-outlined text-[11px]">
                      {isCopilot ? "smart_toy" : "person"}
                    </span>
                    <span>{isCopilot ? "Copilot" : "Adjuster"}</span>
                  </div>
                  <div
                    className={`rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                      isCopilot
                        ? "w-full max-w-[95%] bg-[#f8fafc] text-slate-800 rounded-tl-xs border border-slate-200/80 shadow-2xs"
                        : "max-w-[85%] bg-[#00647c] text-white rounded-tr-xs shadow-xs whitespace-pre-wrap"
                    }`}
                  >
                    {isCopilot ? (
                      <div>
                        <MarkdownRenderer content={m.message} />
                        <div className="mt-2.5 pt-2 border-t border-slate-200/70 flex items-center justify-end">
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(m.message);
                              setCopiedIndex(i);
                              setTimeout(() => setCopiedIndex(null), 2000);
                            }}
                            className="text-[10px] text-slate-500 hover:text-[#00647c] flex items-center gap-1 font-semibold transition cursor-pointer"
                            title="Copy Copilot response"
                          >
                            <span className="material-symbols-outlined text-xs">
                              {copiedIndex === i ? "check" : "content_copy"}
                            </span>
                            <span>{copiedIndex === i ? "Copied" : "Copy response"}</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      m.message
                    )}
                  </div>
                </div>
              );
            })
          )}

          {copilotChatLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-400 p-2">
              <div className="w-4 h-4 border-2 border-[#00647c] border-t-transparent rounded-full animate-spin" />
              <span>Copilot is formulating advice…</span>
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSendCopilotMessage();
          }}
          className="p-3 border-t border-[#e0e3e5] bg-white flex gap-2 shrink-0"
        >
          <input
            type="text"
            value={copilotMessage}
            onChange={(e) => setCopilotMessage(e.target.value)}
            placeholder="Ask Copilot about this claim…"
            disabled={copilotChatLoading}
            className="flex-1 border border-slate-300 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!copilotMessage.trim() || copilotChatLoading}
            className="bg-[#00647c] hover:bg-[#004e61] text-white px-4 py-2.5 rounded-xl text-xs font-semibold disabled:opacity-50 transition cursor-pointer flex items-center gap-1 shadow-xs"
          >
            <span className="material-symbols-outlined text-sm">send</span>
            <span>Send</span>
          </button>
        </form>
      </section>
    </div>
  );
};