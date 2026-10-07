'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, ChevronRight, FileText } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { BadgeDot } from '@/components/ui/Badge';
import { Claim } from '@/lib/types';
import { api } from '@/lib/api';

export default function TrackClaimsPage() {
  const router = useRouter();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get<any>('/api/v1/claims')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setClaims(list);
      })
      .catch(() => {
        setClaims([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return <BadgeDot status="complete" label="Approved" />;
      case 'under_review':
        return <BadgeDot status="progress" label="In Review" />;
      case 'pending_evidence':
        return <BadgeDot status="warning" label="Pending Evidence" />;
      case 'rejected':
        return <BadgeDot status="rejected" label="Rejected" />;
      default:
        return <BadgeDot status="neutral" label="Draft" />;
    }
  };

  const columns: Column<Claim>[] = [
    {
      key: 'ticket_id',
      header: 'Ticket ID',
      render: (c) => <span className="snow-table-id">#{c.ticket_id}</span>,
    },
    { key: 'insurance_type', header: 'Policy Type', render: (c) => c.insurance_type || 'General' },
    { key: 'event_date', header: 'Incident Date', render: (c) => c.event_date || 'N/A' },
    {
      key: 'event_description',
      header: 'Loss Summary',
      render: (c) => (
        <span style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block', whiteSpace: 'nowrap' }}>
          {c.event_description || '—'}
        </span>
      ),
    },
    {
      key: 'estimated_claim_amount',
      header: 'Estimated Loss',
      render: (c) => (c.estimated_claim_amount ? `$${Number(c.estimated_claim_amount).toLocaleString()}` : '—'),
    },
    {
      key: 'status',
      header: 'Adjudication Status',
      render: (c) => getStatusBadge(c.status),
    },
  ];

  return (
    <AppShell breadcrumbs={['Claimant', 'Track Claims']} activeTitle="Track Submitted Claims">
      <Table
        columns={columns}
        data={claims}
        keyField="ticket_id"
        addLabel="File New Claim"
        onAdd={() => router.push('/claimant/file-claim')}
        onRowClick={(item) => router.push(`/claimant/claims/${item.ticket_id}`)}
        searchPlaceholder="Search claims..."
      />
    </AppShell>
  );
}
