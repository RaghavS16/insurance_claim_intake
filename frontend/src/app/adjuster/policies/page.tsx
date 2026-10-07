'use client';

import React, { useState, useEffect } from 'react';
import { ShieldCheck, Search, Filter, AlertTriangle, Inbox } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgePill } from '@/components/ui/Badge';
import { Policy } from '@/lib/types';
import { api } from '@/lib/api';

export default function AdjusterPolicyDirectoryPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPolicies = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>('/api/v1/policies');
      const list: Policy[] = Array.isArray(data) ? data : data?.items || [];
      setPolicies(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load underwriting policies.');
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const columns: Column<Policy>[] = [
    {
      key: 'policy_number',
      header: 'Policy Number',
      render: (p) => (
        <div className="snow-flex snow-items-center snow-gap-2">
          <ShieldCheck size={16} color="#007AFF" />
          <span className="snow-table-id">{p.policy_number}</span>
        </div>
      ),
    },
    {
      key: 'policyholder_name',
      header: 'Policyholder',
      render: (p) => <span style={{ fontWeight: 500 }}>{p.policyholder_name || 'Individual Insured'}</span>,
    },
    { key: 'policy_type', header: 'Policy Form' },
    {
      key: 'coverage_amount',
      header: 'Limit ($)',
      render: (p) => `$${Number(p.coverage_amount || 0).toLocaleString()}`,
    },
    {
      key: 'deductible',
      header: 'Deductible',
      render: (p) => `$${Number(p.deductible || 0).toLocaleString()}`,
    },
    {
      key: 'expiry_date',
      header: 'Term Validity',
      render: (p) => <span className="snow-caption">{p.effective_date} to {p.expiry_date}</span>,
    },
    {
      key: 'is_active',
      header: 'Status',
      render: (p) => (
        <BadgePill variant={p.is_active ? 'mint' : 'rose'}>
          {p.is_active ? 'Active' : 'Expired'}
        </BadgePill>
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Adjuster', 'Policy Directory']} activeTitle="Underwriting Policy Directory">
      {error && (
        <div
          className="snow-flex snow-items-center snow-gap-2"
          style={{
            padding: '12px 16px',
            backgroundColor: '#FEF2F2',
            border: '1px solid #FCA5A5',
            borderRadius: 12,
            color: '#B91C1C',
            fontSize: 13,
            marginBottom: 20,
          }}
        >
          <AlertTriangle size={16} />
          <span>{error}</span>
          <Button size="sm" variant="secondary" onClick={fetchPolicies} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading policy directory from database...</div>
        </Card>
      ) : policies.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Policies Available</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            There are no underwriting policy records registered in the system.
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={policies}
          keyField="id"
          searchPlaceholder="Filter policy database..."
        />
      )}
    </AppShell>
  );
}
