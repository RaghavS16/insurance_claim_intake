'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function SignUpPage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 4-segment strength calculation
  const getStrengthScore = () => {
    let score = 0;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score;
  };

  const strength = getStrengthScore();

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

    setError('');
    setLoading(true);

    try {
      const res = await api.post<any>('/api/v1/auth/signup', {
        full_name: fullName,
        email,
        phone,
        password,
        confirm_password: repeatPassword,
      });
      if (res?.email_verification_required === true) {
        showToast('Account created! Please verify your email.', 'success');
        router.push(`/verify-email?email=${encodeURIComponent(email)}`);
      } else {
        showToast('Account created! You can now sign in.', 'success');
        router.push('/signin');
      }
    } catch (err: any) {
      const msg = err.message || 'Registration failed. Please check your information.';
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
      {/* Top Header */}
      <header
        className="snow-flex snow-justify-between snow-items-center"
        style={{ width: '100%', maxWidth: 1200, margin: '0 auto' }}
      >
        <Link href="/">
          <img
            src="/primary-logo.png"
            alt="IntelliClaim"
            style={{ width: 165, height: 'auto', objectFit: 'contain', display: 'block' }}
          />
        </Link>



        <div className="snow-flex snow-items-center snow-gap-2">
          <Link href="/signup">
            <Button size="sm" variant="primary" pill>Sign up</Button>
          </Link>
          <Link href="/signin">
            <Button size="sm" variant="ghost">Sign in</Button>
          </Link>
        </div>
      </header>

      {/* Main Sign Up Card */}
      <main style={{ margin: 'auto 0', display: 'flex', justifyContent: 'center' }}>
        <div
          className="snow-card"
          style={{
            width: '100%',
            maxWidth: 440,
            borderRadius: 24,
            padding: '36px 36px',
            boxShadow: '0 8px 30px rgba(0,0,0,0.04)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <h1 className="snow-h1" style={{ fontSize: 24, marginBottom: 8 }}>Sign Up</h1>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              Create your claimant account
            </p>
          </div>

          <form onSubmit={handleSubmit}>
            <Input
              placeholder="Full Name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />

            <Input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <Input
              type="tel"
              placeholder="Phone Number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />

            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            {/* Password strength 4 bars */}
            <div style={{ marginTop: -10, marginBottom: 16 }}>
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
                      transition: 'background-color 0.2s ease',
                    }}
                  />
                ))}
              </div>
              <div className="snow-micro" style={{ color: '#A1A1AA', marginTop: 4 }}>
                Use 8 or more characters with letters, numbers & symbols.
              </div>
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

            <div style={{ marginBottom: 20 }}>
              <Checkbox
                id="terms"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                label={
                  <span className="snow-caption" style={{ color: '#71717A' }}>
                    I Accept the <span style={{ color: '#007AFF' }}>Terms</span>
                  </span>
                }
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15 }}
              disabled={loading}
            >
              {loading ? 'Creating Account...' : 'Sign Up'}
            </Button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <span className="snow-caption" style={{ color: '#71717A' }}>
              Already have an Account?{' '}
            </span>
            <Link
              href="/signin"
              className="snow-caption"
              style={{ color: '#007AFF', fontWeight: 600 }}
            >
              Sign In
            </Link>
          </div>
        </div>
      </main>

      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 IntelliClaim AI Platform
      </footer>
    </div>
  );
}
