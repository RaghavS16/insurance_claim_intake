import React from "react";
import { AdjusterUser, AdjusterViewType, Claim } from "./types";

interface AdjusterSidebarProps {
  view: AdjusterViewType;
  setView: (v: AdjusterViewType) => void;
  user: AdjusterUser | null;
  selected?: string;
  claims: Claim[];
  onOpenClaim: (id: string) => void;
}

const NAV_ITEMS: [AdjusterViewType, string, string][] = [
  ["queue", "inbox", "Claims Queue"],
  ["file", "folder_open", "Claim File"],
  ["evidence", "description", "Evidence Review"],
  ["knowledge", "menu_book", "Policy & Regulations"],
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

  return (
    <aside className="hidden md:flex w-60 bg-white border-r border-[#e0e3e5] p-4 flex-col shrink-0">
      <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] px-2 py-3 font-bold">
        Operations Core
      </div>
      {NAV_ITEMS.map(([id, icon, label]) => (
        <button
          key={id}
          onClick={() => handleNavClick(id)}
          className={
            "flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-xs font-semibold mb-1 cursor-pointer transition-colors " +
            (view === id
              ? "bg-[#d0e1fb] text-[#254b59] font-bold shadow-2xs"
              : "text-[#526066] hover:bg-[#f2f4f6]")
          }
        >
          <span className="material-symbols-outlined text-[18px]">{icon}</span>
          <span>{label}</span>
        </button>
      ))}
      <div className="mt-auto border-t border-[#e0e3e5] pt-4 px-2 text-xs">
        <b>{user?.full_name || "Adjuster"}</b>
        <div className="text-[10px] text-[#6e797e] mt-0.5">Claims Operations</div>
      </div>
    </aside>
  );
};
