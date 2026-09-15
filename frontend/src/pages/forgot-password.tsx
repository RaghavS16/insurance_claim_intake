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

        {/* Right Side: Value Proposition & Graphic (Hidden on Mobile) */}
        <div className="hidden lg:flex lg:w-1/2 relative bg-[#FFFFFF] overflow-hidden flex-col items-center justify-center p-16 border-l border-[#e0e3e5]">
          {/* Animated Background Wave Graphic */}
          <div className="absolute inset-0 pointer-events-none opacity-25">
            <svg className="absolute w-[200%] h-full bottom-0 left-0 animate-wave" preserveAspectRatio="none" viewBox="0 0 1200 400">
              <path className="text-[#0EA5E9]" d="M0,250 C200,150 400,350 600,250 C800,150 1000,350 1200,250 C1400,150 1600,350 1800,250 C2000,150 2200,350 2400,250 L2400,400 L0,400 Z" fill="currentColor"></path>
            </svg>
            <svg className="absolute w-[200%] h-full bottom-0 left-0 animate-wave-slow opacity-60" preserveAspectRatio="none" viewBox="0 0 1200 400">
              <path className="text-[#0891B2]" d="M0,300 C300,200 600,400 900,300 C1200,200 1500,400 1800,300 C2100,200 2400,400 2700,300 L2700,400 L0,400 Z" fill="currentColor"></path>
            </svg>
          </div>

          {/* Content Overlay */}
          <div className="relative z-10 max-w-lg px-12 text-center flex flex-col items-center">
            {/* Graphic Element Indicator */}
            <div className="mb-10 relative flex items-center justify-center w-24 h-24">
              <div className="absolute inset-0 rounded-full border-2 border-[#0891B2] opacity-30 animate-[ping_3s_cubic-bezier(0,0,0.2,1)_infinite]"></div>
              <div className="absolute inset-2 rounded-full border-2 border-[#0891B2] opacity-50 animate-[ping_3s_cubic-bezier(0,0,0.2,1)_infinite_0.5s]"></div>
              <div className="w-14 h-14 rounded-full bg-[#0891B2] flex items-center justify-center text-white shadow-[0_0_40px_rgba(8,145,178,0.4)]">
                <span className="material-symbols-outlined fill text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  mic
                </span>
              </div>
            </div>

            <h2 className="font-headline text-3xl font-bold text-[#00647c] mb-4 tracking-tight">
              Clarity in every<br />conversation.
            </h2>
            <p className="font-body text-sm text-[#505f76] leading-relaxed">
              Securely regain access to your high-performance claim intelligence platform.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
