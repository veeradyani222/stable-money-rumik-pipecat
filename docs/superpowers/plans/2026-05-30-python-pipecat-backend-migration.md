# Python + Pipecat Backend Migration Plan

## Recommendation

Use a staged migration:

1. Port the backend contracts to Python without changing the call UI.
2. Introduce Pipecat as a parallel voice pipeline behind a feature flag.
3. Move business logic from TypeScript to Python after the media path works.
4. Remove legacy browser voice code only after parity is verified.

Default transport choice: direct Pipecat WebRTC for MVP, LiveKit for the final production-grade transport.

## Step 1: Freeze Current Contracts

- Capture endpoint contracts for onboarding, agent, voice, and timing APIs.
- Add or mirror tests for:
  - session/cookie mismatch behavior
  - persona selection persistence
  - call verification persistence
  - mobile-step and pending-route DOB retries
  - support ticket mutation
  - secure link mutation
  - Rumik text normalization
  - SSE event framing
- Keep Next.js as the active runtime.

Acceptance:

- Existing `npm test` still passes.
- Python contract test fixtures exist before route migration starts.

## Step 2: Scaffold Python FastAPI Backend

- Add `python_backend/` with FastAPI app, config, DB pool, schemas, and test setup.
- Use the existing Postgres schema.
- Implement health and timing-log endpoints first.
- Add environment variables matching current names where possible.

Acceptance:

- Python app starts locally.
- DB connection lifecycle works.
- Basic tests run without live OpenAI/Rumik calls.

## Step 3: Port Session, Onboarding, Persona APIs

- Port:
  - `POST /api/onboarding/init`
  - `POST /api/onboarding/select-persona`
  - `GET /api/agent/session`
- Preserve cookie name and flags.
- Preserve existing persona row merge behavior.
- Preserve verification reset on persona selection.

Acceptance:

- React onboarding can run against Python via proxy or route switch.
- Existing onboarding/persona tests have Python equivalents.

## Step 4: Port Stable Money Domain Layer

- Port persona seeds and DB row conversion.
- Port stable policies and deterministic intent routing.
- Port stable tools.
- Port support tickets and secure links.
- Port session-auth verification stores with DB fallback behavior.
- Port Rumik text normalization and chunking.

Acceptance:

- Python tool tests match TypeScript behavior.
- Verification flow parity is demonstrated for mobile match, DOB failure, DOB success, pending tool execution, and full verification persistence.

## Step 5: Port Agent Respond APIs

- Implement non-streaming `/api/agent/respond`.
- Implement `/api/agent/respond-stream` with the same SSE events.
- Port OpenAI Responses streaming and tool loop, including pre-exec fast path where practical.
- Keep tool allow-list enforcement code-owned.

Acceptance:

- Current React voice client can talk to Python respond-stream without UI changes.
- SSE parser tests pass against Python output.

## Step 6: Build Pipecat Voice MVP

- Add Python call/session endpoint for Pipecat.
- Implement `CallContext`.
- Implement Pipecat pipeline:
  - WebRTC transport input/output
  - VAD/turn detection
  - STT
  - Stable Money agent processor
  - custom Rumik TTS
  - event emitter to browser
- Initially, if faster, Pipecat may call the existing respond-stream endpoint server-side and convert text deltas into Rumik audio.

Acceptance:

- A demo call can be started from a separate test page or feature flag.
- User speech becomes transcript.
- Assistant response is spoken through Rumik from the Python server.
- Interruption cancels stale assistant speech.

## Step 7: Add Frontend Voice Adapter

- Add `VoicePipelineClient` abstraction.
- Keep existing `AgentCallClient` rendering and state names.
- Implement Pipecat WebRTC client behind a feature flag.
- Map Pipecat events to:
  - call state
  - visualizer speaker
  - transcripts
  - verification state
  - terminal goodbye end-call behavior
  - errors
- Keep legacy browser pipeline as fallback until parity is stable.

Acceptance:

- Pre-call and call UI look unchanged.
- Mute/unmute and hangup work.
- No duplicate browser STT/Rumik paths run when Pipecat mode is enabled.

## Step 8: Move Opening, Barge-In, and Fallbacks Server-Side

- Serve the opening greeting through Pipecat/Rumik.
- Remove static-opening echo/barge-in special handling from Pipecat mode.
- Recreate first-audio timeout and fallback behavior in Python.
- Preserve terminal goodbye after response audio completes.

Acceptance:

- Opening audio sounds consistent.
- User can interrupt opening/assistant speech without duplicate stale responses.
- Goodbye ends only after speech finishes.

## Step 9: Retire Legacy Voice Paths

After Pipecat mode is stable:

- Remove browser OpenAI Realtime STT from active call path.
- Remove browser MediaRecorder transcription fallback from active call path.
- Remove browser Rumik websocket playback from active call path.
- Keep or remove old Next endpoints based on deployment needs.

Acceptance:

- Call pipeline is Pipecat-owned end to end.
- Browser only owns UI, mic publication, remote audio playback, and event rendering.

## Step 10: Production Hardening

- Decide final transport:
  - stay direct WebRTC for demo/local
  - move to LiveKit for production reliability
- Add provider timeouts and per-turn budgets.
- Add rate limits to expensive endpoints.
- Add structured timing logs across STT, LLM, tools, TTS, and transport.
- Add deployment docs for running Next frontend and Python backend together.

Acceptance:

- One documented command or compose setup runs frontend + Python backend.
- Voice pipeline has useful latency diagnostics.
- Legacy endpoints are clearly marked or removed.

