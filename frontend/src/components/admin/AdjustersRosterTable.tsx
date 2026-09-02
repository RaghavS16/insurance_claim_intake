import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";

export interface AdjusterItem {
  id: string;
  name: string;
  email: string;
  specialization: string;
  claims_assigned: number;
  is_active: boolean;
}

interface AdjustersRosterTableProps {
  adjusters: AdjusterItem[];
  filteredAdjusters: AdjusterItem[];
  adjusterSearch: string;
  setAdjusterSearch: (v: string) => void;
  adjusterFilterSpec: string;
  setAdjusterFilterSpec: (v: string) => void;
  adjusterSortBy: string;
  setAdjusterSortBy: (v: string) => void;
  adjusterSortOrder: string;
  setAdjusterSortOrder: (v: string) => void;
  loadingAdjusters: boolean;
  onOpenEditAdjuster: (adj: AdjusterItem) => void;
  onResetPassword: (adj: AdjusterItem) => void;
  onOpenDeleteAdjuster: (adj: AdjusterItem) => void;
  resettingPasswordId: string | null;
}

export const AdjustersRosterTable: React.FC<AdjustersRosterTableProps> = ({
  filteredAdjusters,
  adjusterSearch,
  setAdjusterSearch,
  adjusterFilterSpec,
  setAdjusterFilterSpec,
  adjusterSortBy,
  setAdjusterSortBy,
  adjusterSortOrder,
  setAdjusterSortOrder,
  loadingAdjusters,
  onOpenEditAdjuster,
  onResetPassword,
  onOpenDeleteAdjuster,
  resettingPasswordId,
}) => {
  return (
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
                  No adjusters found matching your filter.
                </td>
              </tr>
            ) : (
              filteredAdjusters.map((adj) => (
                <tr key={adj.id} className="hover:bg-[#f7f9fb] transition-colors">
                  <td className="py-3.5 px-4 font-bold text-[#191c1e]">
                    <div>{adj.name}</div>
                    <div className="font-normal text-[11px] text-[#505f76]">{adj.email}</div>
                  </td>
                  <td className="py-3.5 px-4">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        adj.is_active
                          ? "bg-[#d0e1fb] text-[#54647a]"
                          : "bg-[#ffdad6] text-[#93000a]"
                      }`}
                    >
                      {adj.is_active ? "Active" : "Disabled"}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-[#505f76] capitalize">
                    {adj.specialization.replace("_", " ")}
                  </td>
                  <td className="py-3.5 px-4 text-center font-bold text-[#191c1e]">
                    {adj.claims_assigned || 0}
                  </td>
                  <td className="py-3.5 px-4 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button
                        onClick={() => onOpenEditAdjuster(adj)}
                        title="Edit Adjuster"
                        className="text-[#00647c] hover:text-[#007f9d] p-1 rounded hover:bg-[#eceef0] transition-colors cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[16px]">edit</span>
                      </button>
                      <button
                        onClick={() => onResetPassword(adj)}
                        disabled={resettingPasswordId === adj.id}
                        title="Generate New Temporary Password"
                        className="text-[#0891B2] hover:text-[#007f9d] p-1 rounded hover:bg-[#eceef0] transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <span className="material-symbols-outlined text-[16px]">
                          {resettingPasswordId === adj.id ? "progress_activity" : "lock_reset"}
                        </span>
                      </button>
                      <button
                        onClick={() => onOpenDeleteAdjuster(adj)}
                        title="Delete Adjuster"
                        className="text-[#ba1a1a] hover:text-[#93000a] p-1 rounded hover:bg-[#ffdad6]/40 transition-colors cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[16px]">delete</span>
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
