'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Inbox, Plus } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgeDot } from '@/components/ui/Badge';
import { Claim } from '@/lib/types';
import { api } from '@/lib/api';

export default function TrackClaimsPage() {
  const router = useRouter();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get<any>('/api/v1/claims?submitted=true')
      .then((data) => {
        const raw = Array.isArray(data) ? data : data?.items || [];
        // Only filed / submitted claims (exclude drafts / unsubmitted chat sessions)
        const submittedStatuses = ['submitted', 'assigned', 'under_review', 'pending_evidence', 'approved', 'partially_approved', 'rejected', 'escalated', 'closed'];
        const submittedOnly = raw.filter(
          (c: Claim) =>
            c.status &&
            submittedStatuses.includes(c.status.toLowerCase())
        );
        setClaims(submittedOnly);
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
        return <BadgeDot status="neutral" label={status || 'Submitted'} />;
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
      render: (c) => (c.estimated_claim_amount ? `₹${Number(c.estimated_claim_amount).toLocaleString('en-IN')}` : '—'),
    },
    {
      key: 'status',
      header: 'Adjudication Status',
      render: (c) => getStatusBadge(c.status),
    },
  ];

  return (
    <AppShell breadcrumbs={['Claimant', 'Track Claims']} activeTitle="Track Submitted Claims">
      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading submitted claims...</div>
        </Card>
      ) : claims.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Submitted Claims</h3>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            You do not have any filed claims in the adjudication pipeline. Draft chat sessions are not listed here.
          </p>
          <Button
            size="sm"
            variant="primary"
            pill
            icon={<Plus size={14} />}
            onClick={() => router.push('/claimant/file-claim?fresh=true')}
          >
            File New Claim
          </Button>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={claims}
          keyField="ticket_id"
          hideToolbar={true}
          hideRowActions={true}
          onRowClick={(item) => router.push(`/claimant/claims/${item.ticket_id}`)}
        />
      )}
    </AppShell>
  );
}
