'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  FolderOpen,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  UserCheck,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { MetricCard } from '@/components/ui/MetricCard';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgeDot } from '@/components/ui/Badge';
import { DonutChart, BarChart } from '@/components/ui/Charts';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function AdjusterDashboardPage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [metrics, setMetrics] = useState({
    totalClaims: 0,
    assignedToMe: 0,
    slaBreaches: 0,
    underReview: 0,
    pendingEvidence: 0,
  });

  const [recentClaims, setRecentClaims] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    const pDash = api.get<any>('/api/v1/adjuster/dashboard')
      .then((data) => {
        if (data) {
          setMetrics({
            totalClaims: data.total_filed_claims ?? data.total_claims ?? 0,
            assignedToMe: data.assigned_to_me ?? data.claims_assigned ?? 0,
            slaBreaches: data.sla_breached ?? data.sla_breaches ?? 0,
            underReview: data.under_review ?? 0,
            pendingEvidence: data.pending_evidence ?? 0,
          });
          if (Array.isArray(data.recent_claims) && data.recent_claims.length > 0) {
            setRecentClaims(data.recent_claims);
          }
        }
      })
      .catch(() => {});

    const pQueue = api.get<any>('/api/v1/adjuster/queue')
      .then((qData) => {
        const items = Array.isArray(qData) ? qData : qData?.items || [];
        if (items.length > 0) {
          setRecentClaims((prev) => (prev.length > 0 ? prev : items.slice(0, 5)));
        }
      })
      .catch(() => {});

    Promise.allSettled([pDash, pQueue]).finally(() => {
      setLoading(false);
    });
  }, []);

  const donutSegments = [
    { label: 'Under Review', value: Math.max(metrics.underReview, 1), color: '#8B5CF6' },
    { label: 'Pending Evidence', value: Math.max(metrics.pendingEvidence, 1), color: '#00D1FF' },
    { label: 'SLA At Risk', value: Math.max(metrics.slaBreaches, 1), color: '#F59E0B' },
    { label: 'Assigned', value: Math.max(metrics.assignedToMe, 1), color: '#10B981' },
  ];

  const barData = [
    { label: 'Pool', value: metrics.totalClaims, color: '#00D1FF' },
    { label: 'My Queue', value: metrics.assignedToMe, color: '#1C1C1C' },
    { label: 'In Review', value: metrics.underReview, color: '#8B5CF6' },
    { label: 'Evidence', value: metrics.pendingEvidence, color: '#B4C6FC' },
    { label: 'SLA Breach', value: metrics.slaBreaches, color: '#EF4444' },
  ];

  const handleNextClaim = async () => {
    try {
      const next = await api.get<any>('/api/v1/adjuster/next-claim');
      const ticket = next?.claim?.ticket_id || next?.ticket_id;
      if (ticket) {
        router.push(`/adjuster/claims/${ticket}`);
        return;
      }
      showToast('No pending claims waiting in your priority queue.', 'info');
    } catch (err: any) {
      showToast(err.message || 'No claims available to assign.', 'error');
    }
  };

  return (
    <AppShell breadcrumbs={['Adjuster', 'Dashboard']} activeTitle="Adjuster Workspace">
      {/* 4 Pastel Metric Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <MetricCard
          title="Total Claims in Pool"
          value={loading ? '—' : metrics.totalClaims}
          trend={`${metrics.totalClaims} system claims`}
          trendDirection="up"
          tint="sky"
          icon={<FolderOpen size={20} />}
        />
        <MetricCard
          title="Assigned to Me"
          value={loading ? '—' : metrics.assignedToMe}
          trend={metrics.assignedToMe > 0 ? 'Active workload' : 'Queue clear'}
          trendDirection="up"
          tint="indigo"
          icon={<UserCheck size={20} />}
        />
        <MetricCard
          title="SLA Risk / Breaches"
          value={loading ? '—' : metrics.slaBreaches}
          trend={metrics.slaBreaches > 0 ? 'Requires attention' : 'On track'}
          trendDirection={metrics.slaBreaches > 0 ? 'down' : 'up'}
          tint="rose"
          icon={<AlertTriangle size={20} />}
        />
        <MetricCard
          title="Pending Evidence"
          value={loading ? '—' : metrics.pendingEvidence}
          trend={`${metrics.underReview} in review`}
          trendDirection="up"
          tint="purple"
          icon={<TrendingUp size={20} />}
        />
      </div>

      {/* Middle Row: Status Donut Chart & Prioritized Tasks Table */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20, marginBottom: 24 }}>
        <Card title="Adjudication Distribution">
          <DonutChart segments={donutSegments} size={150} strokeWidth={20} />
        </Card>

        <Card
          title="Prioritized Adjudication Queue"
          action={
            <div className="snow-flex snow-gap-2">
              <Button size="sm" variant="primary" onClick={handleNextClaim}>
                Open Next Priority Claim
              </Button>
              <Link href="/adjuster/queue">
                <Button size="sm" variant="ghost" icon={<ArrowRight size={14} />}>
                  View All
                </Button>
              </Link>
            </div>
          }
        >
          <div className="snow-table-container">
            <table className="snow-table">
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Claimant / Customer</th>
                  <th>Coverage Type</th>
                  <th>Incident Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: '#71717A' }}>
                      Loading claims queue...
                    </td>
                  </tr>
                ) : recentClaims.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '32px 16px', color: '#71717A' }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>Queue is currently clear</div>
                      <div style={{ fontSize: 11, marginTop: 4 }}>No active claims requiring immediate action.</div>
                    </td>
                  </tr>
                ) : (
                  recentClaims.map((item) => (
                    <tr
                      key={item.id || item.ticket_id}
                      onClick={() => router.push(`/adjuster/claims/${item.ticket_id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="snow-table-id">#{item.ticket_id}</td>
                      <td style={{ fontWeight: 600 }}>{item.claimant_name || item.customer_id || 'Claimant'}</td>
                      <td>{item.insurance_type || 'General'}</td>
                      <td className="snow-caption">{item.event_date || 'N/A'}</td>
                      <td>
                        {item.status === 'approved' && <BadgeDot status="complete" label="Approved" />}
                        {item.status === 'under_review' && <BadgeDot status="progress" label="In Review" />}
                        {item.status === 'pending_evidence' && <BadgeDot status="warning" label="Pending Evidence" />}
                        {item.status === 'rejected' && <BadgeDot status="rejected" label="Rejected" />}
                        {!['approved', 'under_review', 'pending_evidence', 'rejected'].includes(item.status) && (
                          <BadgeDot status="neutral" label={item.status || 'Submitted'} />
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Bottom Row: Tasks Overview Bar Chart */}
      <Card title="Current Claims Distribution by Status">
        <BarChart data={barData} height={190} />
      </Card>
    </AppShell>
  );
}
