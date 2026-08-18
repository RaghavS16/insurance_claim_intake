"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Role = "CLAIMANT" | "ADJUSTER";

export default function SignupPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("CLAIMANT");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [adjusterCode, setAdjusterCode] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !password || !confirmPassword) return setError("Please fill in all required fields.");
    if (role === "ADJUSTER" && !adjusterCode.trim()) return setError("Adjuster registration code is required.");
    if (password !== confirmPassword) return setError("Passwords do not match.");
    if (password.length < 8 || !/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~`])/.test(password)) {
      return setError("Password must contain 8+ characters, uppercase, lowercase, digit, and special character.");
    }

    setError(""); setSuccess(""); setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/signup`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), phone: phone.trim() || null, password, confirm_password: confirmPassword, role, adjuster_code: role === "ADJUSTER" ? adjusterCode.trim() : null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Sign up failed. Please try again.");
      setSuccess(`${role === "ADJUSTER" ? "Adjuster" : "Claimant"} account created. Redirecting to login...`);
      setTimeout(() => router.push("/login"), 1200);
    } catch (err: any) {
      setError(err.message || "An error occurred during signup.");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900/70 border border-slate-800 rounded-3xl p-8 shadow-2xl">
        <div className="text-center mb-6"><h1 className="text-2xl font-bold text-white">Create Account</h1><p className="text-sm text-slate-400 mt-2">Choose your application role.</p></div>
        <div className="grid grid-cols-2 gap-2 mb-5">
          {(["CLAIMANT", "ADJUSTER"] as Role[]).map((item) => <button key={item} type="button" onClick={() => setRole(item)} className={`rounded-xl py-3 text-sm font-semibold border ${role === item ? "border-cyan-500 bg-cyan-500/10 text-cyan-300" : "border-slate-700 text-slate-400"}`}>{item === "CLAIMANT" ? "Claimant" : "Adjuster"}</button>)}
        </div>
        {error && <div className="mb-4 p-3 rounded-xl bg-rose-950/70 border border-rose-700/50 text-sm text-rose-200">{error}</div>}
        {success && <div className="mb-4 p-3 rounded-xl bg-emerald-950/70 border border-emerald-700/50 text-sm text-emerald-200">{success}</div>}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input aria-label="Full name" placeholder="Full name *" value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" />
          <input aria-label="Email" type="email" placeholder="Email address *" value={email} onChange={(e) => setEmail(e.target.value)} className="input" />
          <input aria-label="Phone" type="tel" placeholder="Phone number (optional)" value={phone} onChange={(e) => setPhone(e.target.value)} className="input" />
          {role === "ADJUSTER" && <input aria-label="Adjuster registration code" type="password" placeholder="Private adjuster registration code *" value={adjusterCode} onChange={(e) => setAdjusterCode(e.target.value)} className="input" />}
          <div className="grid grid-cols-2 gap-3"><input aria-label="Password" type="password" placeholder="Password *" value={password} onChange={(e) => setPassword(e.target.value)} className="input" /><input aria-label="Confirm password" type="password" placeholder="Confirm *" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input" /></div>
          <button type="submit" disabled={loading} className="w-full py-3.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 font-bold disabled:opacity-50">{loading ? "Creating..." : `Create ${role === "ADJUSTER" ? "Adjuster" : "Claimant"} Account`}</button>
        </form>
        <p className="text-center text-xs text-slate-500 mt-6">Already have an account? <Link href="/login" className="text-cyan-400">Log in</Link></p>
      </div>
      <style jsx>{`.input{background:rgba(2,6,23,.5);border:1px solid rgba(51,65,85,.8);border-radius:.75rem;padding:.8rem 1rem;font-size:.875rem;outline:none;width:100%;color:#e2e8f0}.input:focus{border-color:#06b6d4}`}</style>
    </div>
  );
}
