import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";

export interface PolicyFormData {
  policy_number: string;
  policy_type: string;
  coverage_amount: string;
  deductible: string;
  effective_date: string;
  expiry_date: string;
  policyholder_name: string;
  policyholder_dob: string;
  policyholder_phone: string;
  is_active: boolean;
}

interface PolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  formData: PolicyFormData;
  setFormData: React.Dispatch<React.SetStateAction<PolicyFormData>>;
  isEditing: boolean;
  isSaving: boolean;
  errorMessage?: string;
}

export const PolicyModal: React.FC<PolicyModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  formData,
  setFormData,
  isEditing,
  isSaving,
  errorMessage,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl max-h-[90vh] overflow-y-auto border border-[#e0e3e5]">
        <div className="flex justify-between items-center mb-5 pb-3 border-b border-[#e0e3e5]">
          <div>
            <h3 className="font-headline text-lg font-bold text-[#191c1e]">
              {isEditing ? `Edit Policy ${formData.policy_number}` : "Create New Policy"}
            </h3>
            <p className="font-body text-xs text-[#505f76] mt-0.5">
              {isEditing ? "Update existing policy parameters." : "Add a new verifiable policy record."}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[#505f76] hover:text-[#191c1e] p-1 rounded-lg hover:bg-[#f2f4f6]"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        {errorMessage && (
          <div className="mb-4 p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-xl text-[#93000a] text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-sm text-[#ba1a1a]">error</span>
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4 text-xs font-body">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Policy Number *
              </label>
              <input
                type="text"
                required
                disabled={isEditing}
                placeholder="e.g. MOT-9921"
                value={formData.policy_number}
                onChange={(e) => setFormData({ ...formData, policy_number: e.target.value.toUpperCase() })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e] disabled:opacity-60 font-mono"
              />
            </div>

            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Policy Type *
              </label>
              <select
                value={formData.policy_type}
                onChange={(e) => setFormData({ ...formData, policy_type: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e] cursor-pointer"
              >
                {SPECIALIZATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Coverage Amount (₹) *
              </label>
              <input
                type="number"
                required
                min={1000}
                placeholder="500000"
                value={formData.coverage_amount}
                onChange={(e) => setFormData({ ...formData, coverage_amount: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>

            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Deductible (₹) *
              </label>
              <input
                type="number"
                required
                min={0}
                placeholder="5000"
                value={formData.deductible}
                onChange={(e) => setFormData({ ...formData, deductible: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Effective Date *
              </label>
              <input
                type="date"
                required
                value={formData.effective_date}
                onChange={(e) => setFormData({ ...formData, effective_date: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>

            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Expiry Date *
              </label>
              <input
                type="date"
                required
                value={formData.expiry_date}
                onChange={(e) => setFormData({ ...formData, expiry_date: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>
          </div>

          <div>
            <label className="font-label font-medium text-[#505f76] block mb-1">
              Policyholder Full Name
            </label>
            <input
              type="text"
              placeholder="e.g. John Doe"
              value={formData.policyholder_name}
              onChange={(e) => setFormData({ ...formData, policyholder_name: e.target.value })}
              className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Policyholder DOB
              </label>
              <input
                type="date"
                value={formData.policyholder_dob}
                onChange={(e) => setFormData({ ...formData, policyholder_dob: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>

            <div>
              <label className="font-label font-medium text-[#505f76] block mb-1">
                Policyholder Phone
              </label>
              <input
                type="text"
                placeholder="e.g. 9876543210"
                value={formData.policyholder_phone}
                onChange={(e) => setFormData({ ...formData, policyholder_phone: e.target.value })}
                className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <input
              id="isActivePolicy"
              type="checkbox"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="rounded border-[#e0e3e5] text-[#0891B2] focus:ring-[#0891B2]"
            />
            <label htmlFor="isActivePolicy" className="font-label text-xs font-semibold text-[#191c1e] cursor-pointer">
              Policy is Active
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-[#e0e3e5]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-[#e0e3e5] text-[#505f76] hover:bg-[#f2f4f6] font-semibold text-xs transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-5 py-2 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white font-semibold text-xs flex items-center gap-1.5 transition-colors disabled:opacity-50 shadow-sm"
            >
              {isSaving ? (
                <>
                  <span className="material-symbols-outlined text-xs animate-spin">progress_activity</span>
                  <span>Saving...</span>
                </>
              ) : (
                <span>{isEditing ? "Save Changes" : "Create Policy"}</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
