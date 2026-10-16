'use client';

import React, { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  FileText,
  Download,
  Copy,
  Printer,
  MessageSquare,
  ShieldCheck,
  Calendar,
  MapPin,
  Clock,
  ArrowLeft,
  Upload,
  Trash2,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { downloadDossierFile, printAdjudicationCertificate } from '@/lib/dossier-export';

export default function ClaimDetailsPage({
  params,
}: {
  params: Promise<{ ticketId: string }>;
}) {
  const router = useRouter();
  const { showToast } = useToast();
  const resolvedParams = use(params);
  const ticketId = resolvedParams.ticketId;

  const [claim, setClaim] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  // Export Dossier Modal
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [dossierText, setDossierText] = useState('');
  const [certificateData, setCertificateData] = useState<any>(null);

  // Respond Request Modal
  const [respondModalOpen, setRespondModalOpen] = useState(false);
  const [respondNote, setRespondNote] = useState('');
  const [respondFile, setRespondFile] = useState<File | null>(null);
  const [submittingResponse, setSubmittingResponse] = useState(false);

  // Conversation Transcript Drawer
  const [transcriptDrawerOpen, setTranscriptDrawerOpen] = useState(false);
  const [turns, setTurns] = useState<{ speaker: string; text: string }[]>([]);

  const fetchClaimData = () => {
    setLoading(true);
    setNotFound(false);

    api.get<any>(`/api/v1/claims/${ticketId}`)
      .then((data) => {
        if (data) {
          setClaim(data);
        } else {
          setNotFound(true);
        }
      })
      .catch((err) => {
        setNotFound(true);
      })
      .finally(() => {
        setLoading(false);
      });

    api.get<any>(`/api/v1/claims/${ticketId}/conversation`)
      .then((data) => {
        const convList = Array.isArray(data) ? data : data?.turns || data?.conversation || [];
        setTurns(convList);
      })
      .catch(() => {
        setTurns([]);
      });
  };

  useEffect(() => {
    fetchClaimData();
  }, [ticketId]);

  const handleExportDossier = async () => {
    try {
      const res = await api.get<any>(`/api/v1/claims/${ticketId}/export`);
      setDossierText(res?.formatted_text || (typeof res === 'string' ? res : JSON.stringify(res, null, 2)));
      setCertificateData(res?.certificate || null);
      setExportModalOpen(true);
    } catch (err: any) {
      showToast(err.message || 'Failed to export dossier.', 'error');
    }
  };

  const handleCopyDossier = () => {
    navigator.clipboard.writeText(dossierText);
    showToast('Dossier copied to clipboard', 'success');
  };

  const handleRespondRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!claim?.pending_request?.id) return;
    setSubmittingResponse(true);

    try {
      const formData = new FormData();
      if (respondNote.trim()) formData.append('response_note', respondNote.trim());
      if (respondFile) formData.append('file', respondFile);

      await api.post(`/api/v1/claims/${ticketId}/requests/${claim.pending_request.id}/respond`, formData);

      showToast('Response and document submitted to adjuster!', 'success');
      setRespondModalOpen(false);
      setRespondNote('');
      setRespondFile(null);
      fetchClaimData();
    } catch (err: any) {
      showToast(err.message || 'Failed to submit response to adjuster.', 'error');
    } finally {
      setSubmittingResponse(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return <BadgeDot status="complete" label="Approved" />;
      case 'under_review':
        return <BadgeDot status="progress" label="In Review" />;
      case 'pending_evidence':
        return <BadgeDot status="warning" label="Pending Evidence" />;
      case 'rejected':
        return <BadgeDot status="rejected" label="Rejected" />;
      default:
        return <BadgeDot status="neutral" label="Draft" />;
    }
  };

  const handleDiscardDraft = async () => {
    if (!window.confirm(`Are you sure you want to discard draft claim #${ticketId}?`)) return;
    try {
      await api.delete(`/api/v1/claims/${ticketId}`);
      showToast(`Draft claim #${ticketId} was discarded.`, 'info');
      router.push('/claimant/claims');
    } catch (err: any) {
      showToast(err.message || 'Failed to discard draft claim.', 'error');
    }
  };

  if (loading) {
    return (
      <AppShell breadcrumbs={['Claimant', 'Claims', ticketId]} activeTitle={`Claim File #${ticketId}`}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#71717A' }}>
          Loading claim file from database...
        </div>
      </AppShell>
    );
  }

  if (notFound || !claim) {
    return (
      <AppShell breadcrumbs={['Claimant', 'Claims', ticketId]} activeTitle="Claim Not Found">
        <div className="snow-card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="snow-h3" style={{ marginBottom: 8 }}>Claim #{ticketId} was not found</div>
          <div className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            This claim does not exist or you do not have permission to view it.
          </div>
          <Link href="/claimant/claims">
            <Button variant="primary" icon={<ArrowLeft size={14} />}>Back to Claims</Button>
          </Link>
        </div>
      </AppShell>
    );
  }

  const evidenceList = Array.isArray(claim.evidence) ? claim.evidence : [];

  return (
    <AppShell
      breadcrumbs={['Claimant', 'Claims', ticketId]}
      activeTitle={`Claim File #${ticketId}`}
    >
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
        <Link href="/claimant/claims">
          <Button size="sm" variant="secondary" icon={<ArrowLeft size={14} />}>
            Back to Claims
          </Button>
        </Link>

        <div className="snow-flex snow-gap-2">
          {(claim.status === 'draft' || claim.status === 'pending_confirmation') && (
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 size={14} />}
              onClick={handleDiscardDraft}
            >
              Discard Draft
            </Button>
          )}

          <Button
            size="sm"
            variant="secondary"
            icon={<MessageSquare size={14} />}
            onClick={() => setTranscriptDrawerOpen(true)}
          >
            View Dialogue Transcript ({turns.length})
          </Button>

          <Button
            size="sm"
            variant="primary"
            icon={<Download size={14} />}
            onClick={handleExportDossier}
          >
            Export Dossier
          </Button>
        </div>
      </div>

      {/* Adjuster Pending Request Alert Banner */}
      {claim.pending_request && (
        <div
          className="snow-card"
          style={{
            backgroundColor: '#FFF4E5',
            border: '1px solid #FFE4BF',
            marginBottom: 24,
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div className="snow-body" style={{ fontWeight: 600, color: '#D97706' }}>
              Action Required: Adjuster Evidence Inquiry
            </div>
            <div className="snow-caption" style={{ color: '#52525B', marginTop: 2 }}>
              {claim.pending_request.request_text || claim.pending_request.notes || 'Please upload the requested document to proceed.'}
            </div>
          </div>
          <Button size="sm" variant="primary" onClick={() => setRespondModalOpen(true)}>
            Respond with Document
          </Button>
        </div>
      )}

      {/* Claim Overview Anatomy */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        <div className="snow-flex-col snow-gap-6">
          <Card title="Incident Findings & Loss Summary">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Date</span>
                <div className="snow-body">{claim.event_date || 'N/A'}</div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Location</span>
                <div className="snow-body">{claim.event_location || 'N/A'}</div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Estimated Damage</span>
                <div className="snow-body" style={{ fontWeight: 600 }}>
                  {claim.estimated_claim_amount ? `$${Number(claim.estimated_claim_amount).toLocaleString()}` : '—'}
                </div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Adjudication Status</span>
                <div>
                  {getStatusBadge(claim.status)}
                </div>
              </div>
            </div>

            <div>
              <span className="snow-caption" style={{ color: '#A1A1AA' }}>Loss Narrative</span>
              <div className="snow-body" style={{ marginTop: 4, lineHeight: 1.6 }}>
                {claim.event_description || 'No description provided.'}
              </div>
            </div>
          </Card>

          {/* Dynamic Claim Details (RAG Intake Spec) */}
          {(() => {
            const ext = claim.extracted_data || claim.pipeline_state?.extracted_data || {};
            const keys = Object.keys(ext).filter(
              (k) => !['policy_id', 'insurance_type', 'event_date', 'event_location', 'event_description', 'estimated_claim_amount'].includes(k)
            );
            if (keys.length === 0) return null;
            return (
              <Card title="Policy Loss Specifics & Questionnaire Answers">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  {keys.map((k) => (
                    <div key={k} style={{ padding: '8px 12px', backgroundColor: '#FAFAFB', borderRadius: 8 }}>
                      <span className="snow-caption" style={{ color: '#71717A', textTransform: 'capitalize' }}>
                        {k.replace(/_/g, ' ')}
                      </span>
                      <div className="snow-body" style={{ fontWeight: 500, marginTop: 2 }}>
                        {typeof ext[k] === 'boolean' ? (ext[k] ? 'Yes' : 'No') : String(ext[k] ?? '—')}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })()}

          {/* Adjuster Evidence Requests History */}
          {(claim.evidence_requests && claim.evidence_requests.length > 0) && (
            <Card title="Adjuster Inquiries & Document Requests">
              <div className="snow-flex-col snow-gap-3">
                {claim.evidence_requests.map((req: any, idx: number) => (
                  <div
                    key={req.id || idx}
                    style={{
                      padding: '12px 14px',
                      backgroundColor: req.status === 'open' ? '#FFFBEB' : '#F9FAFB',
                      border: req.status === 'open' ? '1px solid #FDE68A' : '1px solid #E5E7EB',
                      borderRadius: 10,
                    }}
                  >
                    <div className="snow-flex snow-justify-between snow-items-center">
                      <div className="snow-body" style={{ fontWeight: 600, fontSize: 13, color: '#111827' }}>
                        Inquiry #{idx + 1}: {req.request_text || req.notes || 'Evidence required'}
                      </div>
                      <BadgePill variant={req.status === 'open' ? 'amber' : 'mint'}>
                        {req.status === 'open' ? 'Awaiting Response' : 'Responded'}
                      </BadgePill>
                    </div>
                    {req.requested_at && (
                      <div className="snow-micro" style={{ color: '#6B7280', marginTop: 4 }}>
                        Requested: {new Date(req.requested_at).toLocaleString()}
                      </div>
                    )}
                    {req.response_note && (
                      <div style={{ marginTop: 8, padding: '6px 10px', backgroundColor: '#FFFFFF', borderRadius: 6, border: '1px solid #E5E7EB' }}>
                        <span className="snow-micro" style={{ color: '#4B5563', fontWeight: 600 }}>Your Response:</span>
                        <div className="snow-caption" style={{ color: '#1F2937' }}>{req.response_note}</div>
                        {req.evidence_name && (
                          <div className="snow-micro" style={{ color: '#2563EB', marginTop: 2 }}>
                            📎 Attached: {req.evidence_name}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card title="Uploaded Evidence Documents">
            {evidenceList.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: '#71717A', fontSize: 13 }}>
                No evidence files attached to this claim file.
              </div>
            ) : (
              <div className="snow-flex-col snow-gap-2">
                {evidenceList.map((doc: any, i: number) => (
                  <div
                    key={doc.id || i}
                    className="snow-flex snow-items-center snow-justify-between"
                    style={{ padding: '12px 14px', backgroundColor: '#FAFAFB', borderRadius: 10 }}
                  >
                    <div className="snow-flex snow-items-center snow-gap-3">
                      <FileText size={18} color="#007AFF" />
                      <div>
                        <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                          {doc.filename || doc.name || `Document #${i + 1}`}
                        </div>
                        <div className="snow-micro" style={{ color: '#71717A' }}>
                          {doc.document_type || 'Evidence'} • Uploaded {doc.created_at || 'During Intake'}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="snow-flex-col snow-gap-6">
          <Card title="Policy Verification">
            <div className="snow-flex-col snow-gap-3">
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Policy Number</span>
                <div className="snow-table-id">{claim.policy_number || 'N/A'}</div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Coverage Limit</span>
                <div className="snow-body" style={{ fontWeight: 600 }}>
                  {claim.coverage_amount ? `$${Number(claim.coverage_amount).toLocaleString()}` : '—'}
                </div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Applicable Deductible</span>
                <div className="snow-body">
                  {claim.deductible ? `$${Number(claim.deductible).toLocaleString()}` : '—'}
                </div>
              </div>
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Assigned Adjuster</span>
                <div className="snow-body">{claim.assigned_adjuster || claim.pipeline_state?.assigned_adjuster || 'Pending Assignment'}</div>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Export Dossier Modal */}
      <Modal
        isOpen={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        title={`Claim Dossier & Settlement Certificate — #${ticketId}`}
        maxWidth={640}
      >
        <p className="snow-caption" style={{ color: '#71717A', marginBottom: 12 }}>
          Export the complete intake transcript dossier or print/save an official adjudication certificate with verified checksums.
        </p>

        <div style={{ position: 'relative' }}>
          <pre
            style={{
              backgroundColor: '#FAFAFB',
              border: '1px solid #EBECEF',
              borderRadius: 12,
              padding: 16,
              fontSize: 12,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              maxHeight: 280,
              overflowY: 'auto',
            }}
          >
            {dossierText}
          </pre>
        </div>

        <div className="snow-flex snow-justify-between snow-items-center snow-gap-2" style={{ marginTop: 20, flexWrap: 'wrap' }}>
          <div className="snow-flex snow-gap-2">
            <Button
              variant="secondary"
              icon={<Download size={14} />}
              onClick={() => downloadDossierFile(dossierText, `claim_${ticketId}_dossier.md`, 'text/markdown')}
            >
              .MD
            </Button>
            <Button
              variant="secondary"
              icon={<Download size={14} />}
              onClick={() => downloadDossierFile(dossierText, `claim_${ticketId}_dossier.txt`, 'text/plain')}
            >
              .TXT
            </Button>
            <Button
              variant="primary"
              icon={<Printer size={14} />}
              onClick={() => printAdjudicationCertificate(certificateData)}
              disabled={!certificateData}
            >
              Print / Save PDF Certificate
            </Button>
          </div>
          <div className="snow-flex snow-gap-2">
            <Button variant="secondary" icon={<Copy size={14} />} onClick={handleCopyDossier}>
              Copy Text
            </Button>
            <Button variant="secondary" onClick={() => setExportModalOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      </Modal>

      {/* Respond to Adjuster Request Modal */}
      <Modal
        isOpen={respondModalOpen}
        onClose={() => setRespondModalOpen(false)}
        title="Submit Requested Evidence"
      >
        <form onSubmit={handleRespondRequest}>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
            {claim.pending_request?.request_text || claim.pending_request?.notes || 'Please upload the requested document for the adjuster.'}
          </p>

          <Input
            label="Adjuster Response Note"
            placeholder="e.g. Attached certified repair estimate from AutoCraft Collision."
            value={respondNote}
            onChange={(e) => setRespondNote(e.target.value)}
            required
          />

          <div
            style={{
              border: '2px dashed #D1D5DB',
              borderRadius: 14,
              padding: '24px 16px',
              textAlign: 'center',
              backgroundColor: '#FAFAFB',
              marginBottom: 20,
              cursor: 'pointer',
            }}
            onClick={() => document.getElementById('respond-file-input')?.click()}
          >
            <Upload size={28} color="#71717A" style={{ marginBottom: 6 }} />
            <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
              {respondFile ? respondFile.name : 'Select requested PDF / Photo document'}
            </div>
            <input
              id="respond-file-input"
              type="file"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files?.[0]) setRespondFile(e.target.files[0]);
              }}
            />
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3">
            <Button type="button" variant="secondary" onClick={() => setRespondModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submittingResponse}>
              {submittingResponse ? 'Submitting...' : 'Send to Adjuster'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Dialogue Transcript Drawer */}
      <Modal
        isOpen={transcriptDrawerOpen}
        onClose={() => setTranscriptDrawerOpen(false)}
        title="Intake Dialogue Transcript"
        maxWidth={580}
      >
        <div className="snow-flex-col snow-gap-3" style={{ maxHeight: 400, overflowY: 'auto', padding: 8 }}>
          {turns.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#71717A', padding: '24px 0', fontSize: 13 }}>
              No recorded conversational turns for this claim.
            </div>
          ) : (
            turns.map((t, idx) => (
              <div
                key={idx}
                className={t.speaker === 'user' ? 'snow-chat-bubble-user' : 'snow-chat-bubble-assistant'}
              >
                <div className="snow-micro" style={{ marginBottom: 4, fontWeight: 600, opacity: 0.6 }}>
                  {t.speaker.toUpperCase()}
                </div>
                <div>{t.text}</div>
              </div>
            ))
          )}
        </div>
      </Modal>
    </AppShell>
  );
}
