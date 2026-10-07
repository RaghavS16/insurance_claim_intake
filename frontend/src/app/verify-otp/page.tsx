'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { KeyRound } from 'lucide-react';
import { PinInput } from '@/components/ui/PinInput';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

function VerifyOtpContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const { showToast } = useToast();

  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otp.length < 6) return;

    setLoading(true);
    try {
      const res = await api.post<{ reset_token: string }>('/api/v1/auth/verify-otp', {
        email,
        otp,
      });
      showToast('OTP verified! Enter your new password.', 'success');
      router.push(`/reset-password?token=${encodeURIComponent(res.reset_token)}&email=${encodeURIComponent(email)}`);
    } catch (err: any) {
      showToast(err.message || 'Invalid OTP code. Please try again.', 'error');
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
            textAlign: 'center',
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              backgroundColor: '#F4F5F7',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 20,
              color: '#1C1C1C',
            }}
          >
            <KeyRound size={28} />
          </div>

          <h1 className="snow-h1" style={{ fontSize: 22, marginBottom: 8 }}>
            Verify OTP Code
          </h1>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            Enter the 6-digit code sent to {email || 'your email'}
          </p>

          <form onSubmit={handleSubmit}>
            <PinInput length={6} value={otp} onChange={setOtp} />

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15, marginTop: 12 }}
              disabled={loading || otp.length < 6}
            >
              {loading ? 'Verifying...' : 'Verify Code'}
            </Button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Link
              href="/forgot-password"
              className="snow-caption"
              style={{ color: '#007AFF', fontWeight: 600 }}
            >
              Back to Forgot Password
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

export default function VerifyOtpPage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>Loading OTP verification...</div>}>
      <VerifyOtpContent />
    </Suspense>
  );
}
