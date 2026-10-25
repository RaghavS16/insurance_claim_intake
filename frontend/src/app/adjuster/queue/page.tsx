'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  UserCheck,
  CheckCircle2,
  Inbox,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { BadgeDot } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { Claim, ClaimStatus } from '@/lib/types';
import { api } from '@/lib/api';
import { usePolling, LiveIndicator } from '@/lib/use-polling';

export default function AdjusterQueuePage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [scope, setScope] = useState<'assigned' | 'unassigned'>('assigned');

  const {
    data: claimsData,
    setData: setClaimsData,
    isLoading: loading,
    error: pollError,
    secondsAgo,
    isRefreshing,
    refresh: fetchQueue,
  } = usePolling<Claim[]>(
    async (signal) => {
      const data = await api.get<any>(`/api/v1/adjuster/queue?scope=${scope}`, { signal });
      return Array.isArray(data) ? data : data?.items || [];
    },
    {
      intervalMs: 8000,
      initialData: [],
    }
  );

  useEffect(() => {
    fetchQueue();
  }, [scope]);

  const claims = claimsData || [];
  const error = pollError ? pollError.message : null;

  const handleNextClaim = async () => {
    try {
      const res = await api.get<any>('/api/v1/adjuster/next-claim');
      if (res?.claim?.ticket_id) {
        router.push(`/adjuster/claims/${res.claim.ticket_id}`);
        return;
      }
      if (res?.ticket_id) {
        router.push(`/adjuster/claims/${res.ticket_id}`);
        return;
      }
      showToast('No pending claims in your priority queue.', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to fetch next priority claim.', 'error');
    }
  };

  const handleAssignToMe = async (ticketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/assign`);
      showToast(`Claim #${ticketId} assigned to your queue!`, 'success');
      fetchQueue();
    } catch (err: any) {
      showToast(err.message || `Failed to assign claim #${ticketId}`, 'error');
    }
  };

  const getStatusBadge = (status: ClaimStatus) => {
    switch (status) {
      case 'approved': return <BadgeDot status="complete" label="Approved" />;
      case 'under_review': return <BadgeDot status="progress" label="In Review" />;
      case 'pending_evidence': return <BadgeDot status="warning" label="Pending Evidence" />;
      case 'rejected': return <BadgeDot status="rejected" label="Rejected" />;
      case 'escalated': return <BadgeDot status="warning" label="Escalated" />;
      case 'verified': return <BadgeDot status="progress" label="Verified" />;
      default: return <BadgeDot status="neutral" label="Submitted" />;
    }
  };

  const columns: Column<Claim>[] = [
    {
      key: 'ticket_id',
      header: 'Ticket ID',
      render: (c) => <span className="snow-table-id">#{c.ticket_id}</span>,
    },
    {
      key: 'customer_id',
      header: 'Claimant / Customer',
      render: (c: any) => {
        const name = c.policyholder_name || c.customer_name || c.customer_id || 'Claimant';
        return (
          <div className="snow-flex snow-items-center snow-gap-2">
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: '50%',
                backgroundColor: '#1C1C1C',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {name[0].toUpperCase()}
            </div>
            <span style={{ fontWeight: 500 }}>{name}</span>
          </div>
        );
      },
    },
    { key: 'insurance_type', header: 'Policy Coverage' },
    {
      key: 'estimated_claim_amount',
      header: 'Loss Amount',
      render: (c) => (c.estimated_claim_amount ? `₹${Number(c.estimated_claim_amount).toLocaleString('en-IN')}` : '—'),
    },
    {
      key: 'created_at',
      header: 'Filing Date',
      render: (c) => <span className="snow-caption">{c.created_at || c.event_date || '—'}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (c) => getStatusBadge(c.status),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (c) => (
        scope === 'assigned' ? (
          <Button
            size="sm"
            variant="primary"
            onClick={(e) => {
              e.stopPropagation();
              router.push(`/adjuster/claims/${c.ticket_id}`);
            }}
            icon={<ArrowRight size={12} />}
          >
            Adjudicate
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => handleAssignToMe(c.ticket_id, e)}
            icon={<UserCheck size={12} />}
          >
            Assign to Me
          </Button>
        )
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Adjuster', 'Claims Queue']} activeTitle="Claims Adjudication Queue">
      {/* Action Header */}
      <div className="snow-action-bar" style={{ marginBottom: 20 }}>
        <div className="snow-flex snow-items-center snow-gap-3">
          <div
            className="snow-flex snow-gap-1"
            style={{
              backgroundColor: '#F3F4F6',
              padding: '3px',
              borderRadius: 10,
              border: '1px solid #E5E7EB',
            }}
          >
            <button
              type="button"
              onClick={() => setScope('assigned')}
              style={{
                padding: '6px 14px',
                fontSize: 12,
                fontWeight: 600,
                borderRadius: 8,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: scope === 'assigned' ? '#FFFFFF' : 'transparent',
                color: scope === 'assigned' ? '#111827' : '#6B7280',
                boxShadow: scope === 'assigned' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              My Assigned Queue
            </button>
            <button
              type="button"
              onClick={() => setScope('unassigned')}
              style={{
                padding: '6px 14px',
                fontSize: 12,
                fontWeight: 600,
                borderRadius: 8,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: scope === 'unassigned' ? '#FFFFFF' : 'transparent',
                color: scope === 'unassigned' ? '#111827' : '#6B7280',
                boxShadow: scope === 'unassigned' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              Unassigned Pool
            </button>
          </div>
          <LiveIndicator secondsAgo={secondsAgo} isRefreshing={isRefreshing} />
        </div>

        <div className="snow-action-buttons">
          <Button
            variant="primary"
            pill
            onClick={handleNextClaim}
            icon={<CheckCircle2 size={16} />}
          >
            Open Next Priority Claim
          </Button>
        </div>
      </div>

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
          <Button size="sm" variant="secondary" onClick={fetchQueue} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">
            {scope === 'assigned' ? 'Loading your assigned claims queue...' : 'Loading unassigned claims pool...'}
          </div>
        </Card>
      ) : claims.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>
            {scope === 'assigned' ? 'Your Assigned Queue is Clear' : 'No Unassigned Claims in Pool'}
          </h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            {scope === 'assigned'
              ? 'There are currently no active claims assigned to your adjudication queue.'
              : 'All submitted claims across the system are currently assigned to active adjusters.'}
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={claims}
          keyField="ticket_id"
          hideRowActions={true}
          onRowClick={(c) => router.push(`/adjuster/claims/${c.ticket_id}`)}
          searchPlaceholder={scope === 'assigned' ? 'Filter assigned queue...' : 'Filter unassigned pool...'}
        />
      )}
    </AppShell>
  );
}
