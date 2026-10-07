'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token') || '';
  const email = searchParams.get('email') || '';
  const { showToast } = useToast();

  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const getStrength = () => {
    let s = 0;
    if (password.length >= 8) s++;
    if (/[A-Z]/.test(password)) s++;
    if (/[0-9]/.test(password)) s++;
    if (/[^A-Za-z0-9]/.test(password)) s++;
    return s;
  };

  const strength = getStrength();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== repeatPassword) {
      setError('Passwords do not match');
      return;
    }
    if (!acceptedTerms) {
      setError('You must accept the terms');
      return;
    }

    setLoading(true);
    setError('');

    try {
      await api.post('/api/v1/auth/reset-password', {
        email,
        token,
        new_password: password,
      });
      showToast('Password updated! You can now sign in.', 'success');
      router.push('/signin');
    } catch (err: any) {
      const msg = err.message || 'Failed to reset password. Please try again.';
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
        padding: '24px 40px',
      }}
    >
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
          <span>Product</span>
          <span>Solutions</span>
          <span>Resources</span>
          <span>Download</span>
          <span>Pricing</span>
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
            <h1 className="snow-h1" style={{ fontSize: 24, marginBottom: 8 }}>
              Setup New Password
            </h1>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              Have you already reset the password ?{' '}
              <Link href="/signin" style={{ color: '#007AFF', fontWeight: 600 }}>
                Sign In
              </Link>
            </p>
          </div>

          <form onSubmit={handleSubmit}>
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            {/* 4-bar strength indicator */}
            <div style={{ marginTop: -8, marginBottom: 16 }}>
              <div className="snow-flex snow-gap-1" style={{ height: 4 }}>
                {[1, 2, 3, 4].map((bar) => (
                  <div
                    key={bar}
                    style={{
                      flex: 1,
                      borderRadius: 2,
                      backgroundColor:
                        bar <= strength
                          ? strength >= 3
                            ? '#10B981'
                            : strength === 2
                            ? '#F59E0B'
                            : '#EF4444'
                          : '#EBECEF',
                    }}
                  />
                ))}
              </div>
              <p className="snow-micro" style={{ color: '#A1A1AA', marginTop: 4 }}>
                Use 8 or more characters with a mix of letters, numbers & symbols.
              </p>
            </div>

            <Input
              type="password"
              placeholder="Repeat Password"
              value={repeatPassword}
              onChange={(e) => setRepeatPassword(e.target.value)}
              required
            />

            {error && (
              <div className="snow-micro" style={{ color: '#EF4444', marginBottom: 12 }}>
                {error}
              </div>
            )}

            <div className="snow-flex snow-items-center snow-gap-2" style={{ marginBottom: 20 }}>
              <input
                type="checkbox"
                id="resetTerms"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <label htmlFor="resetTerms" className="snow-caption" style={{ color: '#71717A', cursor: 'pointer' }}>
                I Accept the <span style={{ color: '#007AFF' }}>Terms</span>
              </label>
            </div>

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15 }}
              disabled={loading}
            >
              {loading ? 'Updating...' : 'Submit'}
            </Button>
          </form>
        </div>
      </main>

      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>Loading password reset...</div>}>
      <ResetPasswordContent />
    </Suspense>
  );
}
