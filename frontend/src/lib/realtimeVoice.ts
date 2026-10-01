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

const apiBase = () =>
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const wsBase = () =>
  apiBase().replace(/^https:/, "wss:").replace(/^http:/, "ws:");

interface VoiceSessionResponse {
  call_id: string;
  ticket_id: string;
  provider: "pipecat_local";
  transport: "small_webrtc";
}

interface VoiceOfferResponse {
  sdp: string;
  type: "answer";
  pc_id?: string;
}

export class RealtimeVoiceSession {
  private pc: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private eventsSocket: WebSocket | null = null;
  private callId: string | null = null;
  private callbacks: RealtimeVoiceCallbacks = {};
  private closed = false;

  async connect(
    ticketId: string,
    token: string,
    callbacks: RealtimeVoiceCallbacks = {},
  ): Promise<void> {
    this.callbacks = callbacks;
    this.closed = false;
    this.callbacks.onState?.("connecting");

    await this.connectEvents(ticketId, token);
    const session = await this.requestSession(ticketId, token);
    this.callId = session.call_id;

    this.pc = new RTCPeerConnection();

    this.remoteAudio = document.createElement("audio");
    this.remoteAudio.autoplay = true;
    this.remoteAudio.setAttribute("playsinline", "true");
    this.remoteAudio.setAttribute("aria-hidden", "true");
    this.remoteAudio.style.display = "none";
    document.body.appendChild(this.remoteAudio);

    this.pc.ontrack = (event) => {
      const stream = event.streams[0];
      if (!stream || !this.remoteAudio) return;
      this.remoteAudio.srcObject = stream;
      void this.remoteAudio.play().catch(() => {});
    };

    this.pc.onconnectionstatechange = () => {
      if (this.closed) return;
      const state = this.pc?.connectionState;
      if (state === "connected") {
        this.callbacks.onConnected?.();
        this.callbacks.onState?.("listening");
      } else if (state === "failed") {
        this.callbacks.onState?.("error");
        this.callbacks.onError?.(
          "The voice connection failed. You can continue by typing.",
        );
        this.callbacks.onDisconnected?.();
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
    if (!track) {
      throw new Error("Microphone access did not return an audio track.");
    }
    this.pc.addTrack(track, this.localStream);

    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    const response = await fetch(
      apiBase() +
        "/api/v1/voice/realtime/offer/" +
        encodeURIComponent(session.call_id),
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
        body: JSON.stringify({
          ticket_id: ticketId,
          type: offer.type,
          sdp: offer.sdp || "",
        }),
      },
    );

    if (!response.ok) {
      let detail = "Voice service is unavailable.";
      try {
        const json = (await response.json()) as { detail?: string };
        detail = String(json.detail || detail);
      } catch {}
      throw new Error(detail);
    }

    const answer = (await response.json()) as VoiceOfferResponse;
    await this.pc.setRemoteDescription({
      type: answer.type,
      sdp: answer.sdp,
    });
  }

  private async requestSession(
    ticketId: string,
    token: string,
  ): Promise<VoiceSessionResponse> {
    const response = await fetch(
      apiBase() +
        "/api/v1/voice/realtime/session/" +
        encodeURIComponent(ticketId),
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
          "Cache-Control": "no-store",
        },
      },
    );
    if (!response.ok) {
      let detail = "Voice service is unavailable.";
      try {
        const json = (await response.json()) as { detail?: string };
        detail = String(json.detail || detail);
      } catch {}
      throw new Error(detail);
    }
    return (await response.json()) as VoiceSessionResponse;
  }

  private async connectEvents(ticketId: string, token: string): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(
        wsBase() + "/api/v1/voice/events/" + encodeURIComponent(ticketId),
      );
      this.eventsSocket = socket;
      let settled = false;

      const timer = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error("Voice event channel timed out."));
        try {
          socket.close();
        } catch {}
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
          reject(
            new Error("Voice event channel closed before authentication."),
          );
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
      case "voice.user.partial":
        this.callbacks.onUserPartial?.(String(event.text || ""));
        break;
      case "voice.user.final":
        this.callbacks.onUserPartial?.("");
        this.callbacks.onUserFinal?.(
          String(event.text || ""),
          String(event.item_id || ""),
        );
        break;
      case "voice.agent.partial":
        this.callbacks.onAgentPartial?.(String(event.text || ""));
        break;
      case "voice.agent.final":
        this.callbacks.onAgentFinal?.(String(event.text || ""));
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
      case "voice.session.ended":
        if (!this.closed) this.callbacks.onDisconnected?.();
        break;
      default:
        break;
    }
  }

  speakAuthoritativeText(_text: string): void {
    // Authoritative claim-agent replies are automatically sent through Piper
    // by the Pipecat pipeline. There is intentionally no second TTS path.
  }

  stopAssistant(): void {
    try {
      this.remoteAudio?.pause();
    } catch {}
  }

  close(): void {
    this.closed = true;
    try {
      this.eventsSocket?.close();
    } catch {}
    try {
      this.localStream?.getTracks().forEach((track) => track.stop());
    } catch {}
    try {
      this.pc?.close();
    } catch {}
    this.eventsSocket = null;
    this.localStream = null;
    this.pc = null;
    this.callId = null;
    if (this.remoteAudio) {
      this.remoteAudio.srcObject = null;
      this.remoteAudio.remove();
    }
    this.remoteAudio = null;
    this.callbacks.onState?.("idle");
  }
}
