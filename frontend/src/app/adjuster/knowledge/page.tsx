'use client';

import React, { useState, useEffect } from 'react';
import { BookOpen, Upload, Search, RefreshCw, CheckCircle2, FileText, Plus, AlertTriangle, Inbox, Trash2 } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Table, Column } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card } from '@/components/ui/Card';
import { BadgePill } from '@/components/ui/Badge';
import { FileUpload } from '@/components/ui/FileUpload';
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
  const [jurisdiction, setJurisdiction] = useState('India');
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

  // Replace Modal State
  const [replaceModalOpen, setReplaceModalOpen] = useState(false);
  const [selectedDocIdForReplace, setSelectedDocIdForReplace] = useState<string>('');
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replacing, setReplacing] = useState(false);

  const handleReindex = async (docId: string) => {
    try {
      showToast('Re-indexing document chunks...', 'info');
      await api.post(`/api/v1/knowledge/documents/${docId}/reindex`, {});
      showToast('Document re-indexed successfully!', 'success');
      fetchDocuments();
    } catch (err: any) {
      showToast(err.message || 'Failed to re-index document.', 'error');
    }
  };

  const handleReplaceContent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replaceFile || !selectedDocIdForReplace) {
      showToast('Please choose a replacement file.', 'error');
      return;
    }
    setReplacing(true);
    try {
      const formData = new FormData();
      formData.append('file', replaceFile);
      await api.put(`/api/v1/knowledge/documents/${selectedDocIdForReplace}/content`, formData);
      showToast('Document content replaced and re-indexed!', 'success');
      setReplaceModalOpen(false);
      setReplaceFile(null);
      fetchDocuments();
    } catch (err: any) {
      showToast(err.message || 'Failed to replace document file.', 'error');
    } finally {
      setReplacing(false);
    }
  };

  const handlePublish = async (docId: string) => {
    try {
      await api.post(`/api/v1/knowledge/documents/${docId}/publish`, {});
      setDocuments(documents.map((d) => (d.id === docId ? { ...d, is_published: true, publication_status: 'published' } : d)));
      showToast('Document published and compiled into Copilot RAG manifest!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to publish document.', 'error');
    }
  };

  const handleDeleteDocument = async (docId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!confirm('Are you sure you want to delete this knowledge document? This will remove all indexed chunks.')) {
      return;
    }
    try {
      await api.delete(`/api/v1/knowledge/documents/${docId}`);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      showToast('Knowledge document deleted successfully.', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to delete knowledge document.', 'error');
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
    {
      key: 'document_type',
      header: 'Doc Type',
      render: (d) => {
        const type = ((d as any).document_type || '').toLowerCase();
        const isReg = type === 'regulation' || type === 'policy_regulatory' || type === 'regulatory';
        return (
          <BadgePill variant={isReg ? 'purple' : 'neutral'}>
            {isReg ? 'Regulatory' : 'Policy Wording'}
          </BadgePill>
        );
      },
    },
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
        return (
          <div className="snow-flex snow-items-center snow-gap-2">
            {!isPub && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => handlePublish(d.id)}
                icon={<CheckCircle2 size={12} />}
              >
                Publish
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleReindex(d.id)}
              title="Re-index document"
            >
              Re-index
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setSelectedDocIdForReplace(d.id);
                setReplaceModalOpen(true);
              }}
              title="Replace file content"
            >
              Replace File
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={(e) => handleDeleteDocument(d.id, e)}
              title="Delete document"
            >
              Delete
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <AppShell breadcrumbs={['Adjuster', 'Knowledge Base']} activeTitle="Policy & Regulatory Knowledge">
      {/* Action Header */}
      <div className="snow-action-bar">
        <p className="snow-caption" style={{ color: '#71717A', margin: 0 }}>
          Authoritative policy wordings, regulatory guides, and endorsements indexed for Copilot RAG grounding.
        </p>

        <div className="snow-action-buttons">
          <Button
            variant="primary"
            pill
            onClick={() => setUploadModalOpen(true)}
            icon={<Upload size={14} />}
          >
            Ingest Knowledge Document
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
          <Select
            label="Document Form Type"
            value={docType}
            onChange={(val) => setDocType(val)}
            options={[
              { value: 'policy_wording', label: 'Policy Wording' },
              { value: 'policy_regulatory', label: 'Policy Regulatory' },
            ]}
          />

          <Select
            label="Line of Business"
            value={insType}
            onChange={(val) => setInsType(val)}
            options={[
              { value: 'motor', label: 'Motor' },
              { value: 'home', label: 'Home / Property' },
              { value: 'health', label: 'Health' },
              { value: 'senior_health', label: 'Senior Health' },
              { value: 'travel', label: 'Travel' },
              { value: 'cyber', label: 'Cyber' },
            ]}
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

          <FileUpload
            label="Select Document (.PDF, .TXT, .DOCX)"
            accept=".pdf,.txt,.docx"
            value={selectedFile}
            onChange={setSelectedFile}
            buttonLabel="Choose Document File"
            helperText="PDF, DOCX, or TXT up to 150MB"
            required
          />

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

      {/* Replace Document Content Modal */}
      <Modal
        isOpen={replaceModalOpen}
        onClose={() => setReplaceModalOpen(false)}
        title="Replace Document Content File"
      >
        <form onSubmit={handleReplaceContent}>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
            Upload an updated version of this policy document. Existing chunks will be re-parsed and re-indexed.
          </p>

          <FileUpload
            label="Select Replacement File (.PDF, .TXT, .DOCX)"
            accept=".pdf,.txt,.docx"
            value={replaceFile}
            onChange={setReplaceFile}
            buttonLabel="Choose Replacement File"
            helperText="PDF, DOCX, or TXT up to 150MB"
            required
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setReplaceModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={replacing}>
              {replacing ? 'Replacing & Indexing...' : 'Upload & Replace'}
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
