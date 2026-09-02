import React, { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

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
  const [policyNumber, setPolicyNumber] = useState("");
  const [policyholderName, setPolicyholderName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phoneLast4, setPhoneLast4] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState<any>(null);

  const [myPolicies, setMyPolicies] = useState<LinkedPolicy[]>([]);
  const [loadingPolicies, setLoadingPolicies] = useState(true);

  // Initialize from query param if available
  useEffect(() => {
    if (policy && typeof policy === "string") {
      setPolicyNumber(policy.toUpperCase());
    }
  }, [policy]);

  // Authenticate user & load policies
  useEffect(() => {
    const token = localStorage.getItem("access_token");
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
        setCurrentUser(data);
        fetchMyPolicies(token);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        router.push("/login");
      });
  }, [router]);

  const fetchMyPolicies = async (token?: string) => {
    const t = token || localStorage.getItem("access_token");
    if (!t) return;

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

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.replace(/\D/g, "").slice(0, 4);
    setPhoneLast4(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessData(null);

    const token = localStorage.getItem("access_token");
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
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  return (
    <div className="bg-[#f7f9fb] text-[#191c1e] font-body antialiased min-h-screen flex selection:bg-[#b7eaff] selection:text-[#001f28]">
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
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#505f76] hover:bg-[#eceef0] transition-all duration-200 group"
          >
            <span className="material-symbols-outlined text-[20px] group-hover:text-[#00647c] transition-colors">
              dashboard
            </span>
            <span className="font-label text-xs font-medium">Active Intake</span>
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
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#00647c] font-bold bg-[#eceef0] transition-all duration-200 group relative"
          >
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-4 bg-[#00647c] rounded-r-full"></div>
            <span className="material-symbols-outlined fill text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>
              settings
            </span>
            <span className="font-label text-xs font-semibold">Link Policy</span>
          </Link>
        </div>

        {/* User Card in Nav */}
        <div className="mt-auto px-2 pt-6 border-t border-[#e0e3e5] flex items-center justify-between">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-9 h-9 rounded-full bg-[#d0e1fb] text-[#54647a] flex items-center justify-center font-bold text-xs shrink-0">
              {currentUser?.full_name?.charAt(0) || "U"}
            </div>
            <div className="flex flex-col truncate">
              <span className="font-label text-xs text-[#191c1e] font-semibold truncate">
                {currentUser?.full_name || "User"}
              </span>
              <span className="text-[10px] text-[#505f76] capitalize">{currentUser?.role?.toLowerCase() || "Claimant"}</span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded-md hover:bg-[#eceef0] transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-lg">logout</span>
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 md:ml-64 w-full relative pb-24 md:pb-8 bg-white min-h-screen">
        {/* Top App Bar */}
        <header className="w-full top-0 sticky bg-white/90 backdrop-blur-md border-b border-[#e0e3e5] z-30 px-6 py-4 flex justify-between items-center max-w-7xl mx-auto">
          <div className="md:hidden flex items-center gap-2">
            <span className="material-symbols-outlined text-[#00647c] text-2xl">waves</span>
            <h1 className="font-headline text-lg font-bold text-[#191c1e] tracking-tight">InsureClaimAI</h1>
          </div>

          <div className="hidden md:flex flex-1 items-center gap-2 text-[#505f76]">
            <Link href="/claimant" className="font-label text-xs hover:text-[#00647c] transition-colors">
              Claimant Portal
            </Link>
            <span className="material-symbols-outlined text-xs">chevron_right</span>
            <span className="font-label text-xs text-[#191c1e] font-semibold">Link Policy</span>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/claimant"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#f7f9fb] hover:bg-[#eceef0] border border-[#bdc8ce] text-[#505f76] hover:text-[#00647c] transition-colors flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-sm">arrow_back</span>
              <span>Back to Intake</span>
            </Link>
          </div>
        </header>

        {/* Page Canvas */}
        <div className="px-6 md:px-12 max-w-7xl mx-auto py-8">
          <div className="mb-8">
            <h2 className="font-headline text-2xl md:text-3xl font-bold text-[#191c1e] mb-1.5">Verify Your Coverage</h2>
            <p className="font-body text-sm text-[#505f76] max-w-2xl leading-relaxed">
              Connect your existing policy to manage claims, view documents, and access intelligent voice assistance seamlessly.
            </p>
          </div>

          {/* Main Layout Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left Column: Verification Form */}
            <div className="lg:col-span-7 space-y-6">
              <div className="bg-white border border-[#bdc8ce] rounded-2xl p-6 md:p-8 shadow-sm">
                {error && (
                  <div className="mb-5 p-3.5 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-xs text-[#93000a] flex items-start gap-2">
                    <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
                    <div>
                      <p className="font-semibold">Verification Failed</p>
                      <p className="mt-0.5">{error}</p>
                    </div>
                  </div>
                )}

                {successData ? (
                  <div className="p-6 bg-[#F1F5F9] border border-[#0891B2]/40 rounded-xl text-xs text-[#191c1e] flex flex-col gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[#0891B2]/10 text-[#0891B2] flex items-center justify-center text-xl shrink-0">
                        <span className="material-symbols-outlined fill" style={{ fontVariationSettings: "'FILL' 1" }}>verified</span>
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-[#191c1e]">
                          {successData.already_linked ? "Policy Already Linked" : "Policy Successfully Linked!"}
                        </h3>
                        <p className="text-[#505f76] text-xs mt-0.5">
                          Policy <span className="font-mono font-bold text-[#00647c]">{successData.policy_number}</span> {successData.policyholder_name ? `(${successData.policyholder_name})` : ""} is verified and ready for claims intake.
                        </p>
                      </div>
                    </div>

                    <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                      <Link
                        href={`/claimant?policy=${successData.policy_number}`}
                        className="w-full sm:flex-1 py-2.5 px-4 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white font-label font-semibold text-center text-xs shadow-sm transition-colors"
                      >
                        Start Voice Claim Intake
                      </Link>
                      <button
                        onClick={() => {
                          setSuccessData(null);
                          setPolicyNumber("");
                          setPolicyholderName("");
                          setDateOfBirth("");
                          setPhoneLast4("");
                        }}
                        className="w-full sm:w-auto py-2.5 px-4 rounded-lg bg-white border border-[#bdc8ce] text-[#505f76] hover:text-[#191c1e] text-xs font-semibold transition-colors cursor-pointer"
                      >
                        Link Another
                      </button>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-5" id="policy-link-form">
                    <div>
                      <label className="font-label text-xs font-medium text-[#505f76] block mb-1.5" htmlFor="policy-number">
                        Policy Number *
                      </label>
                      <div className="relative">
                        <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[#505f76] text-[20px]">
                          badge
                        </span>
                        <input
                          id="policy-number"
                          type="text"
                          required
                          placeholder="e.g. POL-8492-AX or MOT-5521"
                          value={policyNumber}
                          onChange={(e) => setPolicyNumber(e.target.value.toUpperCase())}
                          className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg py-2.5 pl-[42px] pr-3.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e] font-mono uppercase tracking-wide"
                        />
                      </div>
                      <span className="text-[11px] text-[#505f76] mt-1 block">Found on your policy schedule or insurance document</span>
                    </div>

                    <div>
                      <label className="font-label text-xs font-medium text-[#505f76] block mb-1.5" htmlFor="policyholder-name">
                        Policyholder Full Name *
                      </label>
                      <div className="relative">
                        <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[#505f76] text-[20px]">
                          person
                        </span>
                        <input
                          id="policyholder-name"
                          type="text"
                          required
                          placeholder="e.g. John Doe or Sarah Jenkins"
                          value={policyholderName}
                          onChange={(e) => setPolicyholderName(e.target.value)}
                          className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg py-2.5 pl-[42px] pr-3.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
                        />
                      </div>
                      <span className="text-[11px] text-[#505f76] mt-1 block">Must match the registered policyholder name</span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="font-label text-xs font-medium text-[#505f76] block mb-1.5" htmlFor="dob">
                          Policyholder Date of Birth *
                        </label>
                        <div className="relative">
                          <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[#505f76] text-[20px]">
                            calendar_month
                          </span>
                          <input
                            id="dob"
                            type="date"
                            required
                            value={dateOfBirth}
                            onChange={(e) => setDateOfBirth(e.target.value)}
                            className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg py-2.5 pl-[42px] pr-3.5 font-body text-sm text-[#191c1e]"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="font-label text-xs font-medium text-[#505f76] block mb-1.5" htmlFor="phone-last-4">
                          Phone Number (Last 4 Digits) *
                        </label>
                        <div className="relative">
                          <span className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[#505f76] text-[20px]">
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
                            className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg py-2.5 pl-[42px] pr-3.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e] font-mono tracking-widest"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 flex items-center justify-between">
                      <span className="font-label text-xs text-[#505f76] flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[15px] text-[#00647c]">lock</span> Secure 256-bit Verification
                      </span>
                      <button
                        type="submit"
                        disabled={loading}
                        className="bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-5 py-2.5 rounded-lg transition-colors flex items-center gap-2 shadow-sm disabled:opacity-50 cursor-pointer"
                      >
                        {loading ? (
                          <>
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            <span>Verifying...</span>
                          </>
                        ) : (
                          <>
                            <span>Verify & Link Policy</span>
                            <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>

            {/* Right Column: Info Panel */}
            <div className="lg:col-span-5">
              <div className="bg-[#f2f4f6] border border-[#e0e3e5] rounded-2xl p-6 md:p-8 h-full flex flex-col justify-center">
                <div className="w-12 h-12 rounded-full bg-[#d0e1fb] flex items-center justify-center mb-4 text-[#0891B2]">
                  <span className="material-symbols-outlined text-[24px]">verified_user</span>
                </div>
                <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-2">Why Do I Need to Link My Policy?</h3>
                <p className="font-body text-sm text-[#505f76] mb-4 leading-relaxed">
                  Linking authenticates your identity and ensures your sensitive claim data remains strictly confidential. Once verified, you will unlock full access to:
                </p>
                <ul className="space-y-3">
                  <li className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-[#00647c] text-[18px] mt-0.5">check_circle</span>
                    <span className="font-body text-xs text-[#3e484d] leading-normal">Real-time claim status tracking and auto-routing</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-[#00647c] text-[18px] mt-0.5">check_circle</span>
                    <span className="font-body text-xs text-[#3e484d] leading-normal">Instant digital document verification and deductible calculation</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="material-symbols-outlined text-[#00647c] text-[18px] mt-0.5">check_circle</span>
                    <span className="font-body text-xs text-[#3e484d] leading-normal">Personalized AI voice assistance with seamless incident extraction</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Below Form: My Linked Policies */}
          <div className="mt-12 pt-8 border-t border-[#e0e3e5]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-headline text-xl font-bold text-[#191c1e]">My Linked Policies</h3>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#d0e1fb] text-[#54647a]">
                {myPolicies.length} {myPolicies.length === 1 ? "Policy" : "Policies"} Connected
              </span>
            </div>

            {loadingPolicies ? (
              <div className="p-8 text-center text-xs text-[#505f76] animate-pulse">Loading linked policies...</div>
            ) : myPolicies.length === 0 ? (
              <div className="bg-[#f7f9fb] border border-dashed border-[#bdc8ce] rounded-2xl p-12 flex flex-col items-center justify-center text-center">
                <div className="w-20 h-20 mb-4 relative">
                  <div className="absolute inset-0 bg-[#d0e1fb]/50 rounded-full animate-pulse opacity-60"></div>
                  <div className="absolute inset-1.5 bg-white rounded-full shadow-sm flex items-center justify-center border border-[#e0e3e5]">
                    <span className="material-symbols-outlined text-[#505f76] text-[28px]">folder_off</span>
                  </div>
                </div>
                <h4 className="font-headline text-lg font-bold text-[#191c1e] mb-1">No Policies Linked Yet</h4>
                <p className="font-body text-xs text-[#505f76] max-w-sm leading-relaxed">
                  Use the secure form above to link your first InsureClaimAI policy and unlock your digital voice intake experience.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {myPolicies.map((p) => (
                  <div
                    key={p.policy_number}
                    className="bg-white border border-[#bdc8ce] rounded-xl p-5 shadow-sm hover:border-[#0891B2] transition-colors flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-sm font-bold text-[#00647c]">{p.policy_number}</span>
                        <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-[#d0e1fb] text-[#54647a]">
                          {p.policy_type?.replace("_", " ")}
                        </span>
                      </div>
                      <p className="text-xs text-[#505f76] mb-1">
                        Holder: <span className="font-medium text-[#191c1e]">{p.policyholder_name || "Self"}</span>
                      </p>
                      <div className="text-xs text-[#505f76] flex justify-between mt-2 pt-2 border-t border-[#f2f4f6]">
                        <span>Coverage: ₹{p.coverage_amount?.toLocaleString()}</span>
                        <span>Exp: {p.expiry_date}</span>
                      </div>
                    </div>
                    <div className="mt-4 pt-3 border-t border-[#e0e3e5] flex items-center justify-between">
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span> Verified Active
                      </span>
                      <Link
                        href={`/claimant?policy=${p.policy_number}`}
                        className="text-xs font-semibold text-[#0891B2] hover:underline flex items-center gap-0.5"
                      >
                        <span>File Claim</span>
                        <span className="material-symbols-outlined text-sm">arrow_forward</span>
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
