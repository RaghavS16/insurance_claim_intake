import React from "react";
import { Badge } from "@/components/common/Badge";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

export interface PolicyRecord {
  id: string;
  policy_number: string;
  policy_type: string;
  coverage_amount: number;
  deductible: number;
  effective_date: string;
  expiry_date: string;
  is_active: boolean;
  policyholder_name?: string | null;
  policyholder_phone?: string | null;
  policyholder_dob?: string | null;
  customer_id?: string | null;
}

interface PolicyTableProps {
  policies: PolicyRecord[];
  onEdit: (policy: PolicyRecord) => void;
  onDelete: (policyNumber: string) => void;
  isLoading?: boolean;
}

export const PolicyTable: React.FC<PolicyTableProps> = ({
  policies,
  onEdit,
  onDelete,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-secondary">
        <span className="material-symbols-outlined animate-spin text-3xl mr-2">progress_activity</span>
        <span>Loading policies...</span>
      </div>
    );
  }

  if (policies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-secondary">
        <span className="material-symbols-outlined text-4xl mb-2 text-outline">policy</span>
        <p className="text-sm font-medium">No policies found.</p>
        <p className="text-xs text-secondary/70">Create a new policy or import from CSV.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-surface-container-highest bg-surface shadow-sm">
      <table className="w-full text-left text-xs">
        <thead className="bg-surface-container-low text-secondary border-b border-surface-container-highest uppercase tracking-wider font-semibold">
          <tr>
            <th className="p-4">Policy #</th>
            <th className="p-4">Type</th>
            <th className="p-4">Policyholder</th>
            <th className="p-4">Coverage</th>
            <th className="p-4">Deductible</th>
            <th className="p-4">Validity</th>
            <th className="p-4">Status</th>
            <th className="p-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-container-highest">
          {policies.map((p) => {
            const typeLabel = (SUPPORTED_INSURANCE_TYPES as any)[p.policy_type] || p.policy_type;
            return (
              <tr key={p.id} className="hover:bg-surface-container-low/50 transition-colors">
                <td className="p-4 font-mono font-bold text-on-surface">{p.policy_number}</td>
                <td className="p-4 font-medium text-on-surface">{typeLabel}</td>
                <td className="p-4">
                  <div className="font-medium text-on-surface">{p.policyholder_name || "—"}</div>
                  {p.policyholder_phone && (
                    <div className="text-[10px] text-secondary">{p.policyholder_phone}</div>
                  )}
                </td>
                <td className="p-4 font-medium text-on-surface">
                  ₹{Number(p.coverage_amount).toLocaleString()}
                </td>
                <td className="p-4 font-medium text-on-surface">
                  ₹{Number(p.deductible).toLocaleString()}
                </td>
                <td className="p-4 text-secondary">
                  {p.effective_date} to {p.expiry_date}
                </td>
                <td className="p-4">
                  <Badge
                    status={p.is_active ? "Active" : "Inactive"}
                    variant={p.is_active ? "success" : "neutral"}
                  />
                </td>
                <td className="p-4 text-right space-x-1">
                  <button
                    onClick={() => onEdit(p)}
                    className="p-1.5 rounded-lg text-secondary hover:text-primary hover:bg-surface-container transition-colors"
                    title="Edit policy"
                  >
                    <span className="material-symbols-outlined text-sm">edit</span>
                  </button>
                  <button
                    onClick={() => onDelete(p.policy_number)}
                    className="p-1.5 rounded-lg text-secondary hover:text-error hover:bg-rose-500/10 transition-colors"
                    title="Delete policy"
                  >
                    <span className="material-symbols-outlined text-sm">delete</span>
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
