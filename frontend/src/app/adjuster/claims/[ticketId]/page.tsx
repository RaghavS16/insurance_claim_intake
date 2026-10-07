'use client';

import React, { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ShieldCheck,
  FileText,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Send,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
  ArrowLeft,
  Download,
  Clock,
  User,
  Paperclip,
  Inbox,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

interface CopilotChat {
  id: string;
  sender: 'adjuster' | 'copilot';
  text: string;
  citations?: string[];
}

export default function AdjusterClaimWorkspacePage({
  params,
}: {
  params: Promise<{ ticketId: string }>;
}) {
  const router = useRouter();
  const { showToast } = useToast();
  const resolvedParams = use(params);
  const ticketId = resolvedParams.ticketId;

  const [activeTab, setActiveTab] = useState<'facts' | 'evidence' | 'exceptions' | 'notes' | 'audit'>('facts');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Claim details from server
  const [claimData, setClaimData] = useState<any>(null);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);

  // Copilot State
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [copilotInput, setCopilotInput] = useState('');
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotChats, setCopilotChats] = useState<CopilotChat[]>([]);

  // Decision Modal
  const [decisionModalOpen, setDecisionModalOpen] = useState(false);
  const [decisionVerdict, setDecisionVerdict] = useState<'approve' | 'partial_approve' | 'reject' | 'escalate'>('approve');
  const [payoutAmount, setPayoutAmount] = useState('');
  const [decisionNotes, setDecisionNotes] = useState('Reviewed damages and verified coverage eligibility under policy terms.');
  const [submittingDecision, setSubmittingDecision] = useState(false);

  // Evidence Request Modal
  const [requestModalOpen, setRequestModalOpen] = useState(false);
  const [reqDocType, setReqDocType] = useState('Official Police Report');
  const [reqNotes, setReqNotes] = useState('Please provide the official incident report from the attending authority.');

  // Note Modal
  const [newNote, setNewNote] = useState('');

  const loadClaim = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<any>(`/api/v1/adjuster/claims/${ticketId}`);
      setClaimData(data);
      if (data?.claim?.estimated_claim_amount) {
        setPayoutAmount(String(data.claim.estimated_claim_amount));
      }

      // Populate copilot chat history if stored in pipeline state
      if (Array.isArray(data?.copilot_chat) && data.copilot_chat.length > 0) {
        setCopilotChats(
          data.copilot_chat.map((msg: any, i: number) => ({
            id: `msg-${i}`,
            sender: msg.speaker === 'adjuster' ? 'adjuster' : 'copilot',
            text: msg.text || msg.message || '',
            citations: msg.citations || [],
          }))
        );
      } else if (data?.copilot?.summary) {
        setCopilotChats([
          {
            id: 'init-copilot',
            sender: 'copilot',
            text: data.copilot.summary,
            citations: data.copilot.citations || [],
          },
        ]);
      }
    } catch (err: any) {
      setError(err.message || `Failed to load claim #${ticketId}`);
    } finally {
      setLoading(false);
    }
  };

  const loadAuditEvents = async () => {
    try {
      const res = await api.get<any[]>(`/api/v1/adjuster/claims/${ticketId}/audit`);
      if (Array.isArray(res)) {
        setAuditEvents(res);
      }
    } catch {}
  };

  useEffect(() => {
    loadClaim();
    loadAuditEvents();
  }, [ticketId]);

  const handleCopilotSend = async (suggested?: string) => {
    const text = suggested || copilotInput;
    if (!text.trim()) return;

    const userEntry: CopilotChat = {
      id: `u-${Date.now()}`,
      sender: 'adjuster',
      text,
    };
    setCopilotChats((prev) => [...prev, userEntry]);
    setCopilotInput('');
    setCopilotLoading(true);

    try {
      const res = await api.post<any>(`/api/v1/adjuster/claims/${ticketId}/copilot/chat`, { message: text });
      const reply: CopilotChat = {
        id: `c-${Date.now()}`,
        sender: 'copilot',
        text: res.reply || res.text || 'Copilot completed analysis for this claim.',
        citations: res.citations || [],
      };
      setCopilotChats((prev) => [...prev, reply]);
    } catch (err: any) {
      showToast(err.message || 'Copilot temporarily unavailable.', 'error');
    } finally {
      setCopilotLoading(false);
    }
  };

  const handleRecordDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (decisionNotes.trim().length < 10) {
      showToast('Rationale must be at least 10 characters long.', 'error');
      return;
    }
    setSubmittingDecision(true);

    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/decision`, {
        decision: decisionVerdict,
        approved_amount: payoutAmount ? Number(payoutAmount) : null,
        rationale: decisionNotes.trim(),
      });
      showToast(`Adjudication decision recorded: ${decisionVerdict.toUpperCase()}`, 'success');
      setDecisionModalOpen(false);
      loadClaim();
      loadAuditEvents();
    } catch (err: any) {
      showToast(err.message || 'Failed to record decision.', 'error');
    } finally {
      setSubmittingDecision(false);
    }
  };

  const handleSendEvidenceRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    const reqText = `${reqDocType.trim()}: ${reqNotes.trim()}`;
    if (reqText.length < 5) {
      showToast('Evidence request must be at least 5 characters.', 'error');
      return;
    }

    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/evidence-requests`, {
        request_text: reqText,
      });
      showToast('Official evidence request dispatched to claimant', 'success');
      setRequestModalOpen(false);
      loadClaim();
      loadAuditEvents();
    } catch (err: any) {
      showToast(err.message || 'Failed to dispatch evidence request.', 'error');
    }
  };

  const handleResolveException = async (excId: string) => {
    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/exceptions/${excId}/resolve`);
      showToast('Blocking exception resolved', 'success');
      loadClaim();
      loadAuditEvents();
    } catch (err: any) {
      showToast(err.message || 'Failed to resolve exception.', 'error');
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNote.trim()) return;

    try {
      await api.post(`/api/v1/adjuster/claims/${ticketId}/notes`, {
        note: newNote.trim(),
        visibility: 'internal',
      });
      setNewNote('');
      showToast('Case note added successfully', 'success');
      loadClaim();
      loadAuditEvents();
    } catch (err: any) {
      showToast(err.message || 'Failed to add note.', 'error');
    }
  };

  const claim = claimData?.claim || {};
  const extracted = claimData?.extracted_data || {};
  const policy = claimData?.policy || {};
  const evidenceList = claimData?.evidence || claim?.evidence || [];
  const openExceptions = claim?.open_exceptions || [];
  const notesList = claimData?.notes || [];

  return (
    <AppShell
      breadcrumbs={['Adjuster', 'Claims', ticketId]}
      activeTitle={`Claim Workspace #${ticketId}`}
      hideRightDrawer
    >
      {/* Top Header Actions */}
      <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
        <Link href="/adjuster/queue">
          <Button size="sm" variant="secondary" icon={<ArrowLeft size={14} />}>
            Back to Queue
          </Button>
        </Link>

        <div className="snow-flex snow-gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setRequestModalOpen(true)}
          >
            Request Evidence
          </Button>

          <Button
            size="sm"
            variant="primary"
            onClick={() => setDecisionModalOpen(true)}
            icon={<ShieldCheck size={14} />}
          >
            Record Decision
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
          <Button size="sm" variant="secondary" onClick={loadClaim} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <Card style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>
          <div className="snow-caption">Loading claim file and evidence dossier from database...</div>
        </Card>
      ) : !claimData ? (
        <Card style={{ padding: 48, textAlign: 'center' }}>
          <Inbox size={40} color="#A1A1AA" style={{ margin: '0 auto 12px' }} />
          <h3 className="snow-h2" style={{ fontSize: 16, marginBottom: 4 }}>Claim Not Found</h3>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            The requested claim #{ticketId} was not found or is not accessible.
          </p>
        </Card>
      ) : (
        /* Main Split Layout: Adjudication Tabs on Left, AI Copilot on Right */
        <div style={{ display: 'grid', gridTemplateColumns: copilotOpen ? '1fr 380px' : '1fr', gap: 24 }}>
          {/* Adjudication Workspace Left Column */}
          <div className="snow-flex-col snow-gap-4">
            {/* Workspace Tabs */}
            <div
              className="snow-flex snow-gap-4"
              style={{ borderBottom: '1px solid #EBECEF', paddingBottom: 4 }}
            >
              {[
                { id: 'facts', label: 'Loss Package' },
                { id: 'evidence', label: 'Evidence & Documents' },
                { id: 'exceptions', label: 'Exceptions' },
                { id: 'notes', label: 'Case Notes' },
                { id: 'audit', label: 'Audit Trail' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '8px 12px',
                    cursor: 'pointer',
                    fontSize: 14,
                    fontWeight: activeTab === tab.id ? 600 : 500,
                    color: activeTab === tab.id ? '#1C1C1C' : '#71717A',
                    borderBottom: activeTab === tab.id ? '2px solid #1C1C1C' : 'none',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Loss Package Tab */}
            {activeTab === 'facts' && (
              <div className="snow-flex-col snow-gap-4">
                <Card title="Incident Details & Loss Assessment">
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Claim Status</span>
                      <div className="snow-body" style={{ fontWeight: 600 }}>
                        <BadgeDot
                          status={claim.status === 'approved' ? 'complete' : claim.status === 'under_review' ? 'progress' : 'neutral'}
                          label={claim.status || 'Submitted'}
                        />
                      </div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Policy Ref</span>
                      <div className="snow-table-id">{policy?.policy_number || extracted?.policy_id || '—'}</div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Policy Type</span>
                      <div className="snow-body">{policy?.policy_type || claim.insurance_type || '—'}</div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Policyholder</span>
                      <div className="snow-body">{policy?.policyholder_name || 'Policyholder'}</div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Date</span>
                      <div className="snow-body">{claim.event_date || extracted?.incident_date || '—'}</div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Location</span>
                      <div className="snow-body">{claim.event_location || extracted?.incident_location || '—'}</div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Estimated Loss</span>
                      <div className="snow-body" style={{ fontWeight: 600 }}>
                        {claim.estimated_claim_amount ? `$${Number(claim.estimated_claim_amount).toLocaleString()}` : '—'}
                      </div>
                    </div>
                    <div>
                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Coverage Limit & Deductible</span>
                      <div className="snow-body">
                        {policy?.coverage_amount ? `$${Number(policy.coverage_amount).toLocaleString()} max` : '—'}
                        {policy?.deductible ? ` ($${Number(policy.deductible).toLocaleString()} ded.)` : ''}
                      </div>
                    </div>
                  </div>

                  <span className="snow-caption" style={{ color: '#A1A1AA' }}>Loss Narrative / Extracted Description</span>
                  <p className="snow-body" style={{ marginTop: 4, lineHeight: 1.6 }}>
                    {extracted?.incident_description || claim?.event_description || 'Detailed incident description provided during intake conversation.'}
                  </p>
                </Card>

                {/* Blocking Exceptions Alert */}
                <Card title="Adjudication Exceptions">
                  {openExceptions.length === 0 ? (
                    <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                      No open blocking exceptions on this claim.
                    </div>
                  ) : (
                    openExceptions.map((exc: any) => (
                      <div
                        key={exc.id}
                        className="snow-flex snow-justify-between snow-items-center"
                        style={{
                          padding: 14,
                          backgroundColor: exc.status === 'resolved' ? '#F4F5F7' : '#FFF4E5',
                          border: `1px solid ${exc.status === 'resolved' ? '#EBECEF' : '#FFE4BF'}`,
                          borderRadius: 12,
                          marginBottom: 8,
                        }}
                      >
                        <div>
                          <div className="snow-body" style={{ fontWeight: 600, color: exc.status === 'resolved' ? '#71717A' : '#D97706' }}>
                            {exc.event_type || 'Policy Exception'}
                          </div>
                          <div className="snow-caption" style={{ color: '#52525B' }}>{exc.reason}</div>
                        </div>
                        {exc.status === 'resolved' ? (
                          <BadgePill variant="mint">Resolved</BadgePill>
                        ) : (
                          <Button size="sm" variant="secondary" onClick={() => handleResolveException(exc.id)}>
                            Resolve Exception
                          </Button>
                        )}
                      </div>
                    ))
                  )}
                </Card>
              </div>
            )}

            {/* Evidence Tab */}
            {activeTab === 'evidence' && (
              <Card title="Submitted Claim Evidence & Artifacts">
                <div className="snow-flex-col snow-gap-3">
                  {evidenceList.length === 0 ? (
                    <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                      No evidence files uploaded yet.
                    </div>
                  ) : (
                    evidenceList.map((ev: any, idx: number) => (
                      <div key={idx} className="snow-flex snow-items-center snow-justify-between" style={{ padding: 14, backgroundColor: '#FAFAFB', borderRadius: 12 }}>
                        <div className="snow-flex snow-items-center snow-gap-3">
                          <FileText size={20} color="#007AFF" />
                          <div>
                            <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                              {ev.original_filename || ev.name || ev.filename || `Evidence Document #${idx + 1}`}
                            </div>
                            <div className="snow-micro">
                              {ev.status || ev.verification_status || 'Verified'} • Uploaded by Claimant
                            </div>
                          </div>
                        </div>
                        <BadgePill variant={ev.verification_status === 'verified' ? 'mint' : 'neutral'}>
                          {ev.verification_status || 'Submitted'}
                        </BadgePill>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            )}

            {/* Case Notes Tab */}
            {activeTab === 'notes' && (
              <Card title="Internal Adjudication Notes">
                <form onSubmit={handleAddNote} style={{ marginBottom: 20 }}>
                  <Input
                    placeholder="Add an internal note or underwriting observation..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                  />
                  <Button size="sm" variant="primary" type="submit" style={{ marginTop: 8 }}>
                    Post Note
                  </Button>
                </form>

                <div className="snow-flex-col snow-gap-3">
                  {notesList.length === 0 ? (
                    <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                      No internal notes recorded on this claim yet.
                    </div>
                  ) : (
                    notesList.map((n: any, i: number) => (
                      <div key={i} className="snow-card" style={{ padding: 14, backgroundColor: '#FAFAFB' }}>
                        <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 4 }}>
                          <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>{n.author || 'Adjuster'}</span>
                          <span className="snow-micro">{n.created_at || 'Recently'}</span>
                        </div>
                        <div className="snow-body" style={{ fontSize: 13 }}>{n.note || n.text}</div>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            )}

            {/* Audit Trail Tab */}
            {activeTab === 'audit' && (
              <Card title="Lifecycle Audit Trail">
                <div className="snow-flex-col snow-gap-4">
                  {auditEvents.length === 0 ? (
                    <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                      No audit events recorded yet.
                    </div>
                  ) : (
                    auditEvents.map((ev: any, i: number) => (
                      <div key={i} className="snow-flex snow-items-center snow-gap-3">
                        <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#007AFF' }} />
                        <div style={{ flex: 1 }}>
                          <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>{ev.event_type || ev.action}</span>
                          <div className="snow-caption" style={{ color: '#71717A' }}>
                            {ev.reason || (ev.actor_email ? `By ${ev.actor_email}` : 'System')}
                          </div>
                        </div>
                        <span className="snow-micro" style={{ color: '#A1A1AA' }}>{ev.created_at || ev.timestamp}</span>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            )}
          </div>

          {/* AI Copilot Side Drawer */}
          {copilotOpen && (
            <aside
              className="snow-card"
              style={{
                padding: 20,
                borderRadius: 20,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                maxHeight: 'calc(100vh - 180px)',
                boxShadow: '0 4px 20px rgba(0,0,0,0.04)',
              }}
            >
              {/* Copilot Header */}
              <div>
                <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 16 }}>
                  <div className="snow-flex snow-items-center snow-gap-2">
                    <div
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 6,
                        background: 'linear-gradient(135deg, #FF6B00 0%, #007AFF 50%, #10B981 100%)',
                      }}
                    />
                    <h3 className="snow-h3" style={{ fontSize: 16 }}>Copilot</h3>
                  </div>
                  <span className="snow-badge-pill purple">RAG Grounded</span>
                </div>

                {/* Chat Thread */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 14,
                    overflowY: 'auto',
                    maxHeight: 'calc(100vh - 380px)',
                    paddingRight: 4,
                  }}
                >
                  {copilotChats.length === 0 ? (
                    <div className="snow-caption" style={{ color: '#71717A', fontStyle: 'italic', padding: 8 }}>
                      Ask Copilot to analyze coverage limits, verify exclusions, or check policy clauses.
                    </div>
                  ) : (
                    copilotChats.map((c) => (
                      <div
                        key={c.id}
                        style={{
                          backgroundColor: c.sender === 'adjuster' ? '#B4C6FC' : '#F5F5F7',
                          color: '#1C1C1C',
                          borderRadius: c.sender === 'adjuster' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                          padding: '12px 14px',
                          fontSize: 13,
                          lineHeight: 1.5,
                          alignSelf: c.sender === 'adjuster' ? 'flex-end' : 'flex-start',
                          maxWidth: '92%',
                        }}
                      >
                        <div>{c.text}</div>
                        {c.citations && c.citations.length > 0 && (
                          <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid #EBECEF' }}>
                            <div className="snow-micro" style={{ fontWeight: 600, color: '#71717A', marginBottom: 2 }}>
                              POLICY CITATIONS:
                            </div>
                            {c.citations.map((cite, idx) => (
                              <div key={idx} className="snow-micro" style={{ color: '#007AFF' }}>
                                • {cite}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  {copilotLoading && (
                    <div className="snow-caption" style={{ color: '#71717A', fontStyle: 'italic' }}>
                      Copilot is querying policy knowledge base...
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Action Chips & Input Bar */}
              <div style={{ marginTop: 16 }}>
                <div className="snow-flex snow-gap-1" style={{ marginBottom: 10, overflowX: 'auto' }}>
                  <Button
                    size="sm"
                    variant="ghost"
                    style={{ fontSize: 11, background: '#F4F5F7', whiteSpace: 'nowrap' }}
                    onClick={() => handleCopilotSend('Verify coverage limits and deductible applicability')}
                  >
                    Coverage Limits
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    style={{ fontSize: 11, background: '#F4F5F7', whiteSpace: 'nowrap' }}
                    onClick={() => handleCopilotSend('Are there any policy exclusions or conditions that apply?')}
                  >
                    Exclusions Check
                  </Button>
                </div>

                <div
                  style={{
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    backgroundColor: '#FFFFFF',
                    border: '1px solid #E4E4E7',
                    borderRadius: 20,
                    padding: '4px 8px',
                  }}
                >
                  <input
                    type="text"
                    className="snow-input"
                    style={{ border: 'none', boxShadow: 'none', height: 34, fontSize: 13, padding: '0 8px' }}
                    placeholder="Ask Copilot a question..."
                    value={copilotInput}
                    onChange={(e) => setCopilotInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCopilotSend();
                    }}
                  />
                  <button
                    onClick={() => handleCopilotSend()}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: '#1C1C1C',
                      padding: 4,
                    }}
                    aria-label="Send to Copilot"
                  >
                    <Send size={14} />
                  </button>
                </div>
              </div>
            </aside>
          )}
        </div>
      )}

      {/* Record Decision Modal */}
      <Modal
        isOpen={decisionModalOpen}
        onClose={() => setDecisionModalOpen(false)}
        title="Record Adjudication Verdict"
      >
        <form onSubmit={handleRecordDecision}>
          <div className="snow-form-group">
            <label className="snow-label">Verdict Decision</label>
            <div className="snow-flex snow-gap-2">
              {[
                { id: 'approve', label: 'Approve' },
                { id: 'partial_approve', label: 'Partial Approve' },
                { id: 'reject', label: 'Reject' },
                { id: 'escalate', label: 'Escalate' },
              ].map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setDecisionVerdict(opt.id as any)}
                  style={{
                    flex: 1,
                    padding: '8px 4px',
                    borderRadius: 8,
                    border: decisionVerdict === opt.id ? '2px solid #1C1C1C' : '1px solid #E4E4E7',
                    background: decisionVerdict === opt.id ? '#1C1C1C' : '#FFFFFF',
                    color: decisionVerdict === opt.id ? '#FFFFFF' : '#1C1C1C',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <Input
            label="Settlement Approved Amount ($)"
            type="number"
            value={payoutAmount}
            onChange={(e) => setPayoutAmount(e.target.value)}
          />

          <Input
            label="Adjudication Rationale Note"
            value={decisionNotes}
            onChange={(e) => setDecisionNotes(e.target.value)}
            required
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setDecisionModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submittingDecision}>
              {submittingDecision ? 'Submitting...' : 'Record Verdict & Save'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Request Evidence Modal */}
      <Modal
        isOpen={requestModalOpen}
        onClose={() => setRequestModalOpen(false)}
        title="Request Evidence from Claimant"
      >
        <form onSubmit={handleSendEvidenceRequest}>
          <Input
            label="Evidence Document Type"
            value={reqDocType}
            onChange={(e) => setReqDocType(e.target.value)}
            required
          />

          <Input
            label="Inquiry Instructions for Claimant"
            value={reqNotes}
            onChange={(e) => setReqNotes(e.target.value)}
            required
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button type="button" variant="secondary" onClick={() => setRequestModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Send Request to Claimant
            </Button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
