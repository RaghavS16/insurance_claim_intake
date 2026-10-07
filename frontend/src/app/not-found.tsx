'use client';

import React from 'react';
import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export default function NotFound() {
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

        <div className="snow-flex snow-gap-3">
          <Link href="/signin">
            <Button size="sm" variant="secondary" pill>
              Sign In
            </Button>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main
        className="snow-flex-col snow-items-center snow-justify-center"
        style={{ textAlign: 'center', margin: 'auto 0' }}
      >
        <h1 className="snow-h1" style={{ fontSize: 32, marginBottom: 24 }}>
          Page Not Found
        </h1>

        <div
          style={{
            width: 120,
            height: 120,
            borderRadius: 24,
            backgroundColor: '#FFFFFF',
            border: '1px solid #EBECEF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#1C1C1C',
            marginBottom: 32,
            boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
          }}
        >
          <AlertTriangle size={56} strokeWidth={1.5} color="#007AFF" />
        </div>

        <Link href="/">
          <Button pill variant="primary" size="md">
            Back to Home Page
          </Button>
        </Link>
      </main>

      {/* Footer */}
      <footer style={{ textAlign: 'center', color: '#A1A1AA', fontSize: 12 }}>
        © 2026 ApexCare Claims Platform
      </footer>
    </div>
  );
}
