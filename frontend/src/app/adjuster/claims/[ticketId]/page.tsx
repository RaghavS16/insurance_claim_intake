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
import { usePolling, LiveIndicator } from '@/lib/use-polling';

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
  const [mobileTab, setMobileTab] = useState<'dossier' | 'copilot'>('dossier');
  const [auditEvents, setAuditEvents] = useState<any[]>([]);

  // Copilot State
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [copilotInput, setCopilotInput] = useState('');
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotChats, setCopilotChats] = useState<CopilotChat[]>([]);
  const [copilotSynopsis, setCopilotSynopsis] = useState<any>(null);
  const [fetchingCopilot, setFetchingCopilot] = useState(false);

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

  const isEditing =
    decisionModalOpen ||
    requestModalOpen ||
    Boolean(newNote.trim()) ||
    Boolean(copilotInput.trim());

  const {
    data: claimData,
    setData: setClaimData,
    isLoading: loading,
    error: pollError,
    secondsAgo,
    isRefreshing,
    refresh: loadClaim,
  } = usePolling<any>(
    async (signal) => {
      const data = await api.get<any>(`/api/v1/adjuster/claims/${ticketId}`, { signal });
      return data;
    },
    {
      intervalMs: 8000,
      enabled: Boolean(ticketId),
      isEditing,
      onSuccess: (data) => {
        if (data?.claim?.estimated_claim_amount && !payoutAmount) {
          setPayoutAmount(String(data.claim.estimated_claim_amount));
        }
        if (data?.copilot && Object.keys(data.copilot).length > 0) {
          setCopilotSynopsis((prev: any) => prev || data.copilot);
        }
        if (Array.isArray(data?.copilot_chat) && data.copilot_chat.length > 0) {
          setCopilotChats((prev) =>
            prev.length > 0
              ? prev
              : data.copilot_chat.map((msg: any, i: number) => ({
                id: `msg-${i}`,
                sender: msg.speaker === 'adjuster' ? 'adjuster' : 'copilot',
                text: msg.text || msg.message || '',
                citations: msg.citations || [],
              }))
          );
        } else if (data?.copilot?.summary) {
          setCopilotChats((prev) =>
            prev.length > 0
              ? prev
              : [
                {
                  id: 'init-copilot',
                  sender: 'copilot',
                  text: data.copilot.summary,
                  citations: data.copilot.citations || [],
                },
              ]
          );
        }
      },
    }
  );

  const error = pollError ? pollError.message : null;

  const loadAuditEvents = async () => {
    try {
      const res = await api.get<any[]>(`/api/v1/adjuster/claims/${ticketId}/audit`);
      if (Array.isArray(res)) {
        setAuditEvents(res);
      }
    } catch {
      // Audit logs may not be available yet
    }
  };

  const fetchCopilotSynopsis = async () => {
    setFetchingCopilot(true);
    try {
      const res = await api.get<any>(`/api/v1/adjuster/claims/${ticketId}/copilot`);
      const synopsis = res?.analysis || res?.copilot || (res?.executive_summary ? res : null);
      if (synopsis) {
        setCopilotSynopsis(synopsis);
      }
      if (Array.isArray(res?.chat) && res.chat.length > 0) {
        setCopilotChats((prev) =>
          prev.length > 0
            ? prev
            : res.chat.map((msg: any, i: number) => ({
              id: msg.id || `msg-${i}`,
              sender: msg.speaker === 'adjuster' ? 'adjuster' : 'copilot',
              text: msg.text || msg.message || '',
              citations: msg.citations || [],
            }))
        );
      }
    } catch (err: any) {
      console.debug('Copilot synopsis fetch non-fatal:', err);
    } finally {
      setFetchingCopilot(false);
    }
  };

  useEffect(() => {
    loadClaim();
    loadAuditEvents();
    fetchCopilotSynopsis();
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
        text: res.answer || res.reply || res.text || 'Copilot completed analysis for this claim.',
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
  const collectedFields = claimData?.submission_package?.collected_fields || claimData?.extracted_fields || [];

  return (
    <AppShell
      breadcrumbs={['Adjuster', 'Claims', ticketId]}
      activeTitle={`Claim Workspace #${ticketId}`}
      hideRightDrawer
      noScroll
    >
      {/* Top Header Actions */}
      <div className="snow-action-bar" style={{ flexShrink: 0, marginBottom: 14 }}>
        <div className="snow-flex snow-items-center snow-gap-3">
          <Link href="/adjuster/queue">
            <Button size="sm" variant="secondary" icon={<ArrowLeft size={14} />}>
              Back to Queue
            </Button>
          </Link>
          <LiveIndicator secondsAgo={secondsAgo} isRefreshing={isRefreshing} />
        </div>

        <div className="snow-action-buttons">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setCopilotOpen(!copilotOpen)}
            icon={<Sparkles size={14} color="#7C3AED" />}
          >
            {copilotOpen ? 'Hide Copilot' : 'Show Copilot'}
          </Button>

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
            marginBottom: 14,
            flexShrink: 0,
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
        <>
          {/* Mobile & Tablet Segmented Tab Switcher (<= 1024px) */}
          <div className="snow-workspace-mobile-tabs">
            <button
              type="button"
              className={`snow-workspace-mobile-tab-btn ${mobileTab === 'dossier' ? 'active' : ''}`}
              onClick={() => setMobileTab('dossier')}
            >
              Adjudication Dossier
            </button>
            <button
              type="button"
              className={`snow-workspace-mobile-tab-btn ${mobileTab === 'copilot' ? 'active' : ''}`}
              onClick={() => setMobileTab('copilot')}
            >
              Copilot Assistant
            </button>
          </div>

          {/* Main Split Layout: Fixed Headers, Independent Scrollable Panels */}
          <div className={`snow-workspace-split ${copilotOpen ? '' : 'copilot-closed'}`}>
            {/* Adjudication Workspace Left Column */}
            <div className={`snow-workspace-main-panel ${mobileTab === 'copilot' ? 'mobile-hidden' : ''}`}>
              {/* Workspace Tabs - FIXED */}
              <div className="snow-workspace-tabs-bar">
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
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Scrollable Tab Content Container - Only this scrolls */}
              <div className="snow-workspace-content-scroll snow-scrollbar">
                {/* Loss Package Tab */}
                {activeTab === 'facts' && (
                  <div className="snow-flex-col snow-gap-4">
                    {/* AI Copilot Claims Synopsis Card */}
                    <Card
                      title="AI Copilot Claims Synopsis & Adjudication Recommendation"
                      action={
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={fetchCopilotSynopsis}
                          disabled={fetchingCopilot}
                          icon={<Sparkles size={14} color="#7C3AED" />}
                        >
                          {fetchingCopilot ? 'Analyzing...' : 'Refresh AI Analysis'}
                        </Button>
                      }
                    >
                      {copilotSynopsis ? (
                        <div className="snow-flex-col snow-gap-3">
                          <div style={{ padding: '12px 14px', backgroundColor: '#F5F3FF', borderRadius: 10, border: '1px solid #DDD6FE' }}>
                            <div className="snow-caption" style={{ fontWeight: 700, color: '#6D28D9', textTransform: 'uppercase', marginBottom: 4 }}>
                              Executive Summary
                            </div>
                            <div className="snow-body" style={{ color: '#4C1D95', lineHeight: 1.5 }}>
                              {copilotSynopsis.executive_summary || copilotSynopsis.summary || 'Summary generated from claim facts and policy coverage.'}
                            </div>
                          </div>

                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                            <div style={{ padding: '10px 12px', backgroundColor: '#FAFAFB', borderRadius: 8, border: '1px solid #E5E7EB' }}>
                              <span className="snow-caption" style={{ color: '#6B7280' }}>Recommendation</span>
                              <div className="snow-body" style={{ fontWeight: 700, textTransform: 'uppercase', color: (copilotSynopsis.decision_recommendation || copilotSynopsis.recommendation) === 'approve' ? '#059669' : '#D97706' }}>
                                {copilotSynopsis.decision_recommendation || copilotSynopsis.recommendation || 'Under Review'}
                              </div>
                            </div>
                            <div style={{ padding: '10px 12px', backgroundColor: '#FAFAFB', borderRadius: 8, border: '1px solid #E5E7EB' }}>
                              <span className="snow-caption" style={{ color: '#6B7280' }}>Recommended Payout</span>
                              <div className="snow-body" style={{ fontWeight: 700, color: '#111827' }}>
                                {copilotSynopsis.recommended_payout_amount != null ? `₹${Number(copilotSynopsis.recommended_payout_amount).toLocaleString('en-IN')}` : '—'}
                              </div>
                            </div>
                            <div style={{ padding: '10px 12px', backgroundColor: '#FAFAFB', borderRadius: 8, border: '1px solid #E5E7EB' }}>
                              <span className="snow-caption" style={{ color: '#6B7280' }}>Confidence Score</span>
                              <div className="snow-body" style={{ fontWeight: 700, color: '#2563EB' }}>
                                {copilotSynopsis.confidence_score != null ? `${Math.round(Number(copilotSynopsis.confidence_score) * 100)}%` : '—'}
                              </div>
                            </div>
                          </div>

                          {Array.isArray(copilotSynopsis.risk_flags) && copilotSynopsis.risk_flags.length > 0 && (
                            <div style={{ padding: '10px 12px', backgroundColor: '#FEF2F2', borderRadius: 8, border: '1px solid #FECACA' }}>
                              <span className="snow-micro" style={{ fontWeight: 700, color: '#B91C1C' }}>RISK & FRAUD FLAGS:</span>
                              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                {copilotSynopsis.risk_flags.map((flag: any, idx: number) => (
                                  <li key={idx} className="snow-caption" style={{ color: '#991B1B' }}>
                                    {typeof flag === 'string' ? flag : JSON.stringify(flag)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {Array.isArray(copilotSynopsis.coverage_observations) && copilotSynopsis.coverage_observations.length > 0 && (
                            <div>
                              <span className="snow-micro" style={{ fontWeight: 700, color: '#4B5563' }}>COVERAGE OBSERVATIONS:</span>
                              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                {copilotSynopsis.coverage_observations.map((obs: any, idx: number) => (
                                  <li key={idx} className="snow-caption" style={{ color: '#374151' }}>
                                    {typeof obs === 'string' ? obs : JSON.stringify(obs)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {Array.isArray(copilotSynopsis.actionable_suggestions) && copilotSynopsis.actionable_suggestions.length > 0 && (
                            <div>
                              <span className="snow-micro" style={{ fontWeight: 700, color: '#4B5563' }}>ACTIONABLE SUGGESTIONS:</span>
                              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                {copilotSynopsis.actionable_suggestions.map((sug: any, idx: number) => (
                                  <li key={idx} className="snow-caption" style={{ color: '#374151' }}>
                                    {typeof sug === 'string' ? sug : JSON.stringify(sug)}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div style={{ padding: 16, textAlign: 'center', color: '#6B7280' }}>
                          <Button size="sm" variant="secondary" onClick={fetchCopilotSynopsis} disabled={fetchingCopilot}>
                            {fetchingCopilot ? 'Generating Copilot Analysis...' : 'Generate AI Copilot Analysis'}
                          </Button>
                        </div>
                      )}
                    </Card>

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
                            {claim.estimated_claim_amount ? `₹${Number(claim.estimated_claim_amount).toLocaleString('en-IN')}` : '—'}
                          </div>
                        </div>
                        <div>
                          <span className="snow-caption" style={{ color: '#A1A1AA' }}>Coverage Limit & Deductible</span>
                          <div className="snow-body">
                            {policy?.coverage_amount ? `₹${Number(policy.coverage_amount).toLocaleString('en-IN')} max` : '—'}
                            {policy?.deductible ? ` (₹${Number(policy.deductible).toLocaleString('en-IN')} ded.)` : ''}
                          </div>
                        </div>
                      </div>

                      <span className="snow-caption" style={{ color: '#A1A1AA' }}>Loss Narrative / Extracted Description</span>
                      <p className="snow-body" style={{ marginTop: 4, lineHeight: 1.6 }}>
                        {extracted?.incident_description || claim?.event_description || 'Detailed incident description provided during intake conversation.'}
                      </p>
                    </Card>

                    {/* Dynamically Rendered Policy & Regulatory Requirement Answers */}
                    <Card title="Source-of-Truth Requirements & Collected Answers">
                      <p className="snow-caption" style={{ color: '#71717A', marginBottom: 14 }}>
                        Requirements and verified answers dynamically surfaced from indexed policy wording and regulatory sources for this specific claim.
                      </p>
                      {collectedFields.length === 0 ? (
                        <div className="snow-caption" style={{ color: '#A1A1AA', padding: 8 }}>
                          No dynamic requirements or answers recorded yet.
                        </div>
                      ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                          {collectedFields.map((field: any, idx: number) => (
                            <div
                              key={field.field_key || idx}
                              style={{
                                padding: 14,
                                backgroundColor: '#FAFAFB',
                                borderRadius: 10,
                                border: '1px solid #EBECEF',
                              }}
                            >
                              <div
                                className="snow-caption"
                                style={{
                                  color: '#71717A',
                                  marginBottom: 6,
                                  fontSize: 11,
                                  textTransform: 'uppercase',
                                  letterSpacing: '0.04em',
                                  fontWeight: 600,
                                }}
                              >
                                {field.field_label || field.field_key}
                              </div>
                              <div
                                className="snow-body"
                                style={{
                                  fontWeight: 600,
                                  color: '#1C1C1C',
                                  fontSize: 14,
                                  wordBreak: 'break-word',
                                }}
                              >
                                {String(field.value ?? '—')}
                              </div>
                              {field.source_requirement_id && (
                                <div className="snow-caption" style={{ color: '#A1A1AA', fontSize: 10, marginTop: 6 }}>
                                  Policy Rule: {field.source_requirement_id}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </Card>
                  </div>
                )}

                {/* Evidence Tab */}
                {activeTab === 'evidence' && (
                  <div className="snow-flex-col snow-gap-4">
                    <Card title="Submitted Claim Evidence & Artifacts">
                      <div className="snow-flex-col snow-gap-3">
                        {evidenceList.length === 0 ? (
                          <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                            No evidence files uploaded yet.
                          </div>
                        ) : (
                          evidenceList.map((ev: any, idx: number) => (
                            <div key={idx} style={{ padding: 14, backgroundColor: '#FAFAFB', borderRadius: 12, border: '1px solid #EBECEF' }}>
                              <div className="snow-flex snow-items-center snow-justify-between">
                                <div className="snow-flex snow-items-center snow-gap-3">
                                  <FileText size={20} color="#007AFF" />
                                  <div>
                                    <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                                      {ev.original_filename || ev.name || ev.filename || `Evidence Document #${idx + 1}`}
                                    </div>
                                    <div className="snow-micro" style={{ color: '#71717A' }}>
                                      Detected Type: <strong>{ev.detected_document_type || 'General Evidence'}</strong> • OCR Confidence: <strong>{ev.verification_confidence != null ? `${Math.round(Number(ev.verification_confidence) * 100)}%` : 'N/A'}</strong>
                                    </div>
                                  </div>
                                </div>
                                <div className="snow-flex snow-items-center snow-gap-2">
                                  <BadgePill variant={ev.verification_status === 'verified' ? 'mint' : 'neutral'}>
                                    {ev.verification_status || ev.status || 'Submitted'}
                                  </BadgePill>
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={async () => {
                                      try {
                                        const res = await api.get<any>(`/api/v1/adjuster/claims/${ticketId}/evidence/${ev.id}/url`);
                                        if (res?.url) {
                                          if (res.url.startsWith('/api/')) {
                                            await api.downloadFile(res.url, ev.original_filename || ev.name || ev.filename || `evidence-${ev.id}`);
                                          } else {
                                            window.open(res.url, '_blank');
                                          }
                                        }
                                      } catch (err: any) {
                                        showToast(err.message || 'Failed to get document download URL', 'error');
                                      }
                                    }}
                                  >
                                    View / Download
                                  </Button>
                                </div>
                              </div>
                              {ev.verification_reason && (
                                <div className="snow-micro" style={{ color: '#4B5563', marginTop: 8, padding: '4px 8px', backgroundColor: '#F3F4F6', borderRadius: 6 }}>
                                  Verification: {ev.verification_reason}
                                </div>
                              )}
                              {ev.extracted_fields && Object.keys(ev.extracted_fields).length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <span className="snow-micro" style={{ fontWeight: 600, color: '#6B7280' }}>OCR EXTRACTED FIELDS:</span>
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6, marginTop: 4 }}>
                                    {Object.entries(ev.extracted_fields).map(([k, v]) => (
                                      <div key={k} className="snow-micro" style={{ padding: '2px 6px', backgroundColor: '#FFFFFF', borderRadius: 4, border: '1px solid #E5E7EB' }}>
                                        <strong>{k}:</strong> {String(v)}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </Card>

                    {/* Adjuster Evidence Requests Section */}
                    <Card title="Adjuster Evidence Inquiries & Claimant Responses">
                      {(!claimData?.evidence_requests || claimData.evidence_requests.length === 0) ? (
                        <div className="snow-caption" style={{ color: '#71717A', padding: 8 }}>
                          No evidence requests issued to claimant yet.
                        </div>
                      ) : (
                        <div className="snow-flex-col snow-gap-3">
                          {claimData.evidence_requests.map((req: any, idx: number) => (
                            <div key={req.id || idx} style={{ padding: 12, backgroundColor: req.status === 'open' ? '#FFFBEB' : '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: 10 }}>
                              <div className="snow-flex snow-justify-between snow-items-center">
                                <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                                  Request #{idx + 1}: {req.request_text || req.notes}
                                </span>
                                <BadgePill variant={req.status === 'open' ? 'amber' : 'mint'}>
                                  {req.status === 'open' ? 'Awaiting Claimant' : 'Responded'}
                                </BadgePill>
                              </div>
                              {req.response_note && (
                                <div style={{ marginTop: 6, padding: '6px 8px', backgroundColor: '#FFFFFF', borderRadius: 6, border: '1px solid #E5E7EB' }}>
                                  <span className="snow-micro" style={{ fontWeight: 600, color: '#374151' }}>Claimant Response:</span>
                                  <div className="snow-caption" style={{ color: '#1F2937' }}>{req.response_note}</div>
                                  {req.evidence_name && (
                                    <div className="snow-micro" style={{ color: '#2563EB', marginTop: 2 }}>
                                      📎 Attached Evidence: {req.evidence_name}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </Card>
                  </div>
                )}

                {/* Exceptions Tab */}
                {activeTab === 'exceptions' && (
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
            </div>

            {/* AI Copilot Side Drawer - Fixed Header & Input, Independent Chat Scroll */}
            {copilotOpen && (
              <aside className={`snow-workspace-copilot-panel snow-card ${mobileTab === 'dossier' ? 'mobile-hidden' : ''}`}>
                {/* Copilot Header - FIXED */}
                <div className="snow-workspace-copilot-header">
                  <div className="snow-flex snow-justify-between snow-items-center">
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
                </div>

                {/* Chat Thread - ONLY THIS SCROLLS IN COPILOT */}
                <div className="snow-workspace-copilot-chat snow-scrollbar">
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
                            {c.citations.map((cite, idx) => {
                              const label = typeof cite === 'string' ? cite : ((cite as any)?.citation_label || (cite as any)?.source_name || (cite as any)?.claim || (cite as any)?.source_id || JSON.stringify(cite));
                              return (
                                <div key={idx} className="snow-micro" style={{ color: '#007AFF' }}>
                                  • {label}
                                </div>
                              );
                            })}
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

                {/* Quick Action Chips & Input Bar - FIXED AT BOTTOM */}
                <div className="snow-workspace-copilot-footer">
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
        </>
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
