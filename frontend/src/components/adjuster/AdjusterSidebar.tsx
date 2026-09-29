import React, { useState } from "react";
import { AdjusterUser, AdjusterViewType, Claim, title, money } from "./types";

interface AdjusterSidebarProps {
  view: AdjusterViewType;
  setView: (v: AdjusterViewType) => void;
  user: AdjusterUser | null;
  selected?: string;
  claims: Claim[];
  onOpenClaim: (id: string) => void;
}

export const AdjusterSidebar: React.FC<AdjusterSidebarProps> = ({
  view, setView, user, selected, claims, onOpenClaim,
}) => {
  const [hovered, setHovered] = useState<string | null>(null);
  const open = (id: string, next: AdjusterViewType) => {
    onOpenClaim(id);
    setView(next);
  };
  return (
    <aside className="hidden md:flex w-72 bg-white border-r border-[#e0e3e5] p-3 flex-col shrink-0">
      <div className="px-2 py-3 border-b border-[#e0e3e5]">
        <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] font-bold">Assigned Claims</div>
        <div className="text-xs text-[#526066] mt-1">{claims.length} claim{claims.length === 1 ? "" : "s"} assigned to you</div>
      </div>
      <div className="flex-1 overflow-y-auto py-2 space-y-1.5">
        {claims.length === 0 ? (
          <div className="px-3 py-10 text-center text-xs text-[#778187]">No assigned claims.</div>
        ) : claims.map((claim) => {
          const active = selected === claim.ticket_id;
          const showActions = hovered === claim.ticket_id || active;
          return (
            <div key={claim.ticket_id}
              onMouseEnter={() => setHovered(claim.ticket_id)}
              onMouseLeave={() => setHovered(null)}
              className={"rounded-xl border p-3 transition-colors " + (active ? "border-[#00647c]/30 bg-[#f3f9fb]" : "border-transparent hover:border-[#dce5e9] hover:bg-[#f8fafb]")}>
              <button onClick={() => open(claim.ticket_id, "file")} className="w-full text-left cursor-pointer">
                <div className="flex items-center justify-between gap-2">
                  <b className="text-[12px] text-[#00647c] truncate">#{claim.ticket_id}</b>
                  <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">{title(claim.status)}</span>
                </div>
                <div className="text-[11px] text-[#334155] mt-1 truncate">{title(claim.insurance_type)}</div>
                <div className="text-[10px] text-[#778187] mt-0.5 truncate">{claim.event_date || "Date pending"} · {money(claim.estimated_claim_amount)}</div>
              </button>
              {showActions && (
                <div className="flex gap-1.5 mt-2 pt-2 border-t border-[#e5eaed]">
                  <button onClick={() => open(claim.ticket_id, "file")} className="flex-1 text-[10px] font-semibold px-2 py-1.5 rounded-lg bg-white border border-[#cfd9de] hover:border-[#00647c] cursor-pointer">Claim Details</button>
                  <button onClick={() => open(claim.ticket_id, "evidence")} className="flex-1 text-[10px] font-semibold px-2 py-1.5 rounded-lg bg-white border border-[#cfd9de] hover:border-[#00647c] cursor-pointer">Evidence</button>
                  <button onClick={() => open(claim.ticket_id, "copilot")} className="flex-1 text-[10px] font-semibold px-2 py-1.5 rounded-lg bg-[#00647c] text-white hover:bg-[#004e61] cursor-pointer">AI Copilot</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="border-t border-[#e0e3e5] pt-3 px-2 text-xs">
        <b>{user?.full_name || "Adjuster"}</b>
        <div className="text-[10px] text-[#6e797e] mt-0.5">{user?.email || "Claims Operations"}</div>
      </div>
    </aside>
  );
};
