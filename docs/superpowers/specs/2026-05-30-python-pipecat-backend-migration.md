# Python + Pipecat Backend Migration Spec

## Goal

Migrate the Stable Money Rumik demo from a Next.js-owned backend and browser-owned voice pipeline to a Python backend using Pipecat for the complete live voice call pipeline, while preserving the current user experience and business behavior.

The frontend should continue to feel like the same Stable Money support call: onboarding, persona selection, pre-call screen, call controls, verification flow, tools, secure links, support tickets, Rumik voice style, interruption behavior, and terminal goodbye handling.

## Current System

The app is currently a Next.js/React frontend plus Next.js route handlers.

Current call path:

```text
Browser mic
  -> OpenAI Realtime STT directly from browser
  -> POST /api/agent/respond-stream SSE
  -> OpenAI Responses agent/tool loop in lib/agent/openai-agent.ts
  -> Rumik TTS WebSocket from browser
  -> Browser PCM scheduling/playback
```

The browser currently owns mic capture, VAD fallback, OpenAI Realtime transcription, agent turn orchestration, Rumik TTS websocket playback, interruption/barging, static opening audio, timing beacons, and visualizer state.

The backend currently owns onboarding, session cookies, persona persistence, intent policy, OpenAI agent/tool orchestration, verification persistence, support tickets, secure links, Rumik session minting, and fallback transcription.

## Target Architecture

Target call path:

```text
Browser call UI
  -> WebRTC transport
  -> Python FastAPI + Pipecat bot
  -> Pipecat VAD / turn detection
  -> Pipecat STT service
  -> Stable Money agent/tool layer
  -> custom Rumik Pipecat TTS service
  -> WebRTC audio back to browser
```

Recommended transport:

- MVP: Pipecat direct WebRTC / SmallWebRTC where practical.
- Production-ready final state: Pipecat LiveKit transport.
- Avoid raw browser WebSocket audio as the primary call transport unless WebRTC is blocked; it would require custom jitter buffering, audio packetization, playback timing, backpressure, and interruption handling.

The browser should become a thin call UI:

- start/stop call
- publish mic audio
- mute/unmute
- play remote audio
- render pipeline state events
- keep persona/pre-call UI unchanged

Python/Pipecat should own:

- STT
- VAD and turn-taking
- interruption/barge-in
- assistant speech state
- TTS chunking and Rumik websocket credentials
- call transcript events
- tool/debug/verification events
- opening greeting through the same audio pipeline

## Compatibility Contract

The migration must preserve the current API semantics until each consumer is migrated.

Existing important endpoints:

- `POST /api/onboarding/init`
- `POST /api/onboarding/select-persona`
- `GET /api/agent/session`
- `POST /api/agent/respond`
- `POST /api/agent/respond-stream`
- `POST /api/voice/openai-realtime-token`
- `POST /api/voice/openai-transcribe`
- `POST /api/voice/rumik-session`
- `POST /api/voice/timing-log`

`/api/agent/respond-stream` SSE event names and framing are compatibility-sensitive:

- `ready`
- `delta`
- `route`
- `policy`
- `timing`
- `stream`
- `tool`
- `done`
- `error`
- `close`

Session behavior must remain exact:

- session id may come from request body/query or `demo_session` cookie.
- if explicit session id and cookie both exist and differ, return `403`.
- missing/short session id returns `400`.
- call verification is keyed by `(session_id, call_id)`.
- missing `call_id` falls back to `legacy`.
- mobile-last-four intermediate verification and `pending_route` persist across DOB retries.
- full verification clears the intermediate mobile/pending route state.

## Business Invariants

The Python implementation must preserve the Stable Money policy layer, not merely imitate prompt output.

Auth tiers:

- Tier A: public/safe facts; no verification.
- Tier B: account reads require `verify_read_access`.
- Tier C: sensitive actions are not executed by voice; send secure link or create ticket.
- A/B ticket/grievance behavior must remain available without accidental account data reads.

Tool names must remain stable:

- `verify_read_access`
- `lookup_customer_profile`
- `get_trust_facts`
- `get_canonical_slas`
- `get_disclosure_copy`
- `get_fd_booking_status`
- `get_payment_reconciliation_status`
- `get_kyc_status`
- `get_premature_withdrawal_quote`
- `get_support_ticket_status`
- `get_payment_summary`
- `get_fd_summary`
- `get_refund_status`
- `get_fd_rates`
- `create_support_ticket`
- `send_secure_link`
- `get_support_contact`

Verification flow:

- Ask only for registered mobile last four first.
- Do not ask for DOB in the same turn as the mobile request.
- After mobile match, persist the mobile gate and pending route.
- In DOB phase, treat the latest caller turn as the DOB answer.
- After full verification, force the pending account tool when applicable.
- Never ask for OTP, full Aadhaar, CVV, PIN, bank password, or full mobile number.

Voice output:

- short natural Hinglish, Roman script.
- Rumik-safe text with leading tone tag.
- avoid digits and unsafe punctuation in speakable output.
- keep Rumik normalization behavior available in Python.
- browser should not receive Rumik websocket URL/token in the final Pipecat path.

Side effects:

- support ticket and secure link email dispatch remains fire-and-forget.
- email failures must not fail the spoken tool result.
- support ticket creation mutates `demo_users.open_tickets`.
- secure link sending mutates matching `demo_users.secure_links`.

## Python Service Boundaries

Recommended FastAPI layout:

```text
python_backend/
  app/
    main.py
    core/config.py
    api/onboarding.py
    api/agent.py
    api/voice.py
    api/pipecat_sessions.py
    db/pool.py
    models/schemas.py
    domain/personas.py
    domain/session_auth.py
    domain/policies.py
    domain/tools.py
    domain/agent.py
    domain/support_tickets.py
    domain/secure_links.py
    services/openai_stt.py
    services/openai_realtime.py
    services/rumik.py
    services/email.py
    pipecat/bot.py
    pipecat/call_context.py
    pipecat/rumik_tts.py
    pipecat/events.py
    sse.py
```

Use `asyncpg` or SQLAlchemy async for Postgres. Keep schema compatible with `migrations/001_demo_users.sql`.

## Pipecat Pipeline Design

Each call creates a `CallContext`:

```text
session_id
call_id
persona
history
call_verified
verified_mobile_last_4
pending_route
db/session accessors
tool handlers
event sink to browser
```

Pipeline:

```text
transport.input()
  -> VAD / turn detector
  -> STT
  -> transcript normalizer
  -> Stable Money agent processor
  -> Rumik text normalizer / chunker
  -> custom Rumik TTS service
  -> transport.output()
```

Event channel to browser should be transport data channel or companion WebSocket/SSE:

```ts
type VoicePipelineEvent =
  | { type: 'state'; state: 'calling' | 'connecting' | 'connected' | 'thinking' | 'speaking' | 'error' }
  | { type: 'user_speech_start' | 'user_speech_stop' }
  | { type: 'assistant_speech_start' | 'assistant_speech_stop' }
  | { type: 'transcript'; role: 'user' | 'agent' | 'system'; text: string }
  | { type: 'interim'; text: string }
  | { type: 'verification'; status: 'none' | 'checking' | 'mobile_matched' | 'mobile_failed' | 'dob_failed' | 'verified' }
  | { type: 'policy'; endCallAfterResponse?: boolean }
  | { type: 'tool'; tool: string; phase: 'start' | 'result'; ok?: boolean }
  | { type: 'timing'; event: string; elapsedMs?: number; details?: Record<string, unknown> }
  | { type: 'error'; message: string }
  | { type: 'ended' };
```

## Rumik TTS Integration

Implement a custom Pipecat TTS service if no official Rumik service exists.

Current Rumik protocol:

1. POST `${RUMIK_BASE_URL}/v1/tts/ws-connect` with `{ text, model }`.
2. Receive `ws_url` and `token`.
3. Connect to Rumik websocket using token.
4. Send `{ text, speaker_id }`.
5. Receive binary PCM chunks.
6. Stop on text message `{ type: "done" }`.

The existing browser playback treats output as PCM16 mono at 24 kHz. Confirm this against Rumik docs/API before finalizing the Pipecat audio frame format.

The custom TTS service must preserve:

- `normalizeRumikText`
- leading silence trimming or equivalent
- first-audio timeout/fallback behavior
- interruption cancellation
- rate-limit fallback audio or spoken fallback
- chunking that starts audio early without freezing on short chunks

## Incremental Rollout

Phase 0: contract freeze

- Add Python migration contract tests mirroring current Node tests for sessions, tools, verification, Rumik normalization, SSE framing, support tickets, secure links.
- Keep Next.js behavior untouched.

Phase 1: Python compatibility backend

- Implement FastAPI endpoints equivalent to the existing Next route handlers.
- Point only selected routes or dev proxy traffic at Python.
- Keep frontend and browser voice pipeline unchanged.
- Pass contract tests before moving media.

Phase 2: Pipecat media MVP

- Add `/api/voice/pipecat-session` or equivalent session-minting endpoint.
- Add frontend `VoicePipelineClient` adapter.
- Keep `AgentCallClient` UI and state rendering.
- Move STT, VAD, turn-taking, interruption, Rumik TTS, and opening greeting into Pipecat.
- For the first media MVP, Pipecat may call the existing `/api/agent/respond-stream` server-side to reuse the TypeScript agent brain.

Phase 3: native Python agent/tools

- Port `stable-policy.ts`, `stable-tools.ts`, `openai-agent.ts`, verification AI helpers, support tickets, secure links, and Rumik text helpers to Python.
- Pipecat calls the Python domain layer directly.
- Retire server-side dependency on Next agent routes.

Phase 4: frontend simplification

- Remove browser OpenAI Realtime token path from call flow.
- Remove MediaRecorder fallback transcription from call flow.
- Remove browser Rumik websocket playback from call flow.
- Remove static opening echo heuristics after opening is served by Pipecat.
- Keep local analyser only if needed for visualizer polish; otherwise consume pipeline volume/speech events.

Phase 5: production transport hardening

- Decide between direct WebRTC and LiveKit.
- Add reconnect/error handling, TURN/SFU config, observability, per-call budgets, provider timeouts, and rate limits.
- Remove legacy Next voice endpoints once no longer used.

## Blocking Scope Question

The main blocking scope decision before implementation is transport: should the MVP use direct Pipecat WebRTC for fastest local migration, or should it go straight to LiveKit because production-like call reliability matters more than migration speed?

Default recommendation: direct Pipecat WebRTC for MVP, LiveKit after the behavior is proven.

## Risks

- losing current barge-in quality when moving interruption from browser to Pipecat.
- duplicate turns if browser STT/VAD and Pipecat STT/VAD are both active during rollout.
- verification drift between Next and Python stores.
- reclassifying DOB turns instead of preserving `pending_route`.
- exposing Rumik credentials or websocket URLs to the browser after migration.
- breaking SSE or route compatibility while the frontend still depends on it.
- Python schemas becoming stricter than existing JSONB fixture/DB behavior.
- mobile Safari WebRTC/autoplay/mic-permission regressions.
- worse latency if Pipecat waits for full LLM response before starting Rumik TTS.
- losing fire-and-forget semantics for ticket/link emails.

