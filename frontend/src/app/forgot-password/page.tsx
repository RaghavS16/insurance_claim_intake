'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Mail } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function ForgotPasswordPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await api.post('/api/v1/auth/forgot-password', { email });
      showToast('Password reset code sent to your email', 'success');
      router.push(`/verify-otp?email=${encodeURIComponent(email)}`);
    } catch (err: any) {
      showToast(err.message || 'Failed to send reset code. Please check your email.', 'error');
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

        <Link href="/signin">
          <Button size="sm" variant="ghost">Sign in</Button>
        </Link>
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
              Forgot Password
            </h1>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              Enter your registered email to receive a password reset code.
            </p>
          </div>

          <form onSubmit={handleSubmit}>
            <Input
              type="email"
              placeholder="name@example.com"
              iconLeft={<Mail size={16} />}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15, marginTop: 12 }}
              disabled={loading}
            >
              {loading ? 'Sending Code...' : 'Send Reset Code'}
            </Button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Link
              href="/signin"
              className="snow-caption"
              style={{ color: '#007AFF', fontWeight: 600 }}
            >
              Return to Sign In
            </Link>
          </div>
        </div>
      </main>

      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}
