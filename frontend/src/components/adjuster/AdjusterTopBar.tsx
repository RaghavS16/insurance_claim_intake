import React from "react";
import { AdjusterUser } from "./types";

interface AdjusterTopBarProps {
  user: AdjusterUser | null;
  onSignOut: () => void;
}

export const AdjusterTopBar: React.FC<AdjusterTopBarProps> = ({ user, onSignOut }) => {
  return (
    <header className="h-16 bg-white border-b border-[#e0e3e5] px-6 flex items-center justify-between sticky top-0 z-20 shadow-xs">
      <div className="flex items-center gap-3">
        <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
        <div>
          <b className="font-headline text-[17px]">InsureClaimAI</b>
          <div className="text-[9px] uppercase tracking-[.12em] text-[#778187]">Adjuster Portal</div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <span className="hidden sm:block text-[11px] text-[#505f76]">{user?.email}</span>
        <button
          onClick={onSignOut}
          className="border border-[#bdc8ce] hover:border-[#00647c] rounded-lg px-3 py-1.5 text-xs font-semibold bg-white flex items-center gap-1.5 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-[16px]">logout</span>
          <span>Sign Out</span>
        </button>
      </div>
    </header>
  );
};
