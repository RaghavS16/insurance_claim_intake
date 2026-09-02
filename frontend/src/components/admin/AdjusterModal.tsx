import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";

export interface AdjusterFormData {
  name: string;
  email: string;
  specialization: string;
  is_active: boolean;
}

interface AdjusterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  formData: AdjusterFormData;
  setFormData: React.Dispatch<React.SetStateAction<AdjusterFormData>>;
  isEditing: boolean;
  isSaving: boolean;
  errorMessage?: string;
}

export const AdjusterModal: React.FC<AdjusterModalProps> = ({
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
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-[#e0e3e5]">
        <div className="flex justify-between items-center mb-5 pb-3 border-b border-[#e0e3e5]">
          <div>
            <h3 className="font-headline text-lg font-bold text-[#191c1e]">
              {isEditing ? `Edit Adjuster ${formData.name}` : "Create Adjuster Account"}
            </h3>
            <p className="font-body text-xs text-[#505f76] mt-0.5">
              {isEditing ? "Update claims personnel assignment." : "Provision a new adjuster to the roster."}
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
          <div>
            <label className="font-label font-medium text-[#505f76] block mb-1">
              Full Name *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Priya Sharma"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e]"
            />
          </div>

          <div>
            <label className="font-label font-medium text-[#505f76] block mb-1">
              Email Address *
            </label>
            <input
              type="email"
              required
              disabled={isEditing}
              placeholder="e.g. priya.sharma@insureclaimai.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e] disabled:opacity-60"
            />
          </div>

          <div>
            <label className="font-label font-medium text-[#505f76] block mb-1">
              Specialization *
            </label>
            <select
              value={formData.specialization}
              onChange={(e) => setFormData({ ...formData, specialization: e.target.value })}
              className="w-full bg-[#f7f9fb] border border-[#e0e3e5] rounded-lg px-3 py-2 text-[#191c1e] cursor-pointer"
            >
              {SPECIALIZATION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {isEditing && (
            <div className="flex items-center gap-2 pt-2">
              <input
                id="isActiveAdjuster"
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="rounded border-[#e0e3e5] text-[#0891B2] focus:ring-[#0891B2]"
              />
              <label htmlFor="isActiveAdjuster" className="font-label text-xs font-semibold text-[#191c1e] cursor-pointer">
                Adjuster is Active
              </label>
            </div>
          )}

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
                <span>{isEditing ? "Save Changes" : "Provision Account"}</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
