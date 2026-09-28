import React from "react";
import { AdjusterUser } from "./types";

interface AdjusterTopBarProps {
  user: AdjusterUser | null;
  onSignOut: () => void;
}

export const AdjusterTopBar: React.FC<AdjusterTopBarProps> = ({ user, onSignOut }) => (
  <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-slate-200/80 bg-white/95 px-5 backdrop-blur md:px-7">
    <div className="flex items-center gap-3 md:ml-[300px]">
      <div className="hidden md:block">
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400">Claims operations</p>
        <p className="mt-0.5 text-sm font-semibold tracking-tight text-slate-900">Adjuster workspace</p>
      </div>
      <div className="md:hidden">
        <p className="text-sm font-semibold tracking-tight text-slate-900">InsureClaimAI</p>
      </div>
    </div>
    <div className="flex items-center gap-3">
      <div className="hidden rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 sm:block">
        <span className="text-[10px] font-semibold text-slate-500">{user?.full_name || user?.email || "Adjuster"}</span>
      </div>
      <button onClick={onSignOut} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-[#0b6b72] hover:text-[#0b6b72]">
        Sign out
      </button>
    </div>
  </header>
);