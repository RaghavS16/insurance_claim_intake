import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function VerifyResetPasswordPage() {
  const router = useRouter();
  const { email: queryEmail } = router.query;

  const [email, setEmail] = useState("");
  const [otpDigits, setOtpDigits] = useState(["", "", "", "", "", ""]);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (router.isReady && router.query.email && typeof router.query.email === "string") {
      setEmail(router.query.email);
    }
  }, [router.isReady, router.query.email]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleOtpChange = (index: number, val: string) => {
    // Handle single character
    const cleaned = val.replace(/\D/g, "");
    if (!cleaned) {
      const next = [...otpDigits];
      next[index] = "";
      setOtpDigits(next);
      return;
    }

    // If user pasted multiple digits
    if (cleaned.length > 1) {
      const next = [...otpDigits];
      for (let i = 0; i < 6 && i < cleaned.length; i++) {
        next[i] = cleaned[i];
      }
      setOtpDigits(next);
      const focusIndex = Math.min(cleaned.length, 5);
      inputRefs.current[focusIndex]?.focus();
      return;
    }

    const next = [...otpDigits];
    next[index] = cleaned;
    setOtpDigits(next);

    // Auto advance
    if (index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otpDigits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasteData = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasteData) return;

    const next = [...otpDigits];
    for (let i = 0; i < 6; i++) {
      next[i] = pasteData[i] || "";
    }
    setOtpDigits(next);
    const focusIndex = Math.min(pasteData.length, 5);
    inputRefs.current[focusIndex]?.focus();
  };

  const handleResendCode = async () => {
    const targetEmail = (email || (typeof router.query.email === "string" ? router.query.email : "")).trim();
    if (!targetEmail) {
      setError("Please enter the email address for your account above.");
      return;
    }
    if (resendCooldown > 0) return;

    setResending(true);
    setError("");
    setSuccessMsg("");

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: targetEmail }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Failed to resend code.");
      }
      setSuccessMsg("A new verification code has been sent to your email (and logged in terminal).");
      setResendCooldown(60); // 60 seconds cooldown
    } catch (err: any) {
      setError(err.message || "Failed to resend verification code.");
    } finally {
      setResending(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const fullOtp = otpDigits.join("");

    if (!email.trim()) {
      setError("Please enter the email associated with your account.");
      return;
    }
    if (fullOtp.length !== 6) {
      setError("Please enter the complete 6-digit authentication code.");
      return;
    }
    if (!newPassword.trim() || !confirmPassword.trim()) {
      setError("Please enter and confirm your new password.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~`])/.test(newPassword)) {
      setError("Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.");
      return;
    }

    setError("");
    setSuccessMsg("");
    setLoading(true);

    try {
      // Step 1: Verify OTP & obtain reset_token
      const verifyRes = await fetch(`${API_BASE}/api/v1/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          otp: fullOtp,
        }),
      });

      const verifyData = await verifyRes.json().catch(() => ({}));
      if (!verifyRes.ok) {
        throw new Error(verifyData.detail || "Invalid or expired verification code.");
      }

      const resetToken = verifyData.reset_token;
      if (!resetToken) {
        throw new Error("Failed to obtain password reset authorization.");
      }

      // Step 2: Reset password with verified token
      const resetRes = await fetch(`${API_BASE}/api/v1/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reset_token: resetToken,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });

      const resetData = await resetRes.json().catch(() => ({}));
      if (!resetRes.ok) {
        throw new Error(resetData.detail || "Failed to update password. Please try again.");
      }

      setSuccessMsg("Password updated successfully! Redirecting to login...");
      setTimeout(() => {
        router.push("/login");
      }, 1800);
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f9fb] font-body text-[#191c1e] selection:bg-[#b7eaff] selection:text-[#001f28]">
      {/* Transactional layout */}
      <div className="min-h-screen flex flex-col md:flex-row">
        {/* Left Side: Form Area */}
        <div className="w-full md:w-1/2 flex flex-col justify-center px-6 sm:px-12 lg:px-16 py-12 bg-white md:bg-[#f7f9fb]">
          <div className="max-w-md w-full mx-auto">
            {/* Brand Anchor / Header */}
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-4">
                <span className="material-symbols-outlined fill text-[#00647c] text-[28px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                  shield_locked
                </span>
                <span className="font-headline text-xl font-bold text-[#00647c] tracking-tight">InsureClaimAI</span>
              </div>
              <h1 className="font-headline text-2xl sm:text-3xl font-bold text-[#191c1e] mb-1.5">Verify Identity</h1>
              <p className="font-body text-sm text-[#505f76]">
                {email ? (
                  <>
                    We&apos;ve sent a 6-digit code to <span className="font-semibold text-[#191c1e]">{email}</span>.
                  </>
                ) : (
                  "We've sent a 6-digit code to your email."
                )}
              </p>
            </div>

            {error && (
              <div className="mb-5 p-3.5 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-xs text-[#93000a] flex items-start gap-2">
                <span className="material-symbols-outlined text-base text-[#ba1a1a]">error</span>
                <span className="leading-snug">{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="mb-5 p-3.5 bg-emerald-50 border border-emerald-500/30 rounded-lg text-xs text-emerald-800 flex items-start gap-2">
                <span className="material-symbols-outlined text-base text-emerald-600">check_circle</span>
                <span className="leading-snug">{successMsg}</span>
              </div>
            )}

            <form className="space-y-6" onSubmit={handleSubmit}>
              {/* Email confirmation field (if not provided via query) */}
              {!queryEmail && (
                <div>
                  <label className="block font-label text-xs font-semibold text-[#505f76] mb-1.5 uppercase tracking-wider" htmlFor="verify-email">
                    Account Email
                  </label>
                  <input
                    id="verify-email"
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input-minimal w-full bg-white border border-[#bdc8ce] rounded-lg px-3.5 py-2.5 text-sm text-[#191c1e] focus:outline-none"
                  />
                </div>
              )}

              {/* OTP Input Section */}
              <div>
                <label className="block font-label text-xs font-semibold text-[#505f76] mb-2.5 uppercase tracking-wider">
                  Authentication Code
                </label>
                <div className="flex gap-2 justify-between">
                  {otpDigits.map((digit, idx) => (
                    <input
                      key={idx}
                      ref={(el) => {
                        inputRefs.current[idx] = el;
                      }}
                      className="w-12 h-14 text-center font-headline text-xl font-bold bg-white border border-[#bdc8ce] rounded-lg focus:border-[#00647c] focus:ring-2 focus:ring-[#00647c]/20 outline-none transition-all"
                      maxLength={1}
                      placeholder="•"
                      type="text"
                      inputMode="numeric"
                      value={digit}
                      onChange={(e) => handleOtpChange(idx, e.target.value)}
                      onKeyDown={(e) => handleOtpKeyDown(idx, e)}
                      onPaste={handleOtpPaste}
                    />
                  ))}
                </div>
                <div className="mt-3.5 flex justify-between items-center text-xs">
                  <span className="font-body text-[#505f76]">Didn&apos;t receive the code?</span>
                  <button
                    type="button"
                    onClick={handleResendCode}
                    disabled={resending || resendCooldown > 0}
                    className="font-label text-[#00647c] hover:text-[#007f9d] transition-colors uppercase tracking-wider font-semibold disabled:opacity-50 cursor-pointer"
                  >
                    {resending ? "Sending..." : resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend Code"}
                  </button>
                </div>
              </div>

              <hr className="border-t border-[#e0e3e5] my-4" />

              {/* Password Reset Section */}
              <div className="space-y-4">
                <div>
                  <label className="block font-label text-xs font-semibold text-[#505f76] mb-1.5 uppercase tracking-wider" htmlFor="new_password">
                    New Password
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#505f76] text-lg">
                      lock
                    </span>
                    <input
                      className="input-minimal w-full bg-white border border-[#bdc8ce] rounded-lg py-2.5 pl-10 pr-10 text-sm text-[#191c1e] focus:outline-none"
                      id="new_password"
                      placeholder="••••••••"
                      type={showNewPassword ? "text" : "password"}
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#505f76] hover:text-[#191c1e]"
                    >
                      <span className="material-symbols-outlined text-base">
                        {showNewPassword ? "visibility" : "visibility_off"}
                      </span>
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block font-label text-xs font-semibold text-[#505f76] mb-1.5 uppercase tracking-wider" htmlFor="confirm_password">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#505f76] text-lg">
                      lock_reset
                    </span>
                    <input
                      className="input-minimal w-full bg-white border border-[#bdc8ce] rounded-lg py-2.5 pl-10 pr-10 text-sm text-[#191c1e] focus:outline-none"
                      id="confirm_password"
                      placeholder="••••••••"
                      type={showConfirmPassword ? "text" : "password"}
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#505f76] hover:text-[#191c1e]"
                    >
                      <span className="material-symbols-outlined text-base">
                        {showConfirmPassword ? "visibility" : "visibility_off"}
                      </span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold uppercase tracking-wider py-3.5 rounded-lg transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-sm disabled:opacity-50"
                >
                  {loading ? (
                    <>
                      <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                      <span>Updating Password...</span>
                    </>
                  ) : (
                    <>
                      <span>Update Password</span>
                      <span className="material-symbols-outlined fill text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
                        arrow_forward
                      </span>
                    </>
                  )}
                </button>
                <div className="mt-5 text-center">
                  <Link
                    href="/login"
                    className="font-body text-xs text-[#505f76] hover:text-[#00647c] transition-colors inline-flex items-center gap-1.5"
                  >
                    <span className="material-symbols-outlined text-sm">arrow_back</span>
                    <span>Return to Login</span>
                  </Link>
                </div>
              </div>
            </form>
          </div>

          {/* Minimalist Footer */}
          <div className="mt-12 text-center">
            <p className="font-label text-xs text-[#505f76]/70">
              Secure identity verification powered by InsureClaimAI
            </p>
          </div>
        </div>

        {/* Right Side: Branded Visual */}
        <div className="hidden md:flex md:w-1/2 bg-[#eceef0] relative overflow-hidden flex-col justify-center items-center p-12 border-l border-[#e0e3e5]">
          {/* Tonal layering overlay */}
          <div className="absolute inset-0 bg-[#00647c]/5 backdrop-blur-[2px]"></div>

          {/* Central Iconography Island */}
          <div className="relative z-10 bg-white/90 backdrop-blur-xl p-8 rounded-full shadow-lg border border-[#bdc8ce]/40 flex items-center justify-center animate-pulse">
            <span className="material-symbols-outlined text-[#00647c] text-[64px]" style={{ fontVariationSettings: "'FILL' 0", fontWeight: 300 }}>
              graphic_eq
            </span>
          </div>

          <div className="relative z-10 mt-8 text-center px-8">
            <h2 className="font-headline text-2xl font-bold text-[#191c1e] mb-2">Voice-Powered Security</h2>
            <p className="font-body text-sm text-[#505f76] max-w-md mx-auto leading-relaxed">
              Our systems utilize advanced verification to ensure your claims data remains confidential, secure, and accessible only to you.
            </p>
          </div>

          {/* Decorative structural elements */}
          <div className="absolute top-0 right-0 p-8 pointer-events-none">
            <div className="flex gap-1.5 opacity-25">
              <div className="w-1.5 h-12 bg-[#00647c] rounded-full"></div>
              <div className="w-1.5 h-8 bg-[#00647c] rounded-full mt-2"></div>
              <div className="w-1.5 h-16 bg-[#00647c] rounded-full -mt-2"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
