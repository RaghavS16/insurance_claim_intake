import React, { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/router";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { AdminTopBar } from "@/components/admin/AdminTopBar";
import { CsvDropzone } from "@/components/admin/CsvDropzone";
import { AdminPolicyTable, PolicyItem } from "@/components/admin/AdminPolicyTable";
import { CreateAdjusterCard } from "@/components/admin/CreateAdjusterCard";
import { AdjustersRosterTable, AdjusterItem } from "@/components/admin/AdjustersRosterTable";
import {
  AddPolicyModal,
  EditPolicyModal,
  EditAdjusterModal,
  PasswordResetModal,
  DeleteAdjusterModal,
} from "@/components/admin/AdminModals";
import { getAuthToken, clearAuthToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<"policies" | "adjusters">("policies");
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Policies State
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
  const [newAdjusterPhone, setNewAdjusterPhone] = useState("");
  const [newAdjusterSpec, setNewAdjusterSpec] = useState("motor");
  const [creatingAdjuster, setCreatingAdjuster] = useState(false);
  const [createdAdjusterData, setCreatedAdjusterData] = useState<any>(null);
  const [adjusterError, setAdjusterError] = useState("");
  const [copiedPass, setCopiedPass] = useState(false);

  // Adjuster Edit / Actions State
  const [editingAdjuster, setEditingAdjuster] = useState<AdjusterItem | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
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
    const token = getAuthToken();
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
        clearAuthToken();
        router.push("/login");
      } finally {
        setLoading(false);
      }
    };

    verifyAdmin();
  }, [router]);

  const fetchPolicies = async (token: string) => {
    setLoadingPolicies(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies?page_size=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPolicies(Array.isArray(data) ? data : data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch policies", err);
    } finally {
      setLoadingPolicies(false);
    }
  };

  const fetchAdjusters = async (token: string) => {
    setLoadingAdjusters(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAdjusters(Array.isArray(data) ? data : data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch adjusters", err);
    } finally {
      setLoadingAdjusters(false);
    }
  };

  const handleLogout = async () => {
    const token = getAuthToken();
    if (token) {
      try {
        await fetch(`${API_BASE}/api/v1/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {}
    }
    clearAuthToken();
    router.push("/login");
  };

  // CSV Ingestion
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setCsvFile(e.target.files[0]);
      setImportError("");
      setImportResult(null);
    }
  };

  const handleUploadCsv = async () => {
    if (!csvFile) return;
    const token = getAuthToken();
    if (!token) return;

    setImportingCsv(true);
    setImportError("");
    setImportResult(null);

    const formData = new FormData();
    formData.append("file", csvFile);

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/policies/bulk-import-csv`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to ingest CSV");
      }
      setImportResult(data);
      setCsvFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      fetchPolicies(token);
    } catch (err: any) {
      setImportError(err.message || "An error occurred during CSV ingestion");
    } finally {
      setImportingCsv(false);
    }
  };

  // Create Policy Handler
  const handleOpenCreatePolicy = () => {
    setNewPolicyNum("");
    setNewPolicyType("motor");
    setNewPolicyCov("100000");
    setNewPolicyDed("0");
    setNewPolicyEff(new Date().toISOString().split("T")[0]);
    const expDate = new Date();
    expDate.setFullYear(expDate.getFullYear() + 1);
    setNewPolicyExp(expDate.toISOString().split("T")[0]);
    setNewPolicyHolder("");
    setNewPolicyDob("");
    setNewPolicyPhone("");
    setCreatePolicyError("");
    setShowAddPolicyModal(true);
  };

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;

    setCreatingPolicy(true);
    setCreatePolicyError("");

    try {
      const payload: any = {
        policy_number: newPolicyNum.trim().toUpperCase(),
        policy_type: newPolicyType,
        coverage_amount: parseFloat(newPolicyCov),
        deductible: parseFloat(newPolicyDed),
        effective_date: newPolicyEff,
        expiry_date: newPolicyExp,
        is_active: true,
      };
      if (newPolicyHolder.trim()) payload.policyholder_name = newPolicyHolder.trim();
      if (newPolicyDob.trim()) payload.policyholder_dob = newPolicyDob.trim();
      if (newPolicyPhone.trim()) payload.policyholder_phone = newPolicyPhone.trim();

      const res = await fetch(`${API_BASE}/api/v1/admin/policies`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create policy");
      }
      setShowAddPolicyModal(false);
      fetchPolicies(token);
    } catch (err: any) {
      setCreatePolicyError(err.message || "Error creating policy");
    } finally {
      setCreatingPolicy(false);
    }
  };

  // Edit Policy Handler
  const handleOpenEditPolicy = (p: PolicyItem) => {
    setEditingPolicy(p);
    setEditPolicyType(p.policy_type);
    setEditPolicyCov(String(p.coverage_amount));
    setEditPolicyDed(String(p.deductible));
    setEditPolicyEff(p.effective_date);
    setEditPolicyExp(p.expiry_date);
    setEditPolicyHolder(p.policyholder_name || "");
    setEditPolicyDob(p.policyholder_dob || "");
    setEditPolicyPhone(p.policyholder_phone || "");
    setEditPolicyError("");
  };

  const handleSavePolicyEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPolicy) return;
    const token = getAuthToken();
    if (!token) return;

    setSavingPolicy(true);
    setEditPolicyError("");

    try {
      const payload: any = {
        policy_type: editPolicyType,
        coverage_amount: parseFloat(editPolicyCov),
        deductible: parseFloat(editPolicyDed),
        effective_date: editPolicyEff,
        expiry_date: editPolicyExp,
      };
      if (editPolicyHolder.trim()) payload.policyholder_name = editPolicyHolder.trim();
      if (editPolicyDob.trim()) payload.policyholder_dob = editPolicyDob.trim();
      if (editPolicyPhone.trim()) payload.policyholder_phone = editPolicyPhone.trim();

      const res = await fetch(`${API_BASE}/api/v1/admin/policies/${editingPolicy.policy_number}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to update policy");
      }
      setEditingPolicy(null);
      fetchPolicies(token);
    } catch (err: any) {
      setEditPolicyError(err.message || "Error saving policy updates");
    } finally {
      setSavingPolicy(false);
    }
  };

  // Create Adjuster Handler
  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = getAuthToken();
    if (!token) return;

    setCreatingAdjuster(true);
    setAdjusterError("");
    setCreatedAdjusterData(null);

    try {
      if (!newAdjusterPhone.trim()) {
        throw new Error("Phone number is required.");
      }

      const payload = {
        name: newAdjusterName.trim(),
        email: newAdjusterEmail.trim().toLowerCase(),
        phone: newAdjusterPhone.trim(),
        specialization: newAdjusterSpec,
      };

      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to create adjuster account");
      }
      setCreatedAdjusterData(data);
      setNewAdjusterName("");
      setNewAdjusterEmail("");
      setNewAdjusterPhone("");
      fetchAdjusters(token);
    } catch (err: any) {
      setAdjusterError(err.message || "Error provisioning adjuster");
    } finally {
      setCreatingAdjuster(false);
    }
  };

  // Edit Adjuster Handler
  const handleOpenEditAdjuster = (adj: AdjusterItem) => {
    setEditingAdjuster(adj);
    setEditName(adj.name);
    setEditEmail(adj.email);
    setEditPhone(adj.phone || "");
    setEditSpec(adj.specialization);
    setEditActive(adj.is_active);
    setEditError("");
  };

  const handleSaveAdjusterEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAdjuster) return;
    const token = getAuthToken();
    if (!token) return;

    setSavingEdit(true);
    setEditError("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${editingAdjuster.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: editName.trim(),
          phone: editPhone.trim(),
          specialization: editSpec,
          is_active: editActive,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to update adjuster");
      }
      setEditingAdjuster(null);
      fetchAdjusters(token);
    } catch (err: any) {
      setEditError(err.message || "Error saving adjuster");
    } finally {
      setSavingEdit(false);
    }
  };

  // Reset Password Handler
  const handleResetPassword = async (adj: AdjusterItem) => {
    const token = getAuthToken();
    if (!token) return;

    setResettingPasswordId(adj.id);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${adj.id}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to reset password");
      }
      setPasswordResetData({
        adjuster: adj,
        tempPass: data.temporary_password,
      });
      setCopiedResetPass(false);
    } catch (err: any) {
      alert(`Password reset failed: ${err.message}`);
    } finally {
      setResettingPasswordId(null);
    }
  };

  // Delete Adjuster Handler
  const handleDeleteAdjuster = async () => {
    if (!deletingAdjuster) return;
    const token = getAuthToken();
    if (!token) return;

    setDeletingLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/adjusters/${deletingAdjuster.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete adjuster");
      }
      setDeletingAdjuster(null);
      fetchAdjusters(token);
    } catch (err: any) {
      alert(`Deletion failed: ${err.message}`);
    } finally {
      setDeletingLoading(false);
    }
  };

  // Filter & Sort Calculations
  const filteredPolicies = useMemo(() => {
    return policies
      .filter((p) => {
        const matchesSearch =
          p.policy_number.toLowerCase().includes(policySearch.toLowerCase()) ||
          (p.policyholder_name && p.policyholder_name.toLowerCase().includes(policySearch.toLowerCase())) ||
          (p.policyholder_phone && p.policyholder_phone.includes(policySearch));
        const matchesType = policyFilterType === "all" || p.policy_type === policyFilterType;
        return matchesSearch && matchesType;
      })
      .sort((a, b) => {
        let cmp = 0;
        if (policySortBy === "id") cmp = a.policy_number.localeCompare(b.policy_number);
        else if (policySortBy === "type") cmp = a.policy_type.localeCompare(b.policy_type);
        else if (policySortBy === "coverage") cmp = a.coverage_amount - b.coverage_amount;
        else if (policySortBy === "expiry") cmp = a.expiry_date.localeCompare(b.expiry_date);
        return policySortOrder === "asc" ? cmp : -cmp;
      });
  }, [policies, policySearch, policyFilterType, policySortBy, policySortOrder]);

  const filteredAdjusters = useMemo(() => {
    return adjusters
      .filter((adj) => {
        const matchesSearch =
          adj.name.toLowerCase().includes(adjusterSearch.toLowerCase()) ||
          adj.email.toLowerCase().includes(adjusterSearch.toLowerCase()) ||
          (adj.phone && adj.phone.includes(adjusterSearch));
        const matchesSpec = adjusterFilterSpec === "all" || adj.specialization === adjusterFilterSpec;
        return matchesSearch && matchesSpec;
      })
      .sort((a, b) => {
        let cmp = 0;
        if (adjusterSortBy === "name") cmp = a.name.localeCompare(b.name);
        else if (adjusterSortBy === "email") cmp = a.email.localeCompare(b.email);
        else if (adjusterSortBy === "specialization") cmp = a.specialization.localeCompare(b.specialization);
        else if (adjusterSortBy === "claims") cmp = a.claims_assigned - b.claims_assigned;
        return adjusterSortOrder === "asc" ? cmp : -cmp;
      });
  }, [adjusters, adjusterSearch, adjusterFilterSpec, adjusterSortBy, adjusterSortOrder]);

  if (loading) {
    return (
      <div className="bg-[#f7f9fb] text-[#191c1e] min-h-screen flex items-center justify-center font-body">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-[#00647c] animate-spin text-2xl">progress_activity</span>
          <span className="font-label text-sm text-[#505f76]">Verifying Admin Authorization...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#f7f9fb] text-[#191c1e] font-body antialiased min-h-screen flex flex-col md:flex-row selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Modular Sidebar Component */}
      <AdminSidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        currentUser={currentUser}
        onLogout={handleLogout}
        policiesCount={policies.length}
        adjustersCount={adjusters.length}
        onAddPolicy={() => setShowAddPolicyModal(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 md:ml-64 min-h-screen overflow-y-auto bg-white">
        {/* Modular TopBar Component */}
        <AdminTopBar activeTab={activeTab} currentUser={currentUser} />

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

              {/* Modular CSV Dropzone Component */}
              <CsvDropzone
                fileInputRef={fileInputRef}
                csvFile={csvFile}
                importingCsv={importingCsv}
                importResult={importResult}
                importError={importError}
                onFileChange={handleFileChange}
                onUploadCsv={handleUploadCsv}
              />

              {/* Modular Policy Table Component */}
              <AdminPolicyTable
                policies={policies}
                filteredPolicies={filteredPolicies}
                policySearch={policySearch}
                setPolicySearch={setPolicySearch}
                policyFilterType={policyFilterType}
                setPolicyFilterType={setPolicyFilterType}
                policySortBy={policySortBy}
                setPolicySortBy={setPolicySortBy}
                policySortOrder={policySortOrder}
                setPolicySortOrder={setPolicySortOrder}
                loadingPolicies={loadingPolicies}
                onOpenCreatePolicy={handleOpenCreatePolicy}
                onOpenEditPolicy={handleOpenEditPolicy}
              />
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
                {/* Modular Create Adjuster Card Component */}
                <CreateAdjusterCard
                  newAdjusterName={newAdjusterName}
                  setNewAdjusterName={setNewAdjusterName}
                  newAdjusterEmail={newAdjusterEmail}
                  setNewAdjusterEmail={setNewAdjusterEmail}
                  newAdjusterPhone={newAdjusterPhone}
                  setNewAdjusterPhone={setNewAdjusterPhone}
                  newAdjusterSpec={newAdjusterSpec}
                  setNewAdjusterSpec={setNewAdjusterSpec}
                  creatingAdjuster={creatingAdjuster}
                  adjusterError={adjusterError}
                  createdAdjusterData={createdAdjusterData}
                  copiedPass={copiedPass}
                  setCopiedPass={setCopiedPass}
                  onSubmit={handleCreateAdjuster}
                />

                {/* Modular Adjusters Roster Table Component */}
                <AdjustersRosterTable
                  adjusters={adjusters}
                  filteredAdjusters={filteredAdjusters}
                  adjusterSearch={adjusterSearch}
                  setAdjusterSearch={setAdjusterSearch}
                  adjusterFilterSpec={adjusterFilterSpec}
                  setAdjusterFilterSpec={setAdjusterFilterSpec}
                  adjusterSortBy={adjusterSortBy}
                  setAdjusterSortBy={setAdjusterSortBy}
                  adjusterSortOrder={adjusterSortOrder}
                  setAdjusterSortOrder={setAdjusterSortOrder}
                  loadingAdjusters={loadingAdjusters}
                  onOpenEditAdjuster={handleOpenEditAdjuster}
                  onResetPassword={handleResetPassword}
                  onOpenDeleteAdjuster={(adj) => setDeletingAdjuster(adj)}
                  resettingPasswordId={resettingPasswordId}
                />
              </div>
            </>
          )}
        </div>
      </main>

      {/* Modular Modals */}
      <AddPolicyModal
        isOpen={showAddPolicyModal}
        onClose={() => setShowAddPolicyModal(false)}
        onSubmit={handleCreatePolicy}
        newPolicyNum={newPolicyNum}
        setNewPolicyNum={setNewPolicyNum}
        newPolicyType={newPolicyType}
        setNewPolicyType={setNewPolicyType}
        newPolicyCov={newPolicyCov}
        setNewPolicyCov={setNewPolicyCov}
        newPolicyDed={newPolicyDed}
        setNewPolicyDed={setNewPolicyDed}
        newPolicyEff={newPolicyEff}
        setNewPolicyEff={setNewPolicyEff}
        newPolicyExp={newPolicyExp}
        setNewPolicyExp={setNewPolicyExp}
        newPolicyHolder={newPolicyHolder}
        setNewPolicyHolder={setNewPolicyHolder}
        newPolicyDob={newPolicyDob}
        setNewPolicyDob={setNewPolicyDob}
        newPolicyPhone={newPolicyPhone}
        setNewPolicyPhone={setNewPolicyPhone}
        creatingPolicy={creatingPolicy}
        createPolicyError={createPolicyError}
      />

      <EditPolicyModal
        editingPolicy={editingPolicy}
        onClose={() => setEditingPolicy(null)}
        onSubmit={handleSavePolicyEdit}
        editPolicyType={editPolicyType}
        setEditPolicyType={setEditPolicyType}
        editPolicyCov={editPolicyCov}
        setEditPolicyCov={setEditPolicyCov}
        editPolicyDed={editPolicyDed}
        setEditPolicyDed={setEditPolicyDed}
        editPolicyEff={editPolicyEff}
        setEditPolicyEff={setEditPolicyEff}
        editPolicyExp={editPolicyExp}
        setEditPolicyExp={setEditPolicyExp}
        editPolicyHolder={editPolicyHolder}
        setEditPolicyHolder={setEditPolicyHolder}
        editPolicyDob={editPolicyDob}
        setEditPolicyDob={setEditPolicyDob}
        editPolicyPhone={editPolicyPhone}
        setEditPolicyPhone={setEditPolicyPhone}
        savingPolicy={savingPolicy}
        editPolicyError={editPolicyError}
      />

      <EditAdjusterModal
        editingAdjuster={editingAdjuster}
        onClose={() => setEditingAdjuster(null)}
        onSubmit={handleSaveAdjusterEdit}
        editName={editName}
        setEditName={setEditName}
        editEmail={editEmail}
        setEditEmail={setEditEmail}
        editPhone={editPhone}
        setEditPhone={setEditPhone}
        editSpec={editSpec}
        setEditSpec={setEditSpec}
        editActive={editActive}
        setEditActive={setEditActive}
        savingEdit={savingEdit}
        editError={editError}
      />

      <PasswordResetModal
        passwordResetData={passwordResetData}
        onClose={() => setPasswordResetData(null)}
        copiedResetPass={copiedResetPass}
        setCopiedResetPass={setCopiedResetPass}
      />

      <DeleteAdjusterModal
        deletingAdjuster={deletingAdjuster}
        onClose={() => setDeletingAdjuster(null)}
        onConfirm={handleDeleteAdjuster}
        deletingLoading={deletingLoading}
      />
    </div>
  );
}
