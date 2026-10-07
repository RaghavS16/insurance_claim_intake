'use client';

import React, { useState, useEffect } from 'react';
import { UserPlus, Mail, Download, RefreshCw, Trash2, KeyRound, AlertTriangle, Inbox } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { Adjuster } from '@/lib/types';
import { api } from '@/lib/api';

export default function AdminAdjustersPage() {
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState<'roster' | 'invitations'>('roster');

  const [adjusters, setAdjusters] = useState<Adjuster[]>([]);
  const [invitations, setInvitations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newSpec, setNewSpec] = useState('motor');

  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [selectedAdjuster, setSelectedAdjuster] = useState<Adjuster | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [adjRes, invRes] = await Promise.all([
        api.get<any>('/api/v1/admin/adjusters'),
        api.get<any>('/api/v1/admin/adjusters/invitations').catch(() => []),
      ]);
      const adjList: Adjuster[] = Array.isArray(adjRes) ? adjRes : adjRes?.items || [];
      const invList: any[] = Array.isArray(invRes) ? invRes : invRes?.items || [];
      setAdjusters(adjList);
      setInvitations(invList);
    } catch (err: any) {
      setError(err.message || 'Failed to load adjusters directory.');
      setAdjusters([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await api.post<Adjuster>('/api/v1/admin/adjusters', {
        name: newName,
        email: newEmail,
        phone: newPhone,
        specialization: newSpec,
      });
      showToast('Adjuster profile created successfully!', 'success');
      setCreateModalOpen(false);
      setNewName('');
      setNewEmail('');
      setNewPhone('');
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Failed to create adjuster.', 'error');
    }
  };

  const handleInviteAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post('/api/v1/admin/adjusters/invite', {
        name: newName,
        email: newEmail,
        phone: newPhone,
        specialization: newSpec,
      });
      showToast('Invitation email sent with onboarding link!', 'success');
      setInviteModalOpen(false);
      setNewName('');
      setNewEmail('');
      setNewPhone('');
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Failed to send invitation.', 'error');
    }
  };

  const handleResendInvite = async (invId: string) => {
    try {
      await api.post(`/api/v1/admin/adjusters/invitations/${invId}/resend`);
      showToast('Invitation resent successfully!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to resend invitation.', 'error');
    }
  };

  const handleDeactivate = async () => {
    if (!selectedAdjuster) return;
    try {
      await api.delete(`/api/v1/admin/adjusters/${selectedAdjuster.id}`);
      showToast(`Adjuster ${selectedAdjuster.name} removed/deactivated`, 'info');
      setDeactivateModalOpen(false);
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Failed to deactivate adjuster.', 'error');
    }
  };

  const handleExportCSV = () => {
    const token = localStorage.getItem('token') || '';
    window.open(`/api/v1/admin/adjusters/export?format=csv&token=${encodeURIComponent(token)}`, '_blank');
    showToast('Adjusters roster export initiated', 'info');
  };

  const columns: Column<Adjuster>[] = [
    {
      key: 'name',
      header: 'Adjuster',
      render: (a) => (
        <div className="snow-flex snow-items-center snow-gap-3">
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              backgroundColor: '#1C1C1C',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {a.name ? a.name[0].toUpperCase() : 'A'}
          </div>
          <div>
            <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</div>
            <div className="snow-caption" style={{ color: '#71717A' }}>{a.email}</div>
          </div>
        </div>
      ),
    },
    { key: 'phone', header: 'Contact Phone' },
    { key: 'specialization', header: 'Specialization' },
    {
      key: 'claims_assigned',
      header: 'Assigned Claims',
      render: (a) => <span className="snow-badge-pill neutral">{a.claims_assigned ?? 0} active</span>,
    },
    {
      key: 'is_active',
      header: 'Status',
      render: (a) => (
        <BadgePill variant={a.is_active ? 'mint' : 'rose'}>
          {a.is_active ? 'Active' : 'Inactive'}
        </BadgePill>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (a) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setSelectedAdjuster(a);
            setDeactivateModalOpen(true);
          }}
          icon={<Trash2 size={12} />}
        >
          Remove
        </Button>
      ),
    },
  ];

  const invColumns: Column<any>[] = [
    { key: 'email', header: 'Candidate Email' },
    { key: 'specialization', header: 'Specialization', render: (inv) => inv.specialization || 'General' },
    {
      key: 'created_at',
      header: 'Invited Date',
      render: (inv) => <span className="snow-caption">{inv.created_at || 'Recently'}</span>,
    },
    {
      key: 'status',
      header: 'Onboarding Status',
      render: (inv) => (
        <BadgePill variant={inv.accepted_at ? 'mint' : 'amber'}>
          {inv.accepted_at ? 'Accepted' : 'Pending'}
        </BadgePill>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (inv) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => handleResendInvite(inv.id)}
          icon={<RefreshCw size={12} />}
        >
          Resend
        </Button>
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Admin', 'Adjusters']} activeTitle="Adjusters Roster & Workforce">
      {/* Action Header */}
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
        <div className="snow-flex snow-gap-2">
          <Button
            size="sm"
            variant={activeTab === 'roster' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('roster')}
          >
            Active Roster ({adjusters.length})
          </Button>
          <Button
            size="sm"
            variant={activeTab === 'invitations' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('invitations')}
          >
            Pending Invites ({invitations.length})
          </Button>
        </div>

        <div className="snow-flex snow-gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={handleExportCSV}
            icon={<Download size={14} />}
          >
            Export CSV
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setCreateModalOpen(true)}
            icon={<UserPlus size={14} />}
          >
            Direct Provision
          </Button>
          <Button
            size="sm"
            variant="primary"
            pill
            onClick={() => setInviteModalOpen(true)}
            icon={<Mail size={14} />}
          >
            Send Onboarding Invite
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
          <Button size="sm" variant="secondary" onClick={fetchData} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading adjusters database...</div>
        </Card>
      ) : activeTab === 'roster' ? (
        adjusters.length === 0 ? (
          <Card style={{ padding: 48, textAlign: 'center' }}>
            <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
            <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Active Adjusters</h3>
            <p className="snow-caption" style={{ color: '#71717A' }}>
              No adjusters are currently provisioned in this tenant organization.
            </p>
          </Card>
        ) : (
          <Table
            columns={columns}
            data={adjusters}
            keyField="id"
            searchPlaceholder="Filter adjusters roster..."
          />
        )
      ) : invitations.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Pending Invitations</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            No adjuster onboarding invitations are currently awaiting completion.
          </p>
        </Card>
      ) : (
        <Table
          columns={invColumns}
          data={invitations}
          keyField="id"
          searchPlaceholder="Filter sent invitations..."
        />
      )}

      {/* Direct Provision Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Provision Adjuster Account"
      >
        <form onSubmit={handleCreateAdjuster}>
          <Input
            label="Full Name"
            placeholder="John Doe"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
          <Input
            label="Corporate Email"
            type="email"
            placeholder="j.doe@company.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <Input
            label="Phone Number"
            type="tel"
            placeholder="+1 555-019-2834"
            value={newPhone}
            onChange={(e) => setNewPhone(e.target.value)}
            required
          />
          <div className="snow-form-group">
            <label className="snow-label">Specialization</label>
            <select
              className="snow-select"
              value={newSpec}
              onChange={(e) => setNewSpec(e.target.value)}
            >
              <option value="motor">Motor / Auto</option>
              <option value="home">Home / Property</option>
              <option value="health">Health</option>
              <option value="senior_health">Senior Health</option>
              <option value="travel">Travel</option>
              <option value="cyber">Cyber</option>
            </select>
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Provision Adjuster
            </Button>
          </div>
        </form>
      </Modal>

      {/* Send Invite Modal */}
      <Modal
        isOpen={inviteModalOpen}
        onClose={() => setInviteModalOpen(false)}
        title="Send Adjuster Onboarding Invitation"
      >
        <form onSubmit={handleInviteAdjuster}>
          <Input
            label="Adjuster Full Name"
            placeholder="Jane Smith"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
          <Input
            label="Candidate Email Address"
            type="email"
            placeholder="candidate@company.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <Input
            label="Phone Number"
            type="tel"
            placeholder="+1 555-404-9218"
            value={newPhone}
            onChange={(e) => setNewPhone(e.target.value)}
            required
          />
          <div className="snow-form-group">
            <label className="snow-label">Specialization</label>
            <select
              className="snow-select"
              value={newSpec}
              onChange={(e) => setNewSpec(e.target.value)}
            >
              <option value="motor">Motor / Auto</option>
              <option value="home">Home / Property</option>
              <option value="health">Health</option>
              <option value="senior_health">Senior Health</option>
              <option value="travel">Travel</option>
              <option value="cyber">Cyber</option>
            </select>
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setInviteModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Dispatch Invitation Email
            </Button>
          </div>
        </form>
      </Modal>

      {/* Deactivate Modal */}
      <Modal
        isOpen={deactivateModalOpen}
        onClose={() => setDeactivateModalOpen(false)}
        title="Confirm Adjuster Removal"
      >
        <p className="snow-body" style={{ marginBottom: 20 }}>
          Are you sure you want to deactivate or remove adjuster{' '}
          <strong>{selectedAdjuster?.name}</strong>?
        </p>
        <div className="snow-flex snow-justify-between snow-gap-3">
          <Button type="button" variant="secondary" onClick={() => setDeactivateModalOpen(false)}>
            Cancel
          </Button>
          <Button type="button" variant="primary" onClick={handleDeactivate}>
            Confirm Deactivation
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}
