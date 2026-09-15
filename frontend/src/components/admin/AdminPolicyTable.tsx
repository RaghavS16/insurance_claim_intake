import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";

export interface PolicyItem {
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

interface AdminPolicyTableProps {
  policies: PolicyItem[];
  filteredPolicies: PolicyItem[];
  policySearch: string;
  setPolicySearch: (v: string) => void;
  policyFilterType: string;
  setPolicyFilterType: (v: string) => void;
  policySortBy: string;
  setPolicySortBy: (v: string) => void;
  policySortOrder: string;
  setPolicySortOrder: (v: string) => void;
  loadingPolicies: boolean;
  onOpenCreatePolicy: () => void;
  onOpenEditPolicy: (p: PolicyItem) => void;
}

export const AdminPolicyTable: React.FC<AdminPolicyTableProps> = ({
  policies,
  filteredPolicies,
  policySearch,
  setPolicySearch,
  policyFilterType,
  setPolicyFilterType,
  policySortBy,
  setPolicySortBy,
  policySortOrder,
  setPolicySortOrder,
  loadingPolicies,
  onOpenCreatePolicy,
  onOpenEditPolicy,
}) => {
  const handleDownloadCSV = () => {
    if (!filteredPolicies.length) return;

    const headers = [
      "Policy Number",
      "Policyholder Name",
      "Policy Type",
      "Coverage Amount (INR)",
      "Deductible (INR)",
      "Effective Date",
      "Expiry Date",
      "Status",
      "Link Status",
      "Phone",
      "Date of Birth",
    ];

    const rows = filteredPolicies.map((p) => [
      `"${p.policy_number || ""}"`,
      `"${(p.policyholder_name || "").replace(/"/g, '""')}"`,
      `"${p.policy_type || ""}"`,
      p.coverage_amount ?? "",
      p.deductible ?? "",
      `"${p.effective_date || ""}"`,
      `"${p.expiry_date || ""}"`,
      `"${p.is_active ? "Active" : "Inactive"}"`,
      `"${p.is_linked ? "Linked" : "Unlinked"}"`,
      `"${p.policyholder_phone || ""}"`,
      `"${p.policyholder_dob || ""}"`,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `filtered_policies_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-white rounded-2xl border border-[#e0e3e5] flex flex-col shadow-sm overflow-hidden">
      <div className="p-4 md:p-6 border-b border-[#e0e3e5] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h3 className="font-headline text-lg font-bold text-[#191c1e]">Active Policies Master</h3>
          <p className="font-label text-xs text-[#505f76]">
            {policies.length} total policies available for linkage
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          <button
            onClick={handleDownloadCSV}
            disabled={filteredPolicies.length === 0}
            title={
              filteredPolicies.length === 0
                ? "No policies match the filter"
                : `Download ${filteredPolicies.length} filtered policies as CSV`
            }
            className="bg-[#00647c] hover:bg-[#004e61] disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-label text-xs font-semibold px-3.5 py-1.5 rounded-full transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer"
          >
            <span className="material-symbols-outlined text-sm">download</span>
            <span>Download CSV</span>
          </button>
          <div className="relative w-full sm:w-56">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#505f76] text-[18px]">
              search
            </span>
            <input
              type="text"
              placeholder="Search policies..."
              value={policySearch}
              onChange={(e) => setPolicySearch(e.target.value)}
              className="input-minimal w-full pl-9 pr-4 py-1.5 bg-[#f7f9fb] border border-[#e0e3e5] rounded-full font-body text-xs text-[#191c1e]"
            />
          </div>
          <select
            value={policyFilterType}
            onChange={(e) => setPolicyFilterType(e.target.value)}
            className="input-minimal w-full sm:w-auto bg-[#f7f9fb] border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
          >
            <option value="all">All Types</option>
            {SPECIALIZATION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={policySortBy}
            onChange={(e) => setPolicySortBy(e.target.value)}
            className="input-minimal w-full sm:w-auto bg-[#f7f9fb] border border-[#e0e3e5] rounded-full px-4 py-1.5 font-body text-xs text-[#191c1e] cursor-pointer"
          >
            <option value="id">Sort: Policy ID</option>
            <option value="type">Sort: Type</option>
            <option value="coverage">Sort: Coverage</option>
            <option value="expiry">Sort: Expiry</option>
          </select>
          <button
            type="button"
            onClick={() => setPolicySortOrder(policySortOrder === "asc" ? "desc" : "asc")}
            className="w-8 h-8 flex items-center justify-center rounded-full border border-[#e0e3e5] text-[#505f76] hover:bg-[#eceef0] cursor-pointer shrink-0"
            title="Toggle Sort Order"
          >
            <span className="material-symbols-outlined text-[18px]">
              {policySortOrder === "asc" ? "arrow_upward" : "arrow_downward"}
            </span>
          </button>
        </div>
      </div>

      <div className="overflow-x-auto w-full">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="bg-[#f7f9fb] border-b border-[#e0e3e5] font-label text-[11px] text-[#505f76] font-semibold uppercase tracking-wider">
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
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        p.is_active
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200/80"
                          : "bg-rose-50 text-rose-700 border border-rose-200/80"
                      }`}
                    >
                      {p.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button
                        onClick={() => onOpenEditPolicy(p)}
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
  );
};
