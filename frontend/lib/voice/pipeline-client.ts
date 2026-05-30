import { API_FETCH_OPTIONS, apiUrl } from '@/lib/api-base';

export type PipelineCallState = 'connecting' | 'connected' | 'closed' | 'error';

export interface VoicePipelineClientEvents {
  onState?: (state: PipelineCallState) => void;
  onRemoteStream?: (stream: MediaStream) => void;
  onLocalStream?: (stream: MediaStream) => void;
  onError?: (error: Error) => void;
}

export interface VoicePipelineClientOptions extends VoicePipelineClientEvents {
  sessionId: string;
  callId: string;
}

export class VoicePipelineClient {
  private peer: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;

  constructor(private readonly options: VoicePipelineClientOptions) {}

  async start(): Promise<void> {
    this.options.onState?.('connecting');
    const turnConfigResponse = await fetch(apiUrl('/turn-config'), API_FETCH_OPTIONS);
    if (!turnConfigResponse.ok) throw new Error('Could not load voice transport config');
    const iceServers = (await turnConfigResponse.json()) as RTCIceServer[];
    const peer = new RTCPeerConnection({ iceServers });
    this.peer = peer;

    peer.onconnectionstatechange = () => {
      if (peer.connectionState === 'connected') this.options.onState?.('connected');
      if (peer.connectionState === 'closed') this.options.onState?.('closed');
      if (peer.connectionState === 'failed') {
        const error = new Error('Pipecat voice connection failed');
        this.options.onState?.('error');
        this.options.onError?.(error);
      }
    };

    peer.ontrack = (event) => {
      const stream = event.streams[0] ?? new MediaStream([event.track]);
      this.options.onRemoteStream?.(stream);
      if (!this.remoteAudio) {
        this.remoteAudio = new Audio();
        this.remoteAudio.autoplay = true;
        this.remoteAudio.setAttribute('playsInline', '');
        document.body.appendChild(this.remoteAudio);
      }
      this.remoteAudio.srcObject = stream;
      void this.remoteAudio.play().catch((error: unknown) => {
        this.options.onError?.(error instanceof Error ? error : new Error(String(error)));
      });
    };

    this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    this.options.onLocalStream?.(this.localStream);
    peer.addTransceiver('audio', { direction: 'sendrecv' });
    this.localStream.getAudioTracks().forEach((track) => peer.addTrack(track, this.localStream as MediaStream));

    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    await waitForIceGathering(peer);

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
    const answer = (await response.json()) as RTCSessionDescriptionInit & { error?: string; detail?: string };
    if (!response.ok) throw new Error(answer.error || answer.detail || 'Could not start Pipecat voice');
    await peer.setRemoteDescription(answer);
  }

  setMuted(muted: boolean): void {
    this.localStream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }

  stop(): void {
    this.localStream?.getTracks().forEach((track) => track.stop());
    this.localStream = null;
    this.peer?.close();
    this.peer = null;
    this.remoteAudio?.remove();
    this.remoteAudio = null;
    this.options.onState?.('closed');
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
