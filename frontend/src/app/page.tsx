'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function HomePage() {
  const router = useRouter();
  const { user, role, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated || !user) {
      router.replace('/signin');
      return;
    }

    if (role === 'CLAIMANT') {
      router.replace('/claimant/dashboard');
    } else if (role === 'ADJUSTER') {
      router.replace('/adjuster/dashboard');
    } else if (role === 'ADMIN') {
      router.replace('/admin/claims');
    } else {
      router.replace('/signin');
    }
  }, [isAuthenticated, isLoading, user, role, router]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#F7F9FB',
        gap: 16,
      }}
    >
      <img src="/primary-logo.png" alt="IntelliClaim" style={{ width: 200, height: 'auto', objectFit: 'contain' }} />
      <div className="snow-body-muted">Loading your workspace...</div>
    </div>
  );
}
