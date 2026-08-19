"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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

function LinkPolicyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [policyNumber, setPolicyNumber] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phoneLast4, setPhoneLast4] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState<any>(null);

  const [myPolicies, setMyPolicies] = useState<LinkedPolicy[]>([]);
  const [loadingPolicies, setLoadingPolicies] = useState(true);

  // Initialize from search param if available
  useEffect(() => {
    const pParam = searchParams.get("policy");
    if (pParam) {
      setPolicyNumber(pParam.toUpperCase());
    }
  }, [searchParams]);

  // Fetch current user's linked policies
  const fetchMyPolicies = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/v1/policies/my-policies`, {
        headers: { Authorization: `Bearer ${token}` },
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

  useEffect(() => {
    fetchMyPolicies();
  }, []);

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

    if (!policyNumber.trim() || !dateOfBirth.trim() || phoneLast4.length !== 4) {
      setError("Please fill in all fields with valid information (4 digits for phone).");
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
          date_of_birth: dateOfBirth.trim(),
          phone_last4: phoneLast4.trim(),
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || "Unable to link policy. Please verify your details.");
      }

      setSuccessData(data);
      fetchMyPolicies();
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans p-4 md:p-8 selection:bg-cyan-500 selection:text-white">
      <div className="max-w-4xl mx-auto flex flex-col gap-8">
        {/* Navigation Header */}
        <header className="flex items-center justify-between border-b border-slate-800/80 pb-5">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-xl shadow-lg shadow-cyan-500/20">
              🛡️
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">Policy Link Verification</h1>
              <p className="text-xs text-slate-400">Securely link your policy before filing insurance claims</p>
            </div>
          </div>
          <Link
            href="/claimant"
            className="text-xs font-semibold px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition"
          >
            ← Back to Dashboard
          </Link>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
          {/* Main Link Policy Form Card */}
          <div className="md:col-span-7 bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 md:p-8 backdrop-blur-md shadow-2xl flex flex-col gap-6">
            <div>
              <h2 className="text-lg font-bold text-white">Link Insurance Policy</h2>
              <p className="text-xs text-slate-400 mt-1">
                Enter your policy number and verify ownership using the policyholder date of birth and registered phone number.
              </p>
            </div>

            {error && (
              <div className="p-4 bg-rose-950/70 border border-rose-600/50 rounded-2xl text-xs text-rose-200 leading-normal flex items-start gap-2.5">
                <span className="text-base">⚠️</span>
                <div>
                  <p className="font-semibold">Verification Failed</p>
                  <p className="mt-0.5">{error}</p>
                </div>
              </div>
            )}

            {successData ? (
              <div className="p-6 bg-cyan-950/40 border border-cyan-500/40 rounded-2xl text-xs text-cyan-200 flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-lg">
                    ✓
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">
                      {successData.already_linked ? "Policy Already Linked" : "Policy Successfully Linked!"}
                    </h3>
                    <p className="text-cyan-300/80 text-xs">
                      Policy <span className="font-mono font-bold text-white">{successData.policy_number}</span> is verified and ready for claims intake.
                    </p>
                  </div>
                </div>

                <div className="pt-2 flex items-center gap-3">
                  <Link
                    href="/claimant"
                    className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-center text-xs shadow-md transition"
                  >
                    File a Claim Now
                  </Link>
                  <button
                    onClick={() => {
                      setSuccessData(null);
                      setPolicyNumber("");
                      setDateOfBirth("");
                      setPhoneLast4("");
                    }}
                    className="py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
                  >
                    Link Another Policy
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">
                    Policy Number <span className="text-cyan-400">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. MOT-5521 or XYZ123"
                    value={policyNumber}
                    onChange={(e) => setPolicyNumber(e.target.value.toUpperCase())}
                    required
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 font-mono tracking-wider transition"
                  />
                  <span className="text-[11px] text-slate-500 px-1">Found on your policy schedule or insurance card</span>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">
                    Policyholder Date of Birth <span className="text-cyan-400">*</span>
                  </label>
                  <input
                    type="date"
                    value={dateOfBirth}
                    onChange={(e) => setDateOfBirth(e.target.value)}
                    required
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition [color-scheme:dark]"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">
                    Last 4 Digits of Registered Phone <span className="text-cyan-400">*</span>
                  </label>
                  <input
                    type="text"
                    maxLength={4}
                    placeholder="e.g. 1234"
                    value={phoneLast4}
                    onChange={handlePhoneChange}
                    required
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 font-mono tracking-widest transition"
                  />
                  <span className="text-[11px] text-slate-500 px-1">4 digits only for identity verification</span>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full mt-3 p-3.5 rounded-2xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs shadow-md shadow-cyan-950/30 active:scale-95 transition disabled:opacity-50"
                >
                  {loading ? "Verifying Policy Details..." : "Verify & Link Policy"}
                </button>
              </form>
            )}
          </div>

          {/* Side Panel: Linked Policies Directory */}
          <div className="md:col-span-5 flex flex-col gap-6">
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md shadow-xl flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <span>📑</span>
                  <span>My Linked Policies</span>
                </h3>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                  {myPolicies.length} Active
                </span>
              </div>

              {loadingPolicies ? (
                <div className="py-8 text-center text-xs text-slate-500 animate-pulse">Loading policies...</div>
              ) : myPolicies.length === 0 ? (
                <div className="p-5 border border-dashed border-slate-800 rounded-2xl text-center flex flex-col gap-2">
                  <p className="text-xs text-slate-400 font-medium">No policies linked yet.</p>
                  <p className="text-[11px] text-slate-500">
                    Use the form on the left to link your existing policies to file claims smoothly.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3 max-h-96 overflow-y-auto pr-1">
                  {myPolicies.map((p) => (
                    <div
                      key={p.policy_number}
                      className="p-3.5 bg-slate-950/70 border border-slate-800 rounded-2xl flex flex-col gap-2 hover:border-slate-700 transition"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold text-xs text-cyan-400">{p.policy_number}</span>
                        <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-slate-800 text-slate-300">
                          {p.policy_type.replace("_", " ")}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400 flex justify-between">
                        <span>Coverage: ₹{p.coverage_amount.toLocaleString()}</span>
                        <span>Exp: {p.expiry_date}</span>
                      </div>
                      {p.policyholder_name && (
                        <div className="text-[10px] text-slate-500">
                          Policyholder: <span className="text-slate-300">{p.policyholder_name}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Help / FAQ Card */}
            <div className="bg-slate-900/40 border border-slate-800/60 rounded-3xl p-5 text-xs text-slate-400 flex flex-col gap-2.5">
              <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                <span>💡</span> Why do I need to link my policy?
              </h4>
              <p className="text-[11px] leading-relaxed text-slate-400">
                To protect customer confidentiality and prevent unauthorized claims, every policy must be linked to your claimant account via date of birth and registered contact verification.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LinkPolicyPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950 text-slate-400 p-8">Loading...</div>}>
      <LinkPolicyContent />
    </Suspense>
  );
}
