'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Users, UserCheck, ShieldAlert, ArrowUpDown, ChevronRight, AlertTriangle, Inbox, ShieldCheck, CheckCircle2, TrendingUp, IndianRupee, Layers } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Card } from '@/components/ui/Card';
import { BadgeDot } from '@/components/ui/Badge';
import { MetricCard } from '@/components/ui/MetricCard';
import { DonutChart, BarChart } from '@/components/ui/Charts';
import { useToast } from '@/components/ui/Toast';
import { Claim, Adjuster } from '@/lib/types';
import { api } from '@/lib/api';

export default function AdminClaimsOversightPage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [claims, setClaims] = useState<Claim[]>([]);
  const [adjusters, setAdjusters] = useState<Adjuster[]>([]);
  const [dashboardMetrics, setDashboardMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reassignModalOpen, setReassignModalOpen] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState('');
  const [targetAdjusterId, setTargetAdjusterId] = useState('');
  const [reassignNote, setReassignNote] = useState('Administrative workload rebalancing');
  const [reassigning, setReassigning] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [claimsRes, adjustersRes, dashRes] = await Promise.all([
        api.get<any>('/api/v1/admin/claims'),
        api.get<any>('/api/v1/admin/adjusters').catch(() => []),
        api.get<any>('/api/v1/admin/dashboard').catch(() => null),
      ]);
      const rawList: Claim[] = Array.isArray(claimsRes) ? claimsRes : claimsRes?.items || [];
      // Only filed/submitted claims appear in Enterprise Claims Oversight
      const claimsList = rawList.filter(
        (c) => c.status && !['draft', 'pending_confirmation', 'discarded', 'not_started'].includes(c.status.toLowerCase())
      );
      const adjList: Adjuster[] = Array.isArray(adjustersRes) ? adjustersRes : adjustersRes?.items || [];
      setClaims(claimsList);
      setAdjusters(adjList);
      setDashboardMetrics(dashRes);
      if (adjList.length > 0 && !targetAdjusterId) {
        setTargetAdjusterId(adjList[0].id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load enterprise claims oversight.');
      setClaims([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleReassign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetAdjusterId) {
      showToast('Please select a target adjuster.', 'error');
      return;
    }
    setReassigning(true);

    try {
      await api.post(`/api/v1/admin/claims/${selectedTicket}/reassign`, {
        adjuster_id: targetAdjusterId,
        reason: reassignNote.trim() || 'Workload rebalancing',
      });
      showToast(`Claim #${selectedTicket} reassigned successfully!`, 'success');
      setReassignModalOpen(false);
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Failed to reassign claim.', 'error');
    } finally {
      setReassigning(false);
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
      render: (c) => <span style={{ fontWeight: 500 }}>{c.customer_id || 'Policyholder'}</span>,
    },
    { key: 'insurance_type', header: 'Coverage Form' },
    {
      key: 'estimated_claim_amount',
      header: 'Estimated Loss',
      render: (c) => (c.estimated_claim_amount ? `₹${Number(c.estimated_claim_amount).toLocaleString('en-IN')}` : '—'),
    },
    {
      key: 'assigned_adjuster',
      header: 'Assigned Adjuster',
      render: (c) => (
        <span className="snow-caption" style={{ fontWeight: 600 }}>
          {c.assigned_adjuster_name || c.pipeline_state?.assigned_adjuster_name || 'Unassigned'}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Workflow Stage',
      render: (c) => (
        <BadgeDot
          status={
            c.status === 'approved'
              ? 'complete'
              : c.status === 'under_review'
              ? 'progress'
              : c.status === 'pending_evidence'
              ? 'warning'
              : 'neutral'
          }
          label={c.status}
        />
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (c) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setSelectedTicket(c.ticket_id);
            if (adjusters.length > 0) setTargetAdjusterId(adjusters[0].id);
            setReassignModalOpen(true);
          }}
          icon={<UserCheck size={12} />}
        >
          Reassign
        </Button>
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Admin', 'Claims Oversight']} activeTitle="Enterprise Claims Oversight">
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
          <Button size="sm" variant="secondary" onClick={fetchData} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {dashboardMetrics && (
        <div style={{ marginBottom: 24 }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16,
              marginBottom: 16,
            }}
          >
            <MetricCard
              title="Active Policies"
              value={dashboardMetrics.policies.active}
              trend={`${dashboardMetrics.policies.linked} linked of ${dashboardMetrics.policies.total}`}
              trendDirection="up"
              tint="sky"
              icon={<ShieldCheck size={20} />}
            />
            <MetricCard
              title="Submitted Claims"
              value={dashboardMetrics.claims.total}
              trend={`${dashboardMetrics.claims.stages?.under_review || 0} in active review`}
              trendDirection="up"
              tint="indigo"
              icon={<Layers size={20} />}
            />
            <MetricCard
              title="Approved Settlement"
              value={`₹${Number(dashboardMetrics.settlement.approved_volume || 0).toLocaleString('en-IN')}`}
              trend={`${dashboardMetrics.settlement.approved_count || 0} claims settled`}
              trendDirection="up"
              tint="mint"
              icon={<IndianRupee size={20} />}
            />
            <MetricCard
              title="Adjuster Workload"
              value={`${dashboardMetrics.workload.active_adjusters} Active`}
              trend={`${dashboardMetrics.workload.utilization_pct}% capacity (${dashboardMetrics.workload.assigned_claims}/${dashboardMetrics.workload.capacity})`}
              trendDirection={dashboardMetrics.workload.utilization_pct > 85 ? 'down' : 'up'}
              tint="amber"
              icon={<Users size={20} />}
            />
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: 16,
            }}
          >
            <Card style={{ padding: 20 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 16, color: '#18181B' }}>
                Claims by Workflow Stage
              </div>
              <DonutChart
                segments={[
                  { label: 'Submitted', value: dashboardMetrics.claims.stages?.submitted || 0, color: '#0EA5E9' },
                  { label: 'Under Review', value: dashboardMetrics.claims.stages?.under_review || 0, color: '#6366F1' },
                  { label: 'Approved', value: dashboardMetrics.claims.stages?.approved || 0, color: '#10B981' },
                  { label: 'Settled', value: dashboardMetrics.claims.stages?.settled || 0, color: '#059669' },
                  { label: 'Rejected', value: dashboardMetrics.claims.stages?.rejected || 0, color: '#EF4444' },
                ].filter((s) => s.value > 0)}
              />
            </Card>

            <Card style={{ padding: 20 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 16, color: '#18181B' }}>
                Claims Stage Volume
              </div>
              <BarChart
                data={[
                  { label: 'Subm.', value: dashboardMetrics.claims.stages?.submitted || 0, color: '#0EA5E9' },
                  { label: 'Review', value: dashboardMetrics.claims.stages?.under_review || 0, color: '#6366F1' },
                  { label: 'Appr.', value: dashboardMetrics.claims.stages?.approved || 0, color: '#10B981' },
                  { label: 'Rej.', value: dashboardMetrics.claims.stages?.rejected || 0, color: '#EF4444' },
                ]}
              />
            </Card>
          </div>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading enterprise claims data from database...</div>
        </Card>
      ) : claims.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Enterprise Claims</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            There are currently no active claims recorded in the tenant database.
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={claims}
          keyField="ticket_id"
          hideRowActions={true}
          searchPlaceholder="Filter enterprise claims..."
        />
      )}

      {/* Reassign Adjuster Modal */}
      <Modal
        isOpen={reassignModalOpen}
        onClose={() => setReassignModalOpen(false)}
        title={`Reassign Claim #${selectedTicket}`}
      >
        <form onSubmit={handleReassign}>
          {adjusters.length === 0 ? (
            <div className="snow-form-group">
              <label className="snow-label">Select Target Adjuster</label>
              <p className="snow-caption" style={{ color: '#71717A' }}>
                No active adjusters available for reassignment.
              </p>
            </div>
          ) : (
            <Select
              label="Select Target Adjuster"
              value={targetAdjusterId}
              onChange={(val) => setTargetAdjusterId(val)}
              options={adjusters.map((adj) => ({
                value: adj.id,
                label: `${adj.name} (${adj.email}) — ${adj.specialization}`,
              }))}
              required
            />
          )}

          <div className="snow-form-group">
            <label className="snow-label">Reason for Reassignment</label>
            <input
              type="text"
              className="snow-input"
              value={reassignNote}
              onChange={(e) => setReassignNote(e.target.value)}
              required
            />
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setReassignModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={reassigning || adjusters.length === 0}>
              {reassigning ? 'Reassigning...' : 'Confirm Reassignment'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
