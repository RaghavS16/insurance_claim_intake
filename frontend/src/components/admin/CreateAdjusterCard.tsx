import React from "react";
import { SPECIALIZATION_OPTIONS } from "@/lib/constants";

interface CreateAdjusterCardProps {
  newAdjusterName: string;
  setNewAdjusterName: (v: string) => void;
  newAdjusterEmail: string;
  setNewAdjusterEmail: (v: string) => void;
  newAdjusterSpec: string;
  setNewAdjusterSpec: (v: string) => void;
  creatingAdjuster: boolean;
  adjusterError: string;
  createdAdjusterData: any;
  copiedPass: boolean;
  setCopiedPass: (v: boolean) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export const CreateAdjusterCard: React.FC<CreateAdjusterCardProps> = ({
  newAdjusterName,
  setNewAdjusterName,
  newAdjusterEmail,
  setNewAdjusterEmail,
  newAdjusterSpec,
  setNewAdjusterSpec,
  creatingAdjuster,
  adjusterError,
  createdAdjusterData,
  copiedPass,
  setCopiedPass,
  onSubmit,
}) => {
  return (
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

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
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
  );
};
