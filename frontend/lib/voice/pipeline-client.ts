import { API_FETCH_OPTIONS, apiUrl } from '@/lib/api-base';

export type PipelineCallState = 'connecting' | 'connected' | 'closed' | 'error';

export interface VoicePipelineClientEvents {
  onState?: (state: PipelineCallState) => void;
  onRemoteStream?: (stream: MediaStream) => void;
  onLocalStream?: (stream: MediaStream) => void;
  onError?: (error: Error) => void;
  onRemoteAudioStarted?: () => void;
  onDiagnostic?: (event: string, detail?: Record<string, unknown>) => void;
}

export interface VoicePipelineClientOptions extends VoicePipelineClientEvents {
  sessionId: string;
  callId: string;
}

interface PipecatCloudConfig {
  agentName: string;
  publicApiKey: string;
  apiBaseUrl: string;
}

interface PipecatCloudSession {
  offerUrl: string;
  iceServers: RTCIceServer[];
}

function getPipecatCloudConfig(): PipecatCloudConfig | null {
  const agentName = process.env.NEXT_PUBLIC_PIPECAT_CLOUD_AGENT_NAME?.trim();
  const publicApiKey = process.env.NEXT_PUBLIC_PIPECAT_CLOUD_PUBLIC_API_KEY?.trim();
  const apiBaseUrl = (process.env.NEXT_PUBLIC_PIPECAT_CLOUD_API_BASE_URL || 'https://api.pipecat.daily.co/v1/public')
    .replace(/\/+$/, '');

  if (!agentName || !publicApiKey) return null;
  return { agentName, publicApiKey, apiBaseUrl };
}

export class VoicePipelineClient {
  private peer: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private pcId: string | null = null;
  private pendingIceCandidates: RTCIceCandidateInit[] = [];
  private stopped = false;
  private offerUrl = apiUrl('/offer');
  private patchOfferUrl = apiUrl('/offer');
  private signalingHeaders: HeadersInit = { 'Content-Type': 'application/json' };
  private readonly startedAt = performance.now();

  constructor(private readonly options: VoicePipelineClientOptions) {}

  async start(): Promise<void> {
    try {
      this.options.onState?.('connecting');
      const cloudSessionPromise = this.startPipecatCloudSession();
      const localStreamPromise = navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      const [cloudSession, localStream] = await Promise.all([cloudSessionPromise, localStreamPromise]);
      this.localStream = localStream;
      if (this.stopped) {
        localStream.getTracks().forEach((track) => track.stop());
        this.localStream = null;
        this.ensureActive();
      }
      this.ensureActive();
      const iceServers = cloudSession?.iceServers ?? await this.loadLocalIceServers();
      this.ensureActive();
      this.diagnostic('setup:microphone_ready');
      const peer = new RTCPeerConnection({ iceServers });
      this.peer = peer;

      peer.onicecandidate = (event) => {
        if (this.stopped || !event.candidate) return;
        this.queueOrPatchIceCandidate(event.candidate.toJSON());
      };

      peer.onconnectionstatechange = () => {
        if (this.stopped) return;
        if (peer.connectionState === 'connected') this.options.onState?.('connected');
        if (peer.connectionState === 'closed') this.options.onState?.('closed');
        if (peer.connectionState === 'failed') {
          const error = new Error('Pipecat voice connection failed');
          this.options.onState?.('error');
          this.options.onError?.(error);
        }
      };

      peer.ontrack = (event) => {
        if (this.stopped) return;
        const stream = event.streams[0] ?? new MediaStream([event.track]);
        this.options.onDiagnostic?.('remote_audio:track', {
          streamCount: event.streams.length,
          trackKind: event.track.kind,
        });
        this.options.onRemoteStream?.(stream);
        if (!this.remoteAudio) {
          this.remoteAudio = new Audio();
          this.remoteAudio.autoplay = true;
          this.remoteAudio.setAttribute('playsInline', '');
          document.body.appendChild(this.remoteAudio);
        }
        this.remoteAudio.srcObject = stream;
        void this.remoteAudio.play()
          .then(() => {
            if (this.stopped) return;
            this.options.onRemoteAudioStarted?.();
            this.options.onDiagnostic?.('remote_audio:play:started');
          })
          .catch((error: unknown) => {
            this.options.onDiagnostic?.('remote_audio:play:failed', {
              reason: error instanceof Error ? error.message || error.name : String(error),
            });
            this.options.onError?.(error instanceof Error ? error : new Error(String(error)));
          });
      };

      this.options.onLocalStream?.(localStream);
      peer.addTransceiver('audio', { direction: 'sendrecv' });
      localStream.getAudioTracks().forEach((track) => peer.addTrack(track, localStream));

      const offer = await peer.createOffer();
      this.ensureActive();
      await peer.setLocalDescription(offer);
      this.ensureActive();

      const response = await fetch(this.offerUrl, {
        ...API_FETCH_OPTIONS,
        method: 'POST',
        headers: this.signalingHeaders,
        body: JSON.stringify({
          type: peer.localDescription?.type,
          sdp: peer.localDescription?.sdp,
          request_data: {
            session_id: this.options.sessionId,
            call_id: this.options.callId,
          },
        }),
      });
      this.ensureActive();
      const answer = (await response.json()) as RTCSessionDescriptionInit & { error?: string; detail?: string; pc_id?: string };
      this.ensureActive();
      if (!response.ok) throw new Error(answer.error || answer.detail || 'Could not start Pipecat voice');
      this.pcId = typeof answer.pc_id === 'string' ? answer.pc_id : null;
      this.diagnostic('offer:answer_received', { has_pc_id: Boolean(this.pcId) });
      void this.flushPendingIceCandidates();
      await peer.setRemoteDescription(answer);
      this.ensureActive();
      this.diagnostic('setup:complete');
    } catch (error) {
      this.stop();
      throw error;
    }
  }

  setMuted(muted: boolean): void {
    this.localStream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }

  stop(): void {
    const shouldNotify = !this.stopped;
    this.stopped = true;
    this.localStream?.getTracks().forEach((track) => track.stop());
    this.localStream = null;
    this.peer?.close();
    this.peer = null;
    this.remoteAudio?.remove();
    this.remoteAudio = null;
    if (shouldNotify) this.options.onState?.('closed');
  }

  private diagnostic(event: string, detail: Record<string, unknown> = {}): void {
    this.options.onDiagnostic?.(event, {
      ...detail,
      elapsed_ms: Math.round(performance.now() - this.startedAt),
    });
  }

  private queueOrPatchIceCandidate(candidate: RTCIceCandidateInit): void {
    if (candidate.sdpMid === null || candidate.sdpMid === undefined) return;
    if (candidate.sdpMLineIndex === null || candidate.sdpMLineIndex === undefined) return;
    if (!this.pcId) {
      this.pendingIceCandidates.push(candidate);
      this.diagnostic('ice:candidate_queued', { pending: this.pendingIceCandidates.length });
      return;
    }
    void this.patchIceCandidates([candidate]);
  }

  private async flushPendingIceCandidates(): Promise<void> {
    if (!this.pcId || !this.pendingIceCandidates.length) return;
    const candidates = this.pendingIceCandidates.splice(0);
    await this.patchIceCandidates(candidates);
  }

  private async patchIceCandidates(candidates: RTCIceCandidateInit[]): Promise<void> {
    if (!this.pcId || this.stopped || !candidates.length) return;
    try {
      const response = await fetch(this.patchOfferUrl, {
        ...API_FETCH_OPTIONS,
        method: 'PATCH',
        headers: this.signalingHeaders,
        body: JSON.stringify({
          pc_id: this.pcId,
          candidates: candidates.map((candidate) => ({
            candidate: candidate.candidate,
            sdp_mid: candidate.sdpMid,
            sdp_mline_index: candidate.sdpMLineIndex,
          })),
        }),
      });
      this.diagnostic('ice:patch_sent', { count: candidates.length, ok: response.ok });
    } catch (error) {
      this.diagnostic('ice:patch_failed', {
        count: candidates.length,
        reason: error instanceof Error ? error.message || error.name : String(error),
      });
    }
  }

  private async loadLocalIceServers(): Promise<RTCIceServer[]> {
    const turnConfigResponse = await fetch(apiUrl('/turn-config'), API_FETCH_OPTIONS);
    if (!turnConfigResponse.ok) throw new Error('Could not load voice transport config');
    this.diagnostic('setup:turn_config_ready');
    return await turnConfigResponse.json() as RTCIceServer[];
  }

  private async startPipecatCloudSession(): Promise<PipecatCloudSession | null> {
    const cloudConfig = getPipecatCloudConfig();
    if (!cloudConfig) return null;

    const startUrl = `${cloudConfig.apiBaseUrl}/${encodeURIComponent(cloudConfig.agentName)}/start`;
    const response = await fetch(startUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${cloudConfig.publicApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        transport: 'webrtc',
        enableDefaultIceServers: true,
        body: {
          session_id: this.options.sessionId,
          call_id: this.options.callId,
        },
      }),
    });
    this.ensureActive();
    const payload = await response.json() as {
      error?: string;
      message?: string;
      sessionId?: string;
      iceConfig?: { iceServers?: RTCIceServer[] };
    };
    this.ensureActive();
    if (!response.ok || !payload.sessionId) {
      throw new Error(payload.error || payload.message || 'Could not start Pipecat Cloud voice session');
    }

    const sessionPath = `${encodeURIComponent(cloudConfig.agentName)}/sessions/${encodeURIComponent(payload.sessionId)}/api/offer`;
    const cloudSession = {
      offerUrl: `${cloudConfig.apiBaseUrl}/${sessionPath}`,
      iceServers: payload.iceConfig?.iceServers ?? [],
    };
    this.offerUrl = cloudSession.offerUrl;
    this.patchOfferUrl = cloudSession.offerUrl;
    this.signalingHeaders = {
      'Authorization': `Bearer ${cloudConfig.publicApiKey}`,
      'Content-Type': 'application/json',
    };
    this.diagnostic('cloud:session_started', { session_id: payload.sessionId });
    return cloudSession;
  }

  private ensureActive(): void {
    if (this.stopped) throw new Error('Voice pipeline stopped');
  }
}
