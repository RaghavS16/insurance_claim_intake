'use client';

import React, { useState, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Mic,
  MicOff,
  Send,
  Paperclip,
  CheckCircle2,
  AlertTriangle,
  Volume2,
  VolumeX,
  RotateCcw,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

interface Message {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  time: string;
  citations?: string[];
}

function FileClaimContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryTicketId = searchParams.get('ticket_id');
  const isFreshRequest = searchParams.get('fresh') === 'true';

  const { showToast } = useToast();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const liveTranscriptRef = useRef<string>('');
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const [ticketId, setTicketId] = useState<string>(queryTicketId || '');
  const [claimData, setClaimData] = useState<any>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      speaker: 'assistant',
      text: "Hello! I am your IntelliClaim AI Assistant. How can I assist you with your claim today? You can type your request or click the microphone to speak.",
      time: 'Just now',
    },
  ]);

  const [inputTurn, setInputTurn] = useState('');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [speechSynthesisEnabled, setSpeechSynthesisEnabled] = useState(true);

  // User's linked policies
  const [userPolicies, setUserPolicies] = useState<any[]>([]);
  const [selectedPolicyNumber, setSelectedPolicyNumber] = useState<string>('');

  // Evidence Modal
  const [evidenceModalOpen, setEvidenceModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadingEvidence, setUploadingEvidence] = useState(false);

  // Discard / Reset Modal
  const [discardModalOpen, setDiscardModalOpen] = useState(false);

  // Confirm / Submit Claim Modal
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [submittingClaim, setSubmittingClaim] = useState(false);

  // Keep liveTranscriptRef in sync
  useEffect(() => {
    liveTranscriptRef.current = liveTranscript;
  }, [liveTranscript]);

  // Fetch claimant's policies on load
  useEffect(() => {
    api
      .get<any[]>('/api/v1/policies/my-policies')
      .then((data) => {
        const list = Array.isArray(data) ? data : (data as any)?.items || [];
        setUserPolicies(list);
        if (list.length > 0 && !selectedPolicyNumber) {
          setSelectedPolicyNumber(list[0].policy_number);
        }
      })
      .catch(() => {});
  }, []);

  // Handle Session Initialization (Fix 6: fresh chat vs past chat)
  useEffect(() => {
    if (isFreshRequest || !queryTicketId) {
      // FIX 6: Always open fresh blank chat. Do NOT call backend new-session until first message sent.
      setTicketId('');
      setMessages([
        {
          id: `welcome-${Date.now()}`,
          speaker: 'assistant',
          text: "Hello! I am your IntelliClaim AI Assistant. Please describe what happened and when the incident took place, or click the microphone to speak your claim details.",
          time: 'Just now',
        },
      ]);
      return;
    }

    // If a specific past chat was requested from Chat History
    if (queryTicketId) {
      api
        .get<any>(`/api/v1/claims/${queryTicketId}`)
        .then((claim) => {
          if (claim && claim.ticket_id) {
            setTicketId(claim.ticket_id);
            setClaimData(claim);
            if (claim.policy_id) setSelectedPolicyNumber(claim.policy_id);

            if (Array.isArray(claim.conversation) && claim.conversation.length > 0) {
              setMessages(
                claim.conversation.map((turn: any, idx: number) => ({
                  id: `turn-${idx}`,
                  speaker: turn.speaker === 'user' ? 'user' : 'assistant',
                  text: turn.text,
                  time: turn.created_at || 'Saved Turn',
                }))
              );
            }
          }
        })
        .catch(() => {
          showToast('Could not load requested conversation.', 'error');
        });
    }
  }, [queryTicketId, isFreshRequest]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveTranscript, isThinking]);

  // Clean up speech recognition & silence timer on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore abort error on cleanup
        }
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
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
      window.speechSynthesis.speak(utterance);
    } catch {
      // Speech synthesis may be unsupported or blocked
    }
  };

  // Helper: auto-send after 2 minutes of silence while mic active
  const startSilenceTimer = () => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);

    silenceTimerRef.current = setTimeout(() => {
      const currentText = liveTranscriptRef.current;
      if (currentText.trim().length > 0) {
        showToast('Auto-sending transcribed speech after 2 minutes of silence.', 'info');
        stopVoiceRecording(true);
      }
    }, 120_000); // 2 minutes of silence
  };

  const stopVoiceRecording = (sendImmediately = true) => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Ignore stop error on cleanup
      }
      recognitionRef.current = null;
    }
    setIsVoiceActive(false);

    const textFromSpeechApi = liveTranscriptRef.current.trim();
    setLiveTranscript('');
    liveTranscriptRef.current = '';

    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = async () => {
        // Cleanup microphone hardware stream
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((track) => track.stop());
          mediaStreamRef.current = null;
        }

        let finalText = textFromSpeechApi;

        // If Web Speech API had network error or returned empty text, transcribe the recorded audio via local Whisper
        if (!finalText && audioChunksRef.current.length > 0) {
          const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          if (audioBlob.size > 800) {
            try {
              const formData = new FormData();
              formData.append('file', audioBlob, 'recording.webm');
              const res = await api.post<{ text: string }>('/api/v1/voice/transcribe', formData);
              if (res.text && res.text.trim()) {
                finalText = res.text.trim();
              }
            } catch (err: any) {
              console.error('Local transcription error:', err);
            }
          }
        }

        audioChunksRef.current = [];
        mediaRecorderRef.current = null;

        if (sendImmediately && finalText) {
          handleSendText(finalText);
        } else if (finalText) {
          setInputTurn(finalText);
        }
      };

      try {
        recorder.stop();
      } catch {
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((track) => track.stop());
          mediaStreamRef.current = null;
        }
        if (sendImmediately && textFromSpeechApi) {
          handleSendText(textFromSpeechApi);
        }
      }
    } else {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      }
      if (sendImmediately && textFromSpeechApi) {
        handleSendText(textFromSpeechApi);
      }
    }
  };

  // Browser Voice Input with Simultaneous Speak & Transcribe and Whisper Streaming
  const toggleVoiceMode = async () => {
    if (isVoiceActive) {
      // Click mic again to cut mic -> immediate send turn
      stopVoiceRecording(true);
      return;
    }

    if (typeof window === 'undefined') return;

    // 1. Request microphone access and start MediaRecorder for continuous chunk capture
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaStreamRef.current = stream;
        audioChunksRef.current = [];

        const mimeType = MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : '';
        const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            audioChunksRef.current.push(e.data);
          }
        };
        recorder.start(250);
        mediaRecorderRef.current = recorder;
      }
    } catch (err: any) {
      showToast('Could not access microphone. Please grant browser microphone permissions.', 'error');
      return;
    }

    setIsVoiceActive(true);
    setLiveTranscript('');
    liveTranscriptRef.current = '';
    startSilenceTimer();

    // 2. Start Web Speech Recognition with immediate interim results
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onresult = (event: any) => {
          let interimText = '';
          for (let i = 0; i < event.results.length; ++i) {
            interimText += event.results[i][0].transcript;
          }
          if (interimText.trim()) {
            setLiveTranscript(interimText);
            liveTranscriptRef.current = interimText;
            setInputTurn(interimText);
            startSilenceTimer(); // Reset 2-min silence timer on vocal activity
          }
        };

        recognition.onerror = (event: any) => {
          console.debug('SpeechRecognition note:', event.error);
        };

        recognition.onend = () => {
          // If mic is still active and recognition stopped, try restarting if supported
          if (isVoiceActive && recognitionRef.current) {
            try {
              recognitionRef.current.start();
            } catch {
              // Ignore restart error if already listening
            }
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
      } catch (err: any) {
        console.debug('SpeechRecognition start failed, relying on Whisper:', err);
      }
    }
  };

  // Send turn (text or voice) to backend
  const handleSendText = async (textToSend?: string) => {
    const text = (textToSend || inputTurn).trim();
    if (!text) return;

    // FIX 6: If this is the first message in a fresh session, create the claim session now
    let activeTicket = ticketId;
    if (!activeTicket) {
      try {
        const session = await api.post<any>('/api/v1/claims/new-session', {
          policy_number: selectedPolicyNumber || undefined,
        });
        activeTicket = session.ticket_id;
        setTicketId(session.ticket_id);
        setClaimData(session);
        window.history.replaceState(null, '', `/claimant/file-claim?ticket_id=${session.ticket_id}`);
      } catch (e: any) {
        showToast(e.message || 'Failed to start intake session.', 'error');
        return;
      }
    }

    // Add user message to UI
    const userMsg: Message = {
      id: `u-${Date.now()}`,
      speaker: 'user',
      text,
      time: 'Just now',
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputTurn('');
    setIsThinking(true); // FIX 3: Start AI thinking animation bubble

    try {
      const res = await api.post<any>(`/api/v1/claims/${activeTicket}/text-turn`, { text });
      setClaimData(res);

      const replyText =
        res.agent_message ||
        res.message ||
        res.reply ||
        res.text ||
        "I have registered your loss details. You can continue speaking or attach supporting evidence.";

      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        speaker: 'assistant',
        text: replyText,
        time: 'Just now',
        citations: res.citations || res.sources || [],
      };

      setMessages((prev) => [...prev, assistantMsg]);
      speakText(replyText);
    } catch (err: any) {
      showToast(err.message || 'Failed to process message turn.', 'error');
    } finally {
      setIsThinking(false); // FIX 3: Replace thinking indicator with real reply
    }
  };

  // Reset Chat Conversation
  const handleResetChat = async () => {
    try {
      if (ticketId) {
        try {
          await api.delete(`/api/v1/claims/${ticketId}`);
        } catch {
          // Ignore deletion error when resetting session
        }
      }
      setTicketId('');
      setClaimData(null);
      setMessages([
        {
          id: `welcome-${Date.now()}`,
          speaker: 'assistant',
          text: "Hello! I am your IntelliClaim AI Assistant. How can I assist you with your claim today? You can type your request or click the microphone to speak.",
          time: 'Just now',
        },
      ]);
      setDiscardModalOpen(false);
      window.history.replaceState(null, '', '/claimant/file-claim?fresh=true');
      showToast('Conversation reset. Ready for a fresh intake.', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to reset claim session.', 'error');
    }
  };

  // Upload Evidence File
  const handleUploadEvidence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      showToast('Please select a file to upload.', 'error');
      return;
    }
    if (!ticketId) {
      showToast('Please start the intake conversation first.', 'error');
      return;
    }

    setUploadingEvidence(true);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('document_type', 'damage_evidence');

      await api.post(`/api/v1/claims/${ticketId}/evidence`, formData);
      showToast('Evidence document uploaded successfully!', 'success');
      setEvidenceModalOpen(false);
      setSelectedFile(null);
    } catch (err: any) {
      showToast(err.message || 'Evidence upload failed.', 'error');
    } finally {
      setUploadingEvidence(false);
    }
  };

  // Submit Claim for Adjudication Review
  const handleConfirmClaim = async () => {
    if (!ticketId) {
      showToast('No claim session active.', 'error');
      return;
    }

    setSubmittingClaim(true);
    try {
      await api.post(`/api/v1/claims/${ticketId}/confirm`, { confirmed: true });
      showToast('Claim officially submitted for adjudication review!', 'success');
      setConfirmModalOpen(false);
      router.push('/claimant/claims');
    } catch (err: any) {
      const msg =
        typeof err?.detail === 'string'
          ? err.detail
          : err.detail?.message || err.message || 'Submission failed. Please verify claim details.';
      showToast(msg, 'error');
    } finally {
      setSubmittingClaim(false);
    }
  };

  return (
    <AppShell
      breadcrumbs={['Claimant', 'Intake', ticketId ? `#${ticketId}` : 'New Claim']}
      activeTitle="Conversational Claim Intake"
      hideRightDrawer
    >
      {/* Top Bar Policy Selector */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
          padding: '10px 16px',
          backgroundColor: '#FFFFFF',
          borderRadius: 12,
          border: '1px solid #E5E7EB',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
          <ShieldCheck size={18} color="#007AFF" />
          <span className="snow-caption" style={{ fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' }}>
            Filing Against Policy:
          </span>
          <select
            className="snow-select"
            style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #D1D5DB', fontSize: 13, minWidth: 260 }}
            value={selectedPolicyNumber}
            onChange={(e) => setSelectedPolicyNumber(e.target.value)}
          >
            <option value="">-- No Specific Policy (General Inquiry / Auto-Resolve) --</option>
            {userPolicies.map((p) => (
              <option key={p.policy_number} value={p.policy_number}>
                {p.policy_number} — {p.policy_type?.toUpperCase()} (Limit: ${Number(p.coverage_amount || 0).toLocaleString()})
              </option>
            ))}
          </select>
        </div>
        {ticketId && (
          <div className="snow-caption" style={{ color: '#6B7280' }}>
            Claim Ticket: <strong style={{ color: '#111827' }}>#{ticketId}</strong>
          </div>
        )}
      </div>

      {/* 2-Column Responsive Layout: Chat + Live Claim Dossier */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.8fr) minmax(320px, 1.2fr)',
          gap: 16,
          height: 'calc(100vh - 220px)',
          minHeight: 520,
        }}
      >
        {/* Left Column: Chat Messages & Input */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minWidth: 0,
          }}
        >
          {/* Messages Scroll Area */}
          <div
            className="snow-card"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              marginBottom: 14,
              borderRadius: 16,
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
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{m.text}</div>
                {/* Safe Citation Rendering (handling strings & object citations) */}
                {m.speaker === 'assistant' && m.citations && m.citations.length > 0 && (
                  <div
                    style={{
                      marginTop: 8,
                      paddingTop: 6,
                      borderTop: '1px solid rgba(0,0,0,0.06)',
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 6,
                    }}
                  >
                    {m.citations.map((cite: any, idx: number) => {
                      const label =
                        typeof cite === 'string'
                          ? cite
                          : (cite.citation_label || cite.source_name || cite.claim || cite.source_id || JSON.stringify(cite));
                      return (
                        <span
                          key={idx}
                          style={{
                            fontSize: 11,
                            backgroundColor: '#EFF6FF',
                            color: '#1D4ED8',
                            border: '1px solid #DBEAFE',
                            padding: '2px 8px',
                            borderRadius: 6,
                            fontWeight: 500,
                          }}
                        >
                          📖 {label}
                        </span>
                      );
                    })}
                  </div>
                )}
                <div
                  className="snow-flex snow-justify-between snow-items-center"
                  style={{
                    marginTop: 6,
                    opacity: 0.75,
                    fontSize: 11,
                  }}
                >
                  <span className="snow-micro">{m.time}</span>
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
                </div>
              </div>
            ))}

          {/* Real-Time Live Transcribing Speech Bubble (on user's right side) */}
          {isVoiceActive && (
            <div
              className="snow-chat-bubble-user"
              style={{
                opacity: 0.95,
                border: '1.5px dashed #007AFF',
                backgroundColor: '#F0F7FF',
                color: '#1C1C1C',
                position: 'relative',
              }}
            >
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                {liveTranscript || 'Listening to microphone... Speak your claim details'}
              </div>
              <div
                className="snow-flex snow-items-center snow-gap-2"
                style={{ marginTop: 6, fontSize: 11, color: '#007AFF', fontWeight: 500 }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    backgroundColor: '#007AFF',
                    animation: 'snowPulseRing 1.2s infinite',
                  }}
                />
                <span>{liveTranscript ? 'Transcribing live in real time...' : 'Microphone open — speak now...'}</span>
              </div>
            </div>
          )}

          {/* FIX 3: AI Typing / Thinking Animation Bubble (on AI's left side) */}
          {isThinking && (
            <div
              className="snow-chat-bubble-assistant"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '12px 18px',
                width: 'fit-content',
                backgroundColor: '#F4F5F7',
                borderRadius: 16,
              }}
            >
              <span style={{ fontSize: 13, color: '#71717A', fontWeight: 500 }}>
                IntelliClaim AI is thinking
              </span>
              <div className="snow-flex snow-items-center snow-gap-1">
                <span className="snow-typing-dot" />
                <span className="snow-typing-dot" style={{ animationDelay: '0.2s' }} />
                <span className="snow-typing-dot" style={{ animationDelay: '0.4s' }} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div
          className="snow-card"
          style={{
            padding: '8px 12px',
            borderRadius: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            boxShadow: '0 4px 18px rgba(0,0,0,0.06)',
            backgroundColor: '#FFFFFF',
          }}
        >
          {/* Reset Chat Button */}
          <button
            type="button"
            onClick={() => setDiscardModalOpen(true)}
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
              flexShrink: 0,
            }}
            title="Reset conversation"
          >
            <RotateCcw size={15} />
          </button>

          {/* Attach Evidence */}
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
              flexShrink: 0,
            }}
            title="Attach Evidence Photo/Receipt"
          >
            <Paperclip size={17} />
          </button>

          {/* Text Input */}
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
            placeholder={
              isVoiceActive
                ? 'Listening & transcribing simultaneously... Speak or click mic to send'
                : 'Type your message or click the mic to speak...'
            }
            value={inputTurn}
            onChange={(e) => setInputTurn(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSendText();
            }}
          />

          {/* Microphone Button with Real-Time Listening State */}
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
              flexShrink: 0,
              animation: isVoiceActive ? 'snowPulseRing 1.4s infinite' : 'none',
            }}
            title={isVoiceActive ? 'Click to cut microphone & send message immediately' : 'Click to speak & transcribe live'}
          >
            {isVoiceActive ? <MicOff size={18} /> : <Mic size={18} />}
          </button>

          {/* Send Button */}
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

          {/* Submit Claim Button */}
          {ticketId && (
            <Button
              size="sm"
              variant="secondary"
              pill
              onClick={() => setConfirmModalOpen(true)}
            >
              Submit Claim
            </Button>
          )}
        </div>
      </div>

      {/* Right Column: Live Claim Dossier Panel */}
      <div
        className="snow-card"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          padding: 18,
          borderRadius: 16,
          overflowY: 'auto',
          backgroundColor: '#FFFFFF',
          minWidth: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #F3F4F6', paddingBottom: 10 }}>
          <div className="snow-body" style={{ fontWeight: 700, fontSize: 14, color: '#111827' }}>
            Live Claim Dossier
          </div>
          {claimData?.status && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, fontWeight: 600, backgroundColor: '#E0F2FE', color: '#0369A1' }}>
              {claimData.status.toUpperCase()}
            </span>
          )}
        </div>

        {/* Canonical Summary */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <span className="snow-caption" style={{ color: '#9CA3AF' }}>Policy</span>
            <div className="snow-body" style={{ fontWeight: 600, fontSize: 12 }}>
              {claimData?.policy_number || claimData?.extracted_data?.policy_id || selectedPolicyNumber || 'Pending'}
            </div>
          </div>
          <div>
            <span className="snow-caption" style={{ color: '#9CA3AF' }}>Coverage Type</span>
            <div className="snow-body" style={{ fontWeight: 600, fontSize: 12 }}>
              {claimData?.insurance_type || claimData?.extracted_data?.insurance_type || 'Resolving...'}
            </div>
          </div>
          <div>
            <span className="snow-caption" style={{ color: '#9CA3AF' }}>Incident Date</span>
            <div className="snow-body" style={{ fontSize: 12 }}>
              {claimData?.event_date || claimData?.extracted_data?.event_date || 'Awaiting'}
            </div>
          </div>
          <div>
            <span className="snow-caption" style={{ color: '#9CA3AF' }}>Est. Amount</span>
            <div className="snow-body" style={{ fontSize: 12, fontWeight: 600 }}>
              {claimData?.estimated_claim_amount ? `$${Number(claimData.estimated_claim_amount).toLocaleString()}` : (claimData?.extracted_data?.estimated_claim_amount ? `$${Number(claimData.extracted_data.estimated_claim_amount).toLocaleString()}` : '—')}
            </div>
          </div>
        </div>

        {/* Dynamic RAG Requirements & Questionnaire Fields */}
        <div style={{ marginTop: 6 }}>
          <span className="snow-caption" style={{ fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
            Loss Specifics & Verification Answers
          </span>
          {(() => {
            const ext = claimData?.extracted_data || {};
            const entries = Object.entries(ext).filter(([k]) => !['policy_id', 'insurance_type', 'event_date', 'event_location', 'event_description', 'estimated_claim_amount'].includes(k));
            if (entries.length === 0) {
              return (
                <div style={{ padding: 12, backgroundColor: '#F9FAFB', borderRadius: 8, color: '#6B7280', fontSize: 12, textAlign: 'center' }}>
                  Answer the AI assistant's questions to populate loss specifics.
                </div>
              );
            }
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {entries.map(([k, v]) => (
                  <div key={k} style={{ padding: '6px 10px', backgroundColor: '#F9FAFB', borderRadius: 6, border: '1px solid #F3F4F6' }}>
                    <span className="snow-micro" style={{ color: '#6B7280', textTransform: 'capitalize' }}>
                      {k.replace(/_/g, ' ')}
                    </span>
                    <div className="snow-caption" style={{ fontWeight: 600, color: '#1F2937' }}>
                      {typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v ?? '—')}
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>

        {/* Policy Details */}
        {(claimData?.coverage_amount || claimData?.deductible) && (
          <div style={{ padding: 10, backgroundColor: '#F0FDF4', borderRadius: 8, border: '1px solid #DCFCE7' }}>
            <div className="snow-micro" style={{ color: '#166534', fontWeight: 600 }}>Underwriting Bounds</div>
            <div className="snow-caption" style={{ color: '#15803D', marginTop: 2 }}>
              Limit: ${Number(claimData.coverage_amount || 0).toLocaleString()} • Deductible: ${Number(claimData.deductible || 0).toLocaleString()}
            </div>
          </div>
        )}
      </div>
    </div>

      {/* Evidence Upload Modal */}
      <Modal
        isOpen={evidenceModalOpen}
        onClose={() => setEvidenceModalOpen(false)}
        title="Upload Damage Evidence"
      >
        <form onSubmit={handleUploadEvidence}>
          <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
            Attach repair estimates, garage quotations, or accident photos to verify your claim.
          </p>

          <input
            type="file"
            accept="image/*,application/pdf"
            onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: 10,
              border: '1px dashed #D4D4D8',
              backgroundColor: '#FAFAFA',
              marginBottom: 20,
            }}
          />

          <div className="snow-flex snow-justify-between snow-gap-3">
            <Button type="button" variant="secondary" onClick={() => setEvidenceModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!selectedFile || uploadingEvidence}>
              {uploadingEvidence ? 'Uploading...' : 'Upload & Attach'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Discard / Reset Modal */}
      <Modal
        isOpen={discardModalOpen}
        onClose={() => setDiscardModalOpen(false)}
        title="Reset Conversation?"
      >
        <div style={{ padding: '8px 0 16px' }}>
          <p className="snow-body" style={{ color: '#52525B' }}>
            Are you sure you want to reset this conversation? This will clear the current dialogue and start a fresh intake.
          </p>
        </div>

        <div className="snow-flex snow-justify-between snow-gap-3">
          <Button type="button" variant="secondary" onClick={() => setDiscardModalOpen(false)}>
            Keep Conversation
          </Button>
          <Button type="button" variant="danger" onClick={handleResetChat}>
            Reset Chat
          </Button>
        </div>
      </Modal>

      {/* Confirm / Submit Claim Modal */}
      <Modal
        isOpen={confirmModalOpen}
        onClose={() => setConfirmModalOpen(false)}
        title="Submit Claim for Adjudication"
      >
        <div style={{ padding: '8px 0 16px' }}>
          <p className="snow-body" style={{ color: '#52525B' }}>
            You are submitting claim <strong>#{ticketId}</strong> to the insurance adjudication queue. An assigned adjuster will review your loss details and policy terms.
          </p>
        </div>

        <div className="snow-flex snow-justify-between snow-gap-3">
          <Button type="button" variant="secondary" onClick={() => setConfirmModalOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={handleConfirmClaim}
            disabled={submittingClaim}
          >
            {submittingClaim ? 'Submitting...' : 'Confirm Submission'}
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}

export default function FileClaimPage() {
  return (
    <Suspense fallback={<div style={{ padding: 48, textAlign: 'center', color: '#71717A' }}>Loading claim intake...</div>}>
      <FileClaimContent />
    </Suspense>
  );
}
