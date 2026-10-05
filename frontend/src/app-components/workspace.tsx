"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { 
  Activity, 
  AlertCircle, 
  Bell, 
  BookOpen, 
  CheckCircle2, 
  CircleHelp, 
  ClipboardList, 
  FilePlus2, 
  Fingerprint, 
  KeyRound, 
  LayoutDashboard, 
  Lock, 
  LogOut, 
  Menu, 
  MessageCircle, 
  Search, 
  Settings, 
  ShieldCheck, 
  Sparkles, 
  Users 
} from "lucide-react";
import { api } from "@/lib/api";
import { assertWebAuthnSupport, prepareCreationOptions, prepareRequestOptions, serializeCredential } from "@/lib/webauthn";
import { Card, Empty, Page, ThemeToggle } from "@/app-components/ui";
import { ClaimantChat } from "@/app-components/claimant-chat";
import { AdjusterOnboardingPage } from "@/app-components/adjuster-onboarding";
import { AdjusterDashboard, AdjusterQueue, Workbench } from "@/app-components/adjuster-workspace";
import { AdminDashboard, Admin, AdminClaims, Audit } from "@/app-components/admin-workspace";
import { Policies, LinkPolicy, Claims, Track, ClaimDetail, Evidence, Messages } from "@/app-components/claimant-workspace";
import { Knowledge } from "@/app-components/knowledge-workspace";
import { EmailVerificationPage } from "@/app-components/email-verification";

export type User = {
  id: string;
  full_name?: string;
  email: string;
  role: "CLAIMANT" | "ADJUSTER" | "ADMIN";
  status?: string;
};

const first = (u: User) => ((u.full_name || u.email || "U")[0] || "U").toUpperCase();

/* ==========================================================================
   Split-Screen Authentication Shell (Clerk.com & Linear.app Benchmark)
   ========================================================================== */

function AuthShell({
  title,
  subtitle,
  children
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="auth-split-shell">
      {/* Left Feature Showcase */}
      <section className="auth-hero-pane" aria-label="Platform Highlights">
        <div className="auth-hero-brand">
          <span className="brand-mark">F</span>
          <span>Flowa</span>
          <span className="brand-tag">Claims AI</span>
        </div>

        <div className="auth-hero-body">
          <div className="auth-hero-eyebrow">
            <Sparkles size={13} />
            <span>Anti-Slop Claim Intelligence</span>
          </div>

          <h2 className="auth-hero-title">
            Intelligent Claim Intake with Dual-Mode Precision
          </h2>
          <p className="auth-hero-desc">
            Transform voice and unstructured evidence into verified policy packages. Human-in-the-loop workflows with automated regulatory compliance.
          </p>

          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <ShieldCheck size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Phishing-Resistant Security</b>
                <span>FIDO2 WebAuthn passkeys and continuous session monitoring</span>
              </div>
            </div>

            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <Activity size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Realtime Voice & Multimodal Evidence</b>
                <span>WebRTC conversational intake paired with automated OCR verification</span>
              </div>
            </div>

            <div className="auth-feature-item">
              <div className="auth-feature-icon">
                <Lock size={14} />
              </div>
              <div className="auth-feature-text">
                <b>Statutory SLA Adjudication</b>
                <span>Deterministic coverage verification backed by published policy wording</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-hero-footer">
          <span>Enterprise Grade · SOC2 Type II Certified · 99.99% Uptime</span>
        </div>
      </section>

      {/* Right Interactive Form Pane */}
      <section className="auth-form-pane">
        <div className="auth-form-container">
          <header className="auth-form-header">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="brand" style={{ margin: 0, display: "flex" }}>
                <span className="brand-mark">F</span>
                <span>Flowa</span>
              </div>
              <ThemeToggle />
            </div>
            <h1 className="auth-form-title">{title}</h1>
            <p className="auth-form-subtitle">{subtitle}</p>
          </header>

          {children}
        </div>
      </section>
    </main>
  );
}

/* ==========================================================================
   Registration Page
   ========================================================================== */

export function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");

    if (password !== confirm) {
      setError("Passwords do not match.");
      setBusy(false);
      return;
    }

    try {
      const r = await api<any>("/api/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName,
          email,
          phone,
          password,
          confirm_password: confirm
        })
      });

      if (r.email_verification_required) {
        router.replace("/verify-email?email=" + encodeURIComponent(email));
        return;
      }
      setMessage("Account created successfully. Redirecting to sign in…");
      setTimeout(() => router.replace("/login"), 800);
    } catch (e: any) {
      setError(e.message || "Unable to create your account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Create your claimant account"
      subtitle="Register securely to file claims, upload evidence, and track adjudication in real time."
    >
      <form className="form" onSubmit={submit}>
        <label>
          Full name
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jane Doe"
            autoComplete="name"
            required
          />
        </label>

        <label>
          Work or personal email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="jane@example.com"
            autoComplete="email"
            required
          />
        </label>

        <label>
          Phone number
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+1 (555) 000-0000"
            autoComplete="tel"
            required
          />
        </label>

        <div className="form-grid">
          <label>
            Password
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
        </div>

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
          {busy ? "Creating account…" : "Create account"}
        </button>

        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginTop: 4 }}>
          <Link className="link" href="/login">
            Already have an account? Sign in
          </Link>
          <span style={{ color: "var(--muted)" }}>Claimant access</span>
        </div>
      </form>
    </AuthShell>
  );
}

/* ==========================================================================
   Login Page with WebAuthn Passkeys & MFA Challenge Support
   ========================================================================== */

export function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [passkeyBusy, setPasskeyBusy] = useState(false);

  async function finish(r: any) {
    if (!r?.access_token) throw Error("Authentication did not return an access token.");
    localStorage.setItem("access_token", r.access_token);
    const u = await api<User>("/api/v1/auth/me");
    router.replace(u.role === "ADJUSTER" ? "/adjuster" : u.role === "ADMIN" ? "/admin" : "/");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");

    try {
      if (challenge) {
        const r = await api<any>("/api/v1/auth/mfa/verify", {
          method: "POST",
          body: JSON.stringify({ challenge_token: challenge, code })
        });
        await finish(r);
        return;
      }

      const r = await api<any>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });

      if (r.mfa_required) {
        setChallenge(r.challenge_token || r.challenge || "");
        return;
      }
      await finish(r);
    } catch (e: any) {
      setError(e.message || "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  async function signInWithPasskey() {
    setPasskeyBusy(true);
    setError("");
    try {
      assertWebAuthnSupport();
      if (!email.trim()) throw Error("Enter your email address before using a passkey.");
      const options = await api<any>("/api/v1/auth/passkey/auth/options", {
        method: "POST",
        body: JSON.stringify({ email })
      });
      const credential = await navigator.credentials.get({
        publicKey: prepareRequestOptions(options.public_key)
      });
      if (!credential) throw Error("Passkey authentication was cancelled.");
      const r = await api<any>("/api/v1/auth/passkey/auth/verify", {
        method: "POST",
        body: JSON.stringify({
          email,
          challenge_id: options.challenge_id,
          credential: serializeCredential(credential as PublicKeyCredential)
        })
      });
      await finish(r);
    } catch (e: any) {
      setError(e.message || "Unable to authenticate with passkey.");
    } finally {
      setPasskeyBusy(false);
    }
  }

  return (
    <AuthShell
      title={challenge ? "Verify your identity" : "Sign in"}
      subtitle={
        challenge
          ? "Enter the 6-digit one-time authenticator code."
          : "Access the secure insurance claims & adjuster workspace."
      }
    >
      <form className="form" onSubmit={submit}>
        {!challenge ? (
          <>
            <label>
              Work or personal email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@organization.com"
                autoComplete="username"
                required
              />
            </label>

            <label>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Password</span>
                <Link className="link" href="/recovery" style={{ fontSize: 12 }}>
                  Forgot password?
                </Link>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
            </label>
          </>
        ) : (
          <label>
            Authenticator code
            <input
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
              placeholder="123456"
              autoComplete="one-time-code"
              required
            />
          </label>
        )}

        {error && (
          <div className="error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        <button
          className="btn primary"
          type="submit"
          disabled={busy || passkeyBusy}
          style={{ width: "100%", height: 42 }}
        >
          {busy ? "Signing in…" : challenge ? "Verify and continue" : "Sign in"}
        </button>

        {!challenge && (
          <>
            <div className="passkey-divider">
              <span>Or use biometrics</span>
            </div>

            <button
              className="btn"
              type="button"
              onClick={signInWithPasskey}
              disabled={busy || passkeyBusy}
              style={{ width: "100%", height: 42, display: "flex", gap: 10 }}
            >
              <Fingerprint size={18} color="var(--blue)" />
              <span>{passkeyBusy ? "Verifying passkey…" : "Sign in with passkey"}</span>
            </button>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginTop: 8 }}>
              <Link className="link" href="/register">
                Create claimant account
              </Link>
              <span style={{ color: "var(--muted)" }}>MFA protected</span>
            </div>
          </>
        )}
      </form>
    </AuthShell>
  );
}

/* ==========================================================================
   Account Recovery Page
   ========================================================================== */

export function RecoveryPage() {
  const [step, setStep] = useState(0);
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    setBusy(true);

    try {
      if (step === 0) {
        const r = await api<any>("/api/v1/auth/forgot-password", {
          method: "POST",
          body: JSON.stringify({ email })
        });
        setMsg(r.message || "A verification code has been sent to your email.");
        setStep(1);
      } else if (step === 1) {
        const r = await api<any>("/api/v1/auth/verify-otp", {
          method: "POST",
          body: JSON.stringify({ email, otp })
        });
        setToken(r.reset_token || r.token || "");
        setStep(2);
      } else {
        if (password !== confirm) {
          throw new Error("Passwords do not match.");
        }
        await api("/api/v1/auth/reset-password", {
          method: "POST",
          body: JSON.stringify({
            reset_token: token,
            new_password: password,
            confirm_password: confirm
          })
        });
        setMsg("Password reset successfully. You may now sign in.");
      }
    } catch (e: any) {
      setError(e.message || "Recovery request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Account recovery"
      subtitle={
        step === 0
          ? "Enter your email to receive a secure one-time verification code."
          : step === 1
          ? "Enter the code sent to your email address."
          : "Create a new strong password for your account."
      }
    >
      <form className="form" onSubmit={submit}>
        {step === 0 && (
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              required
            />
          </label>
        )}

        {step === 1 && (
          <>
            <label>
              Email
              <input type="email" value={email} readOnly disabled />
            </label>
            <label>
              One-time verification code
              <input
                inputMode="numeric"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 8))}
                placeholder="123456"
                required
              />
            </label>
          </>
        )}

        {step === 2 && (
          <>
            <label>
              New password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                minLength={8}
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
                minLength={8}
                required
              />
            </label>
          </>
        )}

        {error && (
          <div className="error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {msg && (
          <div className="notice" role="status">
            <CheckCircle2 size={15} />
            <span>{msg}</span>
          </div>
        )}

        {step === 2 && msg ? (
          <Link className="btn primary" href="/login" style={{ width: "100%", height: 42 }}>
            Return to sign in
          </Link>
        ) : (
          <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%", height: 42 }}>
            {busy ? "Working…" : step === 0 ? "Send verification code" : step === 1 ? "Verify code" : "Reset password"}
          </button>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginTop: 4 }}>
          <Link className="link" href="/login">
            Back to sign in
          </Link>
          <span style={{ color: "var(--muted)" }}>Secure reset</span>
        </div>
      </form>
    </AuthShell>
  );
}

/* ==========================================================================
   Workspace Navigation & Shell (Flowa 272px Architecture)
   ========================================================================== */

type Nav = { href: string; label: string; icon: LucideIcon; exact?: boolean };

function NavItem({ n, p }: { n: Nav; p: string }) {
  const active = n.exact ? p === n.href : p === n.href || p.startsWith(n.href + "/");
  const I = n.icon;
  return (
    <Link className={"nav-link" + (active ? " active" : "")} href={n.href}>
      <I size={17} />
      <span>{n.label}</span>
    </Link>
  );
}

function useUser() {
  const router = useRouter();
  const [u, setU] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      router.replace("/login");
      return;
    }
    let alive = true;
    api<User>("/api/v1/auth/me")
      .then((x) => alive && setU(x))
      .catch(() => {
        localStorage.removeItem("access_token");
        if (alive) router.replace("/login");
      });
    return () => {
      alive = false;
    };
  }, [router]);

  return u;
}

function WorkspaceShell() {
  const path = usePathname() || "/";
  const router = useRouter();
  const user = useUser();
  const [open, setOpen] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const a = () => setOffline(false);
    const b = () => setOffline(true);
    window.addEventListener("online", a);
    window.addEventListener("offline", b);
    setOffline(!navigator.onLine);
    return () => {
      window.removeEventListener("online", a);
      window.removeEventListener("offline", b);
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    const allowed =
      user.role === "CLAIMANT"
        ? ["/chat", "/policies", "/claims", "/track", "/settings"]
        : user.role === "ADJUSTER"
        ? ["/adjuster", "/adjuster/queue", "/policies", "/knowledge", "/settings"]
        : ["/admin", "/admin/audit", "/claims", "/policies", "/settings"];

    if (user.role === "CLAIMANT" && path === "/") {
      router.replace("/chat");
      return;
    }
    const ok = allowed.some((x) => path === x || path.startsWith(x + "/"));
    if (!ok) {
      router.replace(user.role === "ADJUSTER" ? "/adjuster" : user.role === "ADMIN" ? "/admin" : "/chat");
    }
  }, [user, path, router]);

  if (!user) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "var(--bg-base)" }}>
        <div style={{ textAlign: "center", display: "grid", gap: 12 }}>
          <div className="brand" style={{ justifyContent: "center" }}>
            <span className="brand-mark">F</span>
            <span>Flowa</span>
          </div>
          <div className="chat-skeleton" style={{ width: 280 }}>
            <div className="skeleton-shimmer" style={{ height: 16 }} />
            <div className="skeleton-shimmer" style={{ height: 16, width: "70%", margin: "0 auto" }} />
          </div>
        </div>
      </div>
    );
  }

  // Unified Claimant Chat takes full screen viewport
  if (user.role === "CLAIMANT" && (path === "/" || path === "/chat")) {
    return (
      <div className="app-shell" style={{ overflow: "hidden" }}>
        <button className="mobile-menu" onClick={() => setOpen((v) => !v)} aria-label="Open navigation">
          <Menu size={18} />
        </button>
        {open && <div className="overlay" onClick={() => setOpen(false)} />}
        <Sidebar user={user} path={path} open={open} onLogout={logout} />
        <div className="main-area">
          <Header user={user} />
          {offline && <OfflineNotice />}
          <ClaimantChat />
        </div>
      </div>
    );
  }

  const claimantNav: Nav[] = [
    { href: "/chat", label: "Chat", icon: MessageCircle, exact: true },
    { href: "/policies", label: "Policies", icon: ShieldCheck },
    { href: "/claims", label: "Claims", icon: ClipboardList },
    { href: "/track", label: "Track Claims", icon: Activity }
  ];

  const adjusterNav: Nav[] = [
    { href: "/adjuster", label: "Overview", icon: LayoutDashboard, exact: true },
    { href: "/adjuster/queue", label: "Claims Queue", icon: ClipboardList },
    { href: "/policies", label: "Policy & Regulations", icon: ShieldCheck },
    { href: "/knowledge", label: "Knowledge Search", icon: BookOpen },
    { href: "/knowledge/manage", label: "Manage Knowledge", icon: FilePlus2 }
  ];

  const adminNav: Nav[] = [
    { href: "/admin", label: "Administration", icon: Users, exact: true },
    { href: "/policies", label: "Policy Directory", icon: ShieldCheck },
    { href: "/claims", label: "Claims", icon: ClipboardList },
    { href: "/admin/audit", label: "System Audit", icon: Activity }
  ];

  const nav = user.role === "ADJUSTER" ? adjusterNav : user.role === "ADMIN" ? adminNav : claimantNav;

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* best effort cleanup */
    }
    localStorage.removeItem("access_token");
    router.replace("/login");
  }

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setOpen((v) => !v)} aria-label="Open navigation">
        <Menu size={18} />
      </button>
      {open && <div className="overlay" onClick={() => setOpen(false)} />}

      <Sidebar user={user} path={path} open={open} onLogout={logout} nav={nav} />

      <div className="main-area">
        <Header user={user} />
        {offline && <OfflineNotice />}
        <section className="content">
          <Screen p={path} user={user} />
        </section>
      </div>
    </div>
  );
}

function Sidebar({
  user,
  path,
  open,
  onLogout,
  nav
}: {
  user: User;
  path: string;
  open: boolean;
  onLogout: () => void;
  nav?: Nav[];
}) {
  const currentNav =
    nav ||
    (user.role === "ADJUSTER"
      ? [
          { href: "/adjuster", label: "Overview", icon: LayoutDashboard, exact: true },
          { href: "/adjuster/queue", label: "Claims Queue", icon: ClipboardList },
          { href: "/policies", label: "Policy & Regulations", icon: ShieldCheck },
          { href: "/knowledge", label: "Knowledge Search", icon: BookOpen },
          { href: "/knowledge/manage", label: "Manage Knowledge", icon: FilePlus2 }
        ]
      : user.role === "ADMIN"
      ? [
          { href: "/admin", label: "Administration", icon: Users, exact: true },
          { href: "/claims", label: "Claims", icon: ClipboardList },
          { href: "/admin/audit", label: "System Audit", icon: Activity }
        ]
      : [
          { href: "/chat", label: "Chat", icon: MessageCircle, exact: true },
          { href: "/policies", label: "Policies", icon: ShieldCheck },
          { href: "/claims", label: "Claims", icon: ClipboardList },
          { href: "/track", label: "Track Claims", icon: Activity }
        ]);

  return (
    <aside className={"sidebar" + (open ? " open" : "")} aria-label="Main application sidebar">
      <div className="brand">
        <span className="brand-mark">F</span>
        <span>Flowa</span>
      </div>

      <div className="nav-group">
        <div className="nav-label">
          {user.role === "ADJUSTER"
            ? "Adjuster workspace"
            : user.role === "ADMIN"
            ? "Administration"
            : "My account"}
        </div>
        {currentNav.map((n) => (
          <NavItem key={n.href} n={n} p={path} />
        ))}
      </div>

      <div className="side-bottom">
        <Link className="nav-link" href="/settings">
          <CircleHelp size={17} />
          <span>Help Center</span>
        </Link>
        <Link className="nav-link" href="/settings">
          <Settings size={17} />
          <span>Settings</span>
        </Link>
        <button className="nav-link" onClick={onLogout} style={{ border: 0, background: "transparent", textAlign: "left" }}>
          <LogOut size={17} />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}

function Header({ user }: { user: User }) {
  return (
    <header className="topbar">
      <div className="searchbox">
        <Search size={16} />
        <input aria-label="Search workspace" placeholder="Search claims, policies, knowledge…" />
      </div>

      <div className="head-actions">
        <ThemeToggle />
        <button className="icon-btn" aria-label="Notifications" title="Notifications">
          <Bell size={17} />
        </button>
        <Link className="profile" href="/settings" title="Profile and Settings">
          <span className="avatar">{first(user)}</span>
          <span className="profile-meta">
            <b>{user.full_name || user.email}</b>
            <span>
              {user.role === "ADJUSTER"
                ? "Claims Adjuster"
                : user.role === "ADMIN"
                ? "Administrator"
                : "Policy Holder"}
            </span>
          </span>
        </Link>
      </div>
    </header>
  );
}

function OfflineNotice() {
  return (
    <div className="offline">
      <AlertCircle size={15} />
      <span>You are currently offline. Cached views remain accessible; new filings require network connectivity.</span>
    </div>
  );
}

/* ==========================================================================
   Settings Screen with Passkey Registration
   ========================================================================== */

function SettingsScreen({ u }: { u: User }) {
  const [passkey, setPasskey] = useState<{ enabled: boolean; registered: boolean; credential_count: number } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<any>("/api/v1/auth/passkey/status")
      .then(setPasskey)
      .catch(() => setPasskey(null));
  }, []);

  async function registerPasskey() {
    setBusy(true);
    setMsg("");
    setError("");
    try {
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
      setMsg("Passkey registered successfully.");
      setPasskey((prev) => ({
        ...prev,
        enabled: true,
        registered: true,
        credential_count: (prev?.credential_count || 0) + 1
      }));
    } catch (e: any) {
      setError(e.message || "Unable to register passkey.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Settings" subtitle="Account credentials and high-assurance WebAuthn security.">
      <div className="grid grid-2">
        <Card>
          <div className="card-title">User profile</div>
          <div className="detail-grid">
            <div className="detail-item">
              <span>Full Name</span>
              <b>{u.full_name || "—"}</b>
            </div>
            <div className="detail-item">
              <span>Email</span>
              <b>{u.email}</b>
            </div>
            <div className="detail-item">
              <span>Role</span>
              <b>{u.role}</b>
            </div>
          </div>
        </Card>

        <Card>
          <div className="card-title">Security & Credentials</div>
          <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 16px" }}>
            Passkeys provide hardware-backed, phishing-resistant authentication without passwords.
          </p>

          {passkey?.registered ? (
            <div className="notice" style={{ marginBottom: 14 }}>
              <CheckCircle2 size={16} />
              <span>Passkey enrolled ({passkey.credential_count} key active).</span>
            </div>
          ) : (
            <button
              className="btn primary"
              onClick={registerPasskey}
              disabled={busy}
              style={{ display: "flex", gap: 8, marginBottom: 14 }}
            >
              <Fingerprint size={16} />
              <span>{busy ? "Registering passkey…" : "Register a passkey"}</span>
            </button>
          )}

          {error && (
            <div className="error" role="alert" style={{ marginBottom: 12 }}>
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          {msg && (
            <div className="notice" role="status" style={{ marginBottom: 12 }}>
              <CheckCircle2 size={15} />
              <span>{msg}</span>
            </div>
          )}

          <div className="actions">
            <Link className="btn" href="/recovery">
              <KeyRound size={14} />
              <span>Account recovery options</span>
            </Link>
          </div>
        </Card>
      </div>
    </Page>
  );
}

/* ==========================================================================
   Screen Dispatcher
   ========================================================================== */

function Screen({ p, user }: { p: string; user: User }) {
  if (p === "/" || p === "/chat") return <ClaimantChat />;
  if (p === "/policies") return <Policies user={user} />;
  if (p === "/policies/link") return <LinkPolicy />;
  if (p === "/claims") return user.role === "ADMIN" ? <AdminClaims /> : <Claims />;
  if (p === "/track") return <Track />;
  if (p === "/voice" || p.startsWith("/voice/")) return <ClaimantChat />;
  if (p.endsWith("/evidence") && p.startsWith("/claims/")) return <Evidence ticket={decodeURIComponent(p.split("/")[2] || "")} />;
  if (p.endsWith("/messages") && p.startsWith("/claims/")) return <Messages ticket={decodeURIComponent(p.split("/")[2] || "")} />;
  if (p.startsWith("/claims/")) return <ClaimDetail ticket={decodeURIComponent(p.split("/")[2] || "")} />;
  if (p === "/adjuster") return <AdjusterDashboard />;
  if (p === "/adjuster/queue") return <AdjusterQueue />;
  if (p.startsWith("/adjuster/claims/")) return <Workbench ticket={decodeURIComponent(p.split("/")[3] || "")} />;
  if (p === "/knowledge") return <Knowledge />;
  if (p === "/knowledge/manage") return <Knowledge manage />;
  if (p === "/admin") return <Admin />;
  if (p === "/admin/audit") return <Audit />;
  if (p === "/settings") return <SettingsScreen u={user} />;

  return (
    <Page title="Page not found" subtitle="The requested workspace path does not exist.">
      <Card>
        <Empty text="Please select a valid option from the sidebar." />
        <div style={{ textAlign: "center", marginTop: 12 }}>
          <Link className="btn primary" href="/">
            Return to dashboard
          </Link>
        </div>
      </Card>
    </Page>
  );
}

/* ==========================================================================
   Root Route View
   ========================================================================== */

export function RouterView() {
  const p = usePathname() || "/";
  if (p === "/login") return <LoginPage />;
  if (p === "/register") return <RegisterPage />;
  if (p === "/verify-email") return <EmailVerificationPage />;
  if (p === "/recovery") return <RecoveryPage />;
  if (p === "/onboarding/adjuster") return <AdjusterOnboardingPage />;
  return <WorkspaceShell />;
}
