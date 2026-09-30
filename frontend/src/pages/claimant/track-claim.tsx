import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { ClaimantSidebar, ClaimSummary } from "@/components/claimant/ClaimantSidebar";
import { ClaimantTopBar } from "@/components/claimant/ClaimantTopBar";
import { getAuthToken, clearAuthToken, verifySessionOrRedirect } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

type EvidenceRequestItem = {
  id: string;
  claim_id: string;
  adjuster_id: string;
  request_text: string;
  status: string;
  response_note?: string | null;
  requested_at?: string | null;
  responded_at?: string | null;
  response_evidence?: { id?: string; name?: string; verification_status?: string } | null;
};

type TrackedClaim = ClaimSummary & {
  extracted_data?: Record<string, unknown>;
  evidence_requests?: EvidenceRequestItem[];
  open_request_count?: number;
  evidence?: Array<Record<string, unknown>>;
  policy_verification?: Record<string, unknown>;
  assigned_adjuster?: { id?: string; name?: string; specialization?: string };
};

const postSubmission = new Set([
  "submitted",
  "assigned",
  "under_review",
  "pending_evidence",
  "approved",
  "partially_approved",
  "rejected",
  "escalated",
  "closed",
]);

const getStatusBadge = (status: string, openRequests = 0) => {
  if (openRequests > 0 || status?.toLowerCase() === "pending_evidence") {
    return {
      bg: "bg-amber-100 text-amber-900 border-amber-300 font-bold",
      label: "Action Needed",
      icon: "warning",
    };
  }
  switch (status?.toLowerCase()) {
    case "submitted":
      return {
        bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
        label: "Submitted",
        icon: "verified",
      };
    case "assigned":
      return {
        bg: "bg-sky-50 text-sky-700 border-sky-200",
        label: "Assigned",
        icon: "assignment_ind",
      };
    case "under_review":
      return {
        bg: "bg-indigo-50 text-indigo-700 border-indigo-200",
        label: "Under Review",
        icon: "rule",
      };
    case "approved":
      return {
        bg: "bg-emerald-100 text-emerald-800 border-emerald-300",
        label: "Approved",
        icon: "check_circle",
      };
    case "partially_approved":
      return {
        bg: "bg-teal-50 text-teal-800 border-teal-300",
        label: "Partially Approved",
        icon: "check",
      };
    case "rejected":
      return {
        bg: "bg-rose-50 text-rose-700 border-rose-200",
        label: "Rejected",
        icon: "cancel",
      };
    case "escalated":
      return {
        bg: "bg-orange-50 text-orange-700 border-orange-200",
        label: "Escalated",
        icon: "priority_high",
      };
    case "closed":
      return {
        bg: "bg-slate-100 text-slate-700 border-slate-300",
        label: "Closed",
        icon: "lock",
      };
    default:
      return {
        bg: "bg-slate-100 text-slate-700 border-slate-200",
        label: status || "Submitted",
        icon: "hourglass_top",
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
      return "shield";
  }
};

const formatCurrency = (amt?: number | null) => {
  if (amt === null || amt === undefined) return "—";
  return "₹" + Number(amt).toLocaleString("en-IN");
};

export default function TrackClaimPage() {
  const router = useRouter();
  const [userName, setUserName] = useState("Claimant");
  const [allUserClaims, setAllUserClaims] = useState<ClaimSummary[]>([]);
  const [claims, setClaims] = useState<TrackedClaim[]>([]);
  const [selected, setSelected] = useState<TrackedClaim | undefined>();
  const [viewMode, setViewMode] = useState<"queue" | "detail">("queue");
  const [filterTab, setFilterTab] = useState<"all" | "action_needed" | "under_review" | "approved">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string | null>(null);
  const [responseNotes, setResponseNotes] = useState<Record<string, string>>({});
  const [selectedFiles, setSelectedFiles] = useState<Record<string, File | null>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadTrackedClaims = useCallback(async (token: string, targetTicket?: string) => {
    setLoading(true);
    setError("");
    try {
      const [allRes, trackRes] = await Promise.all([
        apiFetch<ClaimSummary[] | { items?: ClaimSummary[] }>("/api/v1/claims", { token }).catch(() => []),
        apiFetch<{ items?: TrackedClaim[] }>("/api/v1/claims/track", { token }),
      ]);
      const allItems = Array.isArray(allRes) ? allRes : allRes?.items || [];
      setAllUserClaims(allItems);

      const items = (trackRes.items || []).filter((c) => postSubmission.has(c.status?.toLowerCase() || ""));
      setClaims(items);

      const q = targetTicket || (typeof router.query.ticket === "string" ? router.query.ticket : "");
      if (q) {
        const matched = items.find((c) => c.ticket_id === q);
        if (matched) {
          setSelected(matched);
          setViewMode("detail");
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load tracked claims.");
    } finally {
      setLoading(false);
    }
  }, [router.query.ticket]);

  useEffect(() => {
    if (!router.isReady) return;
    verifySessionOrRedirect(router, {
      requiredRole: "CLAIMANT",
      onSuccess: (data) => {
        setUserName((data.full_name as string) || "Claimant");
        const token = getAuthToken();
        if (token) void loadTrackedClaims(token);
      },
    });
  }, [router.isReady, loadTrackedClaims, router]);

  const openClaimDetail = (claim: TrackedClaim) => {
    setSelected(claim);
    setViewMode("detail");
    router.replace({ pathname: "/claimant/track-claim", query: { ticket: claim.ticket_id } }, undefined, { shallow: true });
  };

  const backToQueue = () => {
    setViewMode("queue");
    router.replace({ pathname: "/claimant/track-claim" }, undefined, { shallow: true });
  };

  const handleRespondToRequest = async (requestId: string) => {
    const token = getAuthToken();
    if (!selected || !token) return;

    const note = (responseNotes[requestId] || "").trim();
    const file = selectedFiles[requestId] || null;

    if (!file && !note) {
      setError("Please write an explanation or attach a document for the adjuster.");
      return;
    }

    setUploading(requestId);
    setError("");
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      if (note) form.append("response_note", note);

      await apiFetch(`/api/v1/claims/${selected.ticket_id}/requests/${requestId}/respond`, {
        token,
        method: "POST",
        body: form,
      });

      setResponseNotes((prev) => ({ ...prev, [requestId]: "" }));
      setSelectedFiles((prev) => ({ ...prev, [requestId]: null }));
      setSuccess("Your response and documents have been submitted to the adjuster.");
      setTimeout(() => setSuccess(""), 4000);
      await loadTrackedClaims(token, selected.ticket_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not submit evidence response.");
    } finally {
      setUploading(null);
    }
  };

  const getStatusStepIndex = (status?: string) => {
    switch (status?.toLowerCase()) {
      case "approved":
      case "partially_approved":
      case "rejected":
      case "closed":
        return 3;
      case "under_review":
      case "pending_evidence":
        return 2;
      case "assigned":
        return 1;
      case "submitted":
      default:
        return 0;
    }
  };

  const logout = () => {
    clearAuthToken();
    void router.push("/login");
  };

  const actionNeededCount = useMemo(() => {
    return claims.filter((c) => (c.open_request_count && c.open_request_count > 0) || c.status === "pending_evidence").length;
  }, [claims]);

  const underReviewCount = useMemo(() => {
    return claims.filter((c) => c.status === "under_review" || c.status === "assigned" || c.status === "submitted").length;
  }, [claims]);

  const approvedCount = useMemo(() => {
    return claims.filter((c) => c.status === "approved" || c.status === "partially_approved" || c.status === "closed").length;
  }, [claims]);

  const filteredQueue = useMemo(() => {
    return claims.filter((c) => {
      const hasAction = (c.open_request_count && c.open_request_count > 0) || c.status === "pending_evidence";
      if (filterTab === "action_needed" && !hasAction) return false;
      if (filterTab === "under_review" && !(c.status === "under_review" || c.status === "assigned" || c.status === "submitted")) return false;
      if (filterTab === "approved" && !(c.status === "approved" || c.status === "partially_approved" || c.status === "closed")) return false;

      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        c.ticket_id.toLowerCase().includes(q) ||
        (c.insurance_type && c.insurance_type.toLowerCase().includes(q)) ||
        (c.event_description && c.event_description.toLowerCase().includes(q)) ||
        (c.event_location && c.event_location.toLowerCase().includes(q)) ||
        (c.status && c.status.toLowerCase().includes(q))
      );
    });
  }, [claims, filterTab, searchQuery]);

  const openRequests = (selected?.evidence_requests || []).filter((r) => r.status === "open");
  const respondedRequests = (selected?.evidence_requests || []).filter((r) => r.status !== "open");
  const stepIdx = getStatusStepIndex(selected?.status);

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] flex flex-col md:flex-row">
      <ClaimantSidebar
        userName={userName}
        claims={allUserClaims.length > 0 ? allUserClaims : claims}
        activeRoute="track-claim"
        activeTicketId={selected?.ticket_id}
        onSelectClaim={(tid) => {
          const c = claims.find((item) => item.ticket_id === tid);
          if (c) openClaimDetail(c);
        }}
        onNewClaim={() => router.push("/claimant")}
        onDeleteClaim={() => {}}
        onLogout={logout}
        loadingClaims={loading}
      />

      <main className="flex-1 md:ml-64 min-h-screen flex flex-col">
        <ClaimantTopBar
          isRecording={false}
          agentState="idle"
          currentIncidentTitle="Track Claim"
          ticketId={selected?.ticket_id || ""}
          onStartNewSession={() => router.push("/claimant")}
          onExportTranscript={() => {}}
          loading={loading}
          errorBanner={error}
          onDismissError={() => setError("")}
          mobileTab="chat"
          onTabChange={() => {}}
          pendingCount={actionNeededCount}
        />

        <div className="flex-1 max-w-[1300px] w-full mx-auto p-4 md:p-8">
          {success && (
            <div className="mb-5 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-xs font-semibold text-emerald-800 flex items-center justify-between shadow-xs">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-emerald-600 text-lg">check_circle</span>
                <span>{success}</span>
              </div>
              <button onClick={() => setSuccess("")} className="text-emerald-700 hover:text-emerald-950">
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            </div>
          )}

          {/* VIEW MODE 1: CLAIMS QUEUE TABLE (LIKE ADJUSTER QUEUE) */}
          {viewMode === "queue" && (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[#00647c] mb-1 font-bold">
                    Claimant Portal / Claims Tracking
                  </div>
                  <h1 className="font-headline text-2xl font-bold text-slate-900">Submitted Claims Queue</h1>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Review adjudication status and respond to adjuster evidence requests.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const token = getAuthToken();
                      if (token) void loadTrackedClaims(token);
                    }}
                    className="border border-[#bdc8ce] hover:border-[#00647c] bg-white rounded-xl px-3 py-2 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-2xs"
                  >
                    <span className="material-symbols-outlined text-base text-[#00647c]">refresh</span>
                    <span>Refresh</span>
                  </button>
                  <Link
                    href="/claimant"
                    className="bg-[#00647c] hover:bg-[#004e61] text-white rounded-xl px-3.5 py-2 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
                  >
                    <span className="material-symbols-outlined text-base">add</span>
                    <span>New Intake</span>
                  </Link>
                </div>
              </div>

              {/* 4 Metric KPI Cards (Matching Adjuster Style) */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  { label: "Total Submitted", count: claims.length, icon: "assignment_turned_in", alert: false },
                  { label: "Action Needed", count: actionNeededCount, icon: "warning", alert: actionNeededCount > 0 },
                  { label: "Under Review", count: underReviewCount, icon: "hourglass_top", alert: false },
                  { label: "Approved / Closed", count: approvedCount, icon: "verified", alert: false },
                ].map((item, idx) => (
                  <div
                    key={idx}
                    className={`bg-white border rounded-xl p-4 shadow-2xs ${
                      item.alert ? "border-amber-300 ring-2 ring-amber-300/30 bg-amber-50/30" : "border-[#e0e3e5]"
                    }`}
                  >
                    <div className="flex justify-between text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                      <span>{item.label}</span>
                      <span className={`material-symbols-outlined text-lg ${item.alert ? "text-amber-600 animate-pulse" : "text-[#00647c]"}`}>
                        {item.icon}
                      </span>
                    </div>
                    <div className={`font-headline text-2xl font-bold mt-2 ${item.alert ? "text-amber-900" : "text-slate-900"}`}>
                      {item.count}
                    </div>
                  </div>
                ))}
              </div>

              {/* Claims Queue Table Card */}
              <div className="bg-white border border-[#e0e3e5] rounded-2xl overflow-hidden shadow-xs">
                {/* Search & Filter Bar */}
                <div className="p-4 border-b border-[#e0e3e5] flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#f8fafc]">
                  {/* Filter Pills */}
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
                    {[
                      { key: "all", label: `All (${claims.length})` },
                      { key: "action_needed", label: `Action Needed (${actionNeededCount})`, alert: actionNeededCount > 0 },
                      { key: "under_review", label: `Under Review (${underReviewCount})` },
                      { key: "approved", label: `Approved (${approvedCount})` },
                    ].map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setFilterTab(tab.key as typeof filterTab)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                          filterTab === tab.key
                            ? "bg-[#00647c] text-white shadow-2xs"
                            : tab.alert
                            ? "bg-amber-100 text-amber-900 hover:bg-amber-200"
                            : "bg-white text-slate-600 hover:bg-slate-200/60 border border-slate-200"
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Search Input */}
                  <div className="relative w-full md:w-72">
                    <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm pointer-events-none">
                      search
                    </span>
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search claim, type, location..."
                      className="w-full pl-8 pr-7 py-1.5 bg-white border border-[#e2e8f0] rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c]"
                    />
                    {searchQuery && (
                      <button
                        onClick={() => setSearchQuery("")}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                      >
                        <span className="material-symbols-outlined text-xs">close</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Table Header */}
                <div className="hidden md:grid grid-cols-5 gap-4 px-6 py-3 bg-[#f7f9fb] text-[10px] uppercase tracking-wider font-bold text-slate-500 border-b border-[#e0e3e5]">
                  <span>Claim Reference</span>
                  <span>Insurance Type</span>
                  <span>Status</span>
                  <span>Estimated Amount</span>
                  <span className="text-right">Action</span>
                </div>

                {/* Loading / Empty States */}
                {loading && claims.length === 0 ? (
                  <div className="py-16 text-center">
                    <div className="w-8 h-8 border-3 border-[#00647c] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-xs text-slate-500">Loading submitted claims...</p>
                  </div>
                ) : filteredQueue.length === 0 ? (
                  <div className="py-16 text-center px-4">
                    <span className="material-symbols-outlined text-slate-300 text-4xl mb-2 block">
                      track_changes
                    </span>
                    <h3 className="font-headline font-semibold text-slate-700 text-sm">No claims found</h3>
                    <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                      {searchQuery
                        ? "No claims match your search query."
                        : filterTab === "action_needed"
                        ? "No claims require additional evidence right now."
                        : "Claims you submit through intake will appear here in your tracking queue."}
                    </p>
                  </div>
                ) : (
                  /* Queue Rows */
                  filteredQueue.map((c) => {
                    const hasAction = (c.open_request_count && c.open_request_count > 0) || c.status === "pending_evidence";
                    const badge = getStatusBadge(c.status, c.open_request_count || 0);
                    const icon = getInsuranceIcon(c.insurance_type);

                    return (
                      <div
                        key={c.ticket_id}
                        onClick={() => openClaimDetail(c)}
                        className={`group w-full text-left grid grid-cols-1 md:grid-cols-5 gap-2 md:gap-4 px-6 py-4 border-t border-[#edf0f1] hover:bg-[#f8fbfc] transition-all cursor-pointer items-center ${
                          hasAction ? "bg-amber-50/20" : ""
                        }`}
                      >
                        {/* Col 1: Claim ID & Metadata */}
                        <div>
                          <div className="flex items-center gap-1.5">
                            <b className="text-xs font-mono font-bold text-[#00647c] group-hover:underline">
                              #{c.ticket_id}
                            </b>
                            {hasAction && (
                              <span className="flex h-2 w-2 relative">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-500 mt-0.5 truncate">
                            {c.event_date || "Date pending"} · {c.event_location || "Location pending"}
                          </div>
                        </div>

                        {/* Col 2: Type */}
                        <div className="flex items-center gap-1.5 text-xs text-slate-700 capitalize font-medium">
                          <span className="material-symbols-outlined text-sm text-[#00647c]">{icon}</span>
                          <span>{c.insurance_type || "General"}</span>
                        </div>

                        {/* Col 3: Status Badge */}
                        <div>
                          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${badge.bg}`}>
                            <span className="material-symbols-outlined text-[13px]">{badge.icon}</span>
                            <span>{badge.label}</span>
                          </span>
                        </div>

                        {/* Col 4: Amount */}
                        <div className="text-xs font-semibold text-slate-800">
                          {formatCurrency(c.estimated_claim_amount)}
                        </div>

                        {/* Col 5: Action Button */}
                        <div className="md:text-right">
                          {hasAction ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openClaimDetail(c);
                              }}
                              className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-xs font-bold shadow-xs inline-flex items-center gap-1 transition-all cursor-pointer"
                            >
                              <span className="material-symbols-outlined text-xs">edit_note</span>
                              <span>Respond to Request</span>
                            </button>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openClaimDetail(c);
                              }}
                              className="px-3 py-1.5 border border-slate-300 hover:border-[#00647c] hover:bg-white text-slate-700 rounded-xl text-xs font-semibold inline-flex items-center gap-1 transition-all cursor-pointer"
                            >
                              <span>View Status</span>
                              <span className="material-symbols-outlined text-xs">arrow_forward</span>
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* VIEW MODE 2: CLAIM DETAIL & ADJUSTER RESPONSE VIEW */}
          {viewMode === "detail" && selected && (
            <div className="space-y-6">
              {/* Back to Queue Navigation Button */}
              <div className="flex items-center justify-between">
                <button
                  onClick={backToQueue}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-[#00647c] hover:text-[#004e61] px-3 py-1.5 rounded-xl bg-white border border-slate-200 shadow-2xs hover:bg-slate-50 transition-all cursor-pointer"
                >
                  <span className="material-symbols-outlined text-sm">arrow_back</span>
                  <span>Back to Claims Queue</span>
                </button>

                {/* Quick Claim Switcher Dropdown */}
                {claims.length > 1 && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span>Switch claim:</span>
                    <select
                      value={selected.ticket_id}
                      onChange={(e) => {
                        const next = claims.find((c) => c.ticket_id === e.target.value);
                        if (next) openClaimDetail(next);
                      }}
                      className="bg-white border border-slate-300 rounded-lg px-2.5 py-1 text-xs text-slate-800 font-semibold focus:outline-none focus:ring-1 focus:ring-[#00647c]"
                    >
                      {claims.map((c) => (
                        <option key={c.ticket_id} value={c.ticket_id}>
                          #{c.ticket_id} - {c.insurance_type?.toUpperCase() || "General"} ({c.status})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Status & Overview Box */}
              <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs p-5 md:p-6 space-y-5">
                {/* Top Reference & Badges */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-slate-100">
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                      Claim Reference
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="font-mono text-xl font-bold text-[#00647c]">
                        #{selected.ticket_id}
                      </span>
                      {(() => {
                        const badge = getStatusBadge(selected.status, openRequests.length);
                        return (
                          <span className={`text-[10px] uppercase font-bold px-2.5 py-1 rounded-full border flex items-center gap-1 ${badge.bg}`}>
                            <span className="material-symbols-outlined text-xs">{badge.icon}</span>
                            <span>{badge.label}</span>
                          </span>
                        );
                      })()}
                    </div>
                  </div>

                  <div className="text-left sm:text-right text-xs text-slate-500">
                    <div>Insurance Type: <b>{selected.insurance_type?.toUpperCase() || "General"}</b></div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      Submitted on {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"}
                    </div>
                  </div>
                </div>

                {/* Progress Lifecycle Bar */}
                <div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3">
                    Status Progress Lifecycle
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                    {[
                      { title: "Submitted", desc: "Intake complete", done: stepIdx >= 0, current: stepIdx === 0 },
                      { title: "Assigned", desc: "Adjuster assigned", done: stepIdx >= 1, current: stepIdx === 1 },
                      {
                        title: "Evidence Review",
                        desc: openRequests.length > 0 ? "Action Required" : "Documents review",
                        done: stepIdx >= 2,
                        current: stepIdx === 2,
                        alert: openRequests.length > 0,
                      },
                      {
                        title: "Outcome",
                        desc: selected.status === "approved" ? "Approved" : selected.status === "rejected" ? "Decision Final" : "Final Outcome",
                        done: stepIdx >= 3,
                        current: stepIdx === 3,
                      },
                    ].map((s, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-xl border text-xs ${
                          s.alert
                            ? "bg-amber-50 border-amber-300 text-amber-900 ring-2 ring-amber-300/40"
                            : s.current
                            ? "bg-white border-[#00647c] text-slate-900 ring-1 ring-[#00647c]/20 shadow-xs"
                            : s.done
                            ? "bg-white border-slate-200 text-slate-800"
                            : "bg-slate-100/60 border-slate-200/60 text-slate-400"
                        }`}
                      >
                        <div className="flex items-center gap-1.5 font-bold mb-1">
                          <span className={`material-symbols-outlined text-[15px] ${s.alert ? "text-amber-600" : s.done || s.current ? "text-[#00647c]" : "text-slate-300"}`}>
                            {s.alert ? "warning" : s.done && !s.current ? "check_circle" : "radio_button_checked"}
                          </span>
                          <span>{s.title}</span>
                        </div>
                        <p className="text-[10px] pl-5 text-slate-500">{s.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Incident Summary Fields */}
                <div className="grid sm:grid-cols-3 gap-3 pt-3 border-t border-slate-100 text-xs">
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Incident Date</span>
                    <span className="font-semibold text-slate-800">{selected.event_date || "—"}</span>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Location</span>
                    <span className="font-semibold text-slate-800 truncate block">{selected.event_location || "—"}</span>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Estimated Amount</span>
                    <span className="font-semibold text-slate-800">
                      {formatCurrency(selected.estimated_claim_amount)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Adjuster Evidence Requests (MAIN ACTION AREA) */}
              <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs p-5 md:p-6 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div>
                    <h2 className="font-headline text-base font-bold text-slate-900">
                      Adjuster Evidence Requests
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      If the adjuster needs extra receipts, photos, or explanations, respond directly below.
                    </p>
                  </div>
                  {openRequests.length > 0 && (
                    <span className="px-2.5 py-1 bg-amber-100 border border-amber-300 text-amber-900 text-[10px] font-bold rounded-full animate-pulse">
                      {openRequests.length} Action{openRequests.length > 1 ? "s" : ""} Required
                    </span>
                  )}
                </div>

                {/* OPEN REQUESTS WITH TEXT FIELD & UPLOAD BUTTON */}
                {openRequests.length > 0 ? (
                  <div className="space-y-4">
                    {openRequests.map((req) => (
                      <div key={req.id} className="rounded-2xl border-2 border-amber-300 bg-amber-50/20 p-5 shadow-xs space-y-3">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 pb-2 border-b border-amber-200/60">
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-amber-600 font-bold">priority_high</span>
                            <span className="text-xs font-bold uppercase tracking-wider text-amber-900">
                              Action Needed: Extra Request from Adjuster
                            </span>
                          </div>
                          <span className="text-[10px] text-slate-400">
                            Requested {req.requested_at ? new Date(req.requested_at).toLocaleString() : "Recently"}
                          </span>
                        </div>

                        {/* The Adjuster's Request Text */}
                        <div className="p-3.5 bg-white rounded-xl border border-amber-200 text-xs text-slate-800 font-medium leading-relaxed shadow-2xs">
                          &ldquo;{req.request_text}&rdquo;
                        </div>

                        {/* Text Field & Upload Form */}
                        <div className="space-y-3 pt-1">
                          <div>
                            <label className="text-[11px] font-bold text-slate-700 block mb-1">
                              Response Note / Explanation (Optional if file attached)
                            </label>
                            <textarea
                              value={responseNotes[req.id] || ""}
                              onChange={(e) => setResponseNotes((prev) => ({ ...prev, [req.id]: e.target.value }))}
                              placeholder="Provide any details, explanations, or answers to the adjuster's request…"
                              rows={3}
                              className="w-full border border-slate-200 bg-white rounded-xl p-3 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c]"
                            />
                          </div>

                          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                            <div className="flex-1">
                              <label className="text-[11px] font-bold text-slate-700 block mb-1">
                                Attach Evidence Document / Image
                              </label>
                              <input
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.txt"
                                onChange={(e) => {
                                  const file = e.target.files?.[0] || null;
                                  setSelectedFiles((prev) => ({ ...prev, [req.id]: file }));
                                }}
                                className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-[#00647c]/10 file:text-[#00647c] hover:file:bg-[#00647c]/20 cursor-pointer"
                              />
                            </div>

                            <div className="sm:self-end">
                              <button
                                onClick={() => void handleRespondToRequest(req.id)}
                                disabled={uploading === req.id || (!responseNotes[req.id]?.trim() && !selectedFiles[req.id])}
                                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-[#00647c] hover:bg-[#004e61] disabled:opacity-50 text-white text-xs font-semibold shadow-xs flex items-center justify-center gap-1.5 cursor-pointer transition-all"
                              >
                                {uploading === req.id ? (
                                  <>
                                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                    <span>Submitting…</span>
                                  </>
                                ) : (
                                  <>
                                    <span className="material-symbols-outlined text-sm">upload</span>
                                    <span>Submit to Adjuster</span>
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 text-center">
                    <div className="w-9 h-9 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mx-auto mb-2">
                      <span className="material-symbols-outlined text-lg">check</span>
                    </div>
                    <h4 className="text-xs font-bold text-slate-800">No Open Adjuster Requests</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      The adjuster has not requested any extra documentation. Your claim is progressing through standard review.
                    </p>
                  </div>
                )}

                {/* Previously Responded Requests */}
                {respondedRequests.length > 0 && (
                  <div className="pt-3 border-t border-slate-100 space-y-2">
                    <h4 className="text-xs font-bold text-slate-700">Completed Requests</h4>
                    {respondedRequests.map((req) => (
                      <div key={req.id} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-xs">
                        <div className="flex justify-between items-center gap-2 mb-1.5">
                          <span className="font-bold text-slate-800">&ldquo;{req.request_text}&rdquo;</span>
                          <span className="text-[9px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                            Responded
                          </span>
                        </div>
                        {req.response_note && (
                          <p className="text-slate-600 bg-white p-2 rounded-lg border border-slate-200 mt-1.5">
                            <b>Your Note:</b> {req.response_note}
                          </p>
                        )}
                        {req.response_evidence?.name && (
                          <div className="mt-1.5 flex items-center gap-1.5 text-slate-600 text-[11px]">
                            <span className="material-symbols-outlined text-sm text-[#00647c]">attach_file</span>
                            <span>Attached: <b>{req.response_evidence.name}</b></span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Uploaded Evidence List */}
              {selected.evidence && selected.evidence.length > 0 && (
                <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs p-5 md:p-6 space-y-3">
                  <h3 className="font-headline text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Uploaded Documents ({selected.evidence.length})
                  </h3>
                  <div className="grid sm:grid-cols-2 gap-2.5">
                    {selected.evidence.map((item, idx) => (
                      <div key={idx} className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 truncate">
                          <span className="material-symbols-outlined text-[#00647c] text-lg">description</span>
                          <span className="font-medium text-slate-800 truncate">
                            {(item.original_filename as string) || (item.name as string) || `Document #${idx + 1}`}
                          </span>
                        </div>
                        <span className="text-[9px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full shrink-0">
                          {(item.verification_status as string) || "UPLOADED"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
