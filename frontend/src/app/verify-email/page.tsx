'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Smartphone } from 'lucide-react';
import { PinInput } from '@/components/ui/PinInput';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const { showToast } = useToast();

  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otp.length < 6) {
      showToast('Please enter the full 6-digit code', 'error');
      return;
    }

    setLoading(true);
    try {
      await api.post('/api/v1/auth/verify-email', { email, code: otp });
      showToast('Email verified successfully! You can now sign in.', 'success');
      router.push('/signin');
    } catch (err: any) {
      showToast(err.message || 'Verification failed. Please check the code.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!email) {
      showToast('No email address provided to resend code to.', 'error');
      return;
    }
    setResending(true);
    try {
      await api.post('/api/v1/auth/resend-verification', { email });
      showToast('Verification code resent to your email', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to resend verification code.', 'error');
    } finally {
      setResending(false);
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
            <Smartphone size={28} />
          </div>

          <h1 className="snow-h1" style={{ fontSize: 22, marginBottom: 8 }}>
            Two Step Verification
          </h1>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 6 }}>
            Enter the verification code we sent to
          </p>
          <p className="snow-body" style={{ fontWeight: 600, marginBottom: 20 }}>
            {email}
          </p>

          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 12 }}>
            Type your 6 digit security code
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
              {loading ? 'Verifying...' : 'Submit'}
            </Button>
          </form>

          <div style={{ marginTop: 24 }}>
            <span className="snow-caption" style={{ color: '#71717A' }}>
              Didn't get the code?{' '}
            </span>
            <button
              onClick={handleResend}
              disabled={resending}
              style={{
                background: 'none',
                border: 'none',
                color: '#007AFF',
                fontWeight: 600,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              {resending ? 'Sending...' : 'Resend'}
            </button>
            <span className="snow-caption" style={{ color: '#71717A' }}> or </span>
            <a href="#" className="snow-caption" style={{ color: '#007AFF', fontWeight: 600 }}>
              Call Us
            </a>
          </div>
        </div>
      </main>

      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>Loading verification...</div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}
