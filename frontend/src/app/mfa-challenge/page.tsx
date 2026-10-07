'use client';

import React, { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ShieldCheck, Key } from 'lucide-react';
import { PinInput } from '@/components/ui/PinInput';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

function MfaChallengeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const urlChallengeToken = searchParams.get('challenge_token') || '';
  const { login } = useAuth();
  const { showToast } = useToast();

  const [challengeToken, setChallengeToken] = useState('');
  const [code, setCode] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token =
      urlChallengeToken ||
      (typeof window !== 'undefined' ? sessionStorage.getItem('mfa_challenge_token') || '' : '');
    setChallengeToken(token);
  }, [urlChallengeToken]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!challengeToken) {
      showToast('MFA session expired. Please sign in again.', 'error');
      router.push('/signin');
      return;
    }
    setLoading(true);

    try {
      let userObj: any = null;
      if (useRecovery) {
        const res = await api.post<any>('/api/v1/auth/mfa/recover', {
          challenge_token: challengeToken,
          recovery_code: recoveryCode,
        });
        login(res.access_token, res.user, res.refresh_token);
        userObj = res.user;
      } else {
        const res = await api.post<any>('/api/v1/auth/mfa/verify', {
          challenge_token: challengeToken,
          code,
        });
        login(res.access_token, res.user, res.refresh_token);
        userObj = res.user;
      }

      showToast('Authentication complete', 'success');
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('mfa_challenge_token');
      }

      const userRole = (userObj?.role || '').toUpperCase();
      if (userRole === 'ADMIN') {
        router.push('/admin/claims');
      } else if (userRole === 'ADJUSTER') {
        router.push('/adjuster/dashboard');
      } else {
        router.push('/claimant/dashboard');
      }
    } catch (err: any) {
      showToast(err.message || 'MFA verification failed. Please try again.', 'error');
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
            <ShieldCheck size={28} />
          </div>

          <h1 className="snow-h1" style={{ fontSize: 22, marginBottom: 8 }}>
            MFA Challenge
          </h1>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            {useRecovery
              ? 'Enter an emergency one-time recovery code'
              : 'Enter the 6-digit code from your authenticator app'}
          </p>

          <form onSubmit={handleSubmit}>
            {useRecovery ? (
              <Input
                placeholder="XXXX-XXXX-XXXX"
                iconLeft={<Key size={16} />}
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                required
              />
            ) : (
              <PinInput length={6} value={code} onChange={setCode} />
            )}

            <Button
              type="submit"
              variant="primary"
              pill
              style={{ width: '100%', height: 44, fontSize: 15, marginTop: 12 }}
              disabled={loading || (!useRecovery && code.length < 6)}
            >
              {loading ? 'Verifying...' : 'Verify & Continue'}
            </Button>
          </form>

          <div style={{ marginTop: 24 }}>
            <button
              onClick={() => setUseRecovery(!useRecovery)}
              style={{
                background: 'none',
                border: 'none',
                color: '#007AFF',
                fontWeight: 600,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              {useRecovery ? 'Use Authenticator App Code' : 'Lost device? Use Recovery Code'}
            </button>
          </div>
        </div>
      </main>

      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}

export default function MfaChallengePage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>Loading MFA...</div>}>
      <MfaChallengeContent />
    </Suspense>
  );
}
