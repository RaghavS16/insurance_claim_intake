"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AdjusterItem {
  id: string;
  name: string;
  email: string;
  specialization: string;
  claims_assigned: number;
  is_active: boolean;
}

interface PolicyItem {
  id: string;
  policy_number: string;
  policy_type: string;
  coverage_amount: number;
  deductible: number;
  effective_date: string;
  expiry_date: string;
  is_active: boolean;
  policyholder_name?: string;
  policyholder_phone_last4?: string;
  is_linked: boolean;
  customer_id?: string;
  linked_at?: string;
}

const CANONICAL_TYPES = [
  { value: "motor", label: "Motor" },
  { value: "health", label: "Health" },
  { value: "senior_health", label: "Senior Health" },
  { value: "home", label: "Home" },
  { value: "travel", label: "Travel" },
  { value: "cyber", label: "Cyber" },
];

export default function AdminDashboardPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<"policies" | "adjusters">("policies");
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Policies State
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [loadingPolicies, setLoadingPolicies] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importingCsv, setImportingCsv] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importError, setImportError] = useState("");

  // Adjusters State
  const [adjusters, setAdjusters] = useState<AdjusterItem[]>([]);
  const [loadingAdjusters, setLoadingAdjusters] = useState(false);
  const [newAdjusterName, setNewAdjusterName] = useState("");
  const [newAdjusterEmail, setNewAdjusterEmail] = useState("");
  const [newAdjusterSpec, setNewAdjusterSpec] = useState("motor");
  const [creatingAdjuster, setCreatingAdjuster] = useState(false);
  const [createdAdjusterData, setCreatedAdjusterData] = useState<any>(null);
  const [adjusterError, setAdjusterError] = useState("");
  const [copiedPass, setCopiedPass] = useState(false);

  // Authenticate Admin
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }

    const verifyAdmin = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          throw new Error("Unauthorized");
        }
        const data = await res.json();
        if (data.role !== "ADMIN") {
          router.push(data.role === "ADJUSTER" ? "/adjuster" : "/claimant");
          return;
        }
        setCurrentUser(data);
        fetchPolicies(token);
        fetchAdjusters(token);
      } catch {
        router.push("/login");
      } finally {
        setLoading(false);
      }
    };

    verifyAdmin();
  }, [router]);

  const fetchPolicies = async (token?: string) => {
    const t = token || localStorage.getItem("access_token");
    if (!t) return;
    setLoadingPolicies(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies?page=1&page_size=100`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPolicies(data.items || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingPolicies(false);
    }
  };

  const fetchAdjusters = async (token?: string) => {
    const t = token || localStorage.getItem("access_token");
    if (!t) return;
    setLoadingAdjusters(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAdjusters(data);
      }
    } catch {
      // ignore
    } finally {
      setLoadingAdjusters(false);
    }
  };

  const handleCsvUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!csvFile) return;

    setImportingCsv(true);
    setImportError("");
    setImportResult(null);

    const token = localStorage.getItem("access_token");
    const formData = new FormData();
    formData.append("file", csvFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to import CSV.");
      }

      setImportResult(data);
      setCsvFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      fetchPolicies();
    } catch (err: any) {
      setImportError(err.message || "An error occurred during CSV import.");
    } finally {
      setImportingCsv(false);
    }
  };

  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdjusterError("");
    setCreatedAdjusterData(null);
    setCopiedPass(false);

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setCreatingAdjuster(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newAdjusterName.trim(),
          email: newAdjusterEmail.trim(),
          specialization: newAdjusterSpec,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create adjuster account.");
      }

      setCreatedAdjusterData(data);
      setNewAdjusterName("");
      setNewAdjusterEmail("");
      fetchAdjusters();
    } catch (err: any) {
      setAdjusterError(err.message || "Error creating adjuster.");
    } finally {
      setCreatingAdjuster(false);
    }
  };

  const handleDownloadSampleCsv = () => {
    const csvContent =
      "policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone_last4,is_active\n" +
      "MOT-9901,motor,750000,5000,2024-01-01,2028-12-31,Vikram Patel,1988-04-12,9876,true\n" +
      "HLT-4402,health,1200000,2500,2024-06-01,2027-05-31,Ananya Sharma,1992-09-25,1234,true\n" +
      "CYB-1010,cyber,2000000,20000,2025-01-01,2026-12-31,Apex Tech,2000-01-01,0000,true\n";

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "policies_sample_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 font-sans">
        <div className="flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-sm">Verifying Administrator Access...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-cyan-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-xl shadow-lg shadow-purple-500/20">
              ⚡
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-white tracking-tight">Insurance Claims Administration</h1>
                <span className="text-[10px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-md bg-purple-950 text-purple-300 border border-purple-800">
                  Admin
                </span>
              </div>
              <p className="text-xs text-slate-400">Policy ingestion, role administration & verification controls</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden sm:flex flex-col text-right">
              <span className="text-xs font-semibold text-white">{currentUser?.full_name || "Ops Admin"}</span>
              <span className="text-[11px] text-slate-400">{currentUser?.email}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-xs font-semibold px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
            >
              Log Out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-6 md:p-8 flex flex-col gap-6">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-3 border-b border-slate-800 pb-2">
          <button
            onClick={() => setActiveTab("policies")}
            className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "policies"
                ? "bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-md shadow-cyan-950/40"
                : "text-slate-400 hover:text-white hover:bg-slate-900"
            }`}
          >
            <span>📜</span>
            <span>Policy Management & CSV Import</span>
            <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-slate-900/60">
              {policies.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("adjusters")}
            className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === "adjusters"
                ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-md shadow-purple-950/40"
                : "text-slate-400 hover:text-white hover:bg-slate-900"
            }`}
          >
            <span>👥</span>
            <span>Adjuster Accounts</span>
            <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-slate-900/60">
              {adjusters.length}
            </span>
          </button>
        </div>

        {/* Tab 1: Policy Management */}
        {activeTab === "policies" && (
          <div className="flex flex-col gap-8">
            {/* Top Import Row */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
              {/* CSV Upload Card */}
              <div className="md:col-span-8 bg-slate-900/60 border border-slate-800 rounded-3xl p-6 md:p-8 backdrop-blur-md shadow-xl flex flex-col gap-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <span>📥</span> Import Policy Data (CSV)
                    </h2>
                    <p className="text-xs text-slate-400 mt-1">
                      Bulk upload or update insurance policies. Existing claimant links will be preserved.
                    </p>
                  </div>
                  <button
                    onClick={handleDownloadSampleCsv}
                    className="text-xs font-medium px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition flex items-center gap-1.5"
                  >
                    <span>📄</span> Download Template
                  </button>
                </div>

                {importError && (
                  <div className="p-3.5 bg-rose-950/70 border border-rose-600/50 rounded-2xl text-xs text-rose-200 flex items-start gap-2">
                    <span>⚠️</span>
                    <span>{importError}</span>
                  </div>
                )}

                {importResult && (
                  <div className="p-4 bg-emerald-950/60 border border-emerald-600/40 rounded-2xl text-xs text-emerald-200 flex flex-col gap-2">
                    <div className="flex items-center gap-2 font-bold text-white">
                      <span>✓</span>
                      <span>Import Completed Successfully!</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-1">
                      <div className="p-2 bg-slate-900/80 rounded-xl">
                        <span className="text-slate-400 block text-[10px]">New Policies</span>
                        <span className="font-bold text-cyan-400 text-sm">{importResult.imported}</span>
                      </div>
                      <div className="p-2 bg-slate-900/80 rounded-xl">
                        <span className="text-slate-400 block text-[10px]">Updated Policies</span>
                        <span className="font-bold text-purple-400 text-sm">{importResult.updated}</span>
                      </div>
                      <div className="p-2 bg-slate-900/80 rounded-xl">
                        <span className="text-slate-400 block text-[10px]">Total Processed</span>
                        <span className="font-bold text-white text-sm">{importResult.total_processed}</span>
                      </div>
                    </div>
                    {importResult.errors && importResult.errors.length > 0 && (
                      <div className="mt-2 text-rose-300 text-[11px]">
                        <span className="font-bold">Errors in {importResult.errors.length} rows:</span>
                        <ul className="list-disc pl-4 mt-1">
                          {importResult.errors.slice(0, 3).map((e: any, i: number) => (
                            <li key={i}>Row {e.row}: {e.error}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                <form onSubmit={handleCsvUpload} className="flex flex-col gap-4">
                  <div className="border-2 border-dashed border-slate-800 hover:border-cyan-500/50 rounded-2xl p-6 text-center flex flex-col items-center justify-center gap-2 transition bg-slate-950/40">
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept=".csv"
                      onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                      className="hidden"
                      id="csv-file-input"
                    />
                    <label
                      htmlFor="csv-file-input"
                      className="cursor-pointer flex flex-col items-center gap-2"
                    >
                      <span className="text-3xl">📁</span>
                      <span className="text-xs font-semibold text-slate-300">
                        {csvFile ? csvFile.name : "Click to browse or drag and drop a .CSV file"}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Supported: Standard CSV with policy details and PII verification columns
                      </span>
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={!csvFile || importingCsv}
                    className="w-full p-3 rounded-2xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs shadow-md shadow-cyan-950/30 transition disabled:opacity-50"
                  >
                    {importingCsv ? "Processing CSV Import..." : "Import Policies"}
                  </button>
                </form>
              </div>

              {/* Ingestion Guidelines */}
              <div className="md:col-span-4 bg-slate-900/40 border border-slate-800/60 rounded-3xl p-6 flex flex-col gap-3 text-xs text-slate-400">
                <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                  <span>ℹ️</span> Policy Ingestion Rules
                </h3>
                <ul className="space-y-2 text-[11px] leading-relaxed">
                  <li className="flex items-start gap-2">
                    <span className="text-cyan-400">▪</span>
                    <span><strong>6 Canonical Types:</strong> <code>health</code>, <code>senior_health</code>, <code>home</code>, <code>travel</code>, <code>motor</code>, <code>cyber</code>.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-cyan-400">▪</span>
                    <span><strong>PII Columns:</strong> <code>policyholder_dob</code> (YYYY-MM-DD) and <code>policyholder_phone_last4</code> (4 digits).</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-cyan-400">▪</span>
                    <span><strong>Ownership Safety:</strong> Re-importing existing policy numbers will update coverage/dates but will <em>never</em> overwrite existing claimant ownership.</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Policies Directory Table */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-xl flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">System Policies Directory</h3>
                  <p className="text-xs text-slate-400">All registered policies and their current claimant link status</p>
                </div>
                <button
                  onClick={() => fetchPolicies()}
                  className="text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                >
                  ↻ Refresh
                </button>
              </div>

              {loadingPolicies ? (
                <div className="py-12 text-center text-xs text-slate-500 animate-pulse">Loading policy records...</div>
              ) : policies.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500">No policies in system. Upload a CSV above to get started.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-[11px] uppercase tracking-wider">
                        <th className="py-3 px-3">Policy #</th>
                        <th className="py-3 px-3">Type</th>
                        <th className="py-3 px-3">Policyholder</th>
                        <th className="py-3 px-3">Phone Last-4</th>
                        <th className="py-3 px-3">Coverage</th>
                        <th className="py-3 px-3">Expiry</th>
                        <th className="py-3 px-3">Link Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {policies.map((p) => (
                        <tr key={p.id} className="hover:bg-slate-800/30 transition">
                          <td className="py-3 px-3 font-mono font-bold text-cyan-400">{p.policy_number}</td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 text-[10px] uppercase font-bold">
                              {p.policy_type.replace("_", " ")}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-slate-200">{p.policyholder_name || "—"}</td>
                          <td className="py-3 px-3 font-mono text-slate-400">{p.policyholder_phone_last4 ? `••• ${p.policyholder_phone_last4}` : "—"}</td>
                          <td className="py-3 px-3 text-slate-300 font-mono">₹{p.coverage_amount.toLocaleString()}</td>
                          <td className="py-3 px-3 text-slate-400">{p.expiry_date}</td>
                          <td className="py-3 px-3">
                            {p.is_linked ? (
                              <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-semibold">
                                Linked
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-semibold">
                                Unlinked
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Adjuster Accounts */}
        {activeTab === "adjusters" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
            {/* Create Adjuster Form Card */}
            <div className="md:col-span-5 bg-slate-900/60 border border-slate-800 rounded-3xl p-6 md:p-8 backdrop-blur-md shadow-xl flex flex-col gap-5">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <span>➕</span> Create Adjuster Account
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Provision a claim adjuster with a specialization and secure initial credentials.
                </p>
              </div>

              {adjusterError && (
                <div className="p-3.5 bg-rose-950/70 border border-rose-600/50 rounded-2xl text-xs text-rose-200 flex items-start gap-2">
                  <span>⚠️</span>
                  <span>{adjusterError}</span>
                </div>
              )}

              {createdAdjusterData && (
                <div className="p-4 bg-emerald-950/60 border border-emerald-500/50 rounded-2xl text-xs text-emerald-200 flex flex-col gap-3">
                  <div className="flex items-center gap-2 font-bold text-white">
                    <span>✓</span>
                    <span>Adjuster Created Successfully!</span>
                  </div>
                  <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl flex flex-col gap-1.5">
                    <div className="text-[11px] text-slate-400">
                      Email: <span className="text-white font-medium">{createdAdjusterData.email}</span>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Specialization: <span className="text-cyan-300 uppercase font-bold">{createdAdjusterData.specialization}</span>
                    </div>
                    <div className="mt-1 pt-1 border-t border-slate-800/80 flex items-center justify-between">
                      <div>
                        <span className="text-[10px] text-amber-400 block">Temporary Password:</span>
                        <span className="font-mono font-bold text-amber-200 text-sm">{createdAdjusterData.temporary_password}</span>
                      </div>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(createdAdjusterData.temporary_password);
                          setCopiedPass(true);
                          setTimeout(() => setCopiedPass(false), 3000);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] transition"
                      >
                        {copiedPass ? "✓ Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <form onSubmit={handleCreateAdjuster} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">Full Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Maya Lin"
                    value={newAdjusterName}
                    onChange={(e) => setNewAdjusterName(e.target.value)}
                    required
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">Email Address</label>
                  <input
                    type="email"
                    placeholder="e.g. maya.lin@insure.co"
                    value={newAdjusterEmail}
                    onChange={(e) => setNewAdjusterEmail(e.target.value)}
                    required
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-300 px-1">Specialization</label>
                  <select
                    value={newAdjusterSpec}
                    onChange={(e) => setNewAdjusterSpec(e.target.value)}
                    className="bg-slate-950/70 border border-slate-800 rounded-2xl px-4 py-3 text-xs text-slate-100 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition"
                  >
                    {CANONICAL_TYPES.map((t) => (
                      <option key={t.value} value={t.value} className="bg-slate-900 text-slate-100">
                        {t.label} Insurance
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={creatingAdjuster}
                  className="w-full mt-2 p-3.5 rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-md shadow-purple-950/30 transition disabled:opacity-50"
                >
                  {creatingAdjuster ? "Creating Adjuster..." : "Create Adjuster"}
                </button>
              </form>
            </div>

            {/* Adjusters Directory */}
            <div className="md:col-span-7 bg-slate-900/60 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-xl flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">Adjusters Roster</h3>
                  <p className="text-xs text-slate-400">Active adjusters assigned across insurance categories</p>
                </div>
                <button
                  onClick={() => fetchAdjusters()}
                  className="text-xs font-semibold px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                >
                  ↻ Refresh
                </button>
              </div>

              {loadingAdjusters ? (
                <div className="py-12 text-center text-xs text-slate-500 animate-pulse">Loading adjusters roster...</div>
              ) : adjusters.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500">No adjusters registered yet.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-[11px] uppercase tracking-wider">
                        <th className="py-3 px-3">Name</th>
                        <th className="py-3 px-3">Email</th>
                        <th className="py-3 px-3">Specialization</th>
                        <th className="py-3 px-3">Assigned</th>
                        <th className="py-3 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {adjusters.map((a) => (
                        <tr key={a.id} className="hover:bg-slate-800/30 transition">
                          <td className="py-3 px-3 font-semibold text-white">{a.name}</td>
                          <td className="py-3 px-3 text-slate-400">{a.email}</td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded-md bg-purple-950 text-purple-300 border border-purple-800 text-[10px] uppercase font-bold">
                              {a.specialization.replace("_", " ")}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-slate-300 font-mono">{a.claims_assigned}</td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-semibold">
                              Active
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
