'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  MessageSquare,
  Plus,
  ShieldCheck,
  Clock,
  CheckCircle2,
  ChevronRight,
  AlertCircle,
  Pencil,
  Trash2,
  ExternalLink,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { MetricCard } from '@/components/ui/MetricCard';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { BadgeDot, BadgePill } from '@/components/ui/Badge';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { useToast } from '@/components/ui/Toast';
import { Claim } from '@/lib/types';
import { api } from '@/lib/api';

export default function ClaimantDashboardPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [policiesCount, setPoliciesCount] = useState(0);
  const [activeDraft, setActiveDraft] = useState<Claim | null>(null);
  const [loading, setLoading] = useState(true);

  // Rename Chat Modal State
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [chatToRename, setChatToRename] = useState<any | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [renaming, setRenaming] = useState(false);

  // Delete Chat Modal State
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [chatToDelete, setChatToDelete] = useState<any | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchDashboardData = () => {
    setLoading(true);

    const pClaims = api
      .get<any>('/api/v1/claims')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setClaims(list);
      })
      .catch(() => {
        setClaims([]);
      });

    const pPolicies = api
      .get<any>('/api/v1/policies/my-policies')
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.items || [];
        setPoliciesCount(list.length);
      })
      .catch(() => {
        setPoliciesCount(0);
      });

    const pActive = api
      .get<any>('/api/v1/claims/active')
      .then((data) => {
        if (data && (data.active || data.status === 'draft')) {
          setActiveDraft(data);
        } else {
          setActiveDraft(null);
        }
      })
      .catch(() => {
        setActiveDraft(null);
      });

    Promise.allSettled([pClaims, pPolicies, pActive]).finally(() => {
      setLoading(false);
    });
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

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

  const formatTimestamp = (dateStr?: string) => {
    if (!dateStr) return 'Recently active';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const handleOpenRename = (chat: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setChatToRename(chat);
    setNewTitle(chat.title || chat.ticket_id);
    setRenameModalOpen(true);
  };

  const handleSaveRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatToRename || !newTitle.trim()) return;

    setRenaming(true);
    try {
      await api.patch(`/api/v1/claims/${chatToRename.ticket_id}`, {
        title: newTitle.trim(),
      });
      setClaims((prev) =>
        prev.map((c) =>
          c.ticket_id === chatToRename.ticket_id
            ? { ...c, title: newTitle.trim() }
            : c
        )
      );
      showToast('Chat session renamed successfully.', 'success');
      setRenameModalOpen(false);
    } catch (err: any) {
      showToast(err.message || 'Failed to rename chat session.', 'error');
    } finally {
      setRenaming(false);
    }
  };

  const handleOpenDelete = (chat: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setChatToDelete(chat);
    setDeleteModalOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!chatToDelete) return;

    setDeleting(true);
    try {
      await api.delete(`/api/v1/claims/${chatToDelete.ticket_id}`);
      setClaims((prev) => prev.filter((c) => c.ticket_id !== chatToDelete.ticket_id));
      if (activeDraft?.ticket_id === chatToDelete.ticket_id) {
        setActiveDraft(null);
      }
      showToast('Chat session deleted.', 'info');
      setDeleteModalOpen(false);
    } catch (err: any) {
      showToast(err.message || 'Failed to delete chat session.', 'error');
    } finally {
      setDeleting(false);
    }
  };

  const activeClaimsCount = claims.filter(
    (c) => c.status !== 'approved' && c.status !== 'rejected' && c.status !== 'discarded'
  ).length;
  const approvedClaims = claims.filter((c) => c.status === 'approved');
  const totalSettlements = approvedClaims.reduce(
    (sum, c) => sum + (c.estimated_claim_amount || 0),
    0
  );
  const pendingActionsCount = claims.filter((c) => c.status === 'pending_evidence').length;

  return (
    <AppShell breadcrumbs={['Claimant', 'Overview']} activeTitle="Claims Overview">
      {/* Metric Cards Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <MetricCard
          title="Active Claims"
          value={loading ? '—' : activeClaimsCount}
          trend={activeClaimsCount > 0 ? `${activeClaimsCount} in progress` : 'No active claims'}
          trendDirection="up"
          tint="sky"
          icon={<Clock size={20} />}
        />
        <MetricCard
          title="Linked Policies"
          value={loading ? '—' : `${policiesCount} Active`}
          trend={policiesCount > 0 ? `${policiesCount} verified` : 'None linked'}
          trendDirection="up"
          tint="indigo"
          icon={<ShieldCheck size={20} />}
        />
        <MetricCard
          title="Approved Payouts"
          value={loading ? '—' : `$${totalSettlements.toLocaleString()}`}
          trend={`${approvedClaims.length} approved`}
          trendDirection="up"
          tint="mint"
          icon={<CheckCircle2 size={20} />}
        />
        <MetricCard
          title="Pending Evidence"
          value={loading ? '—' : `${pendingActionsCount} Items`}
          trend={pendingActionsCount > 0 ? 'Action required' : 'All clear'}
          trendDirection={pendingActionsCount > 0 ? 'down' : 'up'}
          tint="amber"
          icon={<AlertCircle size={20} />}
        />
      </div>

      {/* Resume Draft Banner if exists */}
      {activeDraft && (
        <div
          className="snow-card"
          style={{
            backgroundColor: '#F0EDFF',
            border: '1px solid #DFD8FC',
            marginBottom: 24,
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div className="snow-body" style={{ fontWeight: 600, color: '#7C3AED' }}>
              In-Progress Claim Intake Session ({activeDraft.ticket_id})
            </div>
            <div className="snow-caption" style={{ color: '#52525B', marginTop: 2 }}>
              {activeDraft.event_description || 'You have an unsubmitted claim session in progress.'}
            </div>
          </div>
          <div className="snow-flex snow-gap-2">
            <Link href={`/claimant/file-claim?ticket_id=${activeDraft.ticket_id}`}>
              <Button size="sm" variant="primary">
                Resume Session
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Chat History Panel (Replaced Recent Claim Filings Table) */}
      <Card
        title="Chat History"
        action={
          <Link href="/claimant/file-claim?fresh=true">
            <Button size="sm" variant="primary" pill icon={<Plus size={14} />}>
              Start New Chat
            </Button>
          </Link>
        }
      >
        <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
          Review, rename, or resume your conversational voice and text intake sessions.
        </p>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '36px', color: '#71717A' }}>
            <div className="snow-caption">Loading conversation history from database...</div>
          </div>
        ) : claims.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              padding: '48px 16px',
              backgroundColor: '#FAFAFA',
              borderRadius: 12,
              border: '1px dashed #E4E4E7',
            }}
          >
            <MessageSquare size={36} color="#A1A1AA" style={{ margin: '0 auto 10px' }} />
            <div className="snow-body" style={{ fontWeight: 600, fontSize: 14 }}>
              No chat history yet
            </div>
            <div className="snow-caption" style={{ color: '#71717A', marginTop: 4 }}>
              Click "Start New Chat" above to speak or type your claim details with our AI assistant.
            </div>
          </div>
        ) : (
          <div className="snow-flex-col snow-gap-3">
            {claims.map((claim: any) => {
              const displayTitle =
                claim.title ||
                (claim.last_message
                  ? claim.last_message.slice(0, 45) + (claim.last_message.length > 45 ? '...' : '')
                  : `Claim Intake Session #${claim.ticket_id}`);
              const preview =
                claim.last_message ||
                claim.event_description ||
                'Session initiated. No messages recorded yet.';

              return (
                <div
                  key={claim.id || claim.ticket_id}
                  onClick={() => router.push(`/claimant/file-claim?ticket_id=${claim.ticket_id}`)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 18px',
                    borderRadius: 12,
                    border: '1px solid #EBECEF',
                    backgroundColor: '#FFFFFF',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#F9FAFB';
                    e.currentTarget.style.borderColor = '#D4D4D8';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#FFFFFF';
                    e.currentTarget.style.borderColor = '#EBECEF';
                  }}
                >
                  {/* Left Icon & Text */}
                  <div className="snow-flex snow-items-center snow-gap-3" style={{ minWidth: 0, flex: 1 }}>
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 10,
                        backgroundColor: '#F0EDFF',
                        color: '#7C3AED',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <MessageSquare size={18} />
                    </div>

                    <div style={{ minWidth: 0, flex: 1, paddingRight: 16 }}>
                      <div className="snow-flex snow-items-center snow-gap-2">
                        <span
                          className="snow-body"
                          style={{
                            fontWeight: 600,
                            fontSize: 14,
                            color: '#1C1C1C',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {displayTitle}
                        </span>
                        <span className="snow-badge-pill slate" style={{ fontSize: 11, flexShrink: 0 }}>
                          #{claim.ticket_id}
                        </span>
                      </div>

                      <div
                        className="snow-caption"
                        style={{
                          color: '#71717A',
                          marginTop: 3,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: 12,
                        }}
                      >
                        {claim.last_message_speaker === 'user' ? 'You: ' : 'AI: '}
                        {preview}
                      </div>

                      <div
                        className="snow-flex snow-items-center snow-gap-3"
                        style={{ marginTop: 4, fontSize: 11, color: '#A1A1AA' }}
                      >
                        <span>{formatTimestamp(claim.last_message_time || claim.updated_at || claim.created_at)}</span>
                        <span>•</span>
                        <span>{getStatusBadge(claim.status)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right Actions */}
                  <div className="snow-flex snow-items-center snow-gap-2" style={{ flexShrink: 0 }}>
                    <button
                      type="button"
                      title="Rename chat"
                      onClick={(e) => handleOpenRename(claim, e)}
                      style={{
                        background: 'none',
                        border: 'none',
                        padding: '6px 8px',
                        borderRadius: 6,
                        cursor: 'pointer',
                        color: '#71717A',
                        display: 'flex',
                        alignItems: 'center',
                        transition: 'background-color 0.1s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F4F5F7')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <Pencil size={14} />
                    </button>

                    <button
                      type="button"
                      title="Delete chat session"
                      onClick={(e) => handleOpenDelete(claim, e)}
                      style={{
                        background: 'none',
                        border: 'none',
                        padding: '6px 8px',
                        borderRadius: 6,
                        cursor: 'pointer',
                        color: '#EF4444',
                        display: 'flex',
                        alignItems: 'center',
                        transition: 'background-color 0.1s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#FEE2E2')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <Trash2 size={14} />
                    </button>

                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/claimant/file-claim?ticket_id=${claim.ticket_id}`);
                      }}
                      icon={<ExternalLink size={13} />}
                    >
                      Open
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Rename Chat Modal */}
      <Modal
        isOpen={renameModalOpen}
        onClose={() => setRenameModalOpen(false)}
        title="Rename Chat Session"
      >
        <form onSubmit={handleSaveRename}>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
            Give this conversation a descriptive title for easy reference.
          </p>

          <Input
            label="Chat Title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="e.g. Minor parking lot bumper dent on Oct 1st"
            required
            autoFocus
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 24 }}>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setRenameModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={renaming || !newTitle.trim()}
            >
              {renaming ? 'Saving...' : 'Save Title'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Chat Confirmation Modal */}
      <Modal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Delete Chat Session?"
      >
        <div style={{ textAlign: 'center', padding: '8px 0 16px' }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              backgroundColor: '#FEE2E2',
              color: '#DC2626',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 12px',
            }}
          >
            <Trash2 size={24} />
          </div>
          <h4 className="snow-h2" style={{ fontSize: 16, marginBottom: 6 }}>
            Delete Session #{chatToDelete?.ticket_id}?
          </h4>
          <p className="snow-caption" style={{ color: '#71717A' }}>
            Are you sure you want to remove this chat session from your history? This action cannot be undone.
          </p>
        </div>

        <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 16 }}>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setDeleteModalOpen(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={handleConfirmDelete}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Delete Session'}
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}
