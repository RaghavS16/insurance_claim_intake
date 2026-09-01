import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/router";
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
  policyholder_dob?: string;
  policyholder_phone?: string;
  is_linked: boolean;
  customer_id?: string;
  linked_at?: string;
}

const SPECIALIZATION_OPTIONS = [
  { value: "motor", label: "Motor / Auto" },
  { value: "home", label: "Home / Property" },
  { value: "health", label: "Health & Medical" },
  { value: "senior_health", label: "Senior Health" },
  { value: "travel", label: "Travel & Trip" },
  { value: "cyber", label: "Cyber & Tech" },
];

export default function AdminPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<"policies" | "adjusters">("policies");
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [policySearch, setPolicySearch] = useState("");
  const [policyFilterType, setPolicyFilterType] = useState("all");
  const [policySortBy, setPolicySortBy] = useState("id");
  const [policySortOrder, setPolicySortOrder] = useState("asc");
  const [loadingPolicies, setLoadingPolicies] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importingCsv, setImportingCsv] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importError, setImportError] = useState("");

  // Policy Create Modal State
  const [showAddPolicyModal, setShowAddPolicyModal] = useState(false);
  const [newPolicyNum, setNewPolicyNum] = useState("");
  const [newPolicyType, setNewPolicyType] = useState("motor");
  const [newPolicyCov, setNewPolicyCov] = useState("100000");
  const [newPolicyDed, setNewPolicyDed] = useState("0");
  const [newPolicyEff, setNewPolicyEff] = useState("");
  const [newPolicyExp, setNewPolicyExp] = useState("");
  const [newPolicyHolder, setNewPolicyHolder] = useState("");
  const [newPolicyDob, setNewPolicyDob] = useState("");
  const [newPolicyPhone, setNewPolicyPhone] = useState("");
  const [creatingPolicy, setCreatingPolicy] = useState(false);
  const [createPolicyError, setCreatePolicyError] = useState("");

  // Policy Edit Modal State
  const [editingPolicy, setEditingPolicy] = useState<PolicyItem | null>(null);
  const [editPolicyType, setEditPolicyType] = useState("motor");
  const [editPolicyCov, setEditPolicyCov] = useState("");
  const [editPolicyDed, setEditPolicyDed] = useState("");
  const [editPolicyEff, setEditPolicyEff] = useState("");
  const [editPolicyExp, setEditPolicyExp] = useState("");
  const [editPolicyHolder, setEditPolicyHolder] = useState("");
  const [editPolicyDob, setEditPolicyDob] = useState("");
  const [editPolicyPhone, setEditPolicyPhone] = useState("");
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [editPolicyError, setEditPolicyError] = useState("");

  // Adjusters State
  const [adjusters, setAdjusters] = useState<AdjusterItem[]>([]);
  const [adjusterSearch, setAdjusterSearch] = useState("");
  const [adjusterFilterSpec, setAdjusterFilterSpec] = useState("all");
  const [adjusterSortBy, setAdjusterSortBy] = useState("name");
  const [adjusterSortOrder, setAdjusterSortOrder] = useState("asc");
  const [loadingAdjusters, setLoadingAdjusters] = useState(false);
  const [newAdjusterName, setNewAdjusterName] = useState("");
  const [newAdjusterEmail, setNewAdjusterEmail] = useState("");
  const [newAdjusterSpec, setNewAdjusterSpec] = useState("motor");
  const [creatingAdjuster, setCreatingAdjuster] = useState(false);
  const [createdAdjusterData, setCreatedAdjusterData] = useState<any>(null);
  const [adjusterError, setAdjusterError] = useState("");
  const [copiedPass, setCopiedPass] = useState(false);

  // Adjuster Edit / Actions State
  const [editingAdjuster, setEditingAdjuster] = useState<AdjusterItem | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editSpec, setEditSpec] = useState("motor");
  const [editActive, setEditActive] = useState(true);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState("");

  const [passwordResetData, setPasswordResetData] = useState<{ adjuster: AdjusterItem; tempPass: string } | null>(null);
  const [resettingPasswordId, setResettingPasswordId] = useState<string | null>(null);
  const [copiedResetPass, setCopiedResetPass] = useState(false);

  const [deletingAdjuster, setDeletingAdjuster] = useState<AdjusterItem | null>(null);
  const [deletingLoading, setDeletingLoading] = useState(false);

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
        if (!res.ok) throw new Error("Unauthorized");
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

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/login");
  };

  // CSV Import handler
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setCsvFile(e.target.files[0]);
      setImportError("");
      setImportResult(null);
    }
  };

  const handleUploadCsv = async () => {
    if (!csvFile) return;
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setImportingCsv(true);
    setImportError("");
    setImportResult(null);

    const formData = new FormData();
    formData.append("file", csvFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies/import-csv`, {
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
      fetchPolicies(token);
    } catch (err: any) {
      setImportError(err.message || "An error occurred during import.");
    } finally {
      setImportingCsv(false);
    }
  };

  // Create Single Policy
  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPolicyNum.trim()) {
      setCreatePolicyError("Policy number is required.");
      return;
    }

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setCreatingPolicy(true);
    setCreatePolicyError("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          policy_number: newPolicyNum.trim().toUpperCase(),
          policy_type: newPolicyType,
          coverage_amount: parseFloat(newPolicyCov) || 100000,
          deductible: parseFloat(newPolicyDed) || 0,
          effective_date: newPolicyEff,
          expiry_date: newPolicyExp,
          policyholder_name: newPolicyHolder.trim() || undefined,
          policyholder_dob: newPolicyDob.trim() || undefined,
          policyholder_phone: newPolicyPhone.trim() || undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create policy.");
      }

      setShowAddPolicyModal(false);
      setNewPolicyNum("");
      setNewPolicyHolder("");
      setNewPolicyPhone("");
      fetchPolicies(token);
    } catch (err: any) {
      setCreatePolicyError(err.message || "Failed to create policy.");
    } finally {
      setCreatingPolicy(false);
    }
  };

  // Open Edit Policy
  const handleOpenEditPolicy = (p: PolicyItem) => {
    setEditingPolicy(p);
    setEditPolicyType(p.policy_type || "motor");
    setEditPolicyCov(String(p.coverage_amount || ""));
    setEditPolicyDed(String(p.deductible || ""));
    setEditPolicyEff(p.effective_date || "");
    setEditPolicyExp(p.expiry_date || "");
    setEditPolicyHolder(p.policyholder_name || "");
    setEditPolicyDob(p.policyholder_dob || "");
    setEditPolicyPhone(p.policyholder_phone || "");
    setEditPolicyError("");
  };

  // Save Edit Policy
  const handleSaveEditPolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPolicy) return;
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setSavingPolicy(true);
    setEditPolicyError("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies/${editingPolicy.policy_number}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          policy_type: editPolicyType,
          coverage_amount: parseFloat(editPolicyCov) || undefined,
          deductible: parseFloat(editPolicyDed) || undefined,
          effective_date: editPolicyEff || undefined,
          expiry_date: editPolicyExp || undefined,
          policyholder_name: editPolicyHolder.trim() || undefined,
          policyholder_dob: editPolicyDob.trim() || undefined,
          policyholder_phone: editPolicyPhone.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to update policy.");
      }

      setEditingPolicy(null);
      fetchPolicies(token);
    } catch (err: any) {
      setEditPolicyError(err.message || "Failed to save policy updates.");
    } finally {
      setSavingPolicy(false);
    }
  };

  // Create Adjuster
  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAdjusterName.trim() || !newAdjusterEmail.trim()) {
      setAdjusterError("Please provide both name and email.");
      return;
    }

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setCreatingAdjuster(true);
    setAdjusterError("");
    setCreatedAdjusterData(null);
    setCopiedPass(false);

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: newAdjusterName.trim(),
          email: newAdjusterEmail.trim(),
          specialization: newAdjusterSpec,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create adjuster.");
      }

      setCreatedAdjusterData(data);
      setNewAdjusterName("");
      setNewAdjusterEmail("");
      fetchAdjusters(token);
    } catch (err: any) {
      setAdjusterError(err.message || "Failed to provision adjuster account.");
    } finally {
      setCreatingAdjuster(false);
    }
  };

  // Edit Adjuster
  const handleOpenEditAdjuster = (adj: AdjusterItem) => {
    setEditingAdjuster(adj);
    setEditName(adj.name);
    setEditEmail(adj.email);
    setEditSpec(adj.specialization || "motor");
    setEditActive(adj.is_active);
    setEditError("");
  };

  const handleSaveEditAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAdjuster) return;
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setSavingEdit(true);
    setEditError("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${editingAdjuster.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: editName.trim(),
          email: editEmail.trim(),
          specialization: editSpec,
          is_active: editActive,
        }),
      });

      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to update adjuster.");
      }

      setEditingAdjuster(null);
      fetchAdjusters(token);
    } catch (err: any) {
      setEditError(err.message || "Failed to save adjustments.");
    } finally {
      setSavingEdit(false);
    }
  };

  // Reset Password
  const handleResetPassword = async (adj: AdjusterItem) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    setResettingPasswordId(adj.id);
    setCopiedResetPass(false);

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${adj.id}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to reset password.");

      setPasswordResetData({
        adjuster: adj,
        tempPass: data.temporary_password,
      });
    } catch (err: any) {
      alert(`Password reset error: ${err.message}`);
    } finally {
      setResettingPasswordId(null);
    }
  };

  // Delete Adjuster
  const handleDeleteAdjuster = async () => {
    if (!deletingAdjuster) return;
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setDeletingLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${deletingAdjuster.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Failed to delete adjuster.");
      }
      setDeletingAdjuster(null);
      fetchAdjusters(token);
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    } finally {
      setDeletingLoading(false);
    }
  };

  // Delete Policy - removed

  const filteredPolicies = policies.filter((p) => {
    const q = policySearch.toLowerCase();
    const typeMatch = policyFilterType === "all" || p.policy_type === policyFilterType;
    const searchMatch = (
      p.policy_number?.toLowerCase().includes(q) ||
      p.policyholder_name?.toLowerCase().includes(q) ||
      p.policy_type?.toLowerCase().includes(q)
    );
    return typeMatch && searchMatch;
  }).sort((a, b) => {
    let cmp = 0;
    if (policySortBy === "id") cmp = (a.policy_number || "").localeCompare(b.policy_number || "");
    else if (policySortBy === "type") cmp = (a.policy_type || "").localeCompare(b.policy_type || "");
    else if (policySortBy === "holder") cmp = (a.policyholder_name || "").localeCompare(b.policyholder_name || "");
    else if (policySortBy === "date") cmp = (a.effective_date || "").localeCompare(b.effective_date || "");
    else if (policySortBy === "coverage") cmp = (a.coverage_amount || 0) - (b.coverage_amount || 0);
    return policySortOrder === "asc" ? cmp : -cmp;
  });

  const filteredAdjusters = adjusters.filter((a) => {
    const q = adjusterSearch.toLowerCase();
    const specMatch = adjusterFilterSpec === "all" || a.specialization === adjusterFilterSpec;
    const searchMatch = (
      a.name?.toLowerCase().includes(q) ||
      a.email?.toLowerCase().includes(q) ||
      a.specialization?.toLowerCase().includes(q)
    );
    return specMatch && searchMatch;
  }).sort((a, b) => {
    let cmp = 0;
    if (adjusterSortBy === "name") cmp = (a.name || "").localeCompare(b.name || "");
    else if (adjusterSortBy === "email") cmp = (a.email || "").localeCompare(b.email || "");
    else if (adjusterSortBy === "specialization") cmp = (a.specialization || "").localeCompare(b.specialization || "");
    else if (adjusterSortBy === "claims") cmp = (a.claims_assigned || 0) - (b.claims_assigned || 0);
    return adjusterSortOrder === "asc" ? cmp : -cmp;
  });

  return (
    <div className="bg-[#f7f9fb] font-body text-[#191c1e] min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Mobile Top App Bar */}
      <header className="md:hidden flex justify-between items-center px-4 py-3 w-full sticky top-0 bg-white border-b border-[#e0e3e5] z-50">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#00647c] text-2xl">graphic_eq</span>
          <h1 className="font-headline text-lg font-bold text-[#191c1e]">InsureClaimAI Admin</h1>
        </div>
        <button onClick={handleLogout} className="text-[#505f76] hover:text-[#ba1a1a] p-1 rounded">
          <span className="material-symbols-outlined">logout</span>
        </button>
      </header>

      {/* Side NavBar (Desktop) */}
      <aside className="hidden md:flex flex-col h-full min-h-screen py-8 px-4 w-64 fixed left-0 top-0 bg-[#f7f9fb] border-r border-[#e0e3e5] z-40">
        <div className="mb-8 px-2 flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[#b7eaff] flex items-center justify-center text-[#00647c] font-bold">
            <span className="material-symbols-outlined text-xl">admin_panel_settings</span>
          </div>
          <div>
            <h2 className="font-headline text-lg font-bold text-[#191c1e]">InsureClaimAI</h2>
            <p className="font-label text-[11px] text-[#505f76]">Admin Console</p>
          </div>
        </div>

        <nav className="flex-1 flex flex-col gap-1">
          <button
            onClick={() => setActiveTab("policies")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-label font-medium transition-colors cursor-pointer ${activeTab === "policies"
                ? "bg-[#eceef0] text-[#00647c] font-bold border-l-2 border-[#00647c]"
                : "text-[#505f76] hover:bg-[#eceef0]"
              }`}
          >
            <span
              className="material-symbols-outlined text-[20px]"
              style={{ fontVariationSettings: activeTab === "policies" ? "'FILL' 1" : "'FILL' 0" }}
            >
              policy
            </span>
            <span>Policy Management</span>
          </button>

          <button
            onClick={() => setActiveTab("adjusters")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-label font-medium transition-colors cursor-pointer ${activeTab === "adjusters"
                ? "bg-[#eceef0] text-[#00647c] font-bold border-l-2 border-[#00647c]"
                : "text-[#505f76] hover:bg-[#eceef0]"
              }`}
          >
            <span
              className="material-symbols-outlined text-[20px]"
              style={{ fontVariationSettings: activeTab === "adjusters" ? "'FILL' 1" : "'FILL' 0" }}
            >
              supervisor_account
            </span>
            <span>Adjuster Accounts</span>
          </button>
        </nav>

        <div className="mt-6 pt-4 border-t border-[#e0e3e5] flex items-center justify-between px-2">
          <div className="flex items-center gap-2 truncate">
            <div className="w-8 h-8 rounded-full bg-[#00647c] text-white flex items-center justify-center font-bold text-xs">
              A
            </div>
            <div className="flex flex-col truncate">
              <span className="font-label text-xs text-[#191c1e] font-semibold truncate">
                {currentUser?.full_name || "Admin User"}
              </span>
              <span className="font-label text-[10px] text-[#505f76]">System Administrator</span>
            </div>
          </div>
          <button onClick={handleLogout} title="Sign out" className="text-[#505f76] hover:text-[#ba1a1a] p-1 cursor-pointer">
            <span className="material-symbols-outlined text-lg">logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 md:ml-64 min-h-screen overflow-y-auto bg-white">
        {/* Top App Bar (Desktop) */}
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

        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 pb-32">
          {/* TAB 1: Policy Management */}
          {activeTab === "policies" && (
            <>
              <div>
                <h2 className="font-headline text-2xl md:text-3xl font-bold text-[#191c1e] mb-1">
                  Policy Management
                </h2>
                <p className="font-body text-sm text-[#505f76]">
                  Import, validate, and manage system-wide policy data for claimant intake verification.
                </p>
              </div>

              {/* Import Section */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* CSV Import Dropzone */}
                <div className="md:col-span-2 bg-white border-2 border-dashed border-[#bdc8ce] hover:border-[#0891B2] rounded-2xl p-6 md:p-8 flex flex-col justify-center items-center text-center transition-colors relative group shadow-sm">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleFileChange}
                    className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-10"
                  />
                  <span className="material-symbols-outlined text-4xl text-[#505f76] mb-2 group-hover:text-[#0891B2] transition-colors">
                    upload_file
                  </span>
                  <h3 className="font-headline text-base font-bold text-[#191c1e] mb-1">
                    {csvFile ? csvFile.name : "Drag and drop CSV files here"}
                  </h3>
                  <p className="font-body text-xs text-[#505f76] mb-4">
                    {csvFile
                      ? `${(csvFile.size / 1024).toFixed(1)} KB selected`
                      : "or click anywhere to browse from your computer"}
                  </p>

                  <div className="flex items-center gap-3 z-20">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="bg-[#0891B2] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-4 py-2 rounded-full transition-colors cursor-pointer shadow-sm"
                    >
                      {csvFile ? "Change File" : "Select CSV File"}
                    </button>
                    {csvFile && (
                      <button
                        type="button"
                        onClick={handleUploadCsv}
                        disabled={importingCsv}
                        className="bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-4 py-2 rounded-full transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer"
                      >
                        {importingCsv ? (
                          <>
                            <span className="material-symbols-outlined text-xs animate-spin">progress_activity</span>
                            <span>Importing...</span>
                          </>
                        ) : (
                          <>
                            <span className="material-symbols-outlined text-xs">publish</span>
                            <span>Run Ingestion</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>

                  {importResult && (
                    <div className="mt-4 p-3 bg-emerald-50 border border-emerald-300 rounded-lg text-emerald-800 text-xs flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm text-emerald-600">check_circle</span>
                      <span>
                        Successfully imported {importResult.total_processed || importResult.imported || 0} policies!
                      </span>
                    </div>
                  )}

                  {importError && (
                    <div className="mt-4 p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs flex items-center gap-2">
                      <span className="material-symbols-outlined text-sm text-[#ba1a1a]">error</span>
                      <span>{importError}</span>
                    </div>
                  )}

                  <div className="mt-4 pt-4 border-t border-[#e6e8ea] w-full flex justify-end">
                    <a
                      href="data:text/csv;charset=utf-8,policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone%0APOL-8492-AX,motor,250000,1000,2023-01-01,2026-12-31,Sarah Jenkins,1990-05-15,5550192834%0APOL-3321-HM,home,400000,2000,2023-03-01,2027-03-01,Michael Chang,1985-08-20,5558471029"
                      download="policy_template.csv"
                      className="text-[#0891B2] hover:underline font-label text-xs flex items-center gap-1 z-20"
                    >
                      <span className="material-symbols-outlined text-[16px]">download</span>
                      <span>Download Sample CSV Template</span>
                    </a>
                  </div>
                </div>

                {/* Ingestion Rules Card */}
                <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[#f2f4f6]">
                    <span className="material-symbols-outlined text-[#505f76]">rule</span>
                    <h3 className="font-headline text-base font-bold text-[#191c1e]">Ingestion Rules</h3>
                  </div>
                  <ul className="space-y-4">
                    <li className="flex items-start gap-2.5">
                      <span className="material-symbols-outlined text-[#0891B2] text-[18px] mt-0.5">
                        check_circle
                      </span>
                      <div>
                        <h4 className="font-label text-xs font-semibold text-[#191c1e]">Data Validation</h4>
                        <p className="font-body text-xs text-[#505f76] mt-0.5">
                          Dates must follow standard YYYY-MM-DD format.
                        </p>
                      </div>
                    </li>
                    <li className="flex items-start gap-2.5">
                      <span className="material-symbols-outlined text-[#0891B2] text-[18px] mt-0.5">
                        check_circle
                      </span>
                      <div>
                        <h4 className="font-label text-xs font-semibold text-[#191c1e]">Required Fields</h4>
                        <p className="font-body text-xs text-[#505f76] mt-0.5">
                          Policy Number, Type, Coverage, and Holder DOB are mandatory.
                        </p>
                      </div>
                    </li>
                    <li className="flex items-start gap-2.5">
                      <span className="material-symbols-outlined text-[#ba1a1a] text-[18px] mt-0.5">
                        error
                      </span>
                      <div>
                        <h4 className="font-label text-xs font-semibold text-[#191c1e]">Duplicate Handling</h4>
                        <p className="font-body text-xs text-[#505f76] mt-0.5">
                          Existing Policy IDs will be updated in place with new parameters.
                        </p>
                      </div>
                    </li>
                  </ul>
                </div>
              </div>

              {/* System Policies Directory Table */}
              <div className="bg-white border border-[#e0e3e5] rounded-2xl overflow-hidden shadow-sm">
                <div className="p-4 md:p-6 border-b border-[#f2f4f6] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-[#f7f9fb]">
                  <div>
                    <h3 className="font-headline text-lg font-bold text-[#191c1e]">System Policies Directory</h3>
                    <p className="font-label text-xs text-[#505f76] mt-0.5">
                      Showing {filteredPolicies.length} of {policies.length} total policies
                    </p>
                  </div>

                  <div className="flex items-center gap-3 w-full sm:w-auto">
                    <div className="relative w-full sm:w-64">
                      <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#505f76] text-[18px]">
                        search
                      </span>
                      <input
                        type="text"
                        placeholder="Search policy ID or holder..."
                        value={policySearch}
                        onChange={(e) => setPolicySearch(e.target.value)}
                        className="input-minimal w-full pl-9 pr-4 py-1.5 bg-white border border-[#e0e3e5] rounded-full font-body text-xs text-[#191c1e]"
                      />
                    </div>
                    <select
                      value={policyFilterType}
                      onChange={(e) => setPolicyFilterType(e.target.value)}
                      className="input-minimal w-full sm:w-auto bg-white border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
                    >
                      <option value="all">All Types</option>
                      {SPECIALIZATION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <select
                      value={policySortBy}
                      onChange={(e) => setPolicySortBy(e.target.value)}
                      className="input-minimal w-full sm:w-auto bg-white border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
                    >
                      <option value="id">Sort: ID</option>
                      <option value="type">Sort: Type</option>
                      <option value="holder">Sort: Holder</option>
                      <option value="date">Sort: Effective</option>
                      <option value="coverage">Sort: Coverage</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => setPolicySortOrder(policySortOrder === "asc" ? "desc" : "asc")}
                      className="w-8 h-8 flex items-center justify-center rounded-full border border-[#e0e3e5] text-[#505f76] hover:bg-[#f2f4f6] cursor-pointer shrink-0"
                      title="Toggle Sort Order"
                    >
                      <span className="material-symbols-outlined text-[18px]">
                        {policySortOrder === "asc" ? "arrow_upward" : "arrow_downward"}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowAddPolicyModal(true)}
                      className="bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-4 py-2 rounded-full transition-colors flex items-center gap-1 shadow-sm shrink-0 cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-base">add</span>
                      <span>Add Policy</span>
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse min-w-[750px]">
                    <thead>
                      <tr className="bg-[#f2f4f6] border-b border-[#e0e3e5] font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                        <th className="py-3 px-4">Policy ID</th>
                        <th className="py-3 px-4">Type</th>
                        <th className="py-3 px-4">Holder</th>
                        <th className="py-3 px-4">Holder DOB</th>
                        <th className="py-3 px-4">Phone</th>
                        <th className="py-3 px-4">Coverage</th>
                        <th className="py-3 px-4">Effective</th>
                        <th className="py-3 px-4">Expiry</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4 text-center">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#f2f4f6] font-body text-xs">
                      {loadingPolicies ? (
                        <tr>
                          <td colSpan={10} className="py-8 text-center text-[#505f76] animate-pulse">
                            Loading policies...
                          </td>
                        </tr>
                      ) : filteredPolicies.length === 0 ? (
                        <tr>
                          <td colSpan={10} className="py-8 text-center text-[#505f76]">
                            No policies found matching your search.
                          </td>
                        </tr>
                      ) : (
                        filteredPolicies.map((p) => (
                          <tr key={p.policy_number} className="hover:bg-[#f7f9fb] transition-colors">
                            <td className="py-3.5 px-4 font-mono font-bold text-[#00647c]">{p.policy_number}</td>
                            <td className="py-3.5 px-4 text-[#505f76] capitalize">{p.policy_type?.replace("_", " ")}</td>
                            <td className="py-3.5 px-4 font-medium text-[#191c1e]">{p.policyholder_name || "—"}</td>
                            <td className="py-3.5 px-4 text-[#505f76]">{p.policyholder_dob || "—"}</td>
                            <td className="py-3.5 px-4 text-[#505f76] font-mono">
                              {p.policyholder_phone || "—"}
                            </td>
                            <td className="py-3.5 px-4 font-medium text-[#191c1e]">₹{p.coverage_amount?.toLocaleString()}</td>
                            <td className="py-3.5 px-4 text-[#505f76]">{p.effective_date}</td>
                            <td className="py-3.5 px-4 text-[#505f76]">{p.expiry_date}</td>
                            <td className="py-3.5 px-4">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${p.is_active
                                    ? "bg-[#d0e1fb] text-[#54647a]"
                                    : "bg-[#ffdad6] text-[#93000a]"
                                  }`}
                              >
                                {p.is_active ? "Active" : "Inactive"}
                              </span>
                            </td>
                            <td className="py-3.5 px-4 text-center">
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  onClick={() => handleOpenEditPolicy(p)}
                                  title="Edit Policy"
                                  className="text-[#00647c] hover:text-[#007f9d] p-1 rounded hover:bg-[#eceef0] transition-colors cursor-pointer"
                                >
                                  <span className="material-symbols-outlined text-[16px]">edit</span>
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {/* TAB 2: Adjuster Administration */}
          {activeTab === "adjusters" && (
            <>
              <div>
                <h2 className="font-headline text-2xl md:text-3xl font-bold text-[#191c1e] mb-1">
                  Adjuster Administration
                </h2>
                <p className="font-body text-sm text-[#505f76]">
                  Provision new adjuster accounts and manage roster assignments.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
                {/* Left Column: Create Adjuster Form */}
                <div className="lg:col-span-1 bg-white rounded-2xl border border-[#e0e3e5] p-6 shadow-sm flex flex-col gap-4">
                  <div>
                    <h3 className="font-headline text-lg font-bold text-[#191c1e]">Create Adjuster Account</h3>
                    <p className="font-body text-xs text-[#505f76] mt-0.5">Provision new personnel to the claims roster.</p>
                  </div>

                  {adjusterError && (
                    <div className="p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs flex items-start gap-2">
                      <span className="material-symbols-outlined text-sm text-[#ba1a1a]">error</span>
                      <span>{adjusterError}</span>
                    </div>
                  )}

                  {createdAdjusterData && (
                    <div className="p-4 bg-emerald-50 border border-emerald-400 rounded-xl text-emerald-900 text-xs flex flex-col gap-2">
                      <div className="flex items-center gap-2 font-bold">
                        <span className="material-symbols-outlined text-emerald-700">check_circle</span>
                        <span>Account Provisioned!</span>
                      </div>
                      <p>
                        Email: <span className="font-mono font-bold">{createdAdjusterData.adjuster?.email}</span>
                      </p>
                      <div className="p-2 bg-emerald-100/70 rounded border border-emerald-300 font-mono text-xs flex justify-between items-center">
                        <span>Temp Pass: {createdAdjusterData.temporary_password}</span>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(createdAdjusterData.temporary_password);
                            setCopiedPass(true);
                            setTimeout(() => setCopiedPass(false), 2000);
                          }}
                          className="text-[11px] font-bold text-emerald-800 underline ml-2"
                        >
                          {copiedPass ? "Copied!" : "Copy"}
                        </button>
                      </div>
                      <span className="text-[10px] text-emerald-700">
                        Share this temporary password with the adjuster.
                      </span>
                    </div>
                  )}

                  <form onSubmit={handleCreateAdjuster} className="flex flex-col gap-4">
                    <div className="flex flex-col gap-1">
                      <label className="font-label text-xs font-medium text-[#505f76]" htmlFor="fullName">
                        Full Name *
                      </label>
                      <input
                        id="fullName"
                        type="text"
                        required
                        placeholder="Jane Doe"
                        value={newAdjusterName}
                        onChange={(e) => setNewAdjusterName(e.target.value)}
                        className="input-minimal bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                      />
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="font-label text-xs font-medium text-[#505f76]" htmlFor="emailAddress">
                        Email Address *
                      </label>
                      <input
                        id="emailAddress"
                        type="email"
                        required
                        placeholder="jane.doe@insureclaimai.com"
                        value={newAdjusterEmail}
                        onChange={(e) => setNewAdjusterEmail(e.target.value)}
                        className="input-minimal bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                      />
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="font-label text-xs font-medium text-[#505f76]" htmlFor="specialization">
                        Specialization *
                      </label>
                      <select
                        id="specialization"
                        value={newAdjusterSpec}
                        onChange={(e) => setNewAdjusterSpec(e.target.value)}
                        className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-xs text-[#191c1e] cursor-pointer"
                      >
                        {SPECIALIZATION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="pt-2">
                      <button
                        type="submit"
                        disabled={creatingAdjuster}
                        className="w-full bg-[#0891B2] hover:bg-[#007f9d] text-white font-label text-xs font-semibold py-2.5 rounded-lg flex justify-center items-center gap-1.5 transition-colors shadow-sm cursor-pointer disabled:opacity-50"
                      >
                        {creatingAdjuster ? (
                          <>
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            <span>Provisioning...</span>
                          </>
                        ) : (
                          <>
                            <span className="material-symbols-outlined text-[18px]">add_circle</span>
                            <span>Provision Account</span>
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                </div>

                {/* Right Column: Adjusters Roster Table */}
                <div className="lg:col-span-2 bg-white rounded-2xl border border-[#e0e3e5] flex flex-col shadow-sm overflow-hidden">
                  <div className="p-4 md:p-6 border-b border-[#e0e3e5] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div>
                      <h3 className="font-headline text-lg font-bold text-[#191c1e]">Adjusters Roster</h3>
                      <p className="font-label text-xs text-[#505f76]">
                        {filteredAdjusters.length} active personnel registered
                      </p>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <div className="relative w-full sm:w-56">
                        <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#505f76] text-[18px]">
                          search
                        </span>
                        <input
                          type="text"
                          placeholder="Search roster..."
                          value={adjusterSearch}
                          onChange={(e) => setAdjusterSearch(e.target.value)}
                          className="input-minimal w-full pl-9 pr-4 py-1.5 bg-[#f7f9fb] border border-[#e0e3e5] rounded-full font-body text-xs text-[#191c1e]"
                        />
                      </div>
                      <select
                        value={adjusterFilterSpec}
                        onChange={(e) => setAdjusterFilterSpec(e.target.value)}
                        className="input-minimal w-full sm:w-auto bg-[#f7f9fb] border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
                      >
                        <option value="all">All Specs</option>
                        {SPECIALIZATION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                      <select
                        value={adjusterSortBy}
                        onChange={(e) => setAdjusterSortBy(e.target.value)}
                        className="input-minimal w-full sm:w-auto bg-[#f7f9fb] border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
                      >
                        <option value="name">Sort: Name</option>
                        <option value="email">Sort: Email</option>
                        <option value="specialization">Sort: Spec</option>
                        <option value="claims">Sort: Claims</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => setAdjusterSortOrder(adjusterSortOrder === "asc" ? "desc" : "asc")}
                        className="w-8 h-8 flex items-center justify-center rounded-full border border-[#e0e3e5] text-[#505f76] hover:bg-[#eceef0] cursor-pointer shrink-0"
                        title="Toggle Sort Order"
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          {adjusterSortOrder === "asc" ? "arrow_upward" : "arrow_downward"}
                        </span>
                      </button>
                    </div>
                  </div>

                  <div className="overflow-x-auto w-full">
                    <table className="w-full text-left border-collapse min-w-[620px]">
                      <thead>
                        <tr className="bg-[#f7f9fb] border-b border-[#e0e3e5] font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
                          <th className="py-3 px-4">Name</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4">Specialization</th>
                          <th className="py-3 px-4 text-center">Active Claims</th>
                          <th className="py-3 px-4 text-center">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#e0e3e5] font-body text-xs">
                        {loadingAdjusters ? (
                          <tr>
                            <td colSpan={5} className="py-8 text-center text-[#505f76] animate-pulse">
                              Loading adjusters...
                            </td>
                          </tr>
                        ) : filteredAdjusters.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="py-8 text-center text-[#505f76]">
                              No adjusters found.
                            </td>
                          </tr>
                        ) : (
                          filteredAdjusters.map((adj) => (
                            <tr key={adj.id} className="hover:bg-[#f7f9fb] transition-colors">
                              <td className="py-3.5 px-4">
                                <div className="flex items-center gap-2.5">
                                  <div className="w-8 h-8 rounded-full bg-[#d0e1fb] text-[#54647a] flex items-center justify-center font-bold text-xs shrink-0">
                                    {adj.name?.charAt(0) || "A"}
                                  </div>
                                  <div className="flex flex-col">
                                    <span className="font-label text-xs text-[#191c1e] font-semibold">{adj.name}</span>
                                    <span className="text-[11px] text-[#505f76]">{adj.email}</span>
                                  </div>
                                </div>
                              </td>
                              <td className="py-3.5 px-4">
                                {adj.is_active ? (
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-label text-[10px] font-semibold border border-emerald-200">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse"></span>
                                    Active
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#eceef0] text-[#505f76] font-label text-[10px]">
                                    <span className="w-1.5 h-1.5 rounded-full bg-[#6e797e]"></span>
                                    Offline
                                  </span>
                                )}
                              </td>
                              <td className="py-3.5 px-4 text-[#505f76] capitalize">
                                {SPECIALIZATION_OPTIONS.find((s) => s.value === adj.specialization)?.label ||
                                  adj.specialization}
                              </td>
                              <td className="py-3.5 px-4 text-center font-semibold text-[#191c1e]">
                                {adj.claims_assigned || 0}
                              </td>
                              <td className="py-3.5 px-4 text-center">
                                <div className="flex items-center justify-center gap-1">
                                  <button
                                    onClick={() => handleOpenEditAdjuster(adj)}
                                    title="Edit Adjuster"
                                    className="text-[#505f76] hover:text-[#00647c] p-1.5 rounded hover:bg-[#eceef0] transition-colors cursor-pointer"
                                  >
                                    <span className="material-symbols-outlined text-[17px]">edit</span>
                                  </button>
                                  <button
                                    onClick={() => handleResetPassword(adj)}
                                    disabled={resettingPasswordId === adj.id}
                                    title="Reset Password"
                                    className="text-[#505f76] hover:text-[#0891B2] p-1.5 rounded hover:bg-[#eceef0] transition-colors cursor-pointer"
                                  >
                                    <span className="material-symbols-outlined text-[17px]">key</span>
                                  </button>
                                  <button
                                    onClick={() => setDeletingAdjuster(adj)}
                                    title="Delete Adjuster"
                                    className="text-[#505f76] hover:text-[#ba1a1a] p-1.5 rounded hover:bg-[#eceef0] transition-colors cursor-pointer"
                                  >
                                    <span className="material-symbols-outlined text-[17px]">delete</span>
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="p-3 border-t border-[#e0e3e5] bg-white text-center">
                    <span className="text-[11px] text-[#505f76]">
                      Showing {filteredAdjusters.length} of {adjusters.length} adjusters
                    </span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>

      {/* Edit Adjuster Modal */}
      {editingAdjuster && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">Edit Adjuster</h3>
            <p className="font-body text-xs text-[#505f76] mb-4">Modify personnel profile and status.</p>

            {editError && (
              <div className="mb-4 p-3 bg-[#ffdad6] text-[#93000a] text-xs rounded-lg">{editError}</div>
            )}

            <form onSubmit={handleSaveEditAdjuster} className="space-y-4">
              <div>
                <label className="font-label text-xs text-[#505f76] block mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                />
              </div>

              <div>
                <label className="font-label text-xs text-[#505f76] block mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                />
              </div>

              <div>
                <label className="font-label text-xs text-[#505f76] block mb-1">Specialization</label>
                <select
                  value={editSpec}
                  onChange={(e) => setEditSpec(e.target.value)}
                  className="w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3 py-2 text-xs text-[#191c1e]"
                >
                  {SPECIALIZATION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="activeCheck"
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                  className="rounded text-[#0891B2] focus:ring-[#0891B2]"
                />
                <label htmlFor="activeCheck" className="font-body text-xs text-[#191c1e] cursor-pointer">
                  Account is Active
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#e0e3e5]">
                <button
                  type="button"
                  onClick={() => setEditingAdjuster(null)}
                  className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="px-4 py-2 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {savingEdit ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Password Reset Modal */}
      {passwordResetData && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-2 text-emerald-700 font-bold mb-2">
              <span className="material-symbols-outlined">key</span>
              <h3 className="font-headline text-lg">Password Reset Successfully</h3>
            </div>
            <p className="font-body text-xs text-[#505f76] mb-4">
              A temporary password has been generated for{" "}
              <span className="font-semibold text-[#191c1e]">{passwordResetData.adjuster.name}</span>.
            </p>

            <div className="p-3 bg-[#F1F5F9] rounded-xl border border-[#bdc8ce] font-mono text-xs flex justify-between items-center mb-4">
              <span>{passwordResetData.tempPass}</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(passwordResetData.tempPass);
                  setCopiedResetPass(true);
                  setTimeout(() => setCopiedResetPass(false), 2000);
                }}
                className="text-xs font-bold text-[#0891B2] underline ml-2 cursor-pointer"
              >
                {copiedResetPass ? "Copied!" : "Copy"}
              </button>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setPasswordResetData(null)}
                className="px-4 py-2 rounded-lg bg-[#00647c] text-white text-xs font-semibold cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Adjuster Modal */}
      {deletingAdjuster && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="font-headline text-lg font-bold text-[#ba1a1a] mb-2">Confirm Delete</h3>
            <p className="font-body text-xs text-[#505f76] mb-4">
              Are you sure you want to permanently remove adjuster account{" "}
              <span className="font-semibold text-[#191c1e]">{deletingAdjuster.name}</span> ({deletingAdjuster.email})?
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeletingAdjuster(null)}
                className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteAdjuster}
                disabled={deletingLoading}
                className="px-4 py-2 rounded-lg bg-[#ba1a1a] hover:bg-[#93000a] text-white text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
              >
                {deletingLoading ? "Deleting..." : "Delete Adjuster"}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Add Policy Modal */}
      {showAddPolicyModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">Add New Policy</h3>
            <p className="font-body text-xs text-[#505f76] mb-4">Register a new insurance policy in the system database.</p>

            {createPolicyError && (
              <div className="mb-4 p-3 bg-[#ffdad6] text-[#93000a] text-xs rounded-lg">{createPolicyError}</div>
            )}

            <form onSubmit={handleCreatePolicy} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Policy Number *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. MOT-5521"
                    value={newPolicyNum}
                    onChange={(e) => setNewPolicyNum(e.target.value.toUpperCase())}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs font-mono uppercase text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Policy Type *</label>
                  <select
                    value={newPolicyType}
                    onChange={(e) => setNewPolicyType(e.target.value)}
                    className="w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3 py-2 text-xs text-[#191c1e]"
                  >
                    {SPECIALIZATION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Policyholder Full Name</label>
                  <input
                    type="text"
                    placeholder="e.g. John Doe"
                    value={newPolicyHolder}
                    onChange={(e) => setNewPolicyHolder(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Mobile Number</label>
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="e.g. 5551234567"
                    value={newPolicyPhone}
                    onChange={(e) => setNewPolicyPhone(e.target.value.replace(/\D/g, ""))}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs font-mono text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Coverage Limit (₹) *</label>
                  <input
                    type="number"
                    required
                    min="1"
                    value={newPolicyCov}
                    onChange={(e) => setNewPolicyCov(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Deductible (₹) *</label>
                  <input
                    type="number"
                    required
                    min="0"
                    value={newPolicyDed}
                    onChange={(e) => setNewPolicyDed(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Holder DOB</label>
                  <input
                    type="date"
                    value={newPolicyDob}
                    onChange={(e) => setNewPolicyDob(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Effective Date *</label>
                  <input
                    type="date"
                    required
                    value={newPolicyEff}
                    onChange={(e) => setNewPolicyEff(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Expiry Date *</label>
                  <input
                    type="date"
                    required
                    value={newPolicyExp}
                    onChange={(e) => setNewPolicyExp(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#e0e3e5]">
                <button
                  type="button"
                  onClick={() => setShowAddPolicyModal(false)}
                  className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingPolicy}
                  className="px-4 py-2 rounded-lg bg-[#00647c] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {creatingPolicy ? "Creating..." : "Save Policy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Policy Modal */}
      {editingPolicy && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">
              Edit Policy <span className="font-mono text-[#00647c]">{editingPolicy.policy_number}</span>
            </h3>
            <p className="font-body text-xs text-[#505f76] mb-4">Modify coverage, dates, policyholder info, and status.</p>

            {editPolicyError && (
              <div className="mb-4 p-3 bg-[#ffdad6] text-[#93000a] text-xs rounded-lg">{editPolicyError}</div>
            )}

            <form onSubmit={handleSaveEditPolicy} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Policy Type</label>
                  <select
                    value={editPolicyType}
                    onChange={(e) => setEditPolicyType(e.target.value)}
                    className="w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3 py-2 text-xs text-[#191c1e]"
                  >
                    {SPECIALIZATION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Mobile Number</label>
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="e.g. 5551234567"
                    value={editPolicyPhone}
                    onChange={(e) => setEditPolicyPhone(e.target.value.replace(/\D/g, ""))}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs font-mono text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Policyholder Full Name</label>
                  <input
                    type="text"
                    placeholder="e.g. John Doe"
                    value={editPolicyHolder}
                    onChange={(e) => setEditPolicyHolder(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Holder Date of Birth</label>
                  <input
                    type="date"
                    value={editPolicyDob}
                    onChange={(e) => setEditPolicyDob(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Coverage Limit (₹)</label>
                  <input
                    type="number"
                    min="1"
                    value={editPolicyCov}
                    onChange={(e) => setEditPolicyCov(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Deductible (₹)</label>
                  <input
                    type="number"
                    min="0"
                    value={editPolicyDed}
                    onChange={(e) => setEditPolicyDed(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Effective Date</label>
                  <input
                    type="date"
                    value={editPolicyEff}
                    onChange={(e) => setEditPolicyEff(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
                <div>
                  <label className="font-label text-xs text-[#505f76] block mb-1">Expiry Date</label>
                  <input
                    type="date"
                    value={editPolicyExp}
                    onChange={(e) => setEditPolicyExp(e.target.value)}
                    className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#e0e3e5]">
                <button
                  type="button"
                  onClick={() => setEditingPolicy(null)}
                  className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingPolicy}
                  className="px-4 py-2 rounded-lg bg-[#00647c] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {savingPolicy ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
