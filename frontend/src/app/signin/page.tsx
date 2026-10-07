'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { KeyRound, ShieldAlert } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function SignInPage() {
  const router = useRouter();
  const { login } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await api.post<{ access_token: string; refresh_token: string; user: any; mfa_required?: boolean }>(
        '/api/v1/auth/login',
        { email, password }
      );

      if (res.mfa_required) {
        showToast('Multi-factor authentication required', 'info');
        const token = (res as any).challenge_token || '';
        if (typeof window !== 'undefined' && token) {
          sessionStorage.setItem('mfa_challenge_token', token);
        }
        router.push(`/mfa-challenge?challenge_token=${encodeURIComponent(token)}&email=${encodeURIComponent(email)}`);
        return;
      }

      login(res.access_token, res.user, res.refresh_token);
      showToast('Signed in successfully', 'success');

      if (res.user.role === 'CLAIMANT') router.push('/claimant/dashboard');
      else if (res.user.role === 'ADJUSTER') router.push('/adjuster/dashboard');
      else router.push('/admin/claims');
    } catch (err: any) {
      const msg = err.message || 'Invalid email or password. Please try again.';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handlePasskeyAuth = async () => {
    if (!email.trim()) {
      showToast('Please enter your email to sign in with passkey', 'error');
      return;
    }
    try {
      showToast('Authenticating with WebAuthn Passkey...', 'info');
      const options = await api.post<any>('/api/v1/auth/passkey/auth/options', { email });
      const verifyRes = await api.post<any>('/api/v1/auth/passkey/auth/verify', { email, challenge_id: options?.challenge_id });
      login(verifyRes.access_token, verifyRes.user, verifyRes.refresh_token);
      showToast('Passkey verified successfully', 'success');
      if (verifyRes.user.role === 'CLAIMANT') router.push('/claimant/dashboard');
      else if (verifyRes.user.role === 'ADJUSTER') router.push('/adjuster/dashboard');
      else router.push('/admin/claims');
    } catch (err: any) {
      showToast(err.message || 'Passkey authentication failed.', 'error');
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#F7F9FB',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '24px 40px',
      }}
    >
      {/* Top Header */}
      <header
        className="snow-flex snow-justify-between snow-items-center"
        style={{ width: '100%', maxWidth: 1200, margin: '0 auto' }}
      >
        <div className="snow-flex snow-items-center snow-gap-2">
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #007AFF 0%, #00D1FF 100%)',
            }}
          />
          <span className="snow-body" style={{ fontWeight: 700, letterSpacing: -0.5 }}>
            ApexCare
          </span>
        </div>

        <nav className="snow-flex snow-items-center snow-gap-6 snow-caption" style={{ color: '#71717A' }}>
          <span style={{ cursor: 'pointer' }}>Product</span>
          <span style={{ cursor: 'pointer' }}>Solutions</span>
          <span style={{ cursor: 'pointer' }}>Resources</span>
          <span style={{ cursor: 'pointer' }}>Download</span>
          <span style={{ cursor: 'pointer' }}>Pricing</span>
        </nav>

        <div className="snow-flex snow-items-center snow-gap-2">
          <Link href="/signup">
            <Button size="sm" variant="ghost">Sign up</Button>
          </Link>
          <Link href="/signin">
            <Button size="sm" variant="primary" pill>Sign in</Button>
          </Link>
        </div>
      </header>

      {/* Main Sign In Card */}
      <main style={{ margin: 'auto 0', display: 'flex', justifyContent: 'center' }}>
        <div
          className="snow-card"
          style={{
            width: '100%',
            maxWidth: 440,
            borderRadius: 24,
            padding: '40px 36px',
            boxShadow: '0 8px 30px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <h1 className="snow-h1" style={{ fontSize: 24, marginBottom: 8 }}>Sign In</h1>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              Claims Intake & Adjudication System
            </p>
          </div>

          {/* Social / Passkey Sign In */}
          <div className="snow-flex snow-gap-2" style={{ marginBottom: 20 }}>
            <Button
              type="button"
              variant="secondary"
              pill
              style={{ flex: 1, fontSize: 13, height: 42 }}
              onClick={handlePasskeyAuth}
              icon={<KeyRound size={16} />}
            >
              Passkey Sign In
            </Button>
          </div>

          {/* Divider */}
          <div
            className="snow-flex snow-items-center snow-gap-3"
            style={{ margin: '20px 0', color: '#A1A1AA', fontSize: 12 }}
          >
            <div style={{ flex: 1, height: 1, backgroundColor: '#EBECEF' }} />
            <span>Or with Email</span>
            <div style={{ flex: 1, height: 1, backgroundColor: '#EBECEF' }} />
          </div>

          {error && (
            <div
              className="snow-flex snow-items-center snow-gap-2"
              style={{
                backgroundColor: '#FEE4E2',
                color: '#DC2626',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              <ShieldAlert size={16} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <Input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            <div style={{ textAlign: 'right', marginTop: -8, marginBottom: 20 }}>
              <Link
                href="/forgot-password"
                className="snow-caption"
                style={{ color: '#007AFF', fontWeight: 500 }}
              >
                Forgot Password?
              </Link>
            </div>

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15 }}
              disabled={loading}
            >
              {loading ? 'Signing In...' : 'Sign In'}
            </Button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <span className="snow-caption" style={{ color: '#71717A' }}>
              Not a Member yet?{' '}
            </span>
            <Link
              href="/signup"
              className="snow-caption"
              style={{ color: '#007AFF', fontWeight: 600 }}
            >
              Sign Up
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}
