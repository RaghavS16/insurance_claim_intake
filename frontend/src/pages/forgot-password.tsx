import React, { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }
    setError("");
    setSuccessMsg("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Failed to send reset code. Please try again.");
      }

      setSuccessMsg(data.message || "A 6-digit verification code has been sent to your email.");
      setTimeout(() => {
        router.push(`/verify-reset-password?email=${encodeURIComponent(email.trim())}`);
      }, 1200);
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#f7f9fb] text-[#191c1e] font-body min-h-screen flex items-center justify-center overflow-x-hidden selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Split Screen Layout */}
      <div className="flex w-full min-h-screen bg-[#f7f9fb]">
        {/* Left Side: Form Area */}
        <div className="w-full lg:w-1/2 flex flex-col justify-center px-6 sm:px-12 lg:px-16 py-12 relative bg-white lg:bg-transparent">
          {/* Logo / Brand Anchor */}
          <div className="absolute top-6 left-6 lg:left-12 lg:top-8 flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[#0891b2] flex items-center justify-center text-white">
              <span className="material-symbols-outlined fill text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
                graphic_eq
              </span>
            </div>
            <span className="font-headline text-xl font-bold text-[#0891b2] tracking-tight">InsureClaimAI</span>
          </div>

          {/* Form Container */}
          <div className="w-full max-w-md mx-auto space-y-6 mt-16 lg:mt-0">
            {/* Header */}
            <div className="space-y-2">
              <Link
                href="/login"
                className="inline-flex items-center text-[#505f76] hover:text-[#0891b2] transition-colors duration-200 group mb-4 text-xs font-label font-medium"
              >
                <span className="material-symbols-outlined text-sm mr-1 group-hover:-translate-x-1 transition-transform">
                  arrow_back
                </span>
                <span>Back to Login</span>
              </Link>
              <h1 className="font-headline text-3xl font-bold text-[#191c1e]">Reset Password</h1>
              <p className="font-body text-sm text-[#505f76]">
                Enter your email to receive a 6-digit verification code.
              </p>
            </div>

            {error && (
              <div className="p-3.5 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-xs text-[#93000a] flex items-start gap-2">
                <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
                <span className="leading-snug">{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="p-3.5 bg-emerald-50 border border-emerald-500/30 rounded-lg text-xs text-emerald-800 flex items-start gap-2">
                <span className="material-symbols-outlined text-base text-emerald-600">check_circle</span>
                <span className="leading-snug">{successMsg}</span>
              </div>
            )}

            {/* Form */}
            <form className="space-y-5" onSubmit={handleSubmit}>
              {/* Email Input */}
              <div className="space-y-1.5 relative">
                <label className="font-label text-xs font-medium text-[#191c1e] block" htmlFor="email">
                  Email Address
                </label>
                <div className="relative">
                  <input
                    id="email"
                    name="email"
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input-minimal w-full bg-white border border-[#bdc8ce] rounded-lg px-4 py-3 text-sm text-[#191c1e] focus:outline-none placeholder:text-[#6e797e]"
                  />
                  <span className="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-[#6e797e] pointer-events-none text-xl">
                    mail
                  </span>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#0891b2] hover:bg-[#007f9d] text-white font-label text-xs font-semibold uppercase tracking-wider py-3.5 rounded-lg transition-colors duration-200 flex justify-center items-center gap-2 group cursor-pointer shadow-sm disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                    <span>Sending Code...</span>
                  </>
                ) : (
                  <>
                    <span>Send Reset Code</span>
                    <span className="material-symbols-outlined text-base group-hover:translate-x-1 transition-transform">
                      arrow_forward
                    </span>
                  </>
                )}
              </button>
            </form>

            {/* Help Link */}
            <div className="text-center mt-6">
              <p className="font-body text-xs text-[#505f76]">
                Having trouble?{" "}
                <Link href="/login" className="text-[#0891b2] hover:underline font-semibold transition-all">
                  Return to Login
                </Link>
              </p>
            </div>
          </div>
        </div>

        {/* Right Side: Branded Visual (Hidden on Mobile) */}
        <div className="hidden lg:flex lg:w-1/2 bg-[#f2f4f6] relative items-center justify-center overflow-hidden border-l border-[#e0e3e5]">
          {/* Atmospheric Background Effect */}
          <div className="absolute inset-0 z-0 bg-gradient-to-br from-[#f2f4f6] via-[#f7f9fb] to-[#b7eaff]/20"></div>

          {/* Central Visual Concept */}
          <div className="relative z-10 flex flex-col items-center justify-center max-w-sm text-center space-y-6 px-8">
            {/* Stylized Audio Wave / AI Indicator */}
            <div className="relative w-32 h-32 flex items-center justify-center">
              <div className="absolute inset-0 bg-[#0891b2]/10 rounded-full animate-ping" style={{ animationDuration: "3s" }}></div>
              <div className="absolute inset-4 bg-[#0891b2]/20 rounded-full animate-pulse" style={{ animationDuration: "2s" }}></div>
              <div className="w-16 h-16 bg-white rounded-full shadow-sm flex items-center justify-center z-10 border border-[#bdc8ce]/40">
                <span className="material-symbols-outlined fill text-[#0891b2] text-4xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  graphic_eq
                </span>
              </div>
            </div>

            {/* Tagline */}
            <div className="space-y-3">
              <h2 className="font-headline text-2xl font-bold text-[#191c1e]">Clarity in every conversation.</h2>
              <p className="font-body text-sm text-[#505f76] leading-relaxed">
                Securely regain access to your high-performance claim intelligence platform.
              </p>
            </div>
          </div>

          {/* Subtle Grid Overlay */}
          <div
            className="absolute inset-0 pointer-events-none opacity-40"
            style={{
              backgroundImage: "linear-gradient(to right, rgba(0,0,0,0.03) 1px, transparent 1px), linear-gradient(to bottom, rgba(0,0,0,0.03) 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          ></div>
        </div>
      </div>
    </div>
  );
}
