'use client';

import React, { useState, useEffect } from 'react';
import { Plus, Upload, Download, ShieldCheck, FileSpreadsheet, Trash2, AlertTriangle, Inbox } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { Policy } from '@/lib/types';
import { api } from '@/lib/api';

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
      showToast(`Bulk policies imported! Created: ${res.created ?? 0}, Updated: ${res.updated ?? 0}`, 'success');
      setImportModalOpen(false);
      setImportFile(null);
      fetchPolicies();
    } catch (err: any) {
      showToast(err.message || 'Failed to import policies.', 'error');
    } finally {
      setImporting(false);
    }
  };

  const handleDownloadTemplate = () => {
    const token = localStorage.getItem('token') || '';
    window.open(`/api/v1/admin/policies/template?format=csv&token=${encodeURIComponent(token)}`, '_blank');
    showToast('Policy import template download initiated', 'info');
  };

  const handleExportCSV = () => {
    const token = localStorage.getItem('token') || '';
    window.open(`/api/v1/admin/policies/export?format=csv&token=${encodeURIComponent(token)}`, '_blank');
    showToast('Policies CSV export initiated', 'info');
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
      render: (p) => <span style={{ fontWeight: 600 }}>{p.policyholder_name || 'Individual Insured'}</span>,
    },
    { key: 'policy_type', header: 'Plan Form' },
    {
      key: 'coverage_amount',
      header: 'Coverage Limit',
      render: (p) => `$${Number(p.coverage_amount || 0).toLocaleString()}`,
    },
    {
      key: 'deductible',
      header: 'Deductible',
      render: (p) => `$${Number(p.deductible || 0).toLocaleString()}`,
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
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
        <p className="snow-caption" style={{ color: '#71717A' }}>
          Master registry of underwritten policies. Supports single manual entry and bulk CSV/XLSX imports.
        </p>

        <div className="snow-flex snow-gap-2">
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

          <div className="snow-form-group">
            <label className="snow-label">Policy Form Type</label>
            <select
              className="snow-select"
              value={polType}
              onChange={(e) => setPolType(e.target.value)}
            >
              <option value="motor">Motor / Auto</option>
              <option value="home">Home / Property</option>
              <option value="health">Health</option>
              <option value="senior_health">Senior Health</option>
              <option value="travel">Travel</option>
              <option value="cyber">Cyber</option>
            </select>
          </div>

          <Input
            label="Policyholder Full Name"
            placeholder="Johnathan Doe"
            value={holderName}
            onChange={(e) => setHolderName(e.target.value)}
            required
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input
              label="Policyholder DOB"
              type="date"
              value={holderDob}
              onChange={(e) => setHolderDob(e.target.value)}
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
            <Input
              label="Effective Date"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              required
            />
            <Input
              label="Expiry Date"
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
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
            <label className="snow-label">Select .csv or .xlsx Spreadsheet</label>
            <input
              type="file"
              accept=".csv,.xlsx"
              className="snow-input"
              style={{ paddingTop: 8 }}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setImportFile(e.target.files[0]);
                }
              }}
              required
            />
            <span className="snow-caption" style={{ color: '#71717A', marginTop: 4, display: 'block' }}>
              Download the standard CSV template for required columns and format validation.
            </span>
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
    </AppShell>
  );
}
