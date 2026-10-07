'use client';

import React, { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { UserCheck, KeyRound, ShieldCheck } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

function AdjusterOnboardingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token') || '';
  const { login } = useAuth();
  const { showToast } = useToast();

  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [passkeyEnrolled, setPasskeyEnrolled] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleEnrollPasskey = async () => {
    try {
      showToast('Enrolling WebAuthn Passkey on this device...', 'info');
      await api.post('/api/v1/auth/passkey/registration/options');
      setPasskeyEnrolled(true);
      showToast('Passkey enrolled successfully!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Passkey enrollment unavailable or cancelled.', 'error');
    }
  };

  const handleAccept = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== repeatPassword) {
      showToast('Passwords do not match', 'error');
      return;
    }

    setLoading(true);
    try {
      const res = await api.post<any>('/api/v1/auth/onboarding/adjuster/accept', {
        token,
        password,
        passkey_enrolled: passkeyEnrolled,
      });
      login(res.access_token, res.user);
      showToast('Onboarding complete! Welcome to Adjuster Workspace.', 'success');
      router.push('/adjuster/dashboard');
    } catch (err: any) {
      showToast(err.message || 'Onboarding failed. Please check your invitation link.', 'error');
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
        justifyContent: 'center',
        alignItems: 'center',
        padding: 24,
      }}
    >
      <div
        className="snow-card"
        style={{
          width: '100%',
          maxWidth: 480,
          borderRadius: 24,
          padding: '40px 36px',
          boxShadow: '0 8px 30px rgba(0,0,0,0.04)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              backgroundColor: '#E5ECF6',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 16,
              color: '#3B82F6',
            }}
          >
            <UserCheck size={28} />
          </div>
          <h1 className="snow-h1" style={{ fontSize: 24, marginBottom: 8 }}>
            Adjuster Onboarding
          </h1>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            Activate your profile, establish your credentials, and configure hardware security.
          </p>
        </div>

        <form onSubmit={handleAccept}>
          <Input
            type="password"
            label="Create Secure Password"
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <Input
            type="password"
            label="Confirm Password"
            placeholder="Repeat password"
            value={repeatPassword}
            onChange={(e) => setRepeatPassword(e.target.value)}
            required
          />

          {/* Passkey enrollment block */}
          <div
            className="snow-card"
            style={{
              padding: 16,
              backgroundColor: '#FAFAFB',
              marginBottom: 20,
              borderRadius: 12,
            }}
          >
            <div className="snow-flex snow-justify-between snow-items-center">
              <div>
                <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                  Hardware Passkey (WebAuthn)
                </div>
                <div className="snow-caption" style={{ color: '#71717A' }}>
                  Required for adjuster sign-in & decision authorizations
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant={passkeyEnrolled ? 'secondary' : 'primary'}
                onClick={handleEnrollPasskey}
                icon={passkeyEnrolled ? <ShieldCheck size={14} color="#10B981" /> : <KeyRound size={14} />}
              >
                {passkeyEnrolled ? 'Enrolled' : 'Enroll Key'}
              </Button>
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            pill
            style={{ width: '100%', height: 44, fontSize: 15 }}
            disabled={loading}
          >
            {loading ? 'Activating Profile...' : 'Complete Onboarding & Enter'}
          </Button>
        </form>
      </div>
    </div>
  );
}

export default function AdjusterOnboardingPage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>Loading onboarding...</div>}>
      <AdjusterOnboardingContent />
    </Suspense>
  );
}
