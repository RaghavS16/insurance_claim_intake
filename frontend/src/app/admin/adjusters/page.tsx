'use client';

import React, { useState, useEffect } from 'react';
import { Mail, Download, RefreshCw, Trash2, KeyRound, AlertTriangle, Inbox, Edit2 } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
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
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newSpec, setNewSpec] = useState('motor');

  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [selectedAdjuster, setSelectedAdjuster] = useState<Adjuster | null>(null);

  // Edit Adjuster Modal State
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingAdjuster, setEditingAdjuster] = useState<Adjuster | null>(null);
  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editSpec, setEditSpec] = useState('motor');
  const [editActive, setEditActive] = useState(true);
  const [savingEdit, setSavingEdit] = useState(false);

  // Reset Password State
  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [resetResult, setResetResult] = useState<{ email: string; tempPass: string } | null>(null);

  const handleResetPassword = async (adjusterId: string, name: string) => {
    try {
      const res = await api.post<any>(`/api/v1/admin/adjusters/${adjusterId}/reset-password`);
      setResetResult({
        email: res.email || name,
        tempPass: res.temporary_password,
      });
      setResetModalOpen(true);
      showToast(`Temporary password generated for ${name}`, 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to reset adjuster password.', 'error');
    }
  };

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

  const handleOpenEdit = (adj: Adjuster) => {
    setEditingAdjuster(adj);
    setEditName(adj.name || '');
    setEditEmail(adj.email || '');
    setEditPhone(adj.phone || '');
    setEditSpec(adj.specialization || 'motor');
    setEditActive(adj.is_active !== false);
    setEditModalOpen(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAdjuster) return;
    setSavingEdit(true);
    try {
      await api.put(`/api/v1/admin/adjusters/${editingAdjuster.id}`, {
        name: editName.trim(),
        email: editEmail.trim(),
        phone: editPhone.trim(),
        specialization: editSpec,
        is_active: editActive,
      });
      setAdjusters((prev) =>
        prev.map((a) =>
          a.id === editingAdjuster.id
            ? { ...a, name: editName.trim(), email: editEmail.trim(), phone: editPhone.trim(), specialization: editSpec, is_active: editActive }
            : a
        )
      );
      showToast(`Adjuster ${editName} updated successfully.`, 'success');
      setEditModalOpen(false);
    } catch (err: any) {
      showToast(err.message || 'Failed to update adjuster.', 'error');
    } finally {
      setSavingEdit(false);
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

  const handleExportCSV = async () => {
    try {
      await api.downloadFile('/api/v1/admin/adjusters/export?format=csv', 'adjusters_roster.csv');
      showToast('Adjusters roster export completed', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to export adjusters roster.', 'error');
    }
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
        <div style={{ display: 'flex', gap: 6 }}>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => handleResetPassword(a.id, a.name)}
            icon={<KeyRound size={12} />}
          >
            Reset
          </Button>
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
        </div>
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
      render: (inv) => {
        const isAccepted = inv.status === 'accepted' || Boolean(inv.accepted_at);
        const isExpired = inv.status === 'expired';
        return (
          <BadgePill variant={isAccepted ? 'mint' : isExpired ? 'rose' : 'amber'}>
            {isAccepted ? 'Accepted' : isExpired ? 'Expired' : 'Pending'}
          </BadgePill>
        );
      },
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
      <div className="snow-action-bar">
        <div className="snow-action-buttons">
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

        <div className="snow-action-buttons">
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
            onEditRow={(adj) => handleOpenEdit(adj)}
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
          <Select
            label="Specialization"
            value={newSpec}
            onChange={(val) => setNewSpec(val)}
            options={[
              { value: 'motor', label: 'Motor / Auto' },
              { value: 'home', label: 'Home / Property' },
              { value: 'health', label: 'Health' },
              { value: 'senior_health', label: 'Senior Health' },
              { value: 'travel', label: 'Travel' },
              { value: 'cyber', label: 'Cyber' },
            ]}
          />

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

      {/* Edit Adjuster Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title="Edit Adjuster Profile"
      >
        <form onSubmit={handleSaveEdit}>
          <Input
            label="Full Name"
            placeholder="John Doe"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            required
          />
          <Input
            label="Corporate Email"
            type="email"
            placeholder="john.doe@intelliclaim.com"
            value={editEmail}
            onChange={(e) => setEditEmail(e.target.value)}
            required
          />
          <Input
            label="Direct Phone Number"
            type="tel"
            placeholder="+1 (555) 019-2834"
            value={editPhone}
            onChange={(e) => setEditPhone(e.target.value)}
            required
          />

          <Select
            label="Claim Adjudication Specialization"
            value={editSpec}
            onChange={(val) => setEditSpec(val)}
            options={[
              { value: 'motor', label: 'Motor & Collision Auto' },
              { value: 'home', label: 'Property & Casualty (Home)' },
              { value: 'health', label: 'Health & Medical Benefits' },
              { value: 'senior_health', label: 'Senior Health & Comprehensive Care' },
              { value: 'travel', label: 'Travel & Trip Delay' },
              { value: 'cyber', label: 'Cyber Risk & Data Breach' },
            ]}
          />

          <Select
            label="Account Status"
            value={editActive ? 'active' : 'inactive'}
            onChange={(val) => setEditActive(val === 'active')}
            options={[
              { value: 'active', label: 'Active (Can receive claim assignments)' },
              { value: 'inactive', label: 'Inactive / Suspended (No assignments)' },
            ]}
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setEditModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={savingEdit}>
              {savingEdit ? 'Saving Updates...' : 'Save Adjuster Changes'}
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

      {/* Reset Password Result Modal */}
      <Modal
        isOpen={resetModalOpen}
        onClose={() => setResetModalOpen(false)}
        title="Adjuster Temporary Credentials"
      >
        <p className="snow-body" style={{ marginBottom: 16 }}>
          A new temporary password has been generated for <strong>{resetResult?.email}</strong>. Existing sessions have been revoked.
        </p>
        <div style={{ backgroundColor: '#F1F5F9', padding: 12, borderRadius: 6, marginBottom: 20 }}>
          <div className="snow-caption" style={{ color: '#64748B', marginBottom: 4 }}>Temporary Password:</div>
          <code style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', userSelect: 'all' }}>{resetResult?.tempPass}</code>
        </div>
        <div className="snow-flex snow-justify-end">
          <Button type="button" variant="primary" onClick={() => setResetModalOpen(false)}>
            Done
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}
