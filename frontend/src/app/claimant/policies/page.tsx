'use client';

import React, { useState, useEffect } from 'react';
import { Plus, ShieldCheck, Calendar, FileText, CheckCircle2 } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { DatePicker } from '@/components/ui/DatePicker';
import { BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { Policy } from '@/lib/types';
import { api } from '@/lib/api';

export default function ClaimantPoliciesPage() {
  const { showToast } = useToast();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);

  // Link Modal
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [policyNumber, setPolicyNumber] = useState('');
  const [dob, setDob] = useState('');
  const [phoneLast4, setPhoneLast4] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchPolicies = () => {
    setLoading(true);
    api.get<any>('/api/v1/policies/my-policies')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setPolicies(list);
      })
      .catch((err: any) => {
        setPolicies([]);
        showToast(err.message || 'Failed to load linked policies.', 'error');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleLinkPolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const newPolicy = await api.post<Policy>('/api/v1/policies/link', {
        policy_number: policyNumber.trim(),
        policyholder_dob: dob || undefined,
        policyholder_phone_last4: phoneLast4.trim(),
      });

      showToast('Policy successfully linked to your account!', 'success');
      setLinkModalOpen(false);
      setPolicyNumber('');
      setDob('');
      setPhoneLast4('');
      fetchPolicies();
    } catch (err: any) {
      showToast(err.message || 'Failed to link policy. Please check policy number and PII.', 'error');
    } finally {
      setSubmitting(false);
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
    { key: 'policy_type', header: 'Coverage Plan' },
    {
      key: 'coverage_amount',
      header: 'Coverage Limit',
      render: (p) => (p.coverage_amount ? `$${Number(p.coverage_amount).toLocaleString()}` : '—'),
    },
    {
      key: 'deductible',
      header: 'Deductible',
      render: (p) => (p.deductible ? `$${Number(p.deductible).toLocaleString()}` : '—'),
    },
    {
      key: 'expiry_date',
      header: 'Valid Through',
      render: (p) => (
        <span className="snow-caption" style={{ color: '#71717A' }}>
          {p.effective_date || 'N/A'} to {p.expiry_date || 'N/A'}
        </span>
      ),
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
    <AppShell breadcrumbs={['Claimant', 'Policies']} activeTitle="My Insurance Policies">
      <Table
        columns={columns}
        data={policies}
        keyField="policy_number"
        addLabel="Link Existing Policy"
        onAdd={() => setLinkModalOpen(true)}
        searchPlaceholder="Filter policies..."
      />

      {/* Link Policy Modal matching add-data.png */}
      <Modal
        isOpen={linkModalOpen}
        onClose={() => setLinkModalOpen(false)}
        title="Link Insurance Policy"
      >
        <form onSubmit={handleLinkPolicy}>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
            Verify your identity against the enterprise underwriting record to attach your coverage.
          </p>

          <Input
            label="Policy Identification Number"
            placeholder="e.g. MOT-5521"
            value={policyNumber}
            onChange={(e) => setPolicyNumber(e.target.value)}
            required
          />

          <DatePicker
            label="Policyholder Date of Birth"
            placeholder="Select date of birth"
            value={dob}
            onChange={(val) => setDob(val)}
          />

          <Input
            label="Registered Phone (Last 4 digits)"
            placeholder="e.g. 0004"
            maxLength={4}
            value={phoneLast4}
            onChange={(e) => setPhoneLast4(e.target.value)}
            required
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setLinkModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? 'Validating Policy...' : 'Link Policy'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
