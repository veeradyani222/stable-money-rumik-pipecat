# Rumik Warm Opening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prefetch Rumik opening audio and keep the ringing sound active until the opening line audibly starts.

**Architecture:** Add a call-scoped Rumik TTS cache that prewarms the opening utterance in the Pipecat bot before the client-connected event queues `TTSSpeakFrame`. The frontend's remote-audio voice detector remains the source of truth for stopping ringtone playback.

**Tech Stack:** Python FastAPI/Pipecat backend, Rumik websocket TTS, Next.js/TypeScript frontend tests.

---

### Task 1: Backend Rumik Opening Prefetch

**Files:**
- Modify: `backend/app/pipecat_pipeline/rumik_tts.py`
- Modify: `backend/app/pipecat_pipeline/bot.py`
- Test: `backend/tests/test_rumik_tts_prefetch.py`

- [ ] Write failing backend tests for prewarm replay and fallback.
- [ ] Run `python -m pytest backend/tests/test_rumik_tts_prefetch.py -q` and confirm failure.
- [ ] Add `prewarm(text)` and a one-shot cache in `RumikTTSService`.
- [ ] Start `tts.prewarm(STABLE_DEFAULT_OPENING)` when the bot starts, before `on_client_connected` queues the opening frame.
- [ ] Run the backend test and confirm it passes.

### Task 2: Frontend Ringing Regression

**Files:**
- Modify: `frontend/tests/agent-call-ringing.test.ts`
- Verify: `frontend/components/agent/AgentCallClient.tsx`

- [ ] Add source-level assertions that connected/audio-element-start handlers do not stop ringing.
- [ ] Run `npm test -- tests/agent-call-ringing.test.ts` from `frontend/` and confirm the test fails if the guard is missing.
- [ ] Keep or adjust `AgentCallClient.tsx` so only `remote_audio:voice_detected` calls `stopConnectingRingtone('rumik_voice_started')`.
- [ ] Run the frontend test and confirm it passes.

### Task 3: Verification

**Files:**
- Verify: `backend/app/pipecat_pipeline/rumik_tts.py`
- Verify: `backend/app/pipecat_pipeline/bot.py`
- Verify: `frontend/components/agent/AgentCallClient.tsx`

- [ ] Run focused backend tests.
- [ ] Run focused frontend tests.
- [ ] Review `git diff` to ensure only scoped changes were made.
