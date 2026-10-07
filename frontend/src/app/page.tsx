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
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#F7F9FB',
      }}
    >
      <div className="snow-body-muted">Redirecting to your workspace...</div>
    </div>
  );
}
