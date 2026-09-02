import React, { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !password.trim() || !confirmPassword.trim()) {
      setError("Please fill in all required fields.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~`])/.test(password)) {
      setError("Password must contain at least one uppercase letter, one lowercase letter, one digit, and one special character.");
      return;
    }
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim(),
          phone: phone.trim() || null,
          password,
          confirm_password: confirmPassword,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Sign up failed. Please try again.");
      }

      setSuccess("Account created successfully! Redirecting to login...");
      setTimeout(() => {
        router.push("/login");
      }, 1500);
    } catch (err: any) {
      setError(err.message || "An error occurred during signup.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#FFFFFF] text-[#191c1e] font-body min-h-screen flex antialiased selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Left Side: Registration Form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center px-6 sm:px-12 lg:px-16 py-12 bg-[#FFFFFF] z-10 relative">
        {/* Mobile Logo */}
        <div className="lg:hidden mb-8 flex items-center gap-2">
          <span className="material-symbols-outlined fill text-[#0891B2] text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            graphic_eq
          </span>
          <span className="font-headline text-2xl font-bold text-[#191c1e]">InsureClaimAI</span>
        </div>

        <div className="max-w-md w-full mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="font-headline text-3xl font-bold text-[#191c1e] mb-2">Create Account</h1>
            <p className="font-body text-sm text-[#505f76]">
              Register to manage your claims with voice-first assistance.
            </p>
          </div>

          {error && (
            <div className="mb-6 p-3.5 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-xs text-[#93000a] flex items-start gap-2">
              <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
              <span className="leading-snug">{error}</span>
            </div>
          )}

          {success && (
            <div className="mb-6 p-3.5 bg-emerald-50 border border-emerald-500/30 rounded-lg text-xs text-emerald-800 flex items-start gap-2">
              <span className="material-symbols-outlined text-base text-emerald-600">check_circle</span>
              <span className="leading-snug">{success}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Full Name */}
            <div className="flex flex-col">
              <label className="font-label text-xs font-medium text-[#505f76] mb-1" htmlFor="fullName">
                Full Name *
              </label>
              <input
                id="fullName"
                name="fullName"
                type="text"
                required
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="input-minimal bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
              />
            </div>

            {/* Email Address */}
            <div className="flex flex-col">
              <label className="font-label text-xs font-medium text-[#505f76] mb-1" htmlFor="email">
                Email Address *
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                placeholder="john@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-minimal bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
              />
            </div>

            {/* Phone Number */}
            <div className="flex flex-col">
              <label className="font-label text-xs font-medium text-[#505f76] mb-1" htmlFor="phone">
                Phone Number (Optional)
              </label>
              <input
                id="phone"
                name="phone"
                type="tel"
                placeholder="+91 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="input-minimal bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
              />
            </div>

            {/* Password */}
            <div className="flex flex-col">
              <label className="font-label text-xs font-medium text-[#505f76] mb-1" htmlFor="password">
                Password *
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 pr-10 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#505f76] hover:text-[#191c1e]"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? "visibility" : "visibility_off"}
                  </span>
                </button>
              </div>
            </div>

            {/* Confirm Password */}
            <div className="flex flex-col">
              <label className="font-label text-xs font-medium text-[#505f76] mb-1" htmlFor="confirmPassword">
                Confirm Password *
              </label>
              <div className="relative">
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type={showConfirmPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="input-minimal w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 pr-10 font-body text-sm text-[#191c1e] placeholder:text-[#6e797e]"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#505f76] hover:text-[#191c1e]"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showConfirmPassword ? "visibility" : "visibility_off"}
                  </span>
                </button>
              </div>
            </div>

            {/* Actions */}
            <div className="pt-3 space-y-3">
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#0891B2] hover:bg-[#007f9d] text-white font-label font-semibold text-sm py-3 rounded-lg transition-colors flex justify-center items-center gap-2 cursor-pointer shadow-sm disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                    <span>Creating Account...</span>
                  </>
                ) : (
                  "Create Account"
                )}
              </button>

              <div className="text-center">
                <span className="font-body text-xs text-[#505f76]">Already have an account?</span>
                <Link href="/login" className="font-label font-semibold text-xs text-[#0891B2] hover:underline ml-1.5">
                  Sign In
                </Link>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Right Side: Branding Area */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-[#FFFFFF] overflow-hidden flex-col justify-center items-center p-16 border-l border-[#e0e3e5]">
        {/* Animated Background Wave Graphic */}
        <div className="absolute inset-0 pointer-events-none opacity-25">
          <svg className="absolute w-[200%] h-full bottom-0 left-0 animate-wave" preserveAspectRatio="none" viewBox="0 0 1200 400">
            <path className="text-[#0EA5E9]" d="M0,250 C200,150 400,350 600,250 C800,150 1000,350 1200,250 C1400,150 1600,350 1800,250 C2000,150 2200,350 2400,250 L2400,400 L0,400 Z" fill="currentColor"></path>
          </svg>
          <svg className="absolute w-[200%] h-full bottom-0 left-0 animate-wave-slow opacity-60" preserveAspectRatio="none" viewBox="0 0 1200 400">
            <path className="text-[#0891B2]" d="M0,300 C300,200 600,400 900,300 C1200,200 1500,400 1800,300 C2100,200 2400,400 2700,300 L2700,400 L0,400 Z" fill="currentColor"></path>
          </svg>
        </div>

        {/* Top Branding Logo */}
        <div className="absolute top-12 left-12 flex items-center gap-2 opacity-80 z-10">
          <span className="material-symbols-outlined fill text-[#0891B2] text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            graphic_eq
          </span>
          <span className="font-headline text-xl font-bold text-[#191c1e] tracking-tight">InsureClaimAI</span>
        </div>

        {/* Central Visualization */}
        <div className="relative z-10 flex flex-col items-center max-w-md text-center">
          {/* Minimalist Voice Indicator */}
          <div className="relative w-32 h-32 mb-8 flex justify-center items-center">
            {/* Outer Pulse Rings */}
            <div className="absolute inset-0 rounded-full border-2 border-[#0891B2] opacity-30 animate-ping" style={{ animationDuration: "3s" }}></div>
            <div className="absolute inset-4 rounded-full border-2 border-[#0891B2] opacity-50 animate-ping" style={{ animationDuration: "2s", animationDelay: "0.5s" }}></div>
            {/* Core Mic */}
            <div className="bg-white rounded-full w-20 h-20 flex justify-center items-center shadow-[0_10px_30px_rgba(0,0,0,0.08)] z-20 border border-[#bdc8ce]">
              <span className="material-symbols-outlined fill text-[#0891B2] text-4xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                graphic_eq
              </span>
            </div>
          </div>

          {/* Copy */}
          <h2 className="font-headline text-3xl font-bold text-[#191c1e] mb-3 tracking-tight">Clarity in every conversation.</h2>
          <p className="font-body text-sm text-[#505f76] leading-relaxed">
            Our voice-centric AI interface recedes to the background, allowing your claims data and seamless conversation to take center stage. Fast, secure, and quietly intelligent.
          </p>
        </div>
      </div>
    </div>
  );
}
