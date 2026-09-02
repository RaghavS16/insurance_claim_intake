import React from "react";

interface AdminTopBarProps {
  activeTab: "policies" | "adjusters";
  currentUser: any;
}

export const AdminTopBar: React.FC<AdminTopBarProps> = ({ activeTab, currentUser }) => {
  return (
    <header className="hidden md:flex justify-between items-center px-8 py-4 w-full sticky top-0 bg-white/90 backdrop-blur-xl border-b border-[#e0e3e5] z-30">
      <h1 className="font-headline text-xl font-bold text-[#191c1e]">
        {activeTab === "policies" ? "Policy Management" : "Adjuster Administration"}
      </h1>
      <div className="flex items-center gap-3">
        <span className="font-label text-xs text-[#505f76]">{currentUser?.email}</span>
        <div className="w-8 h-8 rounded-full bg-[#d0e1fb] flex items-center justify-center text-[#54647a]">
          <span className="material-symbols-outlined text-base">account_circle</span>
        </div>
      </div>
    </header>
  );
};
