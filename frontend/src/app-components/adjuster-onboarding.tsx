"use client";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, CheckCircle2, Fingerprint, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { assertWebAuthnSupport, prepareCreationOptions, serializeCredential } from "@/lib/webauthn";
import { ThemeToggle } from "@/app-components/ui";

export function AdjusterOnboardingPage() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [info, setInfo] = useState<any>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [step, setStep] = useState<"loading" | "form" | "passkey" | "done" | "error">("loading");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      setStep("error");
      setError("Invitation token is missing.");
      return;
    }
    api<any>("/api/v1/auth/onboarding/adjuster/" + encodeURIComponent(token), { skipAuth: true })
      .then((x) => {
        setInfo(x);
        setStep("form");
      })
      .catch((e) => {
        setError(e.message || "Invitation is invalid or expired.");
        setStep("error");
      });
  }, [token]);

  async function accept() {
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await api<any>("/api/v1/auth/onboarding/adjuster/accept", {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ token, password, confirm_password: confirm })
      });
      localStorage.setItem("access_token", r.setup_access_token);
      setStep("passkey");
    } catch (e: any) {
      setError(e.message || "Unable to complete onboarding.");
    } finally {
      setBusy(false);
    }
  }

  async function registerPasskey() {
    setBusy(true);
    setError("");
    try {
      if (window.isSecureContext === false) {
        throw Error("Passkey setup requires HTTPS or localhost. Open the secure application URL.");
      }
      assertWebAuthnSupport();
      const options = await api<any>("/api/v1/auth/passkey/registration/options", { method: "POST" });
      const credential = await navigator.credentials.create({
        publicKey: prepareCreationOptions(options.public_key)
      });
      if (!credential) throw Error("Passkey registration was cancelled.");
      await api("/api/v1/auth/passkey/registration/verify", {
        method: "POST",
        body: JSON.stringify({
          challenge_id: options.challenge_id,
          credential: serializeCredential(credential as PublicKeyCredential)
        })
      });
      localStorage.removeItem("access_token");
      setStep("done");
    } catch (e: any) {
      setError(e.message || "Unable to register your passkey.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-split-shell">
      {/* Left Feature Showcase */}
      <section className="auth-hero-pane" aria-label="Adjuster Onboarding">
        <div className="auth-hero-brand">
          <span className="brand-mark">F</span>
          <span>Flowa</span>
          <span className="brand-tag">Workbench</span>
        </div>

        <div className="auth-hero-body">
          <div className="auth-hero-eyebrow">
            <Sparkles size={13} />
            <span>Adjuster Activation</span>
          </div>

          <h2 className="auth-hero-title">
            Human-in-the-Loop Claim Adjudication
          </h2>
          <p className="auth-hero-desc">
            Welcome to the Flowa adjuster suite. Set up your privileged credentials and FIDO2 passkey to access claimant queues, AI copilot dossiers, and regulatory policy wording.
          </p>

          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <ShieldCheck size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Mandatory Passkey Security</b>
                <span>Privileged adjuster roles require biometric or hardware token activation</span>
              </div>
            </div>
            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <Lock size={14} />
              </div>
              <div className="auth-feature-text">
                <b>End-to-End Encrypted Audit Trail</b>
                <span>All decisions, claim reassignments, and notes are immutably signed</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-hero-footer">
          <span>Flowa Claims Systems · Adjuster Privileged Portal</span>
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

            {step === "loading" && (
              <>
                <h1 className="auth-form-title">Loading invitation</h1>
                <p className="auth-form-subtitle">Verifying your secure adjuster activation link…</p>
              </>
            )}

            {step === "error" && (
              <>
                <h1 className="auth-form-title">Invitation unavailable</h1>
                <p className="auth-form-subtitle">{error}</p>
              </>
            )}

            {step === "form" && (
              <>
                <h1 className="auth-form-title">Set up your adjuster account</h1>
                <p className="auth-form-subtitle">
                  Welcome {info?.name || "Adjuster"}. Create your password first, then proceed to biometric passkey enrollment.
                </p>
              </>
            )}

            {step === "passkey" && (
              <>
                <h1 className="auth-form-title">Register your passkey</h1>
                <p className="auth-form-subtitle">
                  Enroll your device biometrics (Touch ID / Windows Hello) or physical security key for instant, phishing-resistant access.
                </p>
              </>
            )}

            {step === "done" && (
              <>
                <h1 className="auth-form-title">You’re all set</h1>
                <p className="auth-form-subtitle">
                  Your adjuster account is fully configured with biometric security. Sign in to open your claims queue.
                </p>
              </>
            )}
          </header>

          {step === "error" && (
            <div style={{ display: "grid", gap: 16 }}>
              <div className="error" role="alert">
                <AlertCircle size={15} />
                <span>{error}</span>
              </div>
              <Link className="btn primary" href="/login" style={{ width: "100%", height: 42 }}>
                Return to sign in
              </Link>
            </div>
          )}

          {step === "form" && (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault();
                accept();
              }}
            >
              <label>
                Assigned email
                <input value={info?.email || ""} readOnly disabled />
              </label>

              <label>
                Specialization
                <input value={info?.specialization ? info.specialization.replace(/_/g, " ").toUpperCase() : "GENERAL"} readOnly disabled />
              </label>

              <label>
                Create password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </label>

              <label>
                Confirm password
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </label>

              {error && (
                <div className="error" role="alert">
                  <AlertCircle size={15} />
                  <span>{error}</span>
                </div>
              )}

              <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%", height: 42 }}>
                {busy ? "Activating account…" : "Continue to passkey setup"}
              </button>
            </form>
          )}

          {step === "passkey" && (
            <div style={{ display: "grid", gap: 16 }}>
              {error && (
                <div className="error" role="alert">
                  <AlertCircle size={15} />
                  <span>{error}</span>
                </div>
              )}

              <button
                className="btn primary"
                onClick={registerPasskey}
                disabled={busy}
                style={{ width: "100%", height: 44, display: "flex", gap: 10 }}
              >
                <Fingerprint size={18} />
                <span>{busy ? "Waiting for device authentication…" : "Register passkey with device"}</span>
              </button>
            </div>
          )}

          {step === "done" && (
            <div style={{ display: "grid", gap: 16 }}>
              <div className="notice" role="status">
                <CheckCircle2 size={16} />
                <span>Adjuster profile activated with hardware passkey.</span>
              </div>
              <button
                className="btn primary"
                onClick={() => router.replace("/login")}
                style={{ width: "100%", height: 42 }}
              >
                Continue to sign in
              </button>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
