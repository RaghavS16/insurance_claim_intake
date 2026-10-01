export type RealtimeVoiceState =
  | "idle"
  | "connecting"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "error";

export interface RealtimeVoiceCallbacks {
  onState?: (state: RealtimeVoiceState) => void;
  onUserPartial?: (text: string) => void;
  onUserFinal?: (text: string, itemId: string) => void;
  onAgentPartial?: (text: string) => void;
  onAgentFinal?: (text: string) => void;
  onClaimState?: (payload: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
}

interface RealtimeEvent {
  type?: string;
  delta?: string;
  transcript?: string;
  item_id?: string;
  error?: { message?: string };
}

const apiBase = () =>
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const wsBase = () =>
  apiBase().replace(/^https:/, "wss:").replace(/^http:/, "ws:");

export class RealtimeVoiceSession {
  private pc: RTCPeerConnection | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private eventsSocket: WebSocket | null = null;
  private callbacks: RealtimeVoiceCallbacks = {};
  private agentTextBuffer = "";
  private closed = false;

  async connect(ticketId: string, token: string, callbacks: RealtimeVoiceCallbacks = {}): Promise<void> {
    this.callbacks = callbacks;
    this.closed = false;
    this.agentTextBuffer = "";
    this.callbacks.onState?.("connecting");

    await this.connectEvents(ticketId, token);
    this.pc = new RTCPeerConnection();

    this.remoteAudio = document.createElement("audio");
    this.remoteAudio.autoplay = true;
    this.remoteAudio.setAttribute("playsinline", "true");
    this.remoteAudio.setAttribute("aria-hidden", "true");
    this.remoteAudio.style.display = "none";
    document.body.appendChild(this.remoteAudio);

    this.pc.ontrack = (event) => {
      const stream = event.streams[0];
      if (stream && this.remoteAudio) {
        this.remoteAudio.srcObject = stream;
        void this.remoteAudio.play().catch(() => {});
      }
    };

    this.pc.onconnectionstatechange = () => {
      if (this.closed) return;
      const state = this.pc?.connectionState;
      if (state === "connected") {
        this.callbacks.onConnected?.();
        this.callbacks.onState?.("listening");
      } else if (state === "failed") {
        this.callbacks.onState?.("error");
        this.callbacks.onError?.("The voice connection failed. You can continue by typing.");
      } else if (state === "disconnected") {
        this.callbacks.onDisconnected?.();
      }
    };

    this.localStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const track = this.localStream.getAudioTracks()[0];
    if (!track) throw new Error("Microphone access did not return an audio track.");
    this.pc.addTrack(track, this.localStream);

    this.dataChannel = this.pc.createDataChannel("oai-events");
    this.dataChannel.onopen = () => {
      this.callbacks.onConnected?.();
      this.callbacks.onState?.("listening");
    };
    this.dataChannel.onclose = () => {
      if (!this.closed) this.callbacks.onDisconnected?.();
    };
    this.dataChannel.onerror = () => {
      if (!this.closed) {
        this.callbacks.onState?.("error");
        this.callbacks.onError?.("The realtime voice channel failed. You can continue by typing.");
      }
    };
    this.dataChannel.onmessage = (event) => {
      try {
        this.handleRealtimeEvent(JSON.parse(String(event.data)) as RealtimeEvent);
      } catch {}
    };

    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    const response = await fetch(
      apiBase() + "/api/v1/voice/realtime/session/" + encodeURIComponent(ticketId),
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
          "Content-Type": "application/sdp",
          "Cache-Control": "no-store",
        },
        body: offer.sdp || "",
      },
    );

    if (!response.ok) {
      let detail = "Voice service is unavailable.";
      try {
        const json = (await response.json()) as { detail?: string; message?: string };
        detail = String(json.detail || json.message || detail);
      } catch {}
      throw new Error(detail);
    }

    const answerSdp = await response.text();
    if (!response.headers.get("X-Voice-Call-Id")) {
      throw new Error("Voice service did not return a call identifier.");
    }

    await this.pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
  }

  private async connectEvents(ticketId: string, token: string): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(
        wsBase() + "/api/v1/voice/events/" + encodeURIComponent(ticketId),
      );
      this.eventsSocket = socket;
      let settled = false;

      const timer = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          reject(new Error("Voice event channel timed out."));
          try { socket.close(); } catch {}
        }
      }, 8000);

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "auth", token }));
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data)) as {
            event_type?: string;
            [key: string]: unknown;
          };
          if (payload.event_type === "voice.events.ready") {
            if (!settled) {
              settled = true;
              window.clearTimeout(timer);
              resolve();
            }
            return;
          }
          this.handleApplicationEvent(payload);
        } catch {}
      };

      socket.onerror = () => {
        if (!settled) {
          settled = true;
          window.clearTimeout(timer);
          reject(new Error("Voice event channel failed."));
        }
      };

      socket.onclose = () => {
        window.clearTimeout(timer);
        if (!settled) {
          settled = true;
          reject(new Error("Voice event channel closed before authentication."));
        } else if (!this.closed) {
          this.callbacks.onDisconnected?.();
        }
      };
    });
  }

  private handleApplicationEvent(event: {
    event_type?: string;
    state?: string;
    [key: string]: unknown;
  }): void {
    switch (event.event_type) {
      case "voice.state":
        this.callbacks.onState?.(
          String(event.state || "idle") as RealtimeVoiceState,
        );
        break;
      case "voice.claim.state":
        this.callbacks.onClaimState?.(event);
        break;
      case "voice.error":
        this.callbacks.onState?.("error");
        this.callbacks.onError?.(
          "The voice service encountered an error. You can continue by typing.",
        );
        break;
      default:
        break;
    }
  }

  private handleRealtimeEvent(event: RealtimeEvent): void {
    switch (event.type) {
      case "input_audio_buffer.speech_started":
        this.callbacks.onState?.("listening");
        break;
      case "input_audio_buffer.speech_stopped":
        this.callbacks.onState?.("transcribing");
        break;
      case "conversation.item.input_audio_transcription.delta":
        if (event.delta) this.callbacks.onUserPartial?.(event.delta);
        break;
      case "conversation.item.input_audio_transcription.completed":
        if (event.transcript) {
          this.callbacks.onUserPartial?.("");
          this.callbacks.onUserFinal?.(
            event.transcript,
            String(event.item_id || ""),
          );
        }
        break;
      case "response.created":
        this.agentTextBuffer = "";
        this.callbacks.onState?.("speaking");
        break;
      case "response.output_audio_transcript.delta":
        if (event.delta) {
          this.agentTextBuffer += event.delta;
          this.callbacks.onAgentPartial?.(this.agentTextBuffer);
        }
        break;
      case "response.output_audio_transcript.done":
        if (event.transcript) this.agentTextBuffer = event.transcript;
        if (this.agentTextBuffer) this.callbacks.onAgentFinal?.(this.agentTextBuffer);
        break;
      case "response.done":
      case "response.cancelled":
        if (this.agentTextBuffer) {
          this.callbacks.onAgentFinal?.(this.agentTextBuffer);
          this.agentTextBuffer = "";
        }
        this.callbacks.onState?.("idle");
        break;
      case "error":
        this.callbacks.onState?.("error");
        this.callbacks.onError?.(event.error?.message || "Realtime voice error.");
        break;
      default:
        break;
    }
  }

  speakAuthoritativeText(text: string): void {
    const normalized = text.trim();
    if (!normalized || !this.dataChannel || this.dataChannel.readyState !== "open") return;
    this.dataChannel.send(
      JSON.stringify({
        type: "response.create",
        response: {
          input: [],
          output_modalities: ["audio"],
          instructions:
            "Speak exactly the APPLICATION RESPONSE below. Do not add, remove, reinterpret, or invent information. Use a calm, concise customer-service delivery.\n\n" +
            "APPLICATION RESPONSE:\n" + normalized,
        },
      }),
    );
  }

  stopAssistant(): void {
    if (!this.dataChannel || this.dataChannel.readyState !== "open") return;
    this.dataChannel.send(JSON.stringify({ type: "response.cancel" }));
  }

  close(): void {
    this.closed = true;
    try { this.dataChannel?.send(JSON.stringify({ type: "session.close" })); } catch {}
    try { this.dataChannel?.close(); } catch {}
    try { this.eventsSocket?.close(); } catch {}
    this.dataChannel = null;
    this.eventsSocket = null;
    this.localStream?.getTracks().forEach((track) => track.stop());
    this.localStream = null;
    try { this.pc?.close(); } catch {}
    this.pc = null;
    if (this.remoteAudio) {
      this.remoteAudio.srcObject = null;
      this.remoteAudio.remove();
    }
    this.remoteAudio = null;
    this.callbacks.onState?.("idle");
  }
}
