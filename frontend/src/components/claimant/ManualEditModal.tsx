import React from "react";
import { SUPPORTED_INSURANCE_TYPES } from "@/lib/constants";

interface ManualEditModalProps {
  editingField: string | null;
  editValue: string;
  setEditValue: (v: string) => void;
  onClose: () => void;
  onSave: () => void;
}

export const ManualEditModal: React.FC<ManualEditModalProps> = ({
  editingField,
  editValue,
  setEditValue,
  onClose,
  onSave,
}) => {
  if (!editingField) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fadeIn">
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 max-w-md w-full shadow-2xl">
        <h3 className="font-headline text-lg font-bold text-[#191c1e] mb-1">
          Edit {editingField.replace(/_/g, " ").toUpperCase()}
        </h3>
        <p className="font-body text-xs text-[#505f76] mb-4">
          Update the value manually or let the voice assistant extract it during conversation.
        </p>

        {editingField === "insurance_type" ? (
          <select
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
          >
            <option value="">Select Insurance Type</option>
            {Object.entries(SUPPORTED_INSURANCE_TYPES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        ) : editingField === "event_date" ? (
          <input
            type="date"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
          />
        ) : editingField === "event_description" ? (
          <textarea
            rows={4}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4 resize-none"
          />
        ) : (
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] mb-4"
          />
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#f7f9fb] border border-[#bdc8ce] text-[#505f76] text-xs font-semibold hover:text-[#191c1e] cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            className="px-4 py-2 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white text-xs font-semibold shadow-sm cursor-pointer"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};
