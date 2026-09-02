import React, { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("Please fill in all fields.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Invalid email or password.");
      }

      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);

      // Fetch user role to determine redirection
      const meRes = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });

      if (!meRes.ok) {
        throw new Error("Failed to retrieve user profile.");
      }

      const meData = await meRes.json();
      if (meData.role === "CLAIMANT") {
        router.push("/claimant");
      } else if (meData.role === "ADJUSTER") {
        router.push("/adjuster");
      } else if (meData.role === "ADMIN") {
        router.push("/admin");
      } else {
        setError("Invalid user role.");
      }
    } catch (err: any) {
      setError(err.message || "An error occurred during login.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#FFFFFF] font-body text-[#191c1e] antialiased min-h-screen flex selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Left Side: Authentication Form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center px-6 sm:px-12 lg:px-16 py-12 bg-[#FFFFFF] z-10 relative">
        <div className="mx-auto w-full max-w-sm lg:w-[380px]">
          {/* Brand Identity */}
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 rounded-lg bg-[#F1F5F9] border border-[#bdc8ce] flex items-center justify-center text-[#0891B2]">
              <span className="material-symbols-outlined fill text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                graphic_eq
              </span>
            </div>
            <span className="font-headline text-2xl font-bold text-[#00647c] tracking-tight">InsureClaimAI</span>
          </div>

          {/* Header */}
          <div className="mb-8">
            <h1 className="font-headline text-3xl font-bold text-[#191c1e] mb-2">Welcome back</h1>
            <p className="font-body text-sm text-[#505f76]">
              Sign in to continue to your dashboard and manage your audio flows.
            </p>
          </div>

          {error && (
            <div className="mb-6 p-3.5 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-xs text-[#93000a] flex items-start gap-2">
              <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
              <span className="leading-snug">{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email Input */}
            <div>
              <label className="block font-label text-xs font-medium text-[#505f76] mb-1.5" htmlFor="email">
                Email address
              </label>
              <div className="relative">
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-minimal block w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] placeholder:text-[#6e797e] focus:outline-none"
                />
              </div>
            </div>

            {/* Password Input */}
            <div>
              <label className="block font-label text-xs font-medium text-[#505f76] mb-1.5" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-minimal block w-full bg-[#f7f9fb] border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 pr-10 text-sm text-[#191c1e] placeholder:text-[#6e797e] focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#505f76] hover:text-[#191c1e] transition-colors"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? "visibility" : "visibility_off"}
                  </span>
                </button>
              </div>
            </div>

            {/* Actions Row */}
            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  id="remember-me"
                  name="remember-me"
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-4 w-4 rounded border-[#bdc8ce] text-[#0891B2] focus:ring-[#0891B2] cursor-pointer"
                />
                <span className="font-body text-xs text-[#505f76]">Remember me</span>
              </label>
              <div className="text-xs">
                <Link
                  href="/forgot-password"
                  className="font-label text-[#0891B2] hover:text-[#00647c] transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
            </div>

            {/* Submit Button */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center gap-2 py-3 px-4 rounded-lg bg-[#0891B2] hover:bg-[#007f9d] text-white font-label text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-[#0891B2] transition-all active:scale-[0.99] disabled:opacity-50 cursor-pointer shadow-sm"
              >
                {loading ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                    <span>Signing in...</span>
                  </>
                ) : (
                  "Sign in"
                )}
              </button>
            </div>
          </form>

          {/* Footer Link */}
          <p className="mt-8 text-center font-body text-xs text-[#505f76]">
            Don&apos;t have an account?{" "}
            <Link href="/signup" className="font-label font-semibold text-[#0891B2] hover:text-[#00647c] transition-colors ml-1">
              Create Account
            </Link>
          </p>
        </div>
      </div>

      {/* Right Side: Value Proposition & Graphic */}
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
            Experience the next generation of voice-centric AI. We strip away the noise so you can focus entirely on the signal.
          </p>
        </div>
      </div>
    </div>
  );
}
