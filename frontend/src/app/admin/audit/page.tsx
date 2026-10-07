'use client';

import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, KeyRound, UserCheck, AlertTriangle, Inbox } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgeDot } from '@/components/ui/Badge';
import { api } from '@/lib/api';

export default function AdminAuditTrailPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvents = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>('/api/v1/admin/audit/events');
      const list = Array.isArray(data) ? data : data?.items || [];
      setEvents(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load system audit trail.');
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  const getActionBadge = (action: string) => {
    const act = (action || '').toUpperCase();
    if (act.includes('DECISION') || act.includes('APPROVED')) {
      return <BadgeDot status="complete" label={action} />;
    } else if (act.includes('ENROLLED') || act.includes('VERIFIED') || act.includes('LOGIN')) {
      return <BadgeDot status="progress" label={action} />;
    } else if (act.includes('REASSIGN') || act.includes('INVITATION') || act.includes('FAIL')) {
      return <BadgeDot status="warning" label={action} />;
    }
    return <BadgeDot status="neutral" label={action} />;
  };

  const columns: Column<any>[] = [
    {
      key: 'sequence_no',
      header: 'Seq #',
      render: (e) => <span className="snow-caption" style={{ fontWeight: 600 }}>#{e.sequence_no ?? e.id?.slice(0, 8)}</span>,
    },
    {
      key: 'created_at',
      header: 'Event Timestamp',
      render: (e) => <span className="snow-caption">{e.created_at || e.timestamp || '—'}</span>,
    },
    {
      key: 'event_type',
      header: 'Security / Operational Action',
      render: (e) => getActionBadge(e.event_type || e.action || 'AUDIT_LOG'),
    },
    {
      key: 'resource_type',
      header: 'Target Resource',
      render: (e) => (
        <div>
          <span style={{ fontWeight: 600 }}>{e.resource_type || 'system'}</span>
          {e.resource_id && (
            <span className="snow-caption" style={{ color: '#71717A', marginLeft: 6 }}>
              ({String(e.resource_id).slice(0, 10)})
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'actor_user_id',
      header: 'Actor ID',
      render: (e) => <span className="snow-caption">{e.actor_user_id ? String(e.actor_user_id).slice(0, 12) + '...' : 'System Agent'}</span>,
    },
    {
      key: 'event_hash',
      header: 'Audit Hash',
      render: (e) => (
        <span className="snow-micro" style={{ fontFamily: 'monospace', color: '#71717A' }}>
          {e.event_hash ? e.event_hash.slice(0, 14) + '...' : '—'}
        </span>
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Admin', 'System Audit Trail']} activeTitle="System Security Audit Trail">
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
          <Button size="sm" variant="secondary" onClick={fetchEvents} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading cryptographic audit trail from database...</div>
        </Card>
      ) : events.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Audit Events</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            No administrative or security events have been recorded in the audit log yet.
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={events}
          keyField="id"
          searchPlaceholder="Filter audit records..."
        />
      )}
    </AppShell>
  );
}
