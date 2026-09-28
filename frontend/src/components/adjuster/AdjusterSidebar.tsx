import React from "react";
import { AdjusterUser, AdjusterViewType, Claim, title, money } from "./types";

interface AdjusterSidebarProps {
  view: AdjusterViewType;
  setView: (v: AdjusterViewType) => void;
  user: AdjusterUser | null;
  selected?: string;
  claims: Claim[];
  onOpenClaim: (id: string) => void;
}

const NAV_ITEMS: [AdjusterViewType, string, string][] = [
  ["queue", "inbox", "Claims queue"],
  ["file", "folder_open", "Claim file"],
  ["evidence", "description", "Evidence review"],
  ["knowledge", "menu_book", "Policy library"],
  ["copilot", "auto_awesome", "AI Copilot"],
];

export const AdjusterSidebar: React.FC<AdjusterSidebarProps> = ({
  view,
  setView,
  user,
  selected,
  claims,
  onOpenClaim,
}) => {
  const handleNavClick = (id: AdjusterViewType) => {
    if ((id === "file" || id === "evidence" || id === "copilot") && !selected && claims.length > 0) {
      onOpenClaim(claims[0].ticket_id);
    }
    setView(id);
  };

  const attentionCount = claims.filter((claim) => claim.status === "pending_evidence" || (claim.open_adjuster_requests || 0) > 0).length;

  return (
    <aside className="hidden w-[280px] shrink-0 flex-col border-r border-slate-200/80 bg-[#fbfcfc] md:flex">
      <div className="border-b border-slate-100 px-5 py-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#10373d] text-[#c5e2de]">
            <span className="material-symbols-outlined text-[20px]">shield</span>
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Claims desk</p>
            <p className="mt-0.5 text-sm font-semibold tracking-tight text-slate-900">InsureClaimAI</p>
          </div>
        </div>
      </div>

      <div className="px-3 py-4">
        <div className="mb-2 flex items-center justify-between px-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Workspace</span>
          {attentionCount > 0 && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold text-amber-800">{attentionCount} attention</span>}
        </div>
        {NAV_ITEMS.map(([id, icon, label]) => (
          <button
            key={id}
            onClick={() => handleNavClick(id)}
            className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-xs font-semibold transition ${view === id ? "bg-[#e6f2f0] text-[#0b6b72]" : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"}`}
          >
            <span className="material-symbols-outlined text-[18px]">{icon}</span>
            <span className="flex-1">{label}</span>
            {id === "queue" && claims.length > 0 && <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[9px] text-slate-600">{claims.length}</span>}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 border-t border-slate-100 px-4 py-4">
        <div className="flex items-center justify-between px-1">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Assigned claims</p>
            <p className="mt-1 text-[10px] text-slate-400">Open any claim in the workspace</p>
          </div>
          <span className="text-[10px] font-semibold text-slate-400">{claims.length}</span>
        </div>
        <div className="mt-3 max-h-[48vh] space-y-1.5 overflow-y-auto pr-1">
          {claims.length ? claims.map((claim) => (
            <button
              key={claim.ticket_id}
              onClick={() => onOpenClaim(claim.ticket_id)}
              className={`w-full rounded-xl border px-3 py-3 text-left transition ${selected === claim.ticket_id ? "border-[#b9d8d4] bg-white shadow-sm" : "border-transparent hover:border-slate-200 hover:bg-white"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] font-semibold text-slate-700">#{claim.ticket_id.replace("CLAIM-", "")}</span>
                <span className={`rounded-full px-2 py-0.5 text-[8px] font-bold uppercase ${claim.status === "pending_evidence" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-500"}`}>{title(claim.status)}</span>
              </div>
              <p className="mt-1.5 truncate text-[11px] font-semibold text-slate-800">{title(claim.insurance_type)}</p>
              <div className="mt-1 flex items-center justify-between gap-2 text-[9px] text-slate-400">
                <span>{claim.event_location || "Location pending"}</span>
                <span>{money(claim.estimated_claim_amount)}</span>
              </div>
            </button>
          )) : (
            <div className="rounded-xl border border-dashed border-slate-200 p-4 text-[10px] leading-4 text-slate-400">No assigned claims are waiting for action.</div>
          )}
        </div>
      </div>

      <div className="border-t border-slate-100 px-5 py-4">
        <p className="text-xs font-semibold text-slate-800">{user?.full_name || "Adjuster"}</p>
        <p className="mt-0.5 text-[10px] text-slate-400">{user?.specialization ? title(user.specialization) : "Claims operations"}</p>
      </div>
    </aside>
  );
};