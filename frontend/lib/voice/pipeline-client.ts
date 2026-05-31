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

export class VoicePipelineClient {
  private peer: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private stopped = false;

  constructor(private readonly options: VoicePipelineClientOptions) {}

  async start(): Promise<void> {
    this.options.onState?.('connecting');
    const turnConfigResponse = await fetch(apiUrl('/turn-config'), API_FETCH_OPTIONS);
    this.ensureActive();
    if (!turnConfigResponse.ok) throw new Error('Could not load voice transport config');
    const iceServers = (await turnConfigResponse.json()) as RTCIceServer[];
    this.ensureActive();
    const peer = new RTCPeerConnection({ iceServers });
    this.peer = peer;

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

    this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    this.ensureActive();
    this.options.onLocalStream?.(this.localStream);
    peer.addTransceiver('audio', { direction: 'sendrecv' });
    this.localStream.getAudioTracks().forEach((track) => peer.addTrack(track, this.localStream as MediaStream));

    const offer = await peer.createOffer();
    this.ensureActive();
    await peer.setLocalDescription(offer);
    this.ensureActive();
    await waitForIceGathering(peer);
    this.ensureActive();

    const response = await fetch(apiUrl('/offer'), {
      ...API_FETCH_OPTIONS,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
    const answer = (await response.json()) as RTCSessionDescriptionInit & { error?: string; detail?: string };
    this.ensureActive();
    if (!response.ok) throw new Error(answer.error || answer.detail || 'Could not start Pipecat voice');
    await peer.setRemoteDescription(answer);
    this.ensureActive();
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

  private ensureActive(): void {
    if (this.stopped) throw new Error('Voice pipeline stopped');
  }
}

function waitForIceGathering(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      if (peer.iceGatheringState === 'complete') {
        peer.removeEventListener('icegatheringstatechange', done);
        resolve();
      }
    };
    peer.addEventListener('icegatheringstatechange', done);
    window.setTimeout(resolve, 1800);
  });
}
