import React, { useState } from "react";
import Link from "next/link";

export interface AdminSidebarProps {
  activeTab: "policies" | "adjusters";
  setActiveTab: (tab: "policies" | "adjusters") => void;
  currentUser: any;
  onLogout: () => void;
  policiesCount?: number;
  adjustersCount?: number;
  onAddPolicy?: () => void;
}

export const AdminSidebar: React.FC<AdminSidebarProps> = ({
  activeTab,
  setActiveTab,
  currentUser,
  onLogout,
  policiesCount,
  adjustersCount,
  onAddPolicy,
}) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#f8fafc] border-r border-[#e2e8f0] select-none text-slate-800">
      {/* Brand Header */}
      <div className="p-4 pb-3 border-b border-[#e2e8f0]/80">
        <div className="flex items-center justify-between">
          <Link
            href="/admin"
            className="flex items-center gap-2.5 group outline-none focus:outline-none focus-visible:outline-none"
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-[#00647c] to-[#0891B2] flex items-center justify-center text-white shadow-xs transition-transform group-hover:scale-105">
              <span className="material-symbols-outlined text-[20px]">admin_panel_settings</span>
            </div>
            <div>
              <h1 className="font-headline text-base font-bold text-[#0f172a] tracking-tight leading-tight">
                InsureClaimAI
              </h1>
              <p className="font-label text-[10px] text-[#64748b] uppercase tracking-wider font-semibold">
                Admin Console
              </p>
            </div>
          </Link>
          {mobileOpen && (
            <button
              onClick={() => setMobileOpen(false)}
              className="md:hidden text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-200/50 outline-none focus:outline-none focus-visible:outline-none"
            >
              <span className="material-symbols-outlined text-xl">close</span>
            </button>
          )}
        </div>

        {/* Quick Action Button */}
        {onAddPolicy && (
          <button
            onClick={() => {
              onAddPolicy();
              if (mobileOpen) setMobileOpen(false);
            }}
            className="mt-3.5 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-[#00647c] hover:bg-[#004e61] text-white font-label text-xs font-semibold shadow-xs hover:shadow transition-all duration-200 cursor-pointer active:scale-[0.99] group outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
          >
            <span className="material-symbols-outlined text-base transition-transform group-hover:rotate-90 duration-200">
              add
            </span>
            <span>Add New Policy</span>
          </button>
        )}
      </div>

      {/* Primary Navigation Links */}
      <div className="px-3 pt-3 pb-2 border-b border-[#e2e8f0]/80 space-y-1">
        <button
          type="button"
          onClick={() => {
            setActiveTab("policies");
            if (mobileOpen) setMobileOpen(false);
          }}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-150 cursor-pointer outline-none focus:outline-none focus-visible:outline-none focus:ring-0 ${
            activeTab === "policies"
              ? "bg-white text-[#00647c] font-bold border border-[#00647c]/20 shadow-2xs"
              : "text-slate-600 hover:text-[#00647c] hover:bg-slate-200/50 border border-transparent"
          }`}
        >
          <span
            className={`material-symbols-outlined text-[18px] ${
              activeTab === "policies" ? "text-[#00647c]" : "text-slate-400"
            }`}
          >
            policy
          </span>
          <span className="flex-1 text-left">Policy Management</span>
          {policiesCount !== undefined && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                activeTab === "policies"
                  ? "bg-[#00647c]/10 text-[#00647c]"
                  : "bg-slate-200/80 text-slate-600"
              }`}
            >
              {policiesCount}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab("adjusters");
            if (mobileOpen) setMobileOpen(false);
          }}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-150 cursor-pointer outline-none focus:outline-none focus-visible:outline-none focus:ring-0 ${
            activeTab === "adjusters"
              ? "bg-white text-[#00647c] font-bold border border-[#00647c]/20 shadow-2xs"
              : "text-slate-600 hover:text-[#00647c] hover:bg-slate-200/50 border border-transparent"
          }`}
        >
          <span
            className={`material-symbols-outlined text-[18px] ${
              activeTab === "adjusters" ? "text-[#00647c]" : "text-slate-400"
            }`}
          >
            badge
          </span>
          <span className="flex-1 text-left">Adjuster Accounts</span>
          {adjustersCount !== undefined && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                activeTab === "adjusters"
                  ? "bg-[#00647c]/10 text-[#00647c]"
                  : "bg-slate-200/80 text-slate-600"
              }`}
            >
              {adjustersCount}
            </span>
          )}
        </button>
      </div>

      {/* Spacer to push User Profile Card to the bottom */}
      <div className="flex-1" />

      {/* User Profile Card Footer */}
      <div className="p-3 border-t border-[#e2e8f0] bg-white flex items-center justify-between shadow-2xs">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#00647c] to-[#0284c7] text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-2xs">
            {currentUser?.name
              ? currentUser.name.charAt(0).toUpperCase()
              : currentUser?.email
              ? currentUser.email.charAt(0).toUpperCase()
              : "A"}
          </div>
          <div className="flex flex-col truncate">
            <span className="text-xs text-slate-800 font-semibold truncate leading-tight">
              {currentUser?.name || currentUser?.email || "System Admin"}
            </span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              <span className="text-[10px] text-slate-400 font-medium">System Administrator</span>
            </div>
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Sign out"
          className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors cursor-pointer outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
        >
          <span className="material-symbols-outlined text-lg">logout</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Top AppBar */}
      <header className="md:hidden bg-white text-[#00647c] w-full top-0 sticky flex justify-between items-center px-4 py-3 border-b border-[#e2e8f0] z-40">
        <div className="flex items-center gap-2 font-headline text-base font-bold text-[#0f172a]">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-1 -ml-1 text-slate-600 hover:text-[#00647c] outline-none focus:outline-none focus-visible:outline-none"
          >
            <span className="material-symbols-outlined text-2xl">menu</span>
          </button>
          <span className="material-symbols-outlined text-[#00647c] text-xl">admin_panel_settings</span>
          <span>InsureClaimAI</span>
        </div>
        <div className="flex items-center gap-1.5">
          {onAddPolicy && (
            <button
              onClick={onAddPolicy}
              className="flex items-center gap-1 bg-[#00647c] text-white px-2.5 py-1 rounded-lg text-xs font-semibold outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
            >
              <span className="material-symbols-outlined text-sm">add</span>
              <span>Add</span>
            </button>
          )}
          <button
            onClick={onLogout}
            title="Sign out"
            className="text-slate-500 hover:text-red-600 p-1.5 rounded-md hover:bg-slate-100 outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
          >
            <span className="material-symbols-outlined text-lg">logout</span>
          </button>
        </div>
      </header>

      {/* Mobile Drawer Backdrop */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          className="md:hidden fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 transition-opacity"
        />
      )}

      {/* Mobile Drawer Container */}
      <div
        className={`md:hidden fixed inset-y-0 left-0 w-72 max-w-[85vw] bg-white z-50 transform transition-transform duration-300 ease-in-out ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebarContent}
      </div>

      {/* Desktop Fixed Side Navigation */}
      <nav className="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 z-40 shadow-2xs">
        {sidebarContent}
      </nav>
    </>
  );
};
