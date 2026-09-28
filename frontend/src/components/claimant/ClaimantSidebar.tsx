import React, { useMemo, useState } from "react";
import { useRouter } from "next/router";

export interface ClaimSummary {
  ticket_id: string;
  status: string;
  conversation_status?: string;
  insurance_type?: string;
  event_date?: string | null;
  event_description?: string | null;
  event_location?: string | null;
  estimated_claim_amount?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_message?: string | null;
  turn_count?: number;
  adjuster_requests?: Array<{ id?: string; message?: string; status?: string; requested_at?: string }>;
}

interface ClaimantSidebarProps {
  userName?: string;
  claims: ClaimSummary[];
  activeTicketId?: string;
  activeRoute?: "claimant" | "link-policy";
  loadingClaims?: boolean;
  onSelectClaim: (ticketId: string) => void;
  onNewClaim: () => void;
  onDeleteClaim?: (ticketId: string, e: React.MouseEvent) => void;
  onLogout: () => void;
}

const statusLabel = (value?: string) => (value || "draft").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const dateLabel = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};

export const ClaimantSidebar: React.FC<ClaimantSidebarProps> = ({
  userName,
  claims = [],
  activeTicketId,
  activeRoute = "claimant",
  loadingClaims = false,
  onSelectClaim,
  onNewClaim,
  onDeleteClaim,
  onLogout,
}) => {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return claims;
    return claims.filter((claim) => [claim.ticket_id, claim.insurance_type, claim.status, claim.event_description].some((value) => String(value || "").toLowerCase().includes(q)));
  }, [claims, query]);
  const attention = claims.filter((claim) => claim.adjuster_requests?.some((item) => item.status !== "resolved")).length;

  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r border-slate-200/80 bg-[#fbfcfc] md:flex">
      <div className="border-b border-slate-100 px-5 py-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#10373d] text-[#c5e2de]">
            <span className="material-symbols-outlined text-[20px]">shield</span>
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Claimant portal</p>
            <p className="mt-0.5 text-sm font-semibold tracking-tight text-slate-900">InsureClaimAI</p>
          </div>
        </div>
      </div>

      <div className="px-4 py-4">
        <button onClick={onNewClaim} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0b6b72] px-4 py-3 text-xs font-semibold text-white transition hover:bg-[#095b61]">
          <span className="material-symbols-outlined text-[17px]">add</span>
          Start a new claim
        </button>
        <div className="mt-3 grid gap-1">
          <button onClick={() => router.push("/claimant")} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-xs font-semibold ${activeRoute === "claimant" ? "bg-[#e6f2f0] text-[#0b6b72]" : "text-slate-500 hover:bg-slate-100"}`}>
            <span className="material-symbols-outlined text-[18px]">forum</span>
            <span className="flex-1">Claims & messages</span>
            {attention > 0 && <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold text-amber-800">{attention}</span>}
          </button>
          <button onClick={() => router.push("/claimant/link-policy")} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-xs font-semibold ${activeRoute === "link-policy" ? "bg-[#e6f2f0] text-[#0b6b72]" : "text-slate-500 hover:bg-slate-100"}`}>
            <span className="material-symbols-outlined text-[18px]">verified_user</span>
            <span>My policies</span>
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 border-t border-slate-100 px-4 py-4">
        <div className="flex items-center justify-between px-1">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Your claims</p>
            <p className="mt-1 text-[10px] text-slate-400">{claims.length} total</p>
          </div>
        </div>
        <div className="mt-3">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search claims" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] outline-none focus:border-[#0b6b72]" />
        </div>
        <div className="mt-3 max-h-[48vh] space-y-1.5 overflow-y-auto pr-1">
          {loadingClaims && !claims.length ? (
            <div className="space-y-2"><div className="h-16 animate-pulse rounded-xl bg-slate-100" /><div className="h-16 animate-pulse rounded-xl bg-slate-100" /></div>
          ) : filtered.length ? filtered.map((claim) => {
            const requestOpen = claim.adjuster_requests?.some((item) => item.status !== "resolved");
            return (
              <button key={claim.ticket_id} onClick={() => onSelectClaim(claim.ticket_id)} className={`w-full rounded-xl border px-3 py-3 text-left transition ${activeTicketId === claim.ticket_id ? "border-[#b9d8d4] bg-white shadow-sm" : "border-transparent hover:border-slate-200 hover:bg-white"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[9px] font-semibold text-slate-500">#{claim.ticket_id.replace("CLAIM-", "")}</span>
                  {requestOpen ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[8px] font-bold uppercase text-amber-800">Action needed</span> : <span className="text-[9px] font-semibold text-slate-400">{statusLabel(claim.status)}</span>}
                </div>
                <p className="mt-1.5 truncate text-[11px] font-semibold text-slate-800">{claim.insurance_type ? statusLabel(claim.insurance_type) : "Claim in progress"}</p>
                <div className="mt-1 flex items-center justify-between text-[9px] text-slate-400"><span>{dateLabel(claim.updated_at)}</span><span>{claim.turn_count || 0} messages</span></div>
              </button>
            );
          }) : (
            <div className="rounded-xl border border-dashed border-slate-200 p-4 text-[10px] leading-4 text-slate-400">{query ? "No matching claims." : "Your submitted claims will appear here."}</div>
          )}
        </div>
      </div>

      <div className="border-t border-slate-100 px-5 py-4">
        <p className="text-xs font-semibold text-slate-800">{userName || "Claimant"}</p>
        <button onClick={onLogout} className="mt-2 text-[10px] font-semibold text-slate-400 hover:text-slate-700">Sign out</button>
      </div>
    </aside>
  );
};