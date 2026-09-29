import React, { useState } from "react";
import { AdjusterUser, AdjusterViewType, Claim, title, money } from "./types";

interface AdjusterSidebarProps {
  view: AdjusterViewType;
  setView: (v: AdjusterViewType) => void;
  user: AdjusterUser | null;
  selected?: string;
  claims: Claim[];
  onOpenClaim: (id: string, nextView?: AdjusterViewType) => void;
}

export const AdjusterSidebar: React.FC<AdjusterSidebarProps> = ({
  view, setView, user, selected, claims, onOpenClaim,
}) => {
  const [hovered, setHovered] = useState<string | null>(null);
  const open = (id: string, next: AdjusterViewType) => {
    onOpenClaim(id, next);
  };
  return (
    <aside className="hidden md:flex w-72 bg-white border-r border-[#e0e3e5] p-3 flex-col shrink-0">
      <div className="px-2 py-3 border-b border-[#e0e3e5]">
        <div className="text-[9px] uppercase tracking-[.12em] text-[#778187] font-bold">Operations</div>
        <div className="mt-2 space-y-1">
          <button
            type="button"
            onClick={() => setView("queue")}
            className={"w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-semibold text-left cursor-pointer " +
              (view === "queue" ? "bg-[#eef7fa] text-[#00647c]" : "text-[#526066] hover:bg-[#f5f8f9]")}
          >
            <span className="material-symbols-outlined text-[16px]">inbox</span>
            <span>Claims Queue</span>
          </button>
          <button
            type="button"
            onClick={() => setView("knowledge")}
            className={"w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-semibold text-left cursor-pointer " +
              (view === "knowledge" ? "bg-[#eef7fa] text-[#00647c]" : "text-[#526066] hover:bg-[#f5f8f9]")}
          >
            <span className="material-symbols-outlined text-[16px]">policy</span>
            <span>Policy &amp; Regulations</span>
          </button>
        </div>
      </div>
      <div className="border-t border-[#e0e3e5] pt-3 px-2 text-xs">
        <b>{user?.full_name || "Adjuster"}</b>
        <div className="text-[10px] text-[#6e797e] mt-0.5">{user?.email || "Claims Operations"}</div>
      </div>
    </aside>
  );
};
