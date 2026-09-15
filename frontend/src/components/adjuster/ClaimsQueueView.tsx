import React from "react";
import { Claim, title, money } from "./types";

interface ClaimsQueueViewProps {
  claims: Claim[];
  selected?: string;
  onOpenClaim: (ticketId: string) => void;
  onRefresh: () => void;
}

export const ClaimsQueueView: React.FC<ClaimsQueueViewProps> = ({
  claims,
  selected,
  onOpenClaim,
  onRefresh,
}) => {
  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
        <div>
          <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] mb-1 font-bold">
            Operations / Intake
          </div>
          <h1 className="font-headline text-2xl font-bold">Claims Queue</h1>
          <p className="text-xs text-[#657177] mt-0.5">
            Claims that completed conversational intake, verification, and assignment.
          </p>
        </div>
        <button
          onClick={onRefresh}
          className="border border-[#bdc8ce] hover:border-[#00647c] bg-white rounded-lg px-3 py-2 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto"
        >
          <span className="material-symbols-outlined text-[16px]">refresh</span>
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {[
          ["Total claims", claims.length, "inbox"],
          ["Assigned", claims.filter((c) => c.assigned_adjuster_id).length, "person_check"],
          ["Evidence pending", claims.filter((c) => c.status === "pending_evidence").length, "assignment_late"],
          ["Policy verified", claims.filter((c) => c.policy_verified).length, "verified"],
        ].map(([label, count, icon]) => (
          <div key={label as string} className="bg-white border border-[#e0e3e5] rounded-xl p-4 shadow-2xs">
            <div className="flex justify-between text-[10px] uppercase tracking-[.08em] text-[#778187] font-semibold">
              <span>{label}</span>
              <span className="material-symbols-outlined text-[#00647c] text-[18px]">{icon}</span>
            </div>
            <div className="font-headline text-2xl font-bold mt-2">{count}</div>
          </div>
        ))}
      </div>

      <div className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-[#e0e3e5] flex justify-between items-center">
          <div>
            <h2 className="font-headline font-bold">Review Queue</h2>
            <p className="text-[11px] text-[#6e797e] mt-0.5">
              Automatically assigned claims requiring adjuster action.
            </p>
          </div>
          <span className="text-[10px] text-[#6e797e] font-semibold">{claims.length} records</span>
        </div>

        <div className="hidden md:grid grid-cols-5 gap-4 px-5 py-3 bg-[#f7f9fb] text-[9px] uppercase tracking-[.1em] font-semibold text-[#778187] border-b border-[#e0e3e5]">
          <span>Claim</span>
          <span>Type</span>
          <span>Status</span>
          <span>Amount</span>
          <span>Assigned</span>
        </div>

        {claims.length === 0 ? (
          <div className="py-16 text-center">
            <span className="material-symbols-outlined text-[#9aa5aa] text-4xl">inbox</span>
            <h3 className="font-headline font-semibold mt-3">No claims in queue</h3>
            <p className="text-xs text-[#6e797e] mt-1">
              Verified claims will appear here after automatic assignment.
            </p>
          </div>
        ) : (
          claims.map((c) => (
            <button
              key={c.ticket_id}
              onClick={() => onOpenClaim(c.ticket_id)}
              className={
                "w-full text-left grid grid-cols-1 md:grid-cols-5 gap-2 md:gap-4 px-5 py-4 border-t border-[#edf0f1] hover:bg-[#f8fbfc] transition-colors cursor-pointer " +
                (selected === c.ticket_id ? "bg-[#eef7fa] border-l-4 border-l-[#00647c]" : "")
              }
            >
              <div>
                <b className="text-[13px] text-[#00647c]">#{c.ticket_id}</b>
                <div className="text-[10px] text-[#6e797e] mt-0.5">
                  {c.event_date || "Date pending"} · {c.event_location || "Location pending"}
                </div>
              </div>
              <div className="text-xs capitalize">{title(c.insurance_type)}</div>
              <div>
                <span
                  className={
                    "px-2.5 py-1 rounded-full text-[9px] uppercase font-bold " +
                    (c.status === "pending_evidence"
                      ? "bg-[#fff0d8] text-[#895900]"
                      : c.status === "under_review"
                      ? "bg-cyan-100 text-cyan-800"
                      : c.status === "approved"
                      ? "bg-emerald-100 text-emerald-800"
                      : c.status === "rejected"
                      ? "bg-rose-100 text-rose-800"
                      : "bg-[#dfeafc] text-[#345a72]")
                  }
                >
                  {title(c.status)}
                </span>
              </div>
              <div className="text-xs font-semibold">{money(c.estimated_claim_amount)}</div>
              <div className="text-xs text-[#526066]">
                {c.assigned_adjuster_name || (
                  <span className="text-[#00647c] italic">Auto-assigned</span>
                )}
              </div>
            </button>
          ))
        )}
      </div>
    </>
  );
};
