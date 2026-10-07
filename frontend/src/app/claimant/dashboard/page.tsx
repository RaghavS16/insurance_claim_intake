'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FilePlus, ShieldCheck, Clock, CheckCircle2, ChevronRight, AlertCircle, ArrowUpRight } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { MetricCard } from '@/components/ui/MetricCard';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgeDot } from '@/components/ui/Badge';
import { Claim } from '@/lib/types';
import { api } from '@/lib/api';

export default function ClaimantDashboardPage() {
  const router = useRouter();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [policiesCount, setPoliciesCount] = useState(0);
  const [activeDraft, setActiveDraft] = useState<Claim | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    const pClaims = api.get<any>('/api/v1/claims')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setClaims(list);
      })
      .catch(() => {
        setClaims([]);
      });

    const pPolicies = api.get<any>('/api/v1/policies/my-policies')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setPoliciesCount(list.length);
      })
      .catch(() => {
        setPoliciesCount(0);
      });

    const pActive = api.get<any>('/api/v1/claims/active')
      .then((data) => {
        if (data && (data.active || data.status === 'draft')) {
          setActiveDraft(data);
        } else {
          setActiveDraft(null);
        }
      })
      .catch(() => {
        setActiveDraft(null);
      });

    Promise.allSettled([pClaims, pPolicies, pActive]).finally(() => {
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

  const activeClaimsCount = claims.filter((c) => c.status !== 'approved' && c.status !== 'rejected').length;
  const approvedClaims = claims.filter((c) => c.status === 'approved');
  const totalSettlements = approvedClaims.reduce((sum, c) => sum + (c.estimated_claim_amount || 0), 0);
  const pendingActionsCount = claims.filter((c) => c.status === 'pending_evidence').length;

  return (
    <AppShell breadcrumbs={['Claimant', 'Overview']} activeTitle="Claims Overview">
      {/* Metric Cards Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <MetricCard
          title="Active Claims"
          value={loading ? '—' : activeClaimsCount}
          trend={activeClaimsCount > 0 ? `${activeClaimsCount} in progress` : 'No active claims'}
          trendDirection="up"
          tint="sky"
          icon={<Clock size={20} />}
        />
        <MetricCard
          title="Linked Policies"
          value={loading ? '—' : `${policiesCount} Active`}
          trend={policiesCount > 0 ? `${policiesCount} verified` : 'None linked'}
          trendDirection="up"
          tint="indigo"
          icon={<ShieldCheck size={20} />}
        />
        <MetricCard
          title="Approved Payouts"
          value={loading ? '—' : `$${totalSettlements.toLocaleString()}`}
          trend={`${approvedClaims.length} approved`}
          trendDirection="up"
          tint="mint"
          icon={<CheckCircle2 size={20} />}
        />
        <MetricCard
          title="Pending Evidence"
          value={loading ? '—' : `${pendingActionsCount} Items`}
          trend={pendingActionsCount > 0 ? 'Action required' : 'All clear'}
          trendDirection={pendingActionsCount > 0 ? 'down' : 'up'}
          tint="amber"
          icon={<AlertCircle size={20} />}
        />
      </div>

      {/* Resume Draft Banner if exists */}
      {activeDraft && (
        <div
          className="snow-card"
          style={{
            backgroundColor: '#F0EDFF',
            border: '1px solid #DFD8FC',
            marginBottom: 24,
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div className="snow-body" style={{ fontWeight: 600, color: '#7C3AED' }}>
              In-Progress Claim Intake Session ({activeDraft.ticket_id})
            </div>
            <div className="snow-caption" style={{ color: '#52525B', marginTop: 2 }}>
              {activeDraft.event_description || 'You have an unsubmitted claim session in progress.'}
            </div>
          </div>
          <div className="snow-flex snow-gap-2">
            <Link href="/claimant/file-claim">
              <Button size="sm" variant="primary">
                Resume Session
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Claims Table Section */}
      <Card
        title="Recent Claim Filings"
        action={
          <Link href="/claimant/file-claim">
            <Button size="sm" variant="primary" pill icon={<FilePlus size={14} />}>
              File New Claim
            </Button>
          </Link>
        }
      >
        <div className="snow-table-container">
          <table className="snow-table">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Insurance Type</th>
                <th>Incident Date</th>
                <th>Description</th>
                <th>Estimated Loss</th>
                <th>Status</th>
                <th style={{ width: 40 }} />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: '#71717A' }}>
                    Loading claims from database...
                  </td>
                </tr>
              ) : claims.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '40px 16px', color: '#71717A' }}>
                    <div style={{ fontWeight: 500, fontSize: 14 }}>No claims filed yet</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      Click "File New Claim" above to initiate conversational claim intake.
                    </div>
                  </td>
                </tr>
              ) : (
                claims.map((claim) => (
                  <tr
                    key={claim.id || claim.ticket_id}
                    onClick={() => router.push(`/claimant/claims/${claim.ticket_id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="snow-table-id">#{claim.ticket_id}</td>
                    <td>{claim.insurance_type || 'General'}</td>
                    <td>{claim.event_date || 'N/A'}</td>
                    <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {claim.event_description || '—'}
                    </td>
                    <td style={{ fontWeight: 600 }}>
                      {claim.estimated_claim_amount ? `$${Number(claim.estimated_claim_amount).toLocaleString()}` : '—'}
                    </td>
                    <td>{getStatusBadge(claim.status)}</td>
                    <td>
                      <ChevronRight size={16} color="#A1A1AA" />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </AppShell>
  );
}
