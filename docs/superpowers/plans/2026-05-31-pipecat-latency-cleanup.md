# Pipecat Latency Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete HTTP/SSE voice path, reduce WebRTC startup latency, and make the live Pipecat voice pipeline explicitly observable, interrupt-aware, and Flow-ready.

**Architecture:** Keep the live path centered on `SmallWebRTCTransport` and the backend Pipecat worker. The browser sends offers immediately and trickles ICE candidates after `pc_id` is known. Pipecat uses local Silero VAD, explicit Smart Turn strategies, input muting for opening/tool calls, and terminal-visible observers. Pipecat Flows is introduced as a dependency plus a verification-flow boundary module, without replacing the support router in this pass.

**Tech Stack:** Next.js/TypeScript WebRTC client, FastAPI backend, Pipecat 1.3.0, pipecat-ai-flows 1.2.x, OpenAI STT/Responses, Rumik TTS.

---

### Task 1: Remove Legacy HTTP Voice Surface

**Files:**
- Delete: `README.md`
- Delete: `backend/app/domain/agent.py`
- Delete: `backend/app/sse.py`
- Delete: `backend/tests/test_agent_logging.py`
- Modify: `backend/app/api/agent.py`
- Modify: `backend/app/api/voice.py`
- Modify: `backend/app/api/pipecat_sessions.py`
- Test: backend pytest collection and focused remaining API tests

- [ ] Remove `/api/agent/respond`, `/api/agent/respond-stream`, and `_load_turn_context`.
- [ ] Keep only `GET /api/agent/session` in `backend/app/api/agent.py`.
- [ ] Remove `/api/voice/rumik-session`, `/api/voice/openai-realtime-token`, and `/api/voice/openai-transcribe`.
- [ ] Keep only `POST /api/voice/timing-log`.
- [ ] Remove unused `/api/voice/pipecat-session`.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest tests/test_voice_timing_log.py tests/test_pipecat_llm_brain.py -q`.

### Task 2: Frontend WebRTC Startup Latency

**Files:**
- Modify: `frontend/lib/voice/pipeline-client.ts`
- Modify: `frontend/tests/voice-pipeline-client-stop.test.ts`
- Create: `frontend/tests/voice-pipeline-client.test.ts`

- [ ] Write tests proving TURN config and microphone acquisition start concurrently.
- [ ] Write tests proving ICE candidates are queued until `/offer` returns `pc_id` and then PATCHed as snake_case.
- [ ] Write tests proving setup diagnostics include numeric `elapsed_ms`.
- [ ] Write tests proving tracks are stopped if `stop()` happens during pending setup.
- [ ] Replace `waitForIceGathering()` with trickle ICE and immediate offer POST.
- [ ] Run `npm test -- voice-pipeline-client`.

### Task 3: Pipecat VAD, Turn Strategies, Muting, And Terminal Observability

**Files:**
- Modify: `backend/app/pipecat_pipeline/bot.py`
- Modify: `backend/tests/test_pipecat_pipeline_order.py`

- [ ] Write source-shape tests for `turn_detection=False`, `LLMUserAggregatorParams`, `SileroVADAnalyzer`, explicit turn strategies, muting strategies, and observers passed to `PipelineWorker`.
- [ ] Wire local Silero VAD and explicit Smart Turn user strategies.
- [ ] Add `MuteUntilFirstBotCompleteUserMuteStrategy()` and `FunctionCallUserMuteStrategy()`.
- [ ] Attach `MetricsLogObserver`, `UserBotLatencyObserver`, and `StartupTimingObserver`.
- [ ] Log observer events through `_log_voice_event()` so they print in the terminal via existing app logging.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest tests/test_pipecat_pipeline_order.py -q`.

### Task 4: Pipecat Flows Verification Boundary

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/pipecat_pipeline/verification_flow.py`
- Create: `backend/tests/test_verification_flow.py`

- [ ] Add `pipecat-ai-flows>=1.2,<2` to backend dependencies.
- [ ] Add a small adapter module that imports `FlowManager` lazily and exposes the verification-only boundary.
- [ ] Keep routing ownership in `llm_brain.py`; do not migrate the whole support router yet.
- [ ] Test that Flow imports are lazy and that the module advertises the `support -> verify.mobile -> verify.dob -> support` boundary.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest tests/test_verification_flow.py -q`.

### Task 5: Final Verification

- [ ] Run backend focused tests: `backend\.venv\Scripts\python.exe -m pytest tests/test_voice_timing_log.py tests/test_pipecat_llm_brain.py tests/test_pipecat_pipeline_order.py tests/test_rumik_tts_prefetch.py tests/test_verification_flow.py -q`
- [ ] Run frontend focused tests: `npm test -- voice-pipeline-client`
- [ ] Run full backend tests if focused tests are clean: `backend\.venv\Scripts\python.exe -m pytest -q`
- [ ] Run full frontend tests if focused tests are clean: `npm test`
