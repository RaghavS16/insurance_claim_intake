'use client';

import React, { useState, useEffect } from 'react';
import { Plus, Upload, Download, ShieldCheck, FileSpreadsheet, Trash2, AlertTriangle, Inbox, Edit2 } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DatePicker } from '@/components/ui/DatePicker';
import { BadgePill, BadgeDot } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { FileUpload } from '@/components/ui/FileUpload';
import { Policy } from '@/lib/types';
import { api } from '@/lib/api';

const POLICY_FORM_OPTIONS = [
  { value: 'motor', label: 'Motor / Auto' },
  { value: 'home', label: 'Home / Property' },
  { value: 'health', label: 'Health' },
  { value: 'senior_health', label: 'Senior Health' },
  { value: 'travel', label: 'Travel' },
  { value: 'cyber', label: 'Cyber' },
];

export default function AdminPoliciesPage() {
  const { showToast } = useToast();

  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [isStrictPII, setIsStrictPII] = useState(false);
  const [polNumber, setPolNumber] = useState('');
  const [polType, setPolType] = useState('motor');
  const [holderName, setHolderName] = useState('');
  const [holderDob, setHolderDob] = useState('1990-01-01');
  const [holderPhone, setHolderPhone] = useState('');
  const [holderEmail, setHolderEmail] = useState('');
  const [coverageAmt, setCoverageAmt] = useState('50000');
  const [deductibleAmt, setDeductibleAmt] = useState('500');
  const [effectiveDate, setEffectiveDate] = useState('2026-01-01');
  const [expiryDate, setExpiryDate] = useState('2027-01-01');
  const [creating, setCreating] = useState(false);

  // Import Modal
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);

  // Edit Policy Modal
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
  const [editHolderName, setEditHolderName] = useState('');
  const [editHolderDob, setEditHolderDob] = useState('');
  const [editHolderPhone, setEditHolderPhone] = useState('');
  const [editHolderEmail, setEditHolderEmail] = useState('');
  const [editPolType, setEditPolType] = useState('motor');
  const [editCoverageAmt, setEditCoverageAmt] = useState('50000');
  const [editDeductibleAmt, setEditDeductibleAmt] = useState('500');
  const [editEffectiveDate, setEditEffectiveDate] = useState('2026-01-01');
  const [editExpiryDate, setEditExpiryDate] = useState('2027-01-01');
  const [editIsActive, setEditIsActive] = useState(true);
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchPolicies = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>('/api/v1/admin/policies');
      const list: Policy[] = Array.isArray(data) ? data : data?.items || [];
      setPolicies(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load policies database.');
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleOpenEdit = (p: Policy) => {
    setEditingPolicy(p);
    setEditHolderName(p.policyholder_name || '');
    setEditHolderDob(p.policyholder_dob || '');
    setEditHolderPhone(p.policyholder_phone || '');
    setEditHolderEmail(p.policyholder_email || '');
    setEditPolType(p.policy_type || 'motor');
    setEditCoverageAmt(String(p.coverage_amount || 50000));
    setEditDeductibleAmt(String(p.deductible || 500));
    setEditEffectiveDate(p.effective_date || '2026-01-01');
    setEditExpiryDate(p.expiry_date || '2027-01-01');
    setEditIsActive(p.is_active !== false);
    setEditModalOpen(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPolicy) return;
    setSavingEdit(true);
    try {
      const targetId = editingPolicy.policy_number || editingPolicy.id;
      await api.put(`/api/v1/admin/policies/${targetId}`, {
        policyholder_name: editHolderName.trim() || undefined,
        policyholder_dob: editHolderDob || undefined,
        policyholder_phone: editHolderPhone.trim() || undefined,
        policyholder_email: editHolderEmail.trim() || undefined,
        policy_type: editPolType,
        coverage_amount: Number(editCoverageAmt),
        deductible: Number(editDeductibleAmt),
        effective_date: editEffectiveDate,
        expiry_date: editExpiryDate,
        is_active: editIsActive,
      });
      setPolicies((prev) =>
        prev.map((p) =>
          p.id === editingPolicy.id || p.policy_number === editingPolicy.policy_number
            ? {
                ...p,
                policyholder_name: editHolderName.trim(),
                policyholder_dob: editHolderDob || undefined,
                policyholder_phone: editHolderPhone.trim() || undefined,
                policyholder_email: editHolderEmail.trim() || undefined,
                policy_type: editPolType,
                coverage_amount: Number(editCoverageAmt),
                deductible: Number(editDeductibleAmt),
                effective_date: editEffectiveDate,
                expiry_date: editExpiryDate,
                is_active: editIsActive,
              }
            : p
        )
      );
      showToast(`Policy ${editingPolicy.policy_number} updated successfully.`, 'success');
      setEditModalOpen(false);
    } catch (err: any) {
      showToast(err.message || 'Failed to update policy.', 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeletePolicy = async (p: Policy) => {
    if (!confirm(`Are you sure you want to delete policy ${p.policy_number}? This cannot be undone.`)) return;
    try {
      await api.delete(`/api/v1/admin/policies/${p.id || p.policy_number}`);
      showToast(`Policy ${p.policy_number} deleted successfully.`, 'success');
      setEditModalOpen(false);
      fetchPolicies();
    } catch (err: any) {
      showToast(err.message || 'Failed to delete policy.', 'error');
    }
  };

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    const endpoint = isStrictPII ? '/api/v1/admin/policies/strict' : '/api/v1/admin/policies';

    try {
      await api.post<Policy>(endpoint, {
        policy_number: polNumber.trim().toUpperCase(),
        policy_type: polType,
        policyholder_name: holderName.trim(),
        policyholder_dob: holderDob || undefined,
        policyholder_phone: holderPhone.trim() || undefined,
        policyholder_email: holderEmail.trim() || undefined,
        coverage_amount: Number(coverageAmt),
        deductible: Number(deductibleAmt),
        effective_date: effectiveDate,
        expiry_date: expiryDate,
      });
      showToast('Policy created successfully!', 'success');
      setCreateModalOpen(false);
      setPolNumber('');
      setHolderName('');
      setHolderPhone('');
      fetchPolicies();
    } catch (err: any) {
      showToast(err.message || 'Failed to create policy.', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleImportCSV = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFile) {
      showToast('Please select a .csv or .xlsx file.', 'error');
      return;
    }
    setImporting(true);

    try {
      const formData = new FormData();
      formData.append('file', importFile);
      const res = await api.post<any>('/api/v1/admin/policies/import', formData);
      const createdCount = res.imported ?? res.created ?? 0;
      const updatedCount = res.updated ?? 0;
      let toastMsg = `Bulk policies imported! Created: ${createdCount}, Updated: ${updatedCount}`;
      if (res.errors && Array.isArray(res.errors) && res.errors.length > 0) {
        toastMsg += ` (${res.errors.length} error${res.errors.length > 1 ? 's' : ''}: ${res.errors.slice(0, 2).join('; ')})`;
      }
      showToast(toastMsg, res.errors && res.errors.length > 0 ? 'info' : 'success');
      setImportModalOpen(false);
      setImportFile(null);
      fetchPolicies();
    } catch (err: any) {
      showToast(err.message || 'Failed to import policies.', 'error');
    } finally {
      setImporting(false);
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      await api.downloadFile('/api/v1/admin/policies/template?format=csv', 'policies_import_template.csv');
      showToast('Policy import template download completed', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to download policy template.', 'error');
    }
  };

  const handleExportCSV = async () => {
    try {
      await api.downloadFile('/api/v1/admin/policies/export?format=csv', 'policies_export.csv');
      showToast('Policies CSV export completed', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to export policies.', 'error');
    }
  };

  const columns: Column<Policy>[] = [
    {
      key: 'policy_number',
      header: 'Policy Number',
      render: (p) => (
        <div className="snow-flex snow-items-center snow-gap-2">
          <ShieldCheck size={16} color="#007AFF" />
          <span className="snow-table-id">{p.policy_number}</span>
        </div>
      ),
    },
    {
      key: 'policyholder_name',
      header: 'Policyholder',
      render: (p) => (
        <div className="snow-flex-col">
          <span style={{ fontWeight: 600 }}>{p.policyholder_name || 'Individual Insured'}</span>
          <span className="snow-micro" style={{ color: '#71717A' }}>
            {[p.policyholder_email, p.policyholder_phone].filter(Boolean).join(' • ') || 'No contact on file'}
          </span>
          {p.policyholder_dob && (
            <span className="snow-micro" style={{ color: '#A1A1AA' }}>DOB: {p.policyholder_dob}</span>
          )}
        </div>
      ),
    },
    {
      key: 'is_linked',
      header: 'Link Status',
      render: (p) => (
        <BadgeDot
          status={p.is_linked ? 'complete' : 'neutral'}
          label={p.is_linked ? 'Claimant Linked' : 'Unlinked'}
        />
      ),
    },
    { key: 'policy_type', header: 'Plan Form' },
    {
      key: 'coverage_amount',
      header: 'Coverage Limit',
      render: (p) => `₹${Number(p.coverage_amount || 0).toLocaleString('en-IN')}`,
    },
    {
      key: 'deductible',
      header: 'Deductible',
      render: (p) => `₹${Number(p.deductible || 0).toLocaleString('en-IN')}`,
    },
    {
      key: 'effective_date',
      header: 'Term Validity',
      render: (p) => <span className="snow-caption">{p.effective_date} to {p.expiry_date}</span>,
    },
    {
      key: 'is_active',
      header: 'Status',
      render: (p) => (
        <BadgePill variant={p.is_active ? 'mint' : 'rose'}>
          {p.is_active ? 'Active' : 'Expired'}
        </BadgePill>
      ),
    },
  ];

  return (
    <AppShell breadcrumbs={['Admin', 'Policies']} activeTitle="Policy Underwriting Registry">
      {/* Action Header */}
      <div className="snow-action-bar">
        <p className="snow-caption" style={{ color: '#71717A', margin: 0 }}>
          Master registry of underwritten policies. Supports single manual entry and bulk CSV/XLSX imports.
        </p>

        <div className="snow-action-buttons">
          <Button
            size="sm"
            variant="secondary"
            onClick={handleDownloadTemplate}
            icon={<FileSpreadsheet size={14} />}
          >
            Template
          </Button>
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
            onClick={() => setImportModalOpen(true)}
            icon={<Upload size={14} />}
          >
            Bulk Import
          </Button>
          <Button
            size="sm"
            variant="primary"
            pill
            onClick={() => setCreateModalOpen(true)}
            icon={<Plus size={14} />}
          >
            New Policy
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
          <Button size="sm" variant="secondary" onClick={fetchPolicies} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading policy registry from database...</div>
        </Card>
      ) : policies.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Policies in Registry</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            Create a single policy or perform a bulk CSV import to populate records.
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={policies}
          keyField="id"
          searchPlaceholder="Filter policy registry..."
          onEditRow={(p) => handleOpenEdit(p)}
        />
      )}

      {/* Create Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Create New Insurance Policy"
      >
        <form onSubmit={handleCreatePolicy}>
          <Input
            label="Policy Number"
            placeholder="POL-AUTO-10023"
            value={polNumber}
            onChange={(e) => setPolNumber(e.target.value)}
            required
          />

          <Select
            label="Policy Form Type"
            value={polType}
            options={POLICY_FORM_OPTIONS}
            onChange={setPolType}
            required
          />

          <Input
            label="Policyholder Full Name"
            placeholder="Johnathan Doe"
            value={holderName}
            onChange={(e) => setHolderName(e.target.value)}
            required
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <DatePicker
              label="Policyholder DOB"
              value={holderDob}
              onChange={setHolderDob}
              required
            />
            <Input
              label="Contact Phone"
              type="tel"
              placeholder="+1 555-123-4567"
              value={holderPhone}
              onChange={(e) => setHolderPhone(e.target.value)}
              required
            />
          </div>

          <Input
            label="Policyholder Email"
            type="email"
            placeholder="holder@example.com"
            value={holderEmail}
            onChange={(e) => setHolderEmail(e.target.value)}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input
              label="Coverage Limit ($)"
              type="number"
              value={coverageAmt}
              onChange={(e) => setCoverageAmt(e.target.value)}
              required
            />
            <Input
              label="Deductible ($)"
              type="number"
              value={deductibleAmt}
              onChange={(e) => setDeductibleAmt(e.target.value)}
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <DatePicker
              label="Effective Date"
              value={effectiveDate}
              onChange={setEffectiveDate}
              required
            />
            <DatePicker
              label="Expiry Date"
              value={expiryDate}
              onChange={setExpiryDate}
              required
            />
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={creating}>
              {creating ? 'Creating Policy...' : 'Save Policy Record'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Import Modal */}
      <Modal
        isOpen={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        title="Bulk Import Policies (CSV / Excel)"
      >
        <form onSubmit={handleImportCSV}>
          <div className="snow-form-group">
            <FileUpload
              label="Select .csv or .xlsx Spreadsheet"
              accept=".csv,.xlsx"
              file={importFile}
              onFileSelect={(f: File | null) => setImportFile(f)}
              hint="Download the standard CSV template for required columns and format validation."
            />
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setImportModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={importing}>
              {importing ? 'Processing Bulk File...' : 'Upload & Import'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Policy Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title={`Edit Policy #${editingPolicy?.policy_number || ''}`}
      >
        <form onSubmit={handleSaveEdit}>
          <Input
            label="Policyholder Full Name"
            placeholder="Jane Doe"
            value={editHolderName}
            onChange={(e) => setEditHolderName(e.target.value)}
            required
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <DatePicker
              label="Policyholder DOB"
              value={editHolderDob}
              onChange={(d) => setEditHolderDob(d)}
            />
            <Input
              label="Contact Phone"
              type="tel"
              placeholder="+1 555-0199"
              value={editHolderPhone}
              onChange={(e) => setEditHolderPhone(e.target.value)}
            />
          </div>

          <Input
            label="Policyholder Email"
            type="email"
            placeholder="policyholder@example.com"
            value={editHolderEmail}
            onChange={(e) => setEditHolderEmail(e.target.value)}
          />

          <Select
            label="Insurance Line / Form Type"
            value={editPolType}
            onChange={(val) => setEditPolType(val)}
            options={POLICY_FORM_OPTIONS}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input
              label="Coverage Limit ($)"
              type="number"
              value={editCoverageAmt}
              onChange={(e) => setEditCoverageAmt(e.target.value)}
              required
            />
            <Input
              label="Deductible ($)"
              type="number"
              value={editDeductibleAmt}
              onChange={(e) => setEditDeductibleAmt(e.target.value)}
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <DatePicker
              label="Effective Date"
              value={editEffectiveDate}
              onChange={(d) => setEditEffectiveDate(d)}
            />
            <DatePicker
              label="Expiry Date"
              value={editExpiryDate}
              onChange={(d) => setEditExpiryDate(d)}
            />
          </div>

          <Select
            label="Underwriting Policy Status"
            value={editIsActive ? 'active' : 'expired'}
            onChange={(val) => setEditIsActive(val === 'active')}
            options={[
              { value: 'active', label: 'Active (Valid coverage)' },
              { value: 'expired', label: 'Expired / Inactive' },
            ]}
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button
              type="button"
              variant="danger"
              onClick={() => editingPolicy && handleDeletePolicy(editingPolicy)}
              style={{ marginRight: 'auto' }}
            >
              Delete Policy
            </Button>
            <Button type="button" variant="secondary" onClick={() => setEditModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={savingEdit}>
              {savingEdit ? 'Saving Policy Changes...' : 'Save Policy Changes'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
