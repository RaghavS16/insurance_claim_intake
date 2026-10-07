'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  FolderOpen,
  Filter,
  ArrowUpDown,
  Search,
  UserCheck,
  Kanban,
  List,
  CheckCircle2,
  Clock,
  AlertCircle,
  MoreHorizontal,
  Inbox,
  AlertTriangle,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { Claim, ClaimStatus } from '@/lib/types';
import { api } from '@/lib/api';

export default function AdjusterQueuePage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [viewMode, setViewMode] = useState<'table' | 'kanban'>('table');
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>('/api/v1/adjuster/queue');
      const list: Claim[] = Array.isArray(data) ? data : data?.items || [];
      setClaims(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load claims queue from server.');
      setClaims([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

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
      showToast('No pending claims in your queue.', 'info');
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

  const handleTransitionStatus = async (ticketId: string, newStatus: ClaimStatus) => {
    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/transition`, {
        status: newStatus,
        reason: 'Adjuster Kanban status change',
      });
      setClaims((prev) =>
        prev.map((c) => (c.ticket_id === ticketId ? { ...c, status: newStatus } : c))
      );
      showToast(`Claim #${ticketId} moved to ${newStatus}`, 'success');
    } catch (err: any) {
      showToast(err.message || `Failed to update status for claim #${ticketId}`, 'error');
    }
  };

  const getStatusBadge = (status: ClaimStatus) => {
    switch (status) {
      case 'approved': return <BadgeDot status="complete" label="Approved" />;
      case 'under_review': return <BadgeDot status="progress" label="In Review" />;
      case 'pending_evidence': return <BadgeDot status="warning" label="Pending Evidence" />;
      case 'rejected': return <BadgeDot status="rejected" label="Rejected" />;
      case 'escalated': return <BadgeDot status="warning" label="Escalated" />;
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
      header: 'Policyholder',
      render: (c) => (
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
            {c.customer_id ? c.customer_id[0].toUpperCase() : 'P'}
          </div>
          <span style={{ fontWeight: 500 }}>{c.customer_id || 'Policyholder'}</span>
        </div>
      ),
    },
    { key: 'insurance_type', header: 'Policy Coverage' },
    {
      key: 'estimated_claim_amount',
      header: 'Loss Amount',
      render: (c) => (c.estimated_claim_amount ? `$${c.estimated_claim_amount.toLocaleString()}` : '—'),
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
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => handleAssignToMe(c.ticket_id, e)}
          icon={<UserCheck size={12} />}
        >
          Assign
        </Button>
      ),
    },
  ];

  const kanbanColumns: { id: ClaimStatus; title: string; color: string }[] = [
    { id: 'submitted', title: 'New Submitted', color: '#71717A' },
    { id: 'under_review', title: 'Under Review', color: '#8B5CF6' },
    { id: 'pending_evidence', title: 'Pending Evidence', color: '#F59E0B' },
    { id: 'approved', title: 'Approved', color: '#10B981' },
    { id: 'rejected', title: 'Rejected', color: '#EF4444' },
  ];

  return (
    <AppShell breadcrumbs={['Adjuster', 'Claims Queue']} activeTitle="Claims Adjudication Queue">
      {/* Action Header */}
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
        <div className="snow-flex snow-gap-2">
          <Button
            size="sm"
            variant={viewMode === 'table' ? 'primary' : 'secondary'}
            onClick={() => setViewMode('table')}
            icon={<List size={14} />}
          >
            Table View
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'kanban' ? 'primary' : 'secondary'}
            onClick={() => setViewMode('kanban')}
            icon={<Kanban size={14} />}
          >
            Kanban Board
          </Button>
        </div>

        <Button
          variant="primary"
          pill
          onClick={handleNextClaim}
          icon={<CheckCircle2 size={16} />}
        >
          Open Next Priority Claim
        </Button>
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
          <div className="snow-caption">Loading assigned claims queue from server...</div>
        </Card>
      ) : claims.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Claims in Queue</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            There are currently no active claims requiring adjudication.
          </p>
        </Card>
      ) : viewMode === 'table' ? (
        <Table
          columns={columns}
          data={claims}
          keyField="ticket_id"
          onRowClick={(c) => router.push(`/adjuster/claims/${c.ticket_id}`)}
          searchPlaceholder="Filter queue..."
        />
      ) : (
        /* Kanban Board View */
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: 16,
            overflowX: 'auto',
            paddingBottom: 16,
          }}
        >
          {kanbanColumns.map((col) => {
            const colClaims = claims.filter((c) => c.status === col.id);

            return (
              <div
                key={col.id}
                style={{
                  backgroundColor: '#FAFAFB',
                  border: '1px solid #EBECEF',
                  borderRadius: 16,
                  padding: 16,
                  minWidth: 220,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}
              >
                <div className="snow-flex snow-justify-between snow-items-center">
                  <div className="snow-flex snow-items-center snow-gap-2">
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        backgroundColor: col.color,
                      }}
                    />
                    <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                      {col.title}
                    </span>
                  </div>
                  <span className="snow-badge-pill neutral">{colClaims.length}</span>
                </div>

                <div className="snow-flex-col snow-gap-3" style={{ flex: 1 }}>
                  {colClaims.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px 0', color: '#A1A1AA', fontSize: 12 }}>
                      No claims
                    </div>
                  ) : (
                    colClaims.map((claim) => (
                      <div
                        key={claim.ticket_id}
                        className="snow-card"
                        onClick={() => router.push(`/adjuster/claims/${claim.ticket_id}`)}
                        style={{
                          padding: 14,
                          cursor: 'pointer',
                          transition: 'transform 0.15s ease',
                        }}
                      >
                        <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 6 }}>
                          <span className="snow-table-id" style={{ fontSize: 12 }}>#{claim.ticket_id}</span>
                          <span className="snow-caption" style={{ fontWeight: 600 }}>
                            {claim.estimated_claim_amount ? `$${claim.estimated_claim_amount}` : ''}
                          </span>
                        </div>
                        <div className="snow-caption" style={{ color: '#71717A', marginBottom: 8 }}>
                          {claim.insurance_type}
                        </div>
                        <div className="snow-flex snow-justify-between snow-items-center">
                          <span className="snow-micro" style={{ color: '#A1A1AA' }}>{claim.created_at || claim.event_date || '—'}</span>
                          <select
                            className="snow-caption"
                            style={{
                              background: '#F4F5F7',
                              border: 'none',
                              borderRadius: 4,
                              padding: '2px 4px',
                              cursor: 'pointer',
                            }}
                            value={claim.status}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleTransitionStatus(claim.ticket_id, e.target.value as ClaimStatus)}
                          >
                            <option value="submitted">Submitted</option>
                            <option value="under_review">In Review</option>
                            <option value="pending_evidence">Pending</option>
                            <option value="approved">Approved</option>
                            <option value="rejected">Rejected</option>
                          </select>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
