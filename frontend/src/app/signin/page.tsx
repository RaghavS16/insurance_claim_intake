'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
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
      const res = await api.post<{ access_token: string; refresh_token: string; user: any }>(
        '/api/v1/auth/login',
        { email, password }
      );

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

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#F7F9FB',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '32px 16px',
      }}
    >
      {/* Header Logo */}
      <header className="snow-flex snow-justify-center" style={{ paddingTop: 24 }}>
        <Link href="/">
          <img
            src="/primary-logo.png"
            alt="IntelliClaim"
            style={{ width: 220, maxWidth: '85vw', height: 'auto', objectFit: 'contain', display: 'block' }}
          />
        </Link>
      </header>

      {/* Main Sign In Card */}
      <main className="snow-flex snow-justify-center snow-items-center">
        <div
          className="snow-card"
          style={{
            width: '100%',
            maxWidth: 420,
            padding: '36px 32px',
            borderRadius: 20,
            boxShadow: '0 8px 30px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <h1 className="snow-h1" style={{ fontSize: 24, marginBottom: 8 }}>Sign In</h1>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              Voice-Driven AI Insurance Intake & Adjudication
            </p>
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
        © 2026 IntelliClaim Platform
      </footer>
    </div>
  );
}
