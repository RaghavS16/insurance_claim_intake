import React, { useState, useMemo } from "react";
import { Claim, title, money } from "./types";

interface ClaimsQueueViewProps {
  claims: Claim[];
  selected?: string;
  onOpenClaim: (ticketId: string, nextView?: "file" | "evidence" | "copilot") => void;
  onRefresh: () => void;
}

type QueueFilter = "all" | "active" | "approved" | "pending_evidence" | "rejected";

export const ClaimsQueueView: React.FC<ClaimsQueueViewProps> = ({
  claims,
  selected,
  onOpenClaim,
  onRefresh,
}) => {
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [search, setSearch] = useState("");

  const activeClaims = useMemo(
    () =>
      claims.filter((c) =>
        ["submitted", "pending_adjuster", "assigned", "under_review", "pending_evidence"].includes(
          c.status
        )
      ),
    [claims]
  );

  const approvedClaims = useMemo(
    () => claims.filter((c) => ["approved", "partially_approved"].includes(c.status)),
    [claims]
  );

  const pendingEvidenceClaims = useMemo(
    () => claims.filter((c) => c.status === "pending_evidence"),
    [claims]
  );

  const rejectedClaims = useMemo(
    () => claims.filter((c) => c.status === "rejected"),
    [claims]
  );

  const filteredClaims = useMemo(() => {
    let list = claims;
    if (filter === "active") {
      list = activeClaims;
    } else if (filter === "approved") {
      list = approvedClaims;
    } else if (filter === "pending_evidence") {
      list = pendingEvidenceClaims;
    } else if (filter === "rejected") {
      list = rejectedClaims;
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((c) => {
        return (
          c.ticket_id?.toLowerCase().includes(q) ||
          c.insurance_type?.toLowerCase().includes(q) ||
          c.status?.toLowerCase().includes(q) ||
          c.event_location?.toLowerCase().includes(q) ||
          c.assigned_adjuster_name?.toLowerCase().includes(q)
        );
      });
    }

    return list;
  }, [claims, filter, search, activeClaims, approvedClaims, pendingEvidenceClaims, rejectedClaims]);

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
        <div>
          <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] mb-1 font-bold">
            Operations / Intake
          </div>
          <h1 className="font-headline text-2xl font-bold">Claims Queue</h1>
          <p className="text-xs text-[#657177] mt-0.5">
            Claims that completed conversational intake, verification, and assignment — retained permanently for ongoing audit and future review.
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

      {/* Interactive Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {[
          {
            label: "Total claims",
            count: claims.length,
            icon: "inbox",
            targetFilter: "all" as QueueFilter,
            badgeColor: "text-[#00647c]",
          },
          {
            label: "Action required",
            count: activeClaims.length,
            icon: "pending_actions",
            targetFilter: "active" as QueueFilter,
            badgeColor: "text-amber-600",
          },
          {
            label: "Approved & Retained",
            count: approvedClaims.length,
            icon: "verified",
            targetFilter: "approved" as QueueFilter,
            badgeColor: "text-emerald-600",
          },
          {
            label: "Evidence pending",
            count: pendingEvidenceClaims.length,
            icon: "assignment_late",
            targetFilter: "pending_evidence" as QueueFilter,
            badgeColor: "text-orange-600",
          },
        ].map((item) => {
          const isSelected = filter === item.targetFilter;
          return (
            <div
              key={item.label}
              onClick={() => setFilter(item.targetFilter)}
              className={
                "bg-white border rounded-xl p-4 shadow-2xs cursor-pointer transition-all hover:border-[#00647c] " +
                (isSelected ? "border-[#00647c] ring-1 ring-[#00647c]/30 bg-sky-50/20" : "border-[#e0e3e5]")
              }
            >
              <div className="flex justify-between text-[10px] uppercase tracking-[.08em] text-[#778187] font-semibold">
                <span>{item.label}</span>
                <span className={`material-symbols-outlined text-[18px] ${item.badgeColor}`}>
                  {item.icon}
                </span>
              </div>
              <div className="font-headline text-2xl font-bold mt-2">{item.count}</div>
              <div className="text-[10px] text-[#6e797e] mt-1 flex items-center gap-1">
                <span>{isSelected ? "Active filter" : "Click to filter"}</span>
                {isSelected && <span className="material-symbols-outlined text-xs text-[#00647c]">check</span>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-white border border-[#e0e3e5] rounded-xl overflow-hidden shadow-sm">
        {/* Controls Bar: Filter Tabs & Search */}
        <div className="px-5 py-4 border-b border-[#e0e3e5] flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 flex-wrap">
            {[
              { id: "all" as QueueFilter, label: "All Claims", count: claims.length },
              { id: "active" as QueueFilter, label: "Needs Action", count: activeClaims.length },
              { id: "approved" as QueueFilter, label: "Approved", count: approvedClaims.length },
              { id: "pending_evidence" as QueueFilter, label: "Evidence Pending", count: pendingEvidenceClaims.length },
              { id: "rejected" as QueueFilter, label: "Rejected", count: rejectedClaims.length },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={
                  "px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer " +
                  (filter === tab.id
                    ? "bg-[#00647c] text-white"
                    : "bg-[#f1f5f7] text-[#526066] hover:bg-[#e4ebef]")
                }
              >
                <span>{tab.label}</span>
                <span
                  className={
                    "text-[10px] px-1.5 py-0.2 rounded-full font-bold " +
                    (filter === tab.id ? "bg-white/20 text-white" : "bg-[#dde4e8] text-[#526066]")
                  }
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          <div className="relative w-full md:w-64">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">
              search
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search ID, type, location..."
              className="w-full bg-[#f8fafc] border border-[#d8e0e4] rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c]"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <span className="material-symbols-outlined text-xs">close</span>
              </button>
            )}
          </div>
        </div>

        <div className="hidden md:grid grid-cols-5 gap-4 px-5 py-3 bg-[#f7f9fb] text-[9px] uppercase tracking-[.1em] font-semibold text-[#778187] border-b border-[#e0e3e5]">
          <span>Claim</span>
          <span>Type</span>
          <span>Status</span>
          <span>Amount</span>
          <span>Assigned</span>
        </div>

        {filteredClaims.length === 0 ? (
          <div className="py-16 text-center">
            <span className="material-symbols-outlined text-[#9aa5aa] text-4xl">
              {search ? "search_off" : filter === "approved" ? "verified" : "inbox"}
            </span>
            <h3 className="font-headline font-semibold mt-3 text-slate-800">
              {search
                ? "No matching claims found"
                : filter === "approved"
                ? "No approved claims yet"
                : "No claims in this view"}
            </h3>
            <p className="text-xs text-[#6e797e] mt-1 max-w-sm mx-auto">
              {search
                ? `No claim tickets match "${search}". Try clearing search or selecting "All Claims".`
                : filter === "approved"
                ? "Approved claims will remain safely archived here for future reference and adjuster audit."
                : "Claims will appear here once submitted or assigned."}
            </p>
            {(search || filter !== "all") && (
              <button
                type="button"
                onClick={() => {
                  setFilter("all");
                  setSearch("");
                }}
                className="mt-3 text-xs text-[#00647c] font-semibold hover:underline cursor-pointer"
              >
                View all claims
              </button>
            )}
          </div>
        ) : (
          filteredClaims.map((c) => (
            <div
              key={c.ticket_id}
              onClick={() => onOpenClaim(c.ticket_id, "file")}
              className={
                "group relative w-full text-left grid grid-cols-1 md:grid-cols-5 gap-2 md:gap-4 px-5 py-4 pr-5 md:pr-48 border-t border-[#edf0f1] hover:bg-[#f8fbfc] transition-colors cursor-pointer " +
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
                    "px-2.5 py-1 rounded-full text-[9px] uppercase font-bold inline-flex items-center gap-1 " +
                    (c.status === "pending_evidence"
                      ? "bg-[#fff0d8] text-[#895900] border border-amber-200"
                      : c.status === "under_review"
                      ? "bg-cyan-100 text-cyan-800 border border-cyan-200"
                      : c.status === "approved" || c.status === "partially_approved"
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                      : c.status === "rejected"
                      ? "bg-rose-100 text-rose-800 border border-rose-200"
                      : "bg-[#dfeafc] text-[#345a72] border border-blue-200")
                  }
                >
                  {(c.status === "approved" || c.status === "partially_approved") && (
                    <span className="material-symbols-outlined text-xs">check_circle</span>
                  )}
                  {c.status === "rejected" && (
                    <span className="material-symbols-outlined text-xs">cancel</span>
                  )}
                  {title(c.status)}
                </span>
              </div>
              <div className="text-xs font-semibold">{money(c.estimated_claim_amount)}</div>
              <div className="text-xs text-[#526066]">
                {c.assigned_adjuster_name || (
                  <span className="text-[#00647c] italic">Auto-assigned</span>
                )}
              </div>
              <div
                onClick={(e) => e.stopPropagation()}
                className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-1.5 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
              >
                <button
                  type="button"
                  onClick={() => onOpenClaim(c.ticket_id, "evidence")}
                  className="px-2.5 py-1.5 rounded-lg bg-white border border-[#cfd9de] text-[10px] font-semibold text-[#334155] hover:border-[#00647c] shadow-sm cursor-pointer"
                >
                  Evidence
                </button>
                <button
                  type="button"
                  onClick={() => onOpenClaim(c.ticket_id, "file")}
                  className="px-2.5 py-1.5 rounded-lg bg-white border border-[#cfd9de] text-[10px] font-semibold text-[#334155] hover:border-[#00647c] shadow-sm cursor-pointer"
                >
                  Claim Details
                </button>
                <button
                  type="button"
                  onClick={() => onOpenClaim(c.ticket_id, "copilot")}
                  className="px-2.5 py-1.5 rounded-lg bg-[#00647c] text-white text-[10px] font-semibold hover:bg-[#004e61] shadow-sm cursor-pointer"
                >
                  AI Copilot
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
};
