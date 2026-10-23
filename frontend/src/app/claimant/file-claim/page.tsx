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
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Modal } from '@/components/ui/Modal';
import { FileUpload } from '@/components/ui/FileUpload';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

interface Message {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  time: string;
  citations?: string[];
}

function downsampleTo16k(input: Float32Array, inputSampleRate: number): Float32Array {
  if (inputSampleRate === 16000) return input;
  const ratio = inputSampleRate / 16000;
  const newLength = Math.round(input.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const origIndex = Math.min(Math.round(i * ratio), input.length - 1);
    result[i] = input[origIndex];
  }
  return result;
}

function encodeWav(samples: Float32Array, sampleRate: number = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // Mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); // 16-bit
  writeString(36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

function FileClaimContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryTicketId = searchParams.get('ticket_id');
  const isFreshRequest = searchParams.get('fresh') === 'true';

  const { showToast } = useToast();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const liveTranscriptRef = useRef<string>('');
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const isVoiceActiveRef = useRef<boolean>(false);
  const whisperIntervalRef = useRef<any>(null);
  const audioContextRef = useRef<any>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);
  const isTranscribingRef = useRef<boolean>(false);
  const hasSpokenRef = useRef<boolean>(false);
  const animFrameRef = useRef<number | null>(null);

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
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [isThinking, setIsThinking] = useState(false);
  const [speechSynthesisEnabled, setSpeechSynthesisEnabled] = useState(true);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);

  // User's linked policies
  const [userPolicies, setUserPolicies] = useState<any[]>([]);
  const [selectedPolicyNumber, setSelectedPolicyNumber] = useState<string>('');

  // Evidence Modal
  const [evidenceModalOpen, setEvidenceModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadingEvidence, setUploadingEvidence] = useState(false);

  // Mobile view tab toggle: 'chat' | 'dossier'
  const [mobileTab, setMobileTab] = useState<'chat' | 'dossier'>('chat');

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
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
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

  const stopSpeaking = () => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setSpeakingMessageId(null);
  };

  // Text-to-Speech Speak back from AI with Indian English accent
  const speakText = (text: string, messageId?: string) => {
    if (!speechSynthesisEnabled || typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    try {
      if (window.speechSynthesis.speaking && messageId && speakingMessageId === messageId) {
        stopSpeaking();
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'en-IN';
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      const voices = window.speechSynthesis.getVoices();
      const indianVoice = voices.find(
        (v) => v.lang === 'en-IN' || v.lang.startsWith('en-IN') || v.name.toLowerCase().includes('india')
      );
      if (indianVoice) {
        utterance.voice = indianVoice;
      }

      if (messageId) {
        setSpeakingMessageId(messageId);
        utterance.onend = () => setSpeakingMessageId(null);
        utterance.onerror = () => setSpeakingMessageId(null);
      }
      window.speechSynthesis.speak(utterance);
    } catch {
      setSpeakingMessageId(null);
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

  const stopVoiceRecording = async (sendImmediately = true) => {
    isVoiceActiveRef.current = false;
    setIsVoiceActive(false);

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (whisperIntervalRef.current) {
      clearInterval(whisperIntervalRef.current);
      whisperIntervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (scriptProcessorRef.current) {
      try {
        scriptProcessorRef.current.disconnect();
      } catch (e) {
        console.debug('ScriptProcessor disconnect notice:', e);
      }
      scriptProcessorRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch (e) {
        console.debug('AudioContext close notice:', e);
      }
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {
        console.debug('Recognition stop notice:', e);
      }
      recognitionRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    setAudioLevel(0);

    let finalText = liveTranscriptRef.current.trim();
    setLiveTranscript('');
    liveTranscriptRef.current = '';

    // If live text is not yet available, transcribe the accumulated PCM samples
    if (!finalText && pcmChunksRef.current.length > 0 && audioContextRef.current) {
      try {
        const totalSamples = pcmChunksRef.current.reduce((acc, c) => acc + c.length, 0);
        const sampleRate = audioContextRef.current.sampleRate || 44100;
        if (totalSamples > sampleRate * 0.4) {
          const merged = new Float32Array(totalSamples);
          let offset = 0;
          for (const chunk of pcmChunksRef.current) {
            merged.set(chunk, offset);
            offset += chunk.length;
          }
          const downsampled = downsampleTo16k(merged, sampleRate);
          const wavBlob = encodeWav(downsampled, 16000);
          const formData = new FormData();
          formData.append('file', wavBlob, 'final_speech.wav');
          const res = await api.post<{ text: string }>('/api/v1/voice/transcribe', formData);
          if (res?.text && res.text.trim()) {
            finalText = res.text.trim();
          }
        }
      } catch (err) {
        console.error('Final speech transcribe error:', err);
      }
    }

    pcmChunksRef.current = [];
    audioContextRef.current = null;

    if (sendImmediately && finalText) {
      setInputTurn('');
      handleSendText(finalText, { fromVoice: true });
    }
  };

  // Browser Voice Input with Simultaneous Live Real-Time Transcription
  const toggleVoiceMode = async () => {
    if (isVoiceActive) {
      // Click mic again to cut mic -> immediate send turn
      stopVoiceRecording(true);
      return;
    }

    if (typeof window === 'undefined') return;

    let stream: MediaStream | null = null;
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaStreamRef.current = stream;
        pcmChunksRef.current = [];
        hasSpokenRef.current = false;

        const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioCtxClass) {
          const ctx = new AudioCtxClass();
          audioContextRef.current = ctx;

          const analyser = ctx.createAnalyser();
          analyser.fftSize = 64;

          const source = ctx.createMediaStreamSource(stream);
          source.connect(analyser);

          // Audio buffer processor for live raw PCM capture
          const processor = ctx.createScriptProcessor(4096, 1, 1);
          scriptProcessorRef.current = processor;
          processor.onaudioprocess = (e) => {
            if (!isVoiceActiveRef.current) return;
            const input = e.inputBuffer.getChannelData(0);
            pcmChunksRef.current.push(new Float32Array(input));
          };
          source.connect(processor);
          processor.connect(ctx.destination);

          // Volume animation loop
          const freqData = new Uint8Array(analyser.frequencyBinCount);
          const checkVolume = () => {
            if (!isVoiceActiveRef.current) return;
            analyser.getByteFrequencyData(freqData);
            let sum = 0;
            for (let i = 0; i < freqData.length; i++) sum += freqData[i];
            const normalized = Math.min(1, (sum / freqData.length) / 45);
            setAudioLevel(normalized);
            animFrameRef.current = requestAnimationFrame(checkVolume);
          };
          checkVolume();
        }
      }
    } catch (err: any) {
      showToast('Could not access microphone. Please grant browser microphone permissions.', 'error');
      return;
    }

    isVoiceActiveRef.current = true;
    setIsVoiceActive(true);
    setLiveTranscript('');
    liveTranscriptRef.current = '';
    setInputTurn('');
    startSilenceTimer();

    // 2. Web Speech Recognition for instant client-side speech
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-IN';
        recognition.maxAlternatives = 1;

        recognition.onresult = (event: any) => {
          let finalTranscript = '';
          let interimTranscript = '';
          for (let i = 0; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript + ' ';
            } else {
              interimTranscript += event.results[i][0].transcript;
            }
          }
          const combined = (finalTranscript + interimTranscript).trim();
          if (combined) {
            setLiveTranscript(combined);
            liveTranscriptRef.current = combined;
            hasSpokenRef.current = true;
            startSilenceTimer();
          }
        };

        recognition.onerror = (event: any) => {
          console.debug('SpeechRecognition note:', event.error);
        };

        recognition.onend = () => {
          if (isVoiceActiveRef.current && recognitionRef.current) {
            try {
              recognitionRef.current.start();
            } catch (e) {
              console.debug('Recognition restart notice:', e);
            }
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
      } catch (err: any) {
        console.debug('SpeechRecognition start error:', err);
      }
    }

    // 3. Robust Live Streaming Whisper Poller via PCM WAV
    whisperIntervalRef.current = setInterval(async () => {
      if (!isVoiceActiveRef.current || isTranscribingRef.current) return;
      if (!audioContextRef.current || pcmChunksRef.current.length === 0) return;

      let totalSamples = pcmChunksRef.current.reduce((acc, c) => acc + c.length, 0);
      const sampleRate = audioContextRef.current.sampleRate || 44100;
      // Need at least 0.75 seconds of audio to transcribe meaningfully
      if (totalSamples < sampleRate * 0.75) return;

      // Bound buffer to the most recent 15 seconds to prevent unbounded memory growth
      const maxSamples = sampleRate * 15;
      if (totalSamples > maxSamples) {
        let keptSamples = 0;
        const keptChunks: Float32Array[] = [];
        for (let i = pcmChunksRef.current.length - 1; i >= 0; i--) {
          keptChunks.unshift(pcmChunksRef.current[i]);
          keptSamples += pcmChunksRef.current[i].length;
          if (keptSamples >= maxSamples) break;
        }
        pcmChunksRef.current = keptChunks;
        totalSamples = keptSamples;
      }

      // Merge all PCM chunks into one Float32Array
      const merged = new Float32Array(totalSamples);
      let offset = 0;
      for (const chunk of pcmChunksRef.current) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      // Check vocal energy
      let sumSq = 0;
      for (let i = 0; i < merged.length; i++) {
        sumSq += merged[i] * merged[i];
      }
      const rms = Math.sqrt(sumSq / merged.length);
      // Only transcribe if speech energy is present or has already spoken
      if (rms < 0.008 && !hasSpokenRef.current) return;

      const downsampled = downsampleTo16k(merged, sampleRate);
      const wavBlob = encodeWav(downsampled, 16000);

      isTranscribingRef.current = true;
      try {
        const formData = new FormData();
        formData.append('file', wavBlob, 'live_speech.wav');
        const res = await api.post<{ text: string }>('/api/v1/voice/transcribe', formData);
        if (isVoiceActiveRef.current && res?.text && res.text.trim()) {
          const trimmed = res.text.trim();
          setLiveTranscript(trimmed);
          liveTranscriptRef.current = trimmed;
          hasSpokenRef.current = true;
          startSilenceTimer();
        }
      } catch (err) {
        console.debug('Whisper live poll note:', err);
      } finally {
        isTranscribingRef.current = false;
      }
    }, 1200);
  };

  // Send turn (text or voice) to backend
  const handleSendText = async (textToSend?: string, options?: { fromVoice?: boolean }) => {
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
      if (options?.fromVoice) {
        speakText(replyText, assistantMsg.id);
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to process message turn.', 'error');
    } finally {
      setIsThinking(false); // FIX 3: Replace thinking indicator with real reply
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

      const res = await api.post<any>(`/api/v1/claims/${ticketId}/evidence`, formData);
      if (res?.message) {
        setMessages((prev) => [
          ...prev,
          {
            id: `ev-${Date.now()}`,
            speaker: 'assistant',
            text: res.message,
            time: 'Just now',
            citations: res.citations || [],
          },
        ]);
      }
      try {
        const updatedClaim = await api.get<any>(`/api/v1/claims/${ticketId}`);
        if (updatedClaim) setClaimData(updatedClaim);
      } catch {
        // ignore refresh error
      }
      showToast('Evidence document uploaded and analyzed!', 'success');
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
      hideRightDrawer
      noScroll
    >
      {/* Mobile Tab Switcher */}
      <div className="snow-mobile-intake-tabs">
        <button
          type="button"
          className={`snow-mobile-intake-tab ${mobileTab === 'chat' ? 'active' : ''}`}
          onClick={() => setMobileTab('chat')}
        >
          💬 AI Chat & Voice
        </button>
        <button
          type="button"
          className={`snow-mobile-intake-tab ${mobileTab === 'dossier' ? 'active' : ''}`}
          onClick={() => setMobileTab('dossier')}
        >
          📋 Live Claim Dossier
        </button>
      </div>

      {/* Top Bar Policy Selector */}
      <div
        className="snow-policy-bar-responsive"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
          padding: '10px 14px',
          backgroundColor: '#FFFFFF',
          borderRadius: 12,
          border: '1px solid #E5E7EB',
          gap: 10,
          flexWrap: 'wrap',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 240px', minWidth: 0 }}>
          <ShieldCheck size={18} color="#007AFF" style={{ flexShrink: 0 }} />
          <span className="snow-caption" style={{ fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' }}>
            Filing Against Policy:
          </span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <Select
              size="sm"
              value={selectedPolicyNumber}
              onChange={async (newVal) => {
                setSelectedPolicyNumber(newVal);
                if (ticketId && (!claimData?.status || ['draft', 'verified', 'pending_confirmation'].includes(claimData.status))) {
                  try {
                    const patched = await api.patch<any>(`/api/v1/claims/${ticketId}`, { policy_id: newVal || null });
                    if (patched) setClaimData(patched);
                  } catch {
                    // non-fatal
                  }
                }
              }}
              options={[
                { value: '', label: '-- No Specific Policy (General Inquiry / Auto-Resolve) --' },
                ...userPolicies.map((p) => ({
                  value: p.policy_number,
                  label: `${p.policy_number} — ${p.policy_type?.toUpperCase()} (Limit: ₹${Number(p.coverage_amount || 0).toLocaleString('en-IN')})`,
                })),
              ]}
              style={{ marginBottom: 0 }}
            />
          </div>
        </div>
        {ticketId && (
          <div className="snow-caption" style={{ color: '#6B7280', flexShrink: 0 }}>
            Claim Ticket: <strong style={{ color: '#111827' }}>#{ticketId}</strong>
          </div>
        )}
      </div>

      {/* 2-Column Responsive Layout: Chat + Live Claim Dossier */}
      <div
        className={`snow-file-claim-grid ${mobileTab === 'chat' ? 'show-chat' : 'show-dossier'}`}
        style={{
          gap: 16,
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {/* Left Column: Chat Messages & Input */}
        <div
          className={`snow-chat-col ${mobileTab === 'dossier' ? 'mobile-hidden' : ''}`}
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: 0,
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          {/* Messages Scroll Area */}
          <div
            ref={messagesContainerRef}
            className="snow-card snow-scrollbar"
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              marginBottom: 12,
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
                      onClick={() => {
                        if (speakingMessageId === m.id) {
                          stopSpeaking();
                        } else {
                          speakText(m.text, m.id);
                        }
                      }}
                      style={{
                        background: speakingMessageId === m.id ? '#EFF6FF' : '#F4F5F7',
                        border: speakingMessageId === m.id ? '1px solid #3B82F6' : '1px solid transparent',
                        borderRadius: 6,
                        cursor: 'pointer',
                        color: speakingMessageId === m.id ? '#2563EB' : '#4B5563',
                        padding: '2px 8px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        fontSize: 11,
                        fontWeight: 500,
                        transition: 'all 0.15s ease',
                      }}
                      title={speakingMessageId === m.id ? 'Stop reading aloud' : 'Read aloud'}
                      aria-label={speakingMessageId === m.id ? 'Stop reading aloud' : 'Read aloud'}
                    >
                      {speakingMessageId === m.id ? (
                        <>
                          <VolumeX size={12} color="#2563EB" />
                          <span>Stop</span>
                        </>
                      ) : (
                        <>
                          <Volume2 size={12} />
                          <span>Read Aloud</span>
                        </>
                      )}
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
                opacity: 0.98,
                border: '1.5px solid #007AFF',
                backgroundColor: '#F0F7FF',
                color: '#1C1C1C',
                position: 'relative',
                boxShadow: '0 4px 14px rgba(0, 122, 255, 0.12)',
              }}
            >
              {liveTranscript ? (
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, fontSize: 14, fontWeight: 500, color: '#0F172A' }}>
                  {liveTranscript}
                  <span className="snow-live-cursor" />
                </div>
              ) : (
                <div className="snow-flex snow-items-center snow-gap-2" style={{ padding: '2px 0' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 2, height: 16 }}>
                    <span className="snow-soundwave-bar" />
                    <span className="snow-soundwave-bar" />
                    <span className="snow-soundwave-bar" />
                  </div>
                  <span style={{ fontSize: 13, color: '#007AFF', fontWeight: 500 }}>
                    Listening...
                  </span>
                  <span className="snow-live-cursor" />
                </div>
              )}
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
            flexShrink: 0,
          }}
        >
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
                ? 'Listening & transcribing in real time... Speak now or click mic to send'
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

          {/* Submit Claim / Track Submitted Claim Button */}
          {ticketId && (
            claimData?.status && ['submitted', 'assigned', 'under_review', 'pending_evidence', 'approved', 'partially_approved', 'rejected', 'closed'].includes(claimData.status) ? (
              <Button
                size="sm"
                variant="secondary"
                pill
                onClick={() => router.push(`/claimant/claims/${ticketId}`)}
              >
                Track Claim & Requests
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                pill
                onClick={() => setConfirmModalOpen(true)}
              >
                Submit Claim
              </Button>
            )
          )}
        </div>
      </div>

      {/* Right Column: Live Claim Dossier Panel */}
      <div
        className={`snow-dossier-col snow-card snow-scrollbar ${mobileTab === 'chat' ? 'mobile-hidden' : ''}`}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          padding: 18,
          borderRadius: 16,
          overflowY: 'auto',
          backgroundColor: '#FFFFFF',
          minWidth: 0,
          height: '100%',
          minHeight: 0,
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
              {claimData?.estimated_claim_amount ? `₹${Number(claimData.estimated_claim_amount).toLocaleString('en-IN')}` : (claimData?.extracted_data?.estimated_claim_amount ? `₹${Number(claimData.extracted_data.estimated_claim_amount).toLocaleString('en-IN')}` : '—')}
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
          <div style={{ marginBottom: 20 }}>
            <FileUpload
              label="Select Document or Image"
              accept="image/*,application/pdf"
              file={selectedFile}
              onFileSelect={(f: File | null) => setSelectedFile(f)}
              hint="Attach repair estimates, garage quotations, or accident photos to verify your claim."
            />
          </div>

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

      {/* Confirm / Submit Claim Modal */}

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
