import React from "react";
import Link from "next/link";

interface ClaimantSidebarProps {
  userName: string;
  onLogout: () => void;
}

export const ClaimantSidebar: React.FC<ClaimantSidebarProps> = ({ userName, onLogout }) => {
  return (
    <>
      {/* Mobile TopAppBar */}
      <header className="md:hidden bg-white text-[#00647c] font-body w-full top-0 sticky flex justify-between items-center px-4 py-3 border-b border-[#e0e3e5] z-40">
        <div className="flex items-center gap-2 font-headline text-lg font-bold text-[#191c1e] tracking-tight">
          <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
          <span>InsureClaimAI</span>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/link-policy" className="text-[#505f76] hover:text-[#00647c] p-1.5 rounded-md hover:bg-[#eceef0]">
            <span className="material-symbols-outlined text-xl">settings</span>
          </Link>
          <button onClick={onLogout} className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded-md hover:bg-[#eceef0]">
            <span className="material-symbols-outlined text-xl">logout</span>
          </button>
        </div>
      </header>

      {/* Desktop Side Navigation Shell */}
      <nav className="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 bg-[#f7f9fb] border-r border-[#e0e3e5] py-8 px-4 z-40">
        <div className="mb-8 px-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
            <h1 className="font-headline text-xl font-bold text-[#191c1e] tracking-tight">InsureClaimAI</h1>
          </div>
          <p className="font-label text-xs text-[#505f76] mt-0.5">Kinetic Assurance</p>
        </div>

        <div className="flex-1 space-y-1">
          <Link
            href="/claimant"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#00647c] font-bold bg-[#eceef0] transition-all duration-200 group relative"
          >
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-4 bg-[#00647c] rounded-r-full"></div>
            <span className="material-symbols-outlined fill text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>
              dashboard
            </span>
            <span className="font-label text-xs font-semibold">Active Intake</span>
          </Link>
          <div
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] opacity-50 cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[20px]">history</span>
            <span className="font-label text-xs font-medium">Claims History</span>
          </div>
          <div
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] opacity-50 cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[20px]">description</span>
            <span className="font-label text-xs font-medium">Documents</span>
          </div>
          <Link
            href="/link-policy"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] hover:bg-[#eceef0] transition-all duration-200 group"
          >
            <span className="material-symbols-outlined text-[20px] group-hover:text-[#00647c] transition-colors">
              settings
            </span>
            <span className="font-label text-xs font-medium">Link Policy</span>
          </Link>
        </div>

        {/* User Card in Nav */}
        <div className="mt-auto px-2 pt-6 border-t border-[#e0e3e5] flex items-center justify-between">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-9 h-9 rounded-full bg-[#d0e1fb] text-[#54647a] flex items-center justify-center font-bold text-xs shrink-0">
              {userName.charAt(0) || "U"}
            </div>
            <div className="flex flex-col truncate">
              <span className="font-label text-xs text-[#191c1e] font-semibold truncate">
                {userName || "User"}
              </span>
              <span className="text-[10px] text-[#505f76] capitalize">Claimant</span>
            </div>
          </div>
          <button
            onClick={onLogout}
            title="Sign out"
            className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded-md hover:bg-[#eceef0] transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-lg">logout</span>
          </button>
        </div>
      </nav>
    </>
  );
};
