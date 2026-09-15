import React, { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { ClaimantSidebar, ClaimSummary } from "@/components/claimant/ClaimantSidebar";
import { getAuthToken, clearAuthToken } from "../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LinkedPolicy {
  policy_number: string;
  policy_type: string;
  coverage_amount: number;
  deductible: number;
  is_active: boolean;
  effective_date: string;
  expiry_date: string;
  policyholder_name?: string;
  linked_at?: string;
}

export default function LinkPolicyPage() {
  const router = useRouter();
  const { policy } = router.query;

  const [currentUser, setCurrentUser] = useState<{ id: string; full_name: string; email: string; role: string } | null>(null);
  const [claimsList, setClaimsList] = useState<ClaimSummary[]>([]);
  const [loadingClaims, setLoadingClaims] = useState(false);
  const [policyNumber, setPolicyNumber] = useState("");
  const [policyholderName, setPolicyholderName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phoneLast4, setPhoneLast4] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState<any>(null);

  const [myPolicies, setMyPolicies] = useState<LinkedPolicy[]>([]);
  const [loadingPolicies, setLoadingPolicies] = useState(true);

  const fetchClaimsList = async (token?: string) => {
    const t = token || getAuthToken();
    if (!t) return;
    setLoadingClaims(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/claims`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setClaimsList(Array.isArray(data) ? data : (data.items || []));
      }
    } catch {
      // ignore
    } finally {
      setLoadingClaims(false);
    }
  };

  const fetchMyPolicies = async (token?: string) => {
    const t = token || getAuthToken();
    if (!t) return;
    setLoadingPolicies(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/policies/my-policies`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMyPolicies(data);
      }
    } catch {
      // ignore
    } finally {
      setLoadingPolicies(false);
    }
  };

  // Initialize from query param if available
  useEffect(() => {
    if (policy && typeof policy === "string") {
      setPolicyNumber(policy.toUpperCase());
    }
  }, [policy]);

  // Authenticate user & load policies and claims
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push("/login");
      return;
    }

    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then((data) => {
        if (data.role !== "CLAIMANT") {
          router.push(data.role === "ADMIN" ? "/admin" : "/adjuster");
          return;
        }
        setCurrentUser(data);
        fetchMyPolicies(token);
        fetchClaimsList(token);
      })
      .catch(() => {
        clearAuthToken();
        router.push("/login");
      });
  }, [router]);

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.replace(/\D/g, "").slice(0, 4);
    setPhoneLast4(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessData(null);

    const token = getAuthToken();
    if (!token) {
      router.push("/login");
      return;
    }

    if (!policyNumber.trim() || !policyholderName.trim() || !dateOfBirth.trim() || phoneLast4.length !== 4) {
      setError("Please fill in all required fields (Policy Number, Policyholder Name, DOB, and 4-digit Phone).");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/policies/link`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          policy_number: policyNumber.trim().toUpperCase(),
          policyholder_name: policyholderName.trim(),
          date_of_birth: dateOfBirth.trim(),
          phone_last4: phoneLast4.trim(),
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || "Unable to link policy. Please verify your details.");
      }

      setSuccessData(data);
      fetchMyPolicies(token);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    clearAuthToken();
    router.push("/login");
  };

  const handleSelectClaim = (ticketId: string) => {
    router.push(`/claimant?ticket=${ticketId}`);
  };

  const handleNewClaim = () => {
    router.push("/claimant");
  };

  return (
    <div className="bg-[#f8fafc] text-[#0f172a] font-body antialiased min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Unified Claimant Sidebar */}
      <ClaimantSidebar
        userName={currentUser?.full_name || "Claimant"}
        claims={claimsList}
        activeRoute="link-policy"
        loadingClaims={loadingClaims}
        onSelectClaim={handleSelectClaim}
        onNewClaim={handleNewClaim}
        onLogout={handleLogout}
      />

      {/* Main Content Area */}
      <main className="flex-1 md:ml-64 flex flex-col min-h-screen bg-[#f8fafc] overflow-y-auto">
        {/* Top Header Bar matching ClaimantTopBar style */}
        <header className="px-4 md:px-8 py-3.5 border-b border-[#e2e8f0] bg-white sticky top-0 z-30 flex justify-between items-center shrink-0">
          <div className="flex items-center gap-2 text-slate-500">
            <Link
              href="/claimant"
              className="font-label text-xs hover:text-[#00647c] transition-colors flex items-center gap-1 font-medium"
            >
              <span className="material-symbols-outlined text-sm">forum</span>
              <span>Claimant Portal</span>
            </Link>
            <span className="material-symbols-outlined text-xs text-slate-400">chevron_right</span>
            <span className="font-label text-xs text-[#0f172a] font-bold">Link Policy</span>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/claimant"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-[#00647c] transition-colors flex items-center gap-1.5 shadow-2xs cursor-pointer"
            >
              <span className="material-symbols-outlined text-sm">chat_bubble</span>
              <span>Back to Intake Chat</span>
            </Link>
          </div>
        </header>

        {/* Page Content Canvas */}
        <div className="px-4 md:px-8 lg:px-10 max-w-6xl mx-auto py-8 w-full">
          {/* Header Banner */}
          <div className="mb-8">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#00647c]/10 text-[#00647c] text-xs font-semibold mb-2">
              <span className="material-symbols-outlined text-sm">shield</span>
              <span>Policyholder Verification</span>
            </div>
            <h1 className="font-headline text-2xl md:text-3xl font-bold text-[#0f172a] tracking-tight">
              Link Your Insurance Policy
            </h1>
            <p className="font-body text-xs md:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
              Authenticate your coverage details to unlock instant automated claim triage, zero-wait voice filing, and real-time dossier tracking.
            </p>
          </div>

          {/* Main Layout Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left Column: Verification Form */}
            <div className="lg:col-span-7">
              <div className="bg-white border border-[#e2e8f0] rounded-2xl p-6 md:p-8 shadow-xs">
                {error && (
                  <div className="mb-5 p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-start gap-2.5 animate-fade-in">
                    <span className="material-symbols-outlined text-base text-rose-600 mt-0.5">error</span>
                    <div>
                      <p className="font-semibold">Verification Failed</p>
                      <p className="mt-0.5 text-rose-700">{error}</p>
                    </div>
                  </div>
                )}

                {successData ? (
                  <div className="p-6 bg-slate-50 border border-[#00647c]/30 rounded-2xl text-xs text-[#0f172a] flex flex-col gap-4 animate-fade-in">
                    <div className="flex items-center gap-3">
                      <div className="w-11 h-11 rounded-xl bg-emerald-600 text-white flex items-center justify-center text-xl shrink-0 shadow-xs">
                        <span className="material-symbols-outlined fill" style={{ fontVariationSettings: "'FILL' 1" }}>
                          verified
                        </span>
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-[#0f172a]">
                          {successData.already_linked ? "Policy Already Linked" : "Policy Successfully Connected!"}
                        </h3>
                        <p className="text-slate-500 text-xs mt-0.5">
                          Policy <span className="font-mono font-bold text-[#00647c]">#{successData.policy_number}</span> {successData.policyholder_name ? `(${successData.policyholder_name})` : ""} is verified and active.
                        </p>
                      </div>
                    </div>

                    <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                      <Link
                        href={`/claimant?policy=${successData.policy_number}`}
                        className="w-full sm:flex-1 py-2.5 px-4 rounded-xl bg-[#00647c] hover:bg-[#004e61] text-white font-label font-semibold text-center text-xs shadow-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-sm">record_voice_over</span>
                        <span>Start Claim Intake</span>
                      </Link>
                      <button
                        onClick={() => {
                          setSuccessData(null);
                          setPolicyNumber("");
                          setPolicyholderName("");
                          setDateOfBirth("");
                          setPhoneLast4("");
                        }}
                        className="w-full sm:w-auto py-2.5 px-4 rounded-xl bg-white border border-slate-200 text-slate-700 hover:text-[#00647c] hover:bg-slate-50 text-xs font-semibold transition-colors cursor-pointer"
                      >
                        Link Another
                      </button>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-5" id="policy-link-form">
                    <div>
                      <label className="font-label text-xs font-semibold text-slate-700 block mb-1.5" htmlFor="policy-number">
                        Policy Number <span className="text-rose-500">*</span>
                      </label>
                      <div className="relative">
                        <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]">
                          badge
                        </span>
                        <input
                          id="policy-number"
                          type="text"
                          required
                          placeholder="e.g. POL-8492-AX or MOT-5521"
                          value={policyNumber}
                          onChange={(e) => setPolicyNumber(e.target.value.toUpperCase())}
                          className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-3.5 font-body text-xs md:text-sm text-slate-900 placeholder:text-slate-400 font-mono uppercase tracking-wide focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] transition-all"
                        />
                      </div>
                      <span className="text-[11px] text-slate-400 mt-1 block">
                        Found on your insurance certificate, schedule, or email receipt
                      </span>
                    </div>

                    <div>
                      <label className="font-label text-xs font-semibold text-slate-700 block mb-1.5" htmlFor="policyholder-name">
                        Policyholder Full Name <span className="text-rose-500">*</span>
                      </label>
                      <div className="relative">
                        <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]">
                          person
                        </span>
                        <input
                          id="policyholder-name"
                          type="text"
                          required
                          placeholder="e.g. John Doe or Sarah Jenkins"
                          value={policyholderName}
                          onChange={(e) => setPolicyholderName(e.target.value)}
                          className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-3.5 font-body text-xs md:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] transition-all"
                        />
                      </div>
                      <span className="text-[11px] text-slate-400 mt-1 block">
                        Must match the primary named insured on policy records
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="font-label text-xs font-semibold text-slate-700 block mb-1.5" htmlFor="dob">
                          Date of Birth <span className="text-rose-500">*</span>
                        </label>
                        <div className="relative">
                          <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]">
                            calendar_month
                          </span>
                          <input
                            id="dob"
                            type="date"
                            required
                            value={dateOfBirth}
                            onChange={(e) => setDateOfBirth(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-3.5 font-body text-xs md:text-sm text-slate-900 focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] transition-all"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="font-label text-xs font-semibold text-slate-700 block mb-1.5" htmlFor="phone-last-4">
                          Phone Last 4 Digits <span className="text-rose-500">*</span>
                        </label>
                        <div className="relative">
                          <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]">
                            dialpad
                          </span>
                          <input
                            id="phone-last-4"
                            type="text"
                            maxLength={4}
                            required
                            placeholder="1234"
                            value={phoneLast4}
                            onChange={handlePhoneChange}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-3.5 font-body text-xs md:text-sm text-slate-900 placeholder:text-slate-400 font-mono tracking-widest focus:outline-none focus:ring-1 focus:ring-[#00647c] focus:border-[#00647c] transition-all"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
                      <span className="font-label text-xs text-slate-500 flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[16px] text-emerald-600">lock</span>
                        <span>Encrypted & Verified via InsureClaimAI Core</span>
                      </span>
                      <button
                        type="submit"
                        disabled={loading}
                        className="w-full sm:w-auto bg-[#00647c] hover:bg-[#004e61] text-white font-label text-xs font-semibold px-5 py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-xs disabled:opacity-50 cursor-pointer active:scale-[0.99]"
                      >
                        {loading ? (
                          <>
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            <span>Verifying...</span>
                          </>
                        ) : (
                          <>
                            <span>Verify & Connect Policy</span>
                            <span className="material-symbols-outlined text-base">arrow_forward</span>
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>

            {/* Right Column: Information & Trust Panel */}
            <div className="lg:col-span-5">
              <div className="bg-white border border-[#e2e8f0] rounded-2xl p-6 md:p-8 space-y-5 shadow-xs">
                <div className="w-11 h-11 rounded-xl bg-[#00647c]/10 text-[#00647c] flex items-center justify-center">
                  <span className="material-symbols-outlined text-2xl">verified_user</span>
                </div>
                <div>
                  <h3 className="font-headline text-base md:text-lg font-bold text-[#0f172a]">
                    Why Link Your Policy?
                  </h3>
                  <p className="font-body text-xs text-slate-500 mt-1 leading-relaxed">
                    Connecting your policy allows our autonomous intake agent to instantly retrieve coverage limits, calculate deductibles, and speed up settlement workflows.
                  </p>
                </div>

                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <div className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-emerald-600 text-[18px] shrink-0 mt-0.5">
                      check_circle
                    </span>
                    <div>
                      <p className="font-semibold text-xs text-slate-800">Zero-Wait Voice Intake</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        File claims naturally via conversational voice without manually entering repetitive policy numbers.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-emerald-600 text-[18px] shrink-0 mt-0.5">
                      check_circle
                    </span>
                    <div>
                      <p className="font-semibold text-xs text-slate-800">Coverage & Deductible Pre-Check</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Real-time verification ensures that incident details match active policy limits and clauses.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-emerald-600 text-[18px] shrink-0 mt-0.5">
                      check_circle
                    </span>
                    <div>
                      <p className="font-semibold text-xs text-slate-800">Direct Adjuster Routing</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Submissions are immediately routed to specialized adjusters with full incident dossiers.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Connected Policies Section */}
          <div className="mt-10 pt-8 border-t border-[#e2e8f0]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-headline text-lg md:text-xl font-bold text-[#0f172a]">
                  Connected Policies
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Policies linked to your profile ready for immediate claim intake
                </p>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-200/80 text-slate-700 font-mono">
                {myPolicies.length} {myPolicies.length === 1 ? "Policy" : "Policies"}
              </span>
            </div>

            {loadingPolicies ? (
              <div className="p-8 text-center text-xs text-slate-400 bg-white border border-[#e2e8f0] rounded-2xl flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-[#00647c] border-t-transparent rounded-full animate-spin" />
                <span>Loading your linked policies...</span>
              </div>
            ) : myPolicies.length === 0 ? (
              <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 flex flex-col items-center justify-center text-center">
                <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
                  <span className="material-symbols-outlined text-3xl">folder_off</span>
                </div>
                <h4 className="font-headline text-sm font-bold text-slate-800 mb-1">
                  No Policies Connected Yet
                </h4>
                <p className="font-body text-xs text-slate-500 max-w-sm leading-relaxed">
                  Use the verification form above to link your first policy and start filing claims instantly.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {myPolicies.map((p) => (
                  <div
                    key={p.policy_number}
                    className="bg-white border border-[#e2e8f0] hover:border-[#00647c]/50 rounded-2xl p-5 shadow-xs transition-all duration-200 flex flex-col justify-between group"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-xs font-bold text-[#00647c] bg-[#00647c]/10 px-2 py-0.5 rounded">
                          #{p.policy_number}
                        </span>
                        <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                          {p.policy_type?.replace("_", " ")}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 mt-2">
                        Holder: <span className="font-semibold text-slate-800">{p.policyholder_name || "Self"}</span>
                      </p>
                      <div className="text-xs text-slate-500 flex justify-between mt-2.5 pt-2.5 border-t border-slate-100">
                        <span>Coverage: ₹{p.coverage_amount?.toLocaleString("en-IN") || "N/A"}</span>
                        <span>Exp: {p.expiry_date || "Active"}</span>
                      </div>
                    </div>
                    <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-700">
                        <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Verified Active
                      </span>
                      <Link
                        href={`/claimant?policy=${p.policy_number}`}
                        className="text-xs font-semibold text-[#00647c] group-hover:text-[#004e61] flex items-center gap-1 transition-colors"
                      >
                        <span>File Claim</span>
                        <span className="material-symbols-outlined text-sm transition-transform group-hover:translate-x-0.5">
                          arrow_forward
                        </span>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

