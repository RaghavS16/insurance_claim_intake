'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminKnowledgePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/admin/claims');
  }, [router]);

  return (
    <div style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
      Redirecting to Enterprise Claims Oversight...
    </div>
  );
}
