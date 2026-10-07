'use client';

import React, { useState, useEffect } from 'react';
import { BookOpen, Upload, Search, RefreshCw, CheckCircle2, FileText, Plus, AlertTriangle, Inbox } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { KnowledgeDocument } from '@/lib/types';
import { api } from '@/lib/api';

export default function KnowledgeBasePage() {
  const { showToast } = useToast();

  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload Modal
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [docType, setDocType] = useState('policy_wording');
  const [insType, setInsType] = useState('motor');
  const [jurisdiction, setJurisdiction] = useState('CA');
  const [version, setVersion] = useState('1.0');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  // Semantic Search Tester
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const fetchDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>('/api/v1/knowledge/documents');
      const list: KnowledgeDocument[] = Array.isArray(data) ? data : data?.items || [];
      setDocuments(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load knowledge documents.');
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      showToast('Please select a document file to upload.', 'error');
      return;
    }
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append('document_type', docType);
      formData.append('insurance_type', insType);
      formData.append('jurisdiction', jurisdiction);
      formData.append('policy_version', version);
      formData.append('file', selectedFile);

      await api.post('/api/v1/knowledge/upload', formData);
      showToast('Document uploaded and RAG indexing initiated!', 'success');
      setUploadModalOpen(false);
      setSelectedFile(null);
      fetchDocuments();
    } catch (err: any) {
      showToast(err.message || 'Failed to upload and ingest document.', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleSemanticSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const res = await api.get<any>(`/api/v1/knowledge/search?q=${encodeURIComponent(searchQuery)}`);
      const items = res?.items || (Array.isArray(res) ? res : []);
      setSearchResults(items);
    } catch (err: any) {
      showToast(err.message || 'Semantic search failed.', 'error');
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handlePublish = async (docId: string) => {
    try {
      await api.put(`/api/v1/knowledge/documents/${docId}`, {
        publication_status: 'published',
      });
      setDocuments(documents.map((d) => (d.id === docId ? { ...d, is_published: true, publication_status: 'published' } : d)));
      showToast('Document published to Copilot RAG pool!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to publish document.', 'error');
    }
  };

  const columns: Column<KnowledgeDocument>[] = [
    {
      key: 'source_name',
      header: 'Document Name',
      render: (d) => (
        <div className="snow-flex snow-items-center snow-gap-2">
          <FileText size={16} color="#007AFF" />
          <span style={{ fontWeight: 500 }}>{d.source_name}</span>
        </div>
      ),
    },
    { key: 'insurance_type', header: 'Line of Business' },
    { key: 'jurisdiction', header: 'Jurisdiction', render: (d) => d.jurisdiction || 'All' },
    { key: 'document_version', header: 'Version', render: (d) => d.document_version || d.policy_version || '1.0' },
    {
      key: 'chunk_count',
      header: 'Chunks',
      render: (d) => <span className="snow-caption">{d.chunk_count ?? d.chunks ?? '—'}</span>,
    },
    {
      key: 'is_published',
      header: 'RAG Status',
      render: (d) => {
        const isPub = d.is_published || d.publication_status === 'published';
        return (
          <BadgePill variant={isPub ? 'mint' : 'neutral'}>
            {isPub ? 'Published' : 'Pending'}
          </BadgePill>
        );
      },
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (d) => {
        const isPub = d.is_published || d.publication_status === 'published';
        return !isPub ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => handlePublish(d.id)}
            icon={<CheckCircle2 size={12} />}
          >
            Publish
          </Button>
        ) : (
          <span className="snow-micro" style={{ color: '#10B981', fontWeight: 600 }}>Active</span>
        );
      },
    },
  ];

  return (
    <AppShell breadcrumbs={['Adjuster', 'Knowledge Base']} activeTitle="Policy & Regulatory Knowledge">
      {/* Action Header */}
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 24 }}>
        <p className="snow-caption" style={{ color: '#71717A' }}>
          Authoritative policy wordings, regulatory guides, and endorsements indexed for Copilot RAG grounding.
        </p>

        <Button
          variant="primary"
          pill
          onClick={() => setUploadModalOpen(true)}
          icon={<Upload size={14} />}
        >
          Ingest Knowledge Document
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
          <Button size="sm" variant="secondary" onClick={fetchDocuments} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {/* Semantic Search Tester Card */}
      <Card title="Live RAG Semantic Retrieval Tester" style={{ marginBottom: 24 }}>
        <form onSubmit={handleSemanticSearch} className="snow-flex snow-gap-2">
          <Input
            placeholder="Query policy clauses (e.g., 'What is the standard deductible for windshield collision?')"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            iconLeft={<Search size={16} />}
          />
          <Button type="submit" variant="primary" disabled={searching}>
            {searching ? 'Querying...' : 'Search Vectors'}
          </Button>
        </form>

        {searchResults.length > 0 && (
          <div className="snow-flex-col snow-gap-3" style={{ marginTop: 16 }}>
            <div className="snow-caption" style={{ fontWeight: 600, color: '#1C1C1C' }}>
              Top Semantic Retrieval Matches:
            </div>
            {searchResults.map((res, i) => (
              <div
                key={i}
                style={{
                  padding: 12,
                  backgroundColor: '#FAFAFB',
                  border: '1px solid #EBECEF',
                  borderRadius: 10,
                }}
              >
                <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 4 }}>
                  <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                    {res.source_name || res.source || 'Policy Clause'}
                  </span>
                  <span className="snow-badge-pill purple">Score: {res.score ? res.score.toFixed(2) : '0.92'}</span>
                </div>
                <div className="snow-caption" style={{ color: '#52525B', lineHeight: 1.5 }}>
                  {res.text || res.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Document Library Table */}
      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading knowledge library from database...</div>
        </Card>
      ) : documents.length === 0 ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>No Knowledge Documents</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            No regulatory or policy documents have been ingested yet.
          </p>
        </Card>
      ) : (
        <Table
          columns={columns}
          data={documents}
          keyField="id"
          searchPlaceholder="Filter knowledge base..."
        />
      )}

      {/* Ingest Modal */}
      <Modal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        title="Ingest Policy Knowledge Document"
      >
        <form onSubmit={handleUpload}>
          <div className="snow-form-group">
            <label className="snow-label">Document Form Type</label>
            <select
              className="snow-select"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
            >
              <option value="policy_wording">Policy Master Wording</option>
              <option value="endorsement">Endorsement / Addendum</option>
              <option value="guideline">Adjudication Underwriting Guideline</option>
              <option value="statutory">Statutory / Regulatory Code</option>
            </select>
          </div>

          <Input
            label="Line of Business"
            value={insType}
            onChange={(e) => setInsType(e.target.value)}
            required
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input
              label="Jurisdiction Code"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              required
            />
            <Input
              label="Document Version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              required
            />
          </div>

          <div className="snow-form-group">
            <label className="snow-label">Select Document (.PDF, .TXT, .DOCX)</label>
            <input
              type="file"
              className="snow-input"
              style={{ paddingTop: 8 }}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setSelectedFile(e.target.files[0]);
                }
              }}
              required
            />
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setUploadModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={uploading}>
              {uploading ? 'Processing Ingestion...' : 'Ingest & Index'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
