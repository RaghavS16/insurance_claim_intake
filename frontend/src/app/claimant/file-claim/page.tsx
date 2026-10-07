'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  Mic,
  MicOff,
  Send,
  Paperclip,
  CheckCircle2,
  AlertTriangle,
  Upload,
  Plus,
  Trash2,
  ShieldCheck,
  FileText,
  Volume2,
  VolumeX,
  Radio,
  RotateCcw,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { DatePicker } from '@/components/ui/DatePicker';
import { BadgePill, BadgeDot } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

interface Message {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  time: string;
  citations?: string[];
}

export default function FileClaimPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const [ticketId, setTicketId] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'm1',
      speaker: 'assistant',
      text: "Hello! I am your AI Claim Intake Assistant. I can help you record your loss details and file your claim in minutes. Could you describe what happened and when the incident took place?",
      time: 'Just now',
    },
  ]);

  const [inputTurn, setInputTurn] = useState('');
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<'idle' | 'listening' | 'speaking'>('idle');
  const [speechSynthesisEnabled, setSpeechSynthesisEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  // User's linked policies
  const [userPolicies, setUserPolicies] = useState<any[]>([]);
  const [selectedPolicyNumber, setSelectedPolicyNumber] = useState<string>('');

  // Extracted Claim Facts
  const [extractedFacts, setExtractedFacts] = useState({
    policyId: '',
    insuranceType: 'Motor',
    eventDate: '',
    eventLocation: '',
    eventDescription: '',
    estimatedAmount: 0,
    confidence: 0,
    coverageVerified: false,
    evidenceUploaded: false,
    evidenceName: '',
  });

  // Evidence Modal
  const [evidenceModalOpen, setEvidenceModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadingEvidence, setUploadingEvidence] = useState(false);

  // Edit Facts Modal
  const [editFactsModalOpen, setEditFactsModalOpen] = useState(false);
  const [editPolicy, setEditPolicy] = useState('');
  const [editType, setEditType] = useState('Motor');
  const [editDate, setEditDate] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editAmount, setEditAmount] = useState('');

  // Discard / Clear Chat Confirmation Modal
  const [discardModalOpen, setDiscardModalOpen] = useState(false);

  // Confirm Claim Modal
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [submittingClaim, setSubmittingClaim] = useState(false);

  // Fetch claimant's policies on load
  useEffect(() => {
    api.get<any[]>('/api/v1/policies/my-policies')
      .then((data) => {
        const list = Array.isArray(data) ? data : (data as any)?.items || [];
        setUserPolicies(list);
        if (list.length > 0 && !selectedPolicyNumber) {
          setSelectedPolicyNumber(list[0].policy_number);
        }
      })
      .catch(() => {});
  }, []);

  // Initialize or resume draft session
  useEffect(() => {
    api.get<any>('/api/v1/claims/active')
      .then((active) => {
        if (active && (active.active || active.status === 'draft') && active.ticket_id) {
          setTicketId(active.ticket_id);
          const stateData = active.extracted_data || {};
          const polId = active.policy_id || stateData.policy_id || '';
          if (polId) setSelectedPolicyNumber(polId);

          setExtractedFacts({
            policyId: polId,
            insuranceType: active.insurance_type || stateData.insurance_type || 'Motor',
            eventDate: active.event_date || stateData.event_date || '',
            eventLocation: active.event_location || stateData.event_location || '',
            eventDescription: active.event_description || stateData.event_description || '',
            estimatedAmount: active.estimated_claim_amount || stateData.estimated_claim_amount || 0,
            confidence: active.extraction_confidence || 0.95,
            coverageVerified: !!active.confirmed || !!stateData.coverage_verified,
            evidenceUploaded: Array.isArray(active.evidence) && active.evidence.length > 0,
            evidenceName: Array.isArray(active.evidence) && active.evidence.length > 0 ? active.evidence[0].filename : '',
          });

          if (Array.isArray(active.conversation) && active.conversation.length > 0) {
            setMessages(
              active.conversation.map((turn: any, idx: number) => ({
                id: `turn-${idx}`,
                speaker: turn.speaker === 'user' ? 'user' : 'assistant',
                text: turn.text,
                time: turn.created_at || 'Saved Turn',
              }))
            );
          }
        } else {
          startNewSession();
        }
      })
      .catch(() => {
        startNewSession();
      });
  }, []);

  const startNewSession = async (customPolicy?: string) => {
    const policyToUse = customPolicy || selectedPolicyNumber;
    try {
      const res = await api.post<any>('/api/v1/claims/new-session', {
        policy_number: policyToUse || undefined,
      });
      if (res?.ticket_id) {
        setTicketId(res.ticket_id);
        if (policyToUse) {
          setExtractedFacts((prev) => ({ ...prev, policyId: policyToUse }));
        }
        if (res.initial_message) {
          setMessages([
            {
              id: `welcome-${Date.now()}`,
              speaker: 'assistant',
              text: res.initial_message,
              time: 'Just now',
            },
          ]);
        }
      }
    } catch (e: any) {
      showToast(e.message || 'Failed to initialize intake session', 'error');
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Clean up speech recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Text-to-Speech Speak back from AI
  const speakText = (text: string) => {
    if (!speechSynthesisEnabled || typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.onstart = () => {
        setVoiceStatus('speaking');
      };
      utterance.onend = () => {
        setVoiceStatus('idle');
      };
      utterance.onerror = () => {
        setVoiceStatus('idle');
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      setVoiceStatus('idle');
    }
  };

  const handleSendText = async (textToSend?: string) => {
    const text = textToSend || inputTurn;
    if (!text.trim()) return;

    let activeTicket = ticketId;
    if (!activeTicket) {
      try {
        const session = await api.post<any>('/api/v1/claims/new-session', {
          policy_number: selectedPolicyNumber || undefined,
        });
        activeTicket = session.ticket_id;
        setTicketId(session.ticket_id);
      } catch (e: any) {
        showToast(e.message || 'Failed to start claim session.', 'error');
        return;
      }
    }

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      speaker: 'user',
      text,
      time: 'Just now',
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputTurn('');
    setLoading(true);

    try {
      const res = await api.post<any>(`/api/v1/claims/${activeTicket}/text-turn`, { text });

      const replyText =
        res.agent_message ||
        res.message ||
        res.reply ||
        res.text ||
        "I have registered your loss details. Please review the facts and upload any evidence documents.";

      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        speaker: 'assistant',
        text: replyText,
        time: 'Just now',
        citations: res.citations || res.sources || [],
      };
      setMessages((prev) => [...prev, assistantMsg]);
      speakText(replyText);

      const facts = res.extracted_data || res;
      setExtractedFacts((prev) => ({
        ...prev,
        policyId: facts.policy_id || res.policy_id || prev.policyId || selectedPolicyNumber,
        insuranceType: res.insurance_type || facts.insurance_type || prev.insuranceType,
        eventDate: res.event_date || facts.event_date || prev.eventDate,
        eventLocation: res.event_location || facts.event_location || prev.eventLocation,
        eventDescription: res.event_description || facts.event_description || prev.eventDescription,
        estimatedAmount: res.estimated_claim_amount || facts.estimated_claim_amount || prev.estimatedAmount,
        confidence: res.extraction_confidence || prev.confidence || 0.92,
        coverageVerified: !!res.confirmed || prev.coverageVerified,
        evidenceUploaded: (Array.isArray(res.evidence) && res.evidence.length > 0) || prev.evidenceUploaded,
      }));
    } catch (err: any) {
      showToast(err.message || 'Failed to process message turn.', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Browser Web Speech Recognition Voice Input
  const toggleVoiceMode = () => {
    if (isVoiceActive) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
      setIsVoiceActive(false);
      setVoiceStatus('idle');
      showToast('Voice intake listening stopped', 'info');
      return;
    }

    if (typeof window === 'undefined') return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      showToast('Web Speech API is not supported in this browser. Please use text input.', 'error');
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsVoiceActive(true);
        setVoiceStatus('listening');
        showToast('Listening... Speak your accident details now', 'info');
      };

      recognition.onresult = (event: any) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        setInputTurn(transcript);
      };

      recognition.onend = () => {
        setIsVoiceActive(false);
        setVoiceStatus('idle');
        setInputTurn((current) => {
          if (current.trim().length > 0) {
            handleSendText(current.trim());
          }
          return '';
        });
      };

      recognition.onerror = (event: any) => {
        setIsVoiceActive(false);
        setVoiceStatus('idle');
        if (event.error !== 'no-speech') {
          showToast(`Voice capture note: ${event.error}`, 'info');
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (err: any) {
      setIsVoiceActive(false);
      setVoiceStatus('idle');
      showToast('Could not access microphone. Please verify browser permissions.', 'error');
    }
  };

  // Chat History Management: Discard Draft & Clear Conversation
  const handleDiscardAndReset = async () => {
    try {
      if (ticketId) {
        try {
          await api.delete(`/api/v1/claims/${ticketId}`);
        } catch {}
      }
      setMessages([]);
      setExtractedFacts({
        policyId: selectedPolicyNumber || '',
        insuranceType: 'Motor',
        eventDate: '',
        eventLocation: '',
        eventDescription: '',
        estimatedAmount: 0,
        confidence: 0,
        coverageVerified: false,
        evidenceUploaded: false,
        evidenceName: '',
      });
      setDiscardModalOpen(false);
      await startNewSession(selectedPolicyNumber);
      showToast('Chat history cleared. Started a fresh claim draft.', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to reset claim session.', 'error');
    }
  };

  // Delete single message from view
  const handleDeleteMessage = (id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    showToast('Message removed from view', 'info');
  };

  // Upload claim evidence
  const handleUploadEvidence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      showToast('Please select a file to upload.', 'error');
      return;
    }
    setUploadingEvidence(true);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('document_type', 'damage_evidence');

      await api.post(`/api/v1/claims/${ticketId}/evidence`, formData);
      setExtractedFacts((prev) => ({
        ...prev,
        evidenceUploaded: true,
        evidenceName: selectedFile.name,
      }));
      showToast('Evidence document uploaded and verified!', 'success');
      setEvidenceModalOpen(false);
    } catch (err: any) {
      showToast(err.message || 'Evidence upload failed.', 'error');
    } finally {
      setUploadingEvidence(false);
    }
  };

  const handleVerifyPolicy = async () => {
    if (!ticketId) return;
    try {
      const res = await api.post<any>(`/api/v1/claims/${ticketId}/verify`);
      const isValid = Boolean(res.policy_verification?.valid);
      if (isValid) {
        setExtractedFacts((prev) => ({ ...prev, coverageVerified: true }));
        showToast(res.message || 'Policy coverage verified successfully!', 'success');
      } else {
        showToast(res.message || 'Policy verification could not confirm coverage.', 'info');
      }
    } catch (err: any) {
      showToast(err.message || 'Policy coverage verification failed.', 'error');
    }
  };

  const handleConfirmClaim = async () => {
    setSubmittingClaim(true);
    try {
      await api.post(`/api/v1/claims/${ticketId}/confirm`, { confirmed: true });
      showToast('Claim officially submitted for adjuster adjudication!', 'success');
      setConfirmModalOpen(false);
      router.push('/claimant/claims');
    } catch (err: any) {
      const msg =
        typeof err?.detail === 'string'
          ? err.detail
          : err.detail?.message || err.message || 'Submission failed. Please verify claim requirements.';
      showToast(msg, 'error');
    } finally {
      setSubmittingClaim(false);
    }
  };

  const handleOpenEditFacts = () => {
    setEditPolicy(extractedFacts.policyId || selectedPolicyNumber || '');
    setEditType(extractedFacts.insuranceType || 'Motor');
    setEditDate(extractedFacts.eventDate || '');
    setEditLocation(extractedFacts.eventLocation || '');
    setEditDescription(extractedFacts.eventDescription || '');
    setEditAmount(extractedFacts.estimatedAmount ? String(extractedFacts.estimatedAmount) : '');
    setEditFactsModalOpen(true);
  };

  const handleSaveFacts = async () => {
    const amountNum = Number(editAmount) || extractedFacts.estimatedAmount;
    try {
      if (ticketId) {
        await api.patch(`/api/v1/claims/${ticketId}`, {
          policy_id: editPolicy || undefined,
          insurance_type: editType || undefined,
          event_date: editDate || undefined,
          event_location: editLocation || undefined,
          event_description: editDescription || undefined,
          estimated_claim_amount: amountNum || undefined,
        });
      }
      setExtractedFacts((prev) => ({
        ...prev,
        policyId: editPolicy || prev.policyId,
        insuranceType: editType || prev.insuranceType,
        eventDate: editDate || prev.eventDate,
        eventLocation: editLocation || prev.eventLocation,
        eventDescription: editDescription || prev.eventDescription,
        estimatedAmount: amountNum,
      }));
      if (editPolicy) setSelectedPolicyNumber(editPolicy);
      setEditFactsModalOpen(false);
      showToast('Claim facts updated and synced with backend', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to update claim facts on server', 'error');
    }
  };

  const handlePolicySelectChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newPol = e.target.value;
    setSelectedPolicyNumber(newPol);
    setExtractedFacts((prev) => ({ ...prev, policyId: newPol }));
    if (ticketId && newPol) {
      try {
        await api.patch(`/api/v1/claims/${ticketId}`, { policy_id: newPol });
        showToast(`Policy set to ${newPol}`, 'info');
      } catch {}
    }
  };

  return (
    <AppShell
      breadcrumbs={['Claimant', 'Intake', ticketId ? `#${ticketId}` : 'New Claim']}
      activeTitle="Conversational Claim Intake"
      hideRightDrawer
    >
      <div
        className="snow-intake-container"
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 340px',
          gap: 24,
          minHeight: 'calc(100vh - 180px)',
        }}
      >
        {/* Main Chat Interface */}
        <div className="snow-flex-col" style={{ height: '100%', justifyContent: 'space-between', minWidth: 0 }}>
          {/* Chat Header Status & Management Bar */}
          <div
            className="snow-flex snow-justify-between snow-items-center"
            style={{
              padding: '10px 16px',
              backgroundColor: '#FFFFFF',
              borderRadius: 16,
              border: '1px solid #EBECEF',
              marginBottom: 12,
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div className="snow-flex snow-items-center snow-gap-3">
              <span
                className={`snow-dot ${
                  voiceStatus === 'speaking' ? 'complete' : voiceStatus === 'listening' ? 'progress' : 'default'
                }`}
                style={{
                  animation: voiceStatus !== 'idle' ? 'pulse 1.2s infinite' : 'none',
                }}
              />
              <span className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                {voiceStatus === 'speaking'
                  ? 'AI Speaking...'
                  : voiceStatus === 'listening'
                  ? 'Listening to Microphone...'
                  : 'AI Intake Assistant Ready'}
              </span>
              {ticketId && (
                <span className="snow-badge-pill slate" style={{ fontSize: 11 }}>
                  {ticketId}
                </span>
              )}
            </div>

            <div className="snow-flex snow-items-center snow-gap-2">
              {/* Linked Policy Selector */}
              {userPolicies.length > 0 && (
                <div className="snow-flex snow-items-center snow-gap-1">
                  <span className="snow-micro" style={{ color: '#71717A', fontWeight: 600 }}>Policy:</span>
                  <select
                    value={selectedPolicyNumber}
                    onChange={handlePolicySelectChange}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 8,
                      fontSize: 12,
                      border: '1px solid #EBECEF',
                      backgroundColor: '#F9FAFB',
                      color: '#1C1C1C',
                      fontWeight: 500,
                    }}
                  >
                    <option value="">Select Policy</option>
                    {userPolicies.map((p) => (
                      <option key={p.policy_number} value={p.policy_number}>
                        {p.policy_number} ({p.policy_type})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Toggle Speech Synthesis Speak Back */}
              <button
                type="button"
                onClick={() => {
                  setSpeechSynthesisEnabled(!speechSynthesisEnabled);
                  if (speechSynthesisEnabled && typeof window !== 'undefined' && 'speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                  }
                  showToast(
                    speechSynthesisEnabled ? 'AI Speak Back Muted' : 'AI Speak Back Enabled',
                    'info'
                  );
                }}
                className="snow-flex snow-items-center snow-gap-1 snow-caption"
                style={{
                  background: speechSynthesisEnabled ? '#E3F5FF' : '#F4F5F7',
                  color: speechSynthesisEnabled ? '#0284C7' : '#71717A',
                  border: 'none',
                  padding: '4px 10px',
                  borderRadius: 20,
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
                title={speechSynthesisEnabled ? 'Mute AI voice output' : 'Enable AI voice output'}
              >
                {speechSynthesisEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
                <span>{speechSynthesisEnabled ? 'Voice: On' : 'Voice: Muted'}</span>
              </button>

              {/* Clear / Reset Chat History */}
              <button
                type="button"
                onClick={() => setDiscardModalOpen(true)}
                className="snow-flex snow-items-center snow-gap-1 snow-caption"
                style={{
                  background: '#FEE2E2',
                  color: '#DC2626',
                  border: 'none',
                  padding: '4px 10px',
                  borderRadius: 20,
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
                title="Discard draft and reset conversation"
              >
                <Trash2 size={13} />
                <span>Reset Chat</span>
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div
            className="snow-card"
            style={{
              flex: 1,
              overflowY: 'auto',
              maxHeight: 'calc(100vh - 330px)',
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              marginBottom: 16,
            }}
          >
            {messages.map((m) => (
              <div
                key={m.id}
                className={
                  m.speaker === 'user' ? 'snow-chat-bubble-user' : 'snow-chat-bubble-assistant'
                }
                style={{ position: 'relative' }}
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                <div
                  className="snow-flex snow-justify-between snow-items-center"
                  style={{
                    marginTop: 6,
                    opacity: 0.8,
                    fontSize: 11,
                  }}
                >
                  <span className="snow-micro">{m.time}</span>
                  <div className="snow-flex snow-items-center snow-gap-1">
                    {m.speaker === 'assistant' && (
                      <button
                        type="button"
                        onClick={() => speakText(m.text)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: '#71717A',
                          padding: '2px 4px',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                        title="Speak message aloud"
                      >
                        <Volume2 size={13} />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDeleteMessage(m.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#A1A1AA',
                        padding: '2px 4px',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                      title="Remove message turn"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {loading && (
              <div className="snow-chat-bubble-assistant" style={{ fontStyle: 'italic', color: '#71717A' }}>
                AI Assistant is reasoning with policy terms...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Voice Mode Banner if active */}
          {isVoiceActive && (
            <div
              className="snow-card"
              style={{
                backgroundColor: '#E3F5FF',
                border: '1px solid #CBE8FA',
                padding: '10px 16px',
                marginBottom: 12,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div className="snow-flex snow-items-center snow-gap-3">
                <span className="snow-dot progress" style={{ animation: 'pulse 1s infinite' }} />
                <span className="snow-body" style={{ fontWeight: 600, color: '#0284C7', fontSize: 13 }}>
                  Listening to your voice... Speak your claim details clearly
                </span>
              </div>
              <Button size="sm" variant="danger" pill onClick={toggleVoiceMode}>
                Stop Listening
              </Button>
            </div>
          )}

          {/* Floating Chat Input Bar */}
          <div
            className="snow-card"
            style={{
              padding: '8px 12px',
              borderRadius: 24,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
            }}
          >
            {/* Microphone Button (Voice Message Send) */}
            <button
              type="button"
              onClick={toggleVoiceMode}
              style={{
                width: 38,
                height: 38,
                borderRadius: '50%',
                border: 'none',
                background: isVoiceActive ? '#EF4444' : '#1C1C1C',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                boxShadow: isVoiceActive ? '0 0 0 4px rgba(239,68,68,0.25)' : 'none',
              }}
              title={isVoiceActive ? 'Stop Voice Recording' : 'Speak Voice Message'}
            >
              {isVoiceActive ? <MicOff size={18} /> : <Mic size={18} />}
            </button>

            <button
              type="button"
              onClick={() => setEvidenceModalOpen(true)}
              style={{
                width: 36,
                height: 36,
                borderRadius: '50%',
                border: 'none',
                background: '#F4F5F7',
                color: '#71717A',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
              title="Attach Evidence Photo/Receipt"
            >
              <Paperclip size={18} />
            </button>

            <input
              type="text"
              className="snow-input"
              style={{
                border: 'none',
                boxShadow: 'none',
                fontSize: 14,
                padding: '0 8px',
                height: 38,
                flex: 1,
                minWidth: 0,
              }}
              placeholder={isVoiceActive ? 'Listening... spoken words appear here' : 'Type or click mic to speak your claim...'}
              value={inputTurn}
              onChange={(e) => setInputTurn(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendText();
              }}
            />

            <Button
              pill
              size="sm"
              variant="primary"
              onClick={() => handleSendText()}
              disabled={!inputTurn.trim()}
              icon={<Send size={14} />}
            >
              Send
            </Button>
          </div>
        </div>

        {/* Right Facts Extraction & Submission Panel */}
        <div className="snow-flex-col snow-gap-4" style={{ minWidth: 0 }}>
          <Card
            title="Extracted Claim Facts"
            action={
              <button
                type="button"
                onClick={handleOpenEditFacts}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#007AFF',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Edit
              </button>
            }
          >
            <div className="snow-flex-col snow-gap-3">
              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Linked Policy</span>
                <div className="snow-body" style={{ fontWeight: 600 }}>
                  {extractedFacts.policyId || selectedPolicyNumber || 'Not Selected'}
                </div>
              </div>

              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Line of Business</span>
                <div className="snow-body" style={{ fontWeight: 600 }}>{extractedFacts.insuranceType}</div>
              </div>

              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Date</span>
                <div className="snow-body">{extractedFacts.eventDate || 'Not specified yet'}</div>
              </div>

              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Incident Location</span>
                <div className="snow-body">{extractedFacts.eventLocation || 'Not specified yet'}</div>
              </div>

              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>Estimated Damage</span>
                <div className="snow-body" style={{ fontWeight: 600 }}>
                  {extractedFacts.estimatedAmount ? `$${extractedFacts.estimatedAmount.toLocaleString()}` : '$0'}
                </div>
              </div>

              <div>
                <span className="snow-caption" style={{ color: '#A1A1AA' }}>AI Extraction Confidence</span>
                <div className="snow-flex snow-items-center snow-gap-2">
                  <div style={{ flex: 1, height: 6, backgroundColor: '#EBECEF', borderRadius: 3 }}>
                    <div
                      style={{
                        width: `${Math.min(100, (extractedFacts.confidence || 0.9) * 100)}%`,
                        height: '100%',
                        backgroundColor: '#10B981',
                        borderRadius: 3,
                      }}
                    />
                  </div>
                  <span className="snow-micro" style={{ fontWeight: 600 }}>
                    {Math.round((extractedFacts.confidence || 0.9) * 100)}%
                  </span>
                </div>
              </div>
            </div>
          </Card>

          {/* Readiness & Evidence Card */}
          <Card title="Readiness & Evidence">
            <div className="snow-flex-col snow-gap-3" style={{ marginBottom: 16 }}>
              <div className="snow-flex snow-items-center snow-justify-between">
                <span className="snow-body" style={{ fontSize: 13 }}>Policy Limits Check</span>
                {extractedFacts.coverageVerified ? (
                  <BadgePill variant="mint">Verified</BadgePill>
                ) : (
                  <Button size="sm" variant="secondary" onClick={handleVerifyPolicy}>
                    Verify Policy
                  </Button>
                )}
              </div>

              <div className="snow-flex snow-items-center snow-justify-between">
                <span className="snow-body" style={{ fontSize: 13 }}>Damage Evidence</span>
                {extractedFacts.evidenceUploaded ? (
                  <BadgePill variant="mint">Uploaded</BadgePill>
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setEvidenceModalOpen(true)}>
                    Upload Photo
                  </Button>
                )}
              </div>
            </div>

            <Button
              variant="primary"
              pill
              style={{ width: '100%' }}
              onClick={() => setConfirmModalOpen(true)}
            >
              Submit Claim for Review
            </Button>
          </Card>
        </div>
      </div>

      {/* Evidence Upload Modal */}
      <Modal
        isOpen={evidenceModalOpen}
        onClose={() => setEvidenceModalOpen(false)}
        title="Upload Claim Evidence"
      >
        <form onSubmit={handleUploadEvidence}>
          <div
            style={{
              border: '2px dashed #D1D5DB',
              borderRadius: 16,
              padding: '32px 20px',
              textAlign: 'center',
              backgroundColor: '#FAFAFB',
              marginBottom: 16,
              cursor: 'pointer',
            }}
            onClick={() => document.getElementById('evidence-upload-file')?.click()}
          >
            <input
              id="evidence-upload-file"
              type="file"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setSelectedFile(e.target.files[0]);
                }
              }}
              accept="image/*,application/pdf"
            />
            <Upload size={32} color="#71717A" style={{ margin: '0 auto 8px' }} />
            <div className="snow-body" style={{ fontWeight: 600 }}>
              {selectedFile ? selectedFile.name : 'Click to select damage photo or receipt'}
            </div>
            <div className="snow-caption" style={{ color: '#A1A1AA', marginTop: 4 }}>
              Supports PNG, JPG, or PDF up to 10MB
            </div>
          </div>

          <div className="snow-flex snow-justify-between snow-gap-3">
            <Button variant="secondary" onClick={() => setEvidenceModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={uploadingEvidence || !selectedFile}>
              {uploadingEvidence ? 'Uploading...' : 'Save & Validate'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Facts Modal */}
      <Modal
        isOpen={editFactsModalOpen}
        onClose={() => setEditFactsModalOpen(false)}
        title="Correct Extracted Facts"
      >
        <div className="snow-flex-col snow-gap-3">
          <div>
            <label className="snow-caption" style={{ color: '#71717A', fontWeight: 600, display: 'block', marginBottom: 4 }}>
              Select Linked Policy
            </label>
            <select
              value={editPolicy}
              onChange={(e) => setEditPolicy(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 14,
                border: '1px solid #EBECEF',
                backgroundColor: '#FFFFFF',
              }}
            >
              <option value="">Choose Policy</option>
              {userPolicies.map((p) => (
                <option key={p.policy_number} value={p.policy_number}>
                  {p.policy_number} — {p.policy_type} (${p.coverage_amount?.toLocaleString()})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="snow-caption" style={{ color: '#71717A', fontWeight: 600, display: 'block', marginBottom: 4 }}>
              Line of Business
            </label>
            <select
              value={editType}
              onChange={(e) => setEditType(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                fontSize: 14,
                border: '1px solid #EBECEF',
                backgroundColor: '#FFFFFF',
              }}
            >
              <option value="Motor">Motor / Auto</option>
              <option value="Home">Home / Property</option>
              <option value="Health">Health</option>
              <option value="Travel">Travel</option>
              <option value="Commercial">Commercial</option>
            </select>
          </div>

          <DatePicker
            label="Incident Date"
            value={editDate}
            onChange={(val) => setEditDate(val)}
          />

          <Input
            label="Incident Location"
            value={editLocation}
            onChange={(e) => setEditLocation(e.target.value)}
          />

          <Input
            label="Incident Description"
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
          />

          <Input
            label="Estimated Loss Amount ($)"
            type="number"
            value={editAmount}
            onChange={(e) => setEditAmount(e.target.value)}
          />

          <div className="snow-flex snow-justify-between snow-gap-3" style={{ marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setEditFactsModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveFacts}>
              Save Corrections
            </Button>
          </div>
        </div>
      </Modal>

      {/* Discard & Reset Chat Confirmation Modal */}
      <Modal
        isOpen={discardModalOpen}
        onClose={() => setDiscardModalOpen(false)}
        title="Reset Intake Session & Chat"
      >
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              backgroundColor: '#FEE2E2',
              color: '#DC2626',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
            }}
          >
            <Trash2 size={24} />
          </div>
          <h3 className="snow-h2" style={{ marginBottom: 8, fontSize: 18 }}>
            Discard Draft and Clear History?
          </h3>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            This will discard claim draft #{ticketId} and reset the conversation turns so you can begin fresh.
          </p>
          <div className="snow-flex snow-justify-between snow-gap-3">
            <Button variant="secondary" onClick={() => setDiscardModalOpen(false)}>
              Keep Current Chat
            </Button>
            <Button variant="danger" onClick={handleDiscardAndReset}>
              Discard & Clear
            </Button>
          </div>
        </div>
      </Modal>

      {/* Confirm Claim Modal */}
      <Modal
        isOpen={confirmModalOpen}
        onClose={() => setConfirmModalOpen(false)}
        title="Confirm Claim Submission"
      >
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              backgroundColor: '#E6F9F0',
              color: '#059669',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
            }}
          >
            <ShieldCheck size={28} />
          </div>
          <h3 className="snow-h2" style={{ marginBottom: 8 }}>
            Ready to Submit Claim?
          </h3>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 20 }}>
            Your claim (#{ticketId}) will be submitted to adjuster triage with policy{' '}
            <strong>{extractedFacts.policyId || selectedPolicyNumber || 'Attached'}</strong>.
          </p>
          <div className="snow-flex snow-justify-between snow-gap-3">
            <Button variant="secondary" onClick={() => setConfirmModalOpen(false)}>
              Back
            </Button>
            <Button variant="primary" onClick={handleConfirmClaim} disabled={submittingClaim}>
              {submittingClaim ? 'Submitting...' : 'Confirm Submission'}
            </Button>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
