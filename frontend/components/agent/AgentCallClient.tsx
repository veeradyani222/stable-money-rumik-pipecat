'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import type { PersonaSuggestion, PersonaBrief } from '@/lib/agent/persona-suggestions';
import { buildPersonaDetailSections } from '@/lib/agent/persona-panel';
import type { PersonaSeed } from '@/lib/personas';
import { AgentAudioVisualizerBar, type AgentVisualizerSpeaker } from '@/components/agents-ui/agent-audio-visualizer-bar';
import { PersonaDetailModal } from '@/components/onboarding/PersonaDetailModal';
import { API_FETCH_OPTIONS, apiUrl } from '@/lib/api-base';
import { VoicePipelineClient } from '@/lib/voice/pipeline-client';

type CallState = 'idle' | 'connecting' | 'connected' | 'error';
type AgentConversationPhase = 'user' | 'thinking' | 'agent';

const CONNECTING_RINGTONE_SRC = '/assets/dragon-ringing.mp3';
const RUMIK_VOICE_START_THRESHOLD = 8;
const RUMIK_VOICE_START_FRAMES = 3;
const USER_VOICE_START_THRESHOLD = 8;
const USER_VOICE_SILENCE_FRAMES = 18;

type VoiceTimingDetail = Record<string, string | number | boolean | null | undefined>;

interface AgentSessionPayload {
  session_id: string;
  email: string;
  persona: PersonaSeed;
  brief: PersonaBrief;
  suggestions: PersonaSuggestion[];
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function getCallStatusLabel(callState: CallState, duration: number, error: string, ringtoneActive: boolean): string {
  if (callState === 'error') return error || 'Call failed';
  if (callState === 'connecting') return 'Connecting...';
  if (ringtoneActive) return 'Ringing...';
  if (callState === 'connected') return formatDuration(duration);
  return 'Ready to call';
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message || error.name;
  return String(error);
}

function logVoiceTimingEvent(event: string, detail: VoiceTimingDetail = {}): void {
  if (typeof window === 'undefined') return;
  void fetch(apiUrl('/api/voice/timing-log'), {
    ...API_FETCH_OPTIONS,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, ...detail }),
    keepalive: true,
  }).catch(() => {});
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M15 18 9 12l6-6" />
    </svg>
  );
}

function PhoneOffIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ transform: 'rotate(135deg)' }}>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 10.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <path d="M12 19v3" />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M9 9v3a3 3 0 0 0 5.1 2.1" />
      <path d="M15 9V6a3 3 0 0 0-5.1-2.1" />
      <path d="M17 16.9A7 7 0 0 1 5 12v-2" />
      <path d="M19 10v2c0 1-.2 1.9-.6 2.7" />
      <path d="M12 19v3" />
      <path d="M2 2 22 22" />
    </svg>
  );
}

export function AgentCallClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<AgentSessionPayload | null>(null);
  const [sessionError, setSessionError] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [hasEnteredCall, setHasEnteredCall] = useState(false);
  const [callState, setCallState] = useState<CallState>('idle');
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [agentPhase, setAgentPhase] = useState<AgentConversationPhase>('user');
  const [ringtoneActive, setRingtoneActive] = useState(false);
  const [personaDataOpen, setPersonaDataOpen] = useState(false);
  const [voiceAnalyser, setVoiceAnalyser] = useState<AnalyserNode | null>(null);

  const pipelineClientRef = useRef<VoicePipelineClient | null>(null);
  const callStartedAtRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const remoteAudioContextRef = useRef<AudioContext | null>(null);
  const remoteAudioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const remoteAudioFrameRef = useRef<number | null>(null);
  const ringtoneRef = useRef<HTMLAudioElement | null>(null);
  const callStateRef = useRef<CallState>('idle');
  const agentPhaseRef = useRef<AgentConversationPhase>('user');

  const setNextCallState = useCallback((state: CallState) => {
    callStateRef.current = state;
    setCallState(state);
  }, []);

  const setNextAgentPhase = useCallback((phase: AgentConversationPhase) => {
    if (agentPhaseRef.current === phase) return;
    agentPhaseRef.current = phase;
    setAgentPhase(phase);
  }, []);

  const playConnectingRingtone = useCallback(() => {
    if (typeof window === 'undefined') return;

    if (!ringtoneRef.current) {
      const ringtone = new Audio(CONNECTING_RINGTONE_SRC);
      ringtone.loop = true;
      ringtone.preload = 'auto';
      ringtoneRef.current = ringtone;
    }

    const ringtone = ringtoneRef.current;
    logVoiceTimingEvent('ringtone:play:request', {
      src: CONNECTING_RINGTONE_SRC,
      paused: ringtone.paused,
      readyState: ringtone.readyState,
    });
    void ringtone.play()
      .then(() => {
        logVoiceTimingEvent('ringtone:play:started', {
          src: CONNECTING_RINGTONE_SRC,
          readyState: ringtone.readyState,
        });
      })
      .catch((playError: unknown) => {
        logVoiceTimingEvent('ringtone:play:failed', {
          src: CONNECTING_RINGTONE_SRC,
          reason: describeError(playError),
          readyState: ringtone.readyState,
        });
      });
  }, []);

  const stopConnectingRingtone = useCallback((reason = 'manual') => {
    setRingtoneActive(false);
    const ringtone = ringtoneRef.current;
    if (!ringtone) return;
    ringtone.pause();
    ringtone.currentTime = 0;
    logVoiceTimingEvent('ringtone:stop', {
      reason,
      src: CONNECTING_RINGTONE_SRC,
      readyState: ringtone.readyState,
    });
  }, []);

  const stopRemoteAudioMonitor = useCallback(() => {
    if (remoteAudioFrameRef.current !== null) {
      window.cancelAnimationFrame(remoteAudioFrameRef.current);
      remoteAudioFrameRef.current = null;
    }
    void remoteAudioContextRef.current?.close().catch(() => {});
    remoteAudioContextRef.current = null;
    remoteAudioSourceRef.current = null;
  }, []);

  const endCall = useCallback(() => {
    stopConnectingRingtone('user_end_call');
    pipelineClientRef.current?.stop();
    pipelineClientRef.current = null;
    void audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    stopRemoteAudioMonitor();
    callStartedAtRef.current = null;
    setVoiceAnalyser(null);
    setIsListening(false);
    setNextAgentPhase('user');
    setDuration(0);
    setNextCallState('idle');
  }, [setNextAgentPhase, setNextCallState, stopConnectingRingtone, stopRemoteAudioMonitor]);

  useEffect(() => {
    const nextSessionId = searchParams.get('session_id') || searchParams.get('sessionId') || '';
    setSessionId(nextSessionId);
    if (!nextSessionId) {
      setSessionError('Missing session. Please start again from onboarding.');
      return;
    }

    const abort = new AbortController();
    setSessionError('');
    void fetch(apiUrl(`/api/agent/session?session_id=${encodeURIComponent(nextSessionId)}`), {
      ...API_FETCH_OPTIONS,
      cache: 'no-store',
      signal: abort.signal,
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data?.error || 'Could not load session');
        setSession(data as AgentSessionPayload);
      })
      .catch((loadError) => {
        if (abort.signal.aborted) return;
        setSessionError(loadError instanceof Error ? loadError.message : 'Could not load session');
      });

    return () => abort.abort();
  }, [searchParams]);

  useEffect(() => {
    if (callState !== 'connected') return;
    if (!callStartedAtRef.current) callStartedAtRef.current = Date.now();
    const timer = window.setInterval(() => {
      setDuration(Math.floor((Date.now() - (callStartedAtRef.current ?? Date.now())) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [callState]);

  useEffect(() => {
    pipelineClientRef.current?.setMuted(muted);
  }, [muted]);

  useEffect(() => {
    if (!ringtoneActive) return;
    playConnectingRingtone();
  }, [playConnectingRingtone, ringtoneActive]);

  useEffect(() => () => {
    stopConnectingRingtone('unmount');
    stopRemoteAudioMonitor();
    ringtoneRef.current = null;
  }, [stopConnectingRingtone, stopRemoteAudioMonitor]);

  useEffect(() => () => endCall(), [endCall]);

  const attachLocalAnalyser = useCallback(async (stream: MediaStream) => {
    await audioContextRef.current?.close().catch(() => {});
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    audioContextRef.current = context;
    setVoiceAnalyser(analyser);
    await context.resume();
  }, []);

  useEffect(() => {
    if (callState !== 'connected' || !voiceAnalyser) return;

    const data = new Uint8Array(voiceAnalyser.fftSize);
    let frameId: number | null = null;
    let heardUserSpeech = false;
    let silentFrames = 0;

    const sample = () => {
      if (callStateRef.current !== 'connected') return;

      voiceAnalyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const value of data) {
        peak = Math.max(peak, Math.abs(value - 128));
      }

      if (peak >= USER_VOICE_START_THRESHOLD) {
        heardUserSpeech = true;
        silentFrames = 0;
        setNextAgentPhase('user');
      } else if (heardUserSpeech && agentPhaseRef.current === 'user') {
        silentFrames += 1;
        if (silentFrames >= USER_VOICE_SILENCE_FRAMES) {
          heardUserSpeech = false;
          setAgentPhase('thinking');
          agentPhaseRef.current = 'thinking';
        }
      }

      frameId = window.requestAnimationFrame(sample);
    };

    frameId = window.requestAnimationFrame(sample);
    return () => {
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, [callState, setNextAgentPhase, voiceAnalyser]);

  const monitorRemoteStreamForRumikVoice = useCallback(async (stream: MediaStream) => {
    if (typeof window === 'undefined') return;

    try {
      stopRemoteAudioMonitor();
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      let activeFrames = 0;
      let hasDetectedSpeech = false;

      analyser.fftSize = 1024;
      const data = new Uint8Array(analyser.fftSize);
      source.connect(analyser);
      remoteAudioContextRef.current = context;
      remoteAudioSourceRef.current = source;
      logVoiceTimingEvent('remote_audio:voice_monitor_started', {
        threshold: RUMIK_VOICE_START_THRESHOLD,
        requiredFrames: RUMIK_VOICE_START_FRAMES,
      });
      await context.resume();

      const sample = () => {
        if (remoteAudioContextRef.current !== context) return;

        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const value of data) {
          peak = Math.max(peak, Math.abs(value - 128));
        }

        activeFrames = peak >= RUMIK_VOICE_START_THRESHOLD ? activeFrames + 1 : 0;
        if (activeFrames >= RUMIK_VOICE_START_FRAMES) {
          if (!hasDetectedSpeech) {
            logVoiceTimingEvent('remote_audio:voice_detected', { peak, activeFrames });
            stopConnectingRingtone('rumik_voice_started');
          }
          hasDetectedSpeech = true;
          setAgentPhase('agent');
          agentPhaseRef.current = 'agent';
        }

        remoteAudioFrameRef.current = window.requestAnimationFrame(sample);
      };

      remoteAudioFrameRef.current = window.requestAnimationFrame(sample);
    } catch (monitorError) {
      logVoiceTimingEvent('remote_audio:voice_monitor_failed', {
        reason: describeError(monitorError),
      });
    }
  }, [stopConnectingRingtone, stopRemoteAudioMonitor]);

  const startCall = useCallback(async () => {
    if (!session || !sessionId || pipelineClientRef.current) return;
    setError('');
    setIsListening(false);
    setRingtoneActive(true);
    playConnectingRingtone();
    setNextCallState('connecting');

    const callId = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    const client = new VoicePipelineClient({
      sessionId,
      callId,
      onState: (state) => {
        if (pipelineClientRef.current !== client) return;
        if (state === 'connected') {
          callStartedAtRef.current = Date.now();
          setIsListening(true);
          setNextAgentPhase('user');
          setNextCallState('connected');
        }
        if (state === 'closed' && callStateRef.current !== 'idle') {
          setIsListening(false);
          stopConnectingRingtone('pipeline_closed');
          setNextAgentPhase('user');
          setNextCallState('idle');
        }
        if (state === 'error') {
          setIsListening(false);
          stopConnectingRingtone('pipeline_error');
          setNextAgentPhase('user');
          setNextCallState('error');
        }
      },
      onLocalStream: (stream) => {
        if (pipelineClientRef.current !== client) return;
        void attachLocalAnalyser(stream);
      },
      onRemoteStream: (stream) => {
        if (pipelineClientRef.current !== client) return;
        void monitorRemoteStreamForRumikVoice(stream);
      },
      onError: (pipelineError) => {
        if (pipelineClientRef.current !== client) return;
        setError(pipelineError.message || 'Pipecat voice pipeline failed');
      },
      onRemoteAudioStarted: () => {
        if (pipelineClientRef.current !== client) return;
        logVoiceTimingEvent('pipeline:remote_audio:element_started');
        stopConnectingRingtone('remote_audio_playback_started');
      },
      onDiagnostic: (event, detail) => {
        if (pipelineClientRef.current !== client) return;
        logVoiceTimingEvent(`pipeline:${event}`, detail as VoiceTimingDetail);
      },
    });

    pipelineClientRef.current = client;
    try {
      await client.start();
    } catch (startError) {
      if (pipelineClientRef.current !== client) {
        client.stop();
        return;
      }

      client.stop();
      pipelineClientRef.current = null;
      setError(startError instanceof Error ? startError.message : 'Could not start Pipecat call');
      setIsListening(false);
      stopConnectingRingtone('start_error');
      setNextCallState('error');
    }
  }, [
    attachLocalAnalyser,
    monitorRemoteStreamForRumikVoice,
    playConnectingRingtone,
    session,
    sessionId,
    setNextAgentPhase,
    setNextCallState,
    stopConnectingRingtone,
  ]);

  const enterCall = useCallback(async () => {
    setHasEnteredCall(true);
    await startCall();
  }, [startCall]);

  const handleBack = useCallback(() => {
    if (hasEnteredCall) {
      endCall();
      setHasEnteredCall(false);
      return;
    }

    if (typeof window !== 'undefined' && window.history.length > 1) {
      window.history.back();
      return;
    }

    router.push('/onboarding');
  }, [endCall, hasEnteredCall, router]);

  const visualizerSpeaker = useMemo<AgentVisualizerSpeaker>(() => {
    if (callState === 'connected' && agentPhase === 'agent') return 'agent';
    if (callState === 'connected' && isListening) return 'user';
    return 'neutral';
  }, [agentPhase, callState, isListening]);
  const visualizerAnalyser = callState === 'connected' && agentPhase !== 'agent' ? voiceAnalyser : null;
  const voiceOrbState = callState === 'connected' ? agentPhase : callState;

  if (sessionError) {
    return (
      <main className="agent-page">
        <div className="agent-error-panel">{sessionError}</div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="agent-page">
        <div className="agent-loader-container" role="status" aria-live="polite">
          <div className="agent-spinner" />
          <p className="agent-loader-caption">Loading session...</p>
        </div>
      </main>
    );
  }

  if (!hasEnteredCall) {
    return (
      <main className="agent-page agent-page--precall">
        <section className="agent-precall" aria-label="Stable Money Support introduction">
          <header className="agent-precall__header">
            <button type="button" className="agent-icon-btn" onClick={handleBack} aria-label="Go back">
              <BackIcon />
            </button>
            <p className="agent-precall__eyebrow" style={{ margin: 0 }}>Stable Money Support</p>
          </header>

          <div className="agent-precall__hero">
            <div className="agent-precall__intro">
              <p className="agent-precall__kicker">Account support assistant</p>
              <h2>Talk through fixed deposits, payments, KYC, and account.</h2>
              <p>
                Review the active demo customer below, then start a focused support call with the same voice flow and
                verification behavior.
              </p>
              <button type="button" className="agent-precall__call" onClick={() => void enterCall()}>
                Call Stable Money Support
              </button>
            </div>

            <div className="agent-precall__capabilities" aria-label="Support capabilities">
              <article>
                <span>FD</span>
                <h3>Fixed deposits</h3>
                <p>Status, bookings, maturity, interest, and next steps.</p>
              </article>
              <article>
                <span>PAY</span>
                <h3>Payments</h3>
                <p>Payment status, refunds, failed transfers, and timelines.</p>
              </article>
              <article>
                <span>KYC</span>
                <h3>Verification</h3>
                <p>Mobile and DOB verification before sensitive account help.</p>
              </article>
              <article>
                <span>ACC</span>
                <h3>Account profile</h3>
                <p>Nominee, customer profile, and support context.</p>
              </article>
            </div>
          </div>

          <section className="agent-precall__details" aria-label="Demo customer details">
            <div className="agent-precall__details-heading">
              <p className="agent-precall__eyebrow">Calling as</p>
              <h2>{session.brief.name}</h2>
              <p>{session.brief.customerId}</p>
            </div>
            <div className="agent-precall__detail-grid">
              {buildPersonaDetailSections(session.persona).map((section) => (
                <section key={section.id} className="agent-precall-detail">
                  <h3>{section.title}</h3>
                  <div className="agent-precall-detail__table-wrap">
                    <table className="agent-precall-detail__table">
                      <thead>
                        <tr>
                          {section.columns.map((column) => (
                            <th key={column} scope="col">{column}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.rows.map((row) => (
                          <tr key={row.id}>
                            {row.cells.map((cell, index) => (
                              <td key={`${row.id}-${section.columns[index]}`}>{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ))}
            </div>
          </section>
        </section>
      </main>
    );
  }

  return (
    <main className="agent-page agent-page--call">
      <section className="voice-stage" aria-label="Voice call">
        <header className="voice-stage__header">
          <button type="button" className="agent-icon-btn" onClick={handleBack} aria-label="Go back">
            <BackIcon />
          </button>
          <button type="button" className="agent-data-btn" onClick={() => setPersonaDataOpen(true)}>
            See data
          </button>
        </header>

        <div className="voice-call-stack">
          <div className={`voice-orb voice-orb--${voiceOrbState}`} aria-label="Stable Money Support call">
            <div className="voice-orb__inner">
              <span className="voice-orb__caller">Stable Money Support</span>
            </div>
          </div>

          <div className="voice-call-title">
            <p className="voice-call-title__status" aria-live="polite">
              {getCallStatusLabel(callState, duration, error, ringtoneActive)}
            </p>
          </div>

          <div className="voice-call-visual-panel">
            <AgentAudioVisualizerBar
              size="lg"
              speaker={visualizerSpeaker}
              analyser={visualizerAnalyser}
            />
          </div>

          <div className="voice-call-actions">
            {callState === 'idle' || callState === 'error' ? (
              <button type="button" className="call-primary voice-call-actions__primary" onClick={() => void startCall()}>
                Call Stable Money Support
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className={muted ? 'voice-call-round-btn voice-call-round-btn--mic-muted' : 'voice-call-round-btn voice-call-round-btn--mic'}
                  onClick={() => setMuted((value) => !value)}
                  aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
                >
                  {muted ? <MicOffIcon /> : <MicIcon />}
                </button>
                <button type="button" className="voice-call-round-btn voice-call-round-btn--cut" onClick={endCall} aria-label="End call">
                  <PhoneOffIcon />
                </button>
              </>
            )}
          </div>
        </div>
      </section>
      <PersonaDetailModal persona={personaDataOpen ? session.persona : null} onClose={() => setPersonaDataOpen(false)} />
    </main>
  );
}
