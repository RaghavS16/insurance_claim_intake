import React from "react";
import { Badge } from "@/components/common/Badge";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

export interface AdjusterRecord {
  id: string;
  name: string;
  email: string;
  specialization: string;
  claims_assigned: number;
  is_active: boolean;
}

interface AdjusterTableProps {
  adjusters: AdjusterRecord[];
  onEdit: (adjuster: AdjusterRecord) => void;
  onDelete: (adjusterId: string) => void;
  isLoading?: boolean;
}

export const AdjusterTable: React.FC<AdjusterTableProps> = ({
  adjusters,
  onEdit,
  onDelete,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-secondary">
        <span className="material-symbols-outlined animate-spin text-3xl mr-2">progress_activity</span>
        <span>Loading adjusters...</span>
      </div>
    );
  }

  if (adjusters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center text-secondary">
        <span className="material-symbols-outlined text-4xl mb-2 text-outline">badge</span>
        <p className="text-sm font-medium">No adjusters found.</p>
        <p className="text-xs text-secondary/70">Create a new adjuster to handle claims.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-surface-container-highest bg-surface shadow-sm">
      <table className="w-full text-left text-xs">
        <thead className="bg-surface-container-low text-secondary border-b border-surface-container-highest uppercase tracking-wider font-semibold">
          <tr>
            <th className="p-4">Name</th>
            <th className="p-4">Email</th>
            <th className="p-4">Specialization</th>
            <th className="p-4">Claims Assigned</th>
            <th className="p-4">Status</th>
            <th className="p-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-container-highest">
          {adjusters.map((a) => {
            const specLabel = (SUPPORTED_INSURANCE_TYPES as any)[a.specialization] || a.specialization;
            return (
              <tr key={a.id} className="hover:bg-surface-container-low/50 transition-colors">
                <td className="p-4 font-bold text-on-surface">{a.name}</td>
                <td className="p-4 text-secondary">{a.email}</td>
                <td className="p-4 font-medium text-on-surface">{specLabel}</td>
                <td className="p-4 font-medium text-on-surface">{a.claims_assigned}</td>
                <td className="p-4">
                  <Badge
                    status={a.is_active ? "Active" : "Inactive"}
                    variant={a.is_active ? "success" : "neutral"}
                  />
                </td>
                <td className="p-4 text-right space-x-1">
                  <button
                    onClick={() => onEdit(a)}
                    className="p-1.5 rounded-lg text-secondary hover:text-primary hover:bg-surface-container transition-colors"
                    title="Edit adjuster"
                  >
                    <span className="material-symbols-outlined text-sm">edit</span>
                  </button>
                  <button
                    onClick={() => onDelete(a.id)}
                    className="p-1.5 rounded-lg text-secondary hover:text-error hover:bg-rose-500/10 transition-colors"
                    title="Delete adjuster"
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
