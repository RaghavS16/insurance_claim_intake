import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";
import { PolicyItem } from "./AdminPolicyTable";
import { AdjusterItem } from "./AdjustersRosterTable";

interface AddPolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  newPolicyNum: string;
  setNewPolicyNum: (v: string) => void;
  newPolicyType: string;
  setNewPolicyType: (v: string) => void;
  newPolicyCov: string;
  setNewPolicyCov: (v: string) => void;
  newPolicyDed: string;
  setNewPolicyDed: (v: string) => void;
  newPolicyEff: string;
  setNewPolicyEff: (v: string) => void;
  newPolicyExp: string;
  setNewPolicyExp: (v: string) => void;
  newPolicyHolder: string;
  setNewPolicyHolder: (v: string) => void;
  newPolicyDob: string;
  setNewPolicyDob: (v: string) => void;
  newPolicyPhone: string;
  setNewPolicyPhone: (v: string) => void;
  creatingPolicy: boolean;
  createPolicyError: string;
}

export const AddPolicyModal: React.FC<AddPolicyModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  newPolicyNum,
  setNewPolicyNum,
  newPolicyType,
  setNewPolicyType,
  newPolicyCov,
  setNewPolicyCov,
  newPolicyDed,
  setNewPolicyDed,
  newPolicyEff,
  setNewPolicyEff,
  newPolicyExp,
  setNewPolicyExp,
  newPolicyHolder,
  setNewPolicyHolder,
  newPolicyDob,
  setNewPolicyDob,
  newPolicyPhone,
  setNewPolicyPhone,
  creatingPolicy,
  createPolicyError,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-headline text-lg font-bold text-[#191c1e]">Add New Policy Record</h3>
          <button onClick={onClose} className="text-[#505f76] hover:text-[#191c1e]">
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>

        {createPolicyError && (
          <div className="p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs mb-4">
            {createPolicyError}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Policy ID *</label>
              <input
                type="text"
                required
                placeholder="e.g. POL-8821-AX"
                value={newPolicyNum}
                onChange={(e) => setNewPolicyNum(e.target.value.toUpperCase())}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e] font-mono"
              />
            </div>
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Policy Type *</label>
              <select
                value={newPolicyType}
                onChange={(e) => setNewPolicyType(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
              >
                {SPECIALIZATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Policyholder Full Name</label>
              <input
                type="text"
                placeholder="e.g. Alice Smith"
                value={newPolicyHolder}
                onChange={(e) => setNewPolicyHolder(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
              />
            </div>
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Date of Birth</label>
              <input
                type="date"
                value={newPolicyDob}
                onChange={(e) => setNewPolicyDob(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
              />
            </div>
          </div>

          <div>
            <label className="font-label text-xs text-[#505f76] block mb-1">Phone Number</label>
            <input
              type="text"
              placeholder="e.g. 5551234567"
              value={newPolicyPhone}
              onChange={(e) => setNewPolicyPhone(e.target.value)}
              className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Coverage Limit (₹) *</label>
              <input
                type="number"
                required
                min="1000"
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
              onClick={onClose}
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
  );
};

interface EditPolicyModalProps {
  editingPolicy: PolicyItem | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  editPolicyType: string;
  setEditPolicyType: (v: string) => void;
  editPolicyCov: string;
  setEditPolicyCov: (v: string) => void;
  editPolicyDed: string;
  setEditPolicyDed: (v: string) => void;
  editPolicyEff: string;
  setEditPolicyEff: (v: string) => void;
  editPolicyExp: string;
  setEditPolicyExp: (v: string) => void;
  editPolicyHolder: string;
  setEditPolicyHolder: (v: string) => void;
  editPolicyDob: string;
  setEditPolicyDob: (v: string) => void;
  editPolicyPhone: string;
  setEditPolicyPhone: (v: string) => void;
  savingPolicy: boolean;
  editPolicyError: string;
}

export const EditPolicyModal: React.FC<EditPolicyModalProps> = ({
  editingPolicy,
  onClose,
  onSubmit,
  editPolicyType,
  setEditPolicyType,
  editPolicyCov,
  setEditPolicyCov,
  editPolicyDed,
  setEditPolicyDed,
  editPolicyEff,
  setEditPolicyEff,
  editPolicyExp,
  setEditPolicyExp,
  editPolicyHolder,
  setEditPolicyHolder,
  editPolicyDob,
  setEditPolicyDob,
  editPolicyPhone,
  setEditPolicyPhone,
  savingPolicy,
  editPolicyError,
}) => {
  if (!editingPolicy) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-headline text-lg font-bold text-[#191c1e]">
            Edit Policy {editingPolicy.policy_number}
          </h3>
          <button onClick={onClose} className="text-[#505f76] hover:text-[#191c1e]">
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>

        {editPolicyError && (
          <div className="p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs mb-4">
            {editPolicyError}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="font-label text-xs text-[#505f76] block mb-1">Policy Type</label>
            <select
              value={editPolicyType}
              onChange={(e) => setEditPolicyType(e.target.value)}
              className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
            >
              {SPECIALIZATION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Policyholder Name</label>
              <input
                type="text"
                value={editPolicyHolder}
                onChange={(e) => setEditPolicyHolder(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
              />
            </div>
            <div>
              <label className="font-label text-xs text-[#505f76] block mb-1">Date of Birth</label>
              <input
                type="date"
                value={editPolicyDob}
                onChange={(e) => setEditPolicyDob(e.target.value)}
                className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
              />
            </div>
          </div>

          <div>
            <label className="font-label text-xs text-[#505f76] block mb-1">Phone Number</label>
            <input
              type="text"
              value={editPolicyPhone}
              onChange={(e) => setEditPolicyPhone(e.target.value)}
              className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
            />
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
              onClick={onClose}
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
  );
};

interface EditAdjusterModalProps {
  editingAdjuster: AdjusterItem | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  editName: string;
  setEditName: (v: string) => void;
  editEmail: string;
  setEditEmail: (v: string) => void;
  editPhone: string;
  setEditPhone: (v: string) => void;
  editSpec: string;
  setEditSpec: (v: string) => void;
  editActive: boolean;
  setEditActive: (v: boolean) => void;
  savingEdit: boolean;
  editError: string;
}

export const EditAdjusterModal: React.FC<EditAdjusterModalProps> = ({
  editingAdjuster,
  onClose,
  onSubmit,
  editName,
  setEditName,
  editEmail,
  setEditEmail,
  editPhone,
  setEditPhone,
  editSpec,
  setEditSpec,
  editActive,
  setEditActive,
  savingEdit,
  editError,
}) => {
  if (!editingAdjuster) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
        <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">
          Edit Adjuster Profile
        </h3>
        <p className="font-body text-xs text-[#505f76] mb-4">
          Update personnel attributes or assignment status.
        </p>

        {editError && (
          <div className="p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs mb-4">
            {editError}
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-3">
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
            <label className="font-label text-xs text-[#505f76] block mb-1">Email (System Login)</label>
            <input
              type="email"
              required
              disabled
              value={editEmail}
              onChange={(e) => setEditEmail(e.target.value)}
              className="input-minimal w-full bg-[#e0e3e5]/50 border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#505f76] cursor-not-allowed"
            />
          </div>

          <div>
            <label className="font-label text-xs text-[#505f76] block mb-1">Phone Number *</label>
            <input
              type="tel"
              required
              placeholder="+1 (555) 234-5678"
              value={editPhone}
              onChange={(e) => setEditPhone(e.target.value)}
              className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
            />
          </div>

          <div>
            <label className="font-label text-xs text-[#505f76] block mb-1">Specialization</label>
            <select
              value={editSpec}
              onChange={(e) => setEditSpec(e.target.value)}
              className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2 text-xs text-[#191c1e]"
            >
              {SPECIALIZATION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="editActiveStatus"
              checked={editActive}
              onChange={(e) => setEditActive(e.target.checked)}
              className="w-4 h-4 text-[#00647c] rounded border-[#bdc8ce]"
            />
            <label htmlFor="editActiveStatus" className="font-label text-xs text-[#191c1e] font-medium cursor-pointer">
              Active on Assignment Roster
            </label>
          </div>

          <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-[#e0e3e5]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={savingEdit}
              className="px-4 py-2 rounded-lg bg-[#00647c] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm disabled:opacity-50 cursor-pointer"
            >
              {savingEdit ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

interface PasswordResetModalProps {
  passwordResetData: { adjuster: AdjusterItem; tempPass: string } | null;
  onClose: () => void;
  copiedResetPass: boolean;
  setCopiedResetPass: (v: boolean) => void;
}

export const PasswordResetModal: React.FC<PasswordResetModalProps> = ({
  passwordResetData,
  onClose,
  copiedResetPass,
  setCopiedResetPass,
}) => {
  if (!passwordResetData) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
        <div className="flex items-center gap-2 text-emerald-700 font-bold mb-2">
          <span className="material-symbols-outlined">lock_reset</span>
          <h3 className="font-headline text-lg text-[#191c1e]">Password Reset Complete</h3>
        </div>
        <p className="font-body text-xs text-[#505f76] mb-3">
          A new temporary password has been generated for{" "}
          <span className="font-semibold text-[#191c1e]">{passwordResetData.adjuster.email}</span>.
        </p>

        <div className="p-3 bg-emerald-50 border border-emerald-300 rounded-lg font-mono text-sm flex justify-between items-center mb-4">
          <span className="font-bold text-emerald-950">{passwordResetData.tempPass}</span>
          <button
            onClick={() => {
              navigator.clipboard.writeText(passwordResetData.tempPass);
              setCopiedResetPass(true);
              setTimeout(() => setCopiedResetPass(false), 2000);
            }}
            className="text-xs font-bold text-emerald-700 underline hover:text-emerald-900 ml-2"
          >
            {copiedResetPass ? "Copied!" : "Copy"}
          </button>
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#00647c] text-white text-xs font-semibold hover:bg-[#007f9d]"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

interface DeleteAdjusterModalProps {
  deletingAdjuster: AdjusterItem | null;
  onClose: () => void;
  onConfirm: () => void;
  deletingLoading: boolean;
}

export const DeleteAdjusterModal: React.FC<DeleteAdjusterModalProps> = ({
  deletingAdjuster,
  onClose,
  onConfirm,
  deletingLoading,
}) => {
  if (!deletingAdjuster) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <div className="flex items-center gap-2 text-[#ba1a1a] font-bold mb-2">
          <span className="material-symbols-outlined">warning</span>
          <h3 className="font-headline text-lg text-[#191c1e]">Confirm Deletion</h3>
        </div>
        <p className="font-body text-xs text-[#505f76] mb-4">
          Are you sure you want to remove{" "}
          <span className="font-bold text-[#191c1e]">{deletingAdjuster.name}</span>?
          {deletingAdjuster.claims_assigned > 0 ? (
            <span className="text-[#ba1a1a] block mt-1 font-semibold">
              Warning: This adjuster currently has {deletingAdjuster.claims_assigned} active claims. Deleting them will disable their account.
            </span>
          ) : (
            " This will permanently delete their account and roster entry."
          )}
        </p>

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={deletingLoading}
            className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e]"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deletingLoading}
            className="px-4 py-2 rounded-lg bg-[#ba1a1a] hover:bg-[#93000a] text-white text-xs font-semibold shadow-sm disabled:opacity-50"
          >
            {deletingLoading ? "Deleting..." : "Delete Adjuster"}
          </button>
        </div>
      </div>
    </div>
  );
};
