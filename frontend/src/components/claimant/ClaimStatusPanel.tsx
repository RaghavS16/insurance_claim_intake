import React from "react";

export interface ClaimStatusRequest {
  id?: string;
  message?: string;
  requested_evidence?: string[];
  requested_at?: string;
  status?: string;
}

interface StatusHistoryItem {
  status?: string;
  old_status?: string;
  message?: string;
  created_at?: string;
  event_type?: string;
}

interface ClaimStatusPanelProps {
  status?: string;
  submitted?: boolean;
  adjusterRequests?: ClaimStatusRequest[];
  statusHistory?: StatusHistoryItem[];
}

const label = (value?: string) =>
  (value || "Unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

const dateLabel = (value?: string) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
};

export const ClaimStatusPanel: React.FC<ClaimStatusPanelProps> = ({
  status,
  submitted,
  adjusterRequests = [],
  statusHistory = [],
}) => {
  const openRequests = adjusterRequests.filter((item) => item.status !== "resolved");
  const steps = ["submitted", "assigned", "under_review", "pending_evidence", "approved"];
  const current = status === "rejected" ? "rejected" : status;
  const currentIndex = steps.indexOf(current || "");
  const displayHistory = statusHistory.filter((item) => item.status || item.event_type).slice(-5);

  if (!submitted && !statusHistory.length && !adjusterRequests.length) return null;

  return (
    <section className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_rgba(15,23,42,0.06)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Claim journey</p>
          <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">Where things stand</h3>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600">
          {label(status)}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-5">
        {steps.map((step, index) => {
          const done = currentIndex >= index && currentIndex >= 0;
          const active = current === step;
          return (
            <div key={step} className="relative">
              <div className={`h-1 rounded-full ${done ? "bg-[#0b6b72]" : "bg-slate-100"}`} />
              <div className={`mt-2 text-[10px] font-semibold ${active ? "text-[#0b6b72]" : "text-slate-400"}`}>
                {label(step)}
              </div>
            </div>
          );
        })}
      </div>

      {openRequests.length > 0 && (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-amber-700">priority_high</span>
            <div>
              <p className="text-xs font-bold text-amber-950">Your adjuster needs something from you</p>
              <p className="text-[11px] text-amber-800">This request is part of your claim review.</p>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            {openRequests.slice(-3).map((item, index) => (
              <div key={item.id || index} className="rounded-xl bg-white/80 p-3">
                <p className="text-xs leading-relaxed text-slate-800">{item.message}</p>
                {item.requested_evidence?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.requested_evidence.map((evidence) => (
                      <span key={evidence} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-900">
                        {evidence}
                      </span>
                    ))}
                  </div>
                ) : null}
                {item.requested_at && <p className="mt-2 text-[10px] text-slate-400">{dateLabel(item.requested_at)}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {displayHistory.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Recent updates</p>
          <div className="mt-3 space-y-3">
            {displayHistory.map((item, index) => (
              <div key={`${item.created_at || "event"}-${index}`} className="flex gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#0b6b72]" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-800">
                    {item.event_type === "evidence_requested" ? "Additional information requested" : label(item.status)}
                  </p>
                  {item.message && <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{item.message}</p>}
                  {item.created_at && <p className="mt-1 text-[10px] text-slate-400">{dateLabel(item.created_at)}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};