import React, { useState } from "react";
import Link from "next/link";

export interface ClaimSummary {
  id?: string;
  ticket_id: string;
  status: string;
  conversation_status?: string;
  insurance_type?: string | null;
  event_description?: string | null;
  event_location?: string | null;
  event_date?: string | null;
  estimated_claim_amount?: number | null;
  last_message?: string | null;
  last_message_speaker?: string | null;
  turn_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

interface ClaimantSidebarProps {
  userName: string;
  claims: ClaimSummary[];
  activeTicketId: string;
  loadingClaims?: boolean;
  onSelectClaim: (ticketId: string) => void;
  onNewClaim: () => void;
  onDeleteClaim: (ticketId: string, e: React.MouseEvent) => void;
  onLogout: () => void;
}

const getStatusBadge = (status: string) => {
  switch (status?.toLowerCase()) {
    case "submitted":
      return {
        bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
        label: "Submitted",
        icon: "verified",
      };
    case "verified":
      return {
        bg: "bg-blue-50 text-blue-700 border-blue-200",
        label: "Verified",
        icon: "check_circle",
      };
    case "pending_confirmation":
      return {
        bg: "bg-purple-50 text-purple-700 border-purple-200",
        label: "Review",
        icon: "rate_review",
      };
    case "draft":
    default:
      return {
        bg: "bg-amber-50 text-amber-700 border-amber-200",
        label: "Draft",
        icon: "edit_note",
      };
  }
};

const getInsuranceIcon = (type?: string | null) => {
  switch (type?.toLowerCase()) {
    case "motor":
    case "auto":
      return "directions_car";
    case "health":
      return "medical_services";
    case "home":
    case "property":
      return "home";
    case "travel":
      return "flight";
    default:
      return "chat_bubble";
  }
};

const formatTimeAgo = (isoString?: string | null) => {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diffSec < 60) return "Just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
};

export const ClaimantSidebar: React.FC<ClaimantSidebarProps> = ({
  userName,
  claims,
  activeTicketId,
  loadingClaims = false,
  onSelectClaim,
  onNewClaim,
  onDeleteClaim,
  onLogout,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  const startedClaims = claims.filter((c) => {
    // Only include conversations that have at least one turn or are submitted/verified or have details
    const hasInteraction = (c.turn_count && c.turn_count > 0) || c.status === "submitted" || c.status === "verified" || Boolean(c.event_description);
    return Boolean(hasInteraction);
  });

  const filteredClaims = startedClaims.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.ticket_id.toLowerCase().includes(q) ||
      (c.insurance_type && c.insurance_type.toLowerCase().includes(q)) ||
      (c.event_description && c.event_description.toLowerCase().includes(q)) ||
      (c.last_message && c.last_message.toLowerCase().includes(q)) ||
      (c.status && c.status.toLowerCase().includes(q))
    );
  });

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#f8fafc] border-r border-[#e2e8f0] select-none">
      {/* Brand Header */}
      <div className="p-4 pb-3 border-b border-[#e2e8f0]/80">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-[#00647c] to-[#0891B2] flex items-center justify-center text-white shadow-sm">
              <span className="material-symbols-outlined text-[20px]">shield_with_heart</span>
            </div>
            <div>
              <h1 className="font-headline text-base font-bold text-[#0f172a] tracking-tight leading-tight">
                InsureClaimAI
              </h1>
              <p className="font-label text-[10px] text-[#64748b] uppercase tracking-wider font-semibold">
                Autonomous Intake
              </p>
            </div>
          </div>
          {mobileOpen && (
            <button
              onClick={() => setMobileOpen(false)}
              className="md:hidden text-slate-400 hover:text-slate-600 p-1"
            >
              <span className="material-symbols-outlined text-xl">close</span>
            </button>
          )}
        </div>

        {/* Start New Claim Button */}
        <button
          onClick={() => {
            onNewClaim();
            if (mobileOpen) setMobileOpen(false);
          }}
          className="mt-3.5 w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-[#00647c] hover:bg-[#004e61] text-white font-label text-xs font-semibold shadow-sm hover:shadow transition-all duration-200 cursor-pointer active:scale-[0.99] group"
        >
          <span className="material-symbols-outlined text-base transition-transform group-hover:rotate-90 duration-200">
            add
          </span>
          <span>New Claim Intake</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="px-3 pt-3 pb-1">
        <div className="relative">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm pointer-events-none">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search chat history..."
            className="w-full pl-8 pr-7 py-1.5 bg-white border border-[#e2e8f0] rounded-lg text-xs text-[#1e293b] placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <span className="material-symbols-outlined text-xs">close</span>
            </button>
          )}
        </div>
      </div>

      {/* Chat History Section */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1 scrollbar-thin">
        <div className="flex items-center justify-between px-2 py-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
          <span>Conversations</span>
          <span className="text-[10px] bg-slate-200/70 text-slate-600 px-1.5 py-0.2 rounded-full">
            {filteredClaims.length}
          </span>
        </div>

        {loadingClaims && claims.length === 0 ? (
          <div className="p-4 text-center space-y-2">
            <div className="w-5 h-5 border-2 border-[#00647c] border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-slate-400">Loading history...</p>
          </div>
        ) : filteredClaims.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-slate-400">
            <span className="material-symbols-outlined text-2xl text-slate-300 block mb-1">
              forum
            </span>
            {searchQuery ? "No matching conversations" : "No claim conversations yet"}
          </div>
        ) : (
          filteredClaims.map((claim) => {
            const isActive = claim.ticket_id === activeTicketId;
            const badge = getStatusBadge(claim.status);
            const icon = getInsuranceIcon(claim.insurance_type);
            const timeAgo = formatTimeAgo(claim.updated_at || claim.created_at);
            const isDraft = claim.status === "draft" || claim.status === "pending_confirmation";

            return (
              <div
                key={claim.ticket_id}
                onClick={() => {
                  onSelectClaim(claim.ticket_id);
                  if (mobileOpen) setMobileOpen(false);
                }}
                className={`group relative flex flex-col gap-1 p-2.5 rounded-xl cursor-pointer transition-all duration-150 border ${
                  isActive
                    ? "bg-white border-[#00647c]/30 shadow-sm ring-1 ring-[#00647c]/15"
                    : "bg-transparent border-transparent hover:bg-white/80 hover:border-slate-200/80"
                }`}
              >
                {/* Top Row: Icon + Title + Status */}
                <div className="flex items-center justify-between gap-1.5">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={`material-symbols-outlined text-sm shrink-0 ${
                        isActive ? "text-[#00647c]" : "text-slate-400 group-hover:text-slate-600"
                      }`}
                    >
                      {icon}
                    </span>
                    <span
                      className={`text-xs font-semibold truncate ${
                        isActive ? "text-[#00647c]" : "text-slate-800"
                      }`}
                    >
                      {claim.insurance_type
                        ? `${claim.insurance_type.toUpperCase()} Claim`
                        : claim.ticket_id}
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium border shrink-0 ${badge.bg}`}
                  >
                    {badge.label}
                  </span>
                </div>

                {/* Second Row: Snippet of Last Message */}
                <p className="text-[11px] text-slate-500 line-clamp-1 pl-5">
                  {claim.last_message || claim.event_description || "Intake conversation..."}
                </p>

                {/* Third Row: Time + Turns + Actions */}
                <div className="flex items-center justify-between text-[10px] text-slate-400 pl-5 pt-0.5">
                  <div className="flex items-center gap-2">
                    <span>{timeAgo}</span>
                    {claim.turn_count ? (
                      <span>• {claim.turn_count} msg{claim.turn_count > 1 ? "s" : ""}</span>
                    ) : null}
                  </div>

                  {/* Delete Draft Button */}
                  {isDraft && (
                    <button
                      onClick={(e) => onDeleteClaim(claim.ticket_id, e)}
                      title="Discard draft"
                      className="opacity-0 group-hover:opacity-100 hover:text-red-600 p-0.5 rounded transition-opacity"
                    >
                      <span className="material-symbols-outlined text-[14px]">delete</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Navigation Links */}
      <div className="px-3 py-2 border-t border-[#e2e8f0]/80 space-y-1">
        <Link
          href="/link-policy"
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-slate-600 hover:text-[#00647c] hover:bg-slate-100 transition-colors text-xs font-medium"
        >
          <span className="material-symbols-outlined text-base">link</span>
          <span>Link Policy</span>
        </Link>
      </div>

      {/* User Profile Card Footer */}
      <div className="p-3 border-t border-[#e2e8f0] bg-white flex items-center justify-between">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#00647c] to-[#0284c7] text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-xs">
            {userName.charAt(0) || "U"}
          </div>
          <div className="flex flex-col truncate">
            <span className="text-xs text-slate-800 font-semibold truncate leading-tight">
              {userName || "Claimant"}
            </span>
            <span className="text-[10px] text-slate-400 font-medium">Policyholder</span>
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Sign out"
          className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors cursor-pointer"
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
            className="p-1 -ml-1 text-slate-600 hover:text-[#00647c]"
          >
            <span className="material-symbols-outlined text-2xl">menu</span>
          </button>
          <span className="material-symbols-outlined text-[#00647c] text-xl">shield_with_heart</span>
          <span>InsureClaimAI</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={onNewClaim}
            className="flex items-center gap-1 bg-[#00647c] text-white px-2.5 py-1 rounded-lg text-xs font-semibold"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            <span>New</span>
          </button>
          <button
            onClick={onLogout}
            className="text-slate-500 hover:text-red-600 p-1.5 rounded-md hover:bg-slate-100"
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
      <nav className="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 z-40 shadow-xs">
        {sidebarContent}
      </nav>
    </>
  );
};
