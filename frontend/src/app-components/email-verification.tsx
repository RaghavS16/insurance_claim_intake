"use client";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, MailCheck, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/app-components/ui";

export function EmailVerificationPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [email, setEmail] = useState(params.get("email") || "");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api("/api/v1/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ email, otp })
      });
      setMessage("Email verified successfully! Redirecting to sign in…");
      setTimeout(() => router.replace("/login"), 800);
    } catch (err: any) {
      setError(err.message || "Verification failed. Check the code and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError("");
    setMessage("");
    try {
      const r = await api<any>("/api/v1/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email })
      });
      setMessage(r.message || "A fresh verification code has been dispatched.");
    } catch (err: any) {
      setError(err.message || "Unable to resend the verification code.");
    }
  }

  return (
    <main className="auth-split-shell">
      {/* Left Feature Showcase */}
      <section className="auth-hero-pane" aria-label="Security Overview">
        <div className="auth-hero-brand">
          <span className="brand-mark">F</span>
          <span>Flowa</span>
          <span className="brand-tag">Security</span>
        </div>

        <div className="auth-hero-body">
          <div className="auth-hero-eyebrow">
            <MailCheck size={13} />
            <span>Identity Proofing</span>
          </div>

          <h2 className="auth-hero-title">
            Verifying Your Secure Communication Channel
          </h2>
          <p className="auth-hero-desc">
            To safeguard claims dossiers, policy benefits, and adjuster correspondence, we verify that your email address is active and owned by you.
          </p>

          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <CheckCircle2 size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Cryptographic Time-Limited OTP</b>
                <span>Codes expire automatically after 10 minutes</span>
              </div>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <CheckCircle2 size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Tamper-Proof Audit Logging</b>
                <span>All verification attempts are tied to the tenant audit trail</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-hero-footer">
          <span>Flowa Automated Verification Gateway · SOC2 Type II</span>
        </div>
      </section>

      {/* Right Form Pane */}
      <section className="auth-form-pane">
        <div className="auth-form-container">
          <header className="auth-form-header">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="brand" style={{ margin: 0 }}>
                <span className="brand-mark">F</span>
                <span>Flowa</span>
              </div>
              <ThemeToggle />
            </div>
            <h1 className="auth-form-title">Verify your email</h1>
            <p className="auth-form-subtitle">
              Enter the verification code sent to your email address before signing in.
            </p>
          </header>

          <form className="form" onSubmit={verify}>
            <label>
              Email address
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@organization.com"
                autoComplete="email"
                required
              />
            </label>

            <label>
              Verification code
              <input
                inputMode="numeric"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 8))}
                placeholder="123456"
                autoComplete="one-time-code"
                required
              />
            </label>

            {error && (
              <div className="error" role="alert">
                <AlertCircle size={15} />
                <span>{error}</span>
              </div>
            )}

            {message && (
              <div className="notice" role="status">
                <CheckCircle2 size={15} />
                <span>{message}</span>
              </div>
            )}

            <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%", height: 42 }}>
              {busy ? "Verifying…" : "Verify email"}
            </button>

            <button
              className="btn"
              type="button"
              onClick={resend}
              disabled={!email || busy}
              style={{ width: "100%", height: 40, display: "flex", gap: 8 }}
            >
              <RotateCcw size={14} />
              <span>Resend code</span>
            </button>

            <div style={{ textAlign: "center", fontSize: 13, marginTop: 4 }}>
              <Link className="link" href="/login">
                Back to sign in
              </Link>
            </div>
          </form>
        </div>
      </section>
    </main>
  );
}
