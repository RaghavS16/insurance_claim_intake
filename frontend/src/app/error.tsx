'use client';

import React from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      className="snow-flex-col snow-items-center snow-justify-center"
      style={{ minHeight: '100vh', backgroundColor: '#F7F9FB', padding: 24, textAlign: 'center' }}
    >
      <div
        style={{
          width: 80,
          height: 80,
          borderRadius: 20,
          backgroundColor: '#FEE4E2',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#DC2626',
          marginBottom: 20,
        }}
      >
        <AlertCircle size={40} />
      </div>

      <h1 className="snow-h1" style={{ marginBottom: 12 }}>System Error Occurred</h1>
      <p className="snow-body-muted" style={{ maxWidth: 480, marginBottom: 24 }}>
        {error.message || 'An unexpected application error was encountered while processing your adjudication request.'}
      </p>

      <Button pill variant="primary" onClick={() => reset()}>
        Try Again
      </Button>
    </div>
  );
}
