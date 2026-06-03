# Classifier Token Ramp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ramp the intent classifier output-token budget by call turn instead of starting every request at 1024 tokens.

**Architecture:** Keep the logic inside `backend/app/agent/intent_classifier_ai.py` because request body construction already lives there. Compute the turn from previous user messages plus the current transcript, use 32-token increments for turns 1-4, then 128-token increments after that, capped at the existing 1024 ceiling.

**Tech Stack:** Python, `unittest`, mocked Responses API request capture.

---

### Task 1: Add Classifier Token Ramp

**Files:**
- Modify: `backend/tests/test_intent_classifier_ai.py`
- Modify: `backend/app/agent/intent_classifier_ai.py`

- [ ] **Step 1: Write the failing test**

Add a test that captures classifier request bodies for histories with increasing previous user-turn counts. Assert `max_output_tokens` follows `32, 64, 96, 128, 256, 384, 512, 640, 768, 896, 1024, 1024`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_intent_classifier_ai.py -q`
Expected: FAIL because the classifier still sends `1024` for every request.

- [ ] **Step 3: Write minimal implementation**

Add constants and a small helper in `intent_classifier_ai.py`. Count only history items where `role == "user"`, add one for the current transcript, then compute the budget.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_intent_classifier_ai.py -q`
Expected: PASS.

- [ ] **Step 5: Run focused backend tests**

Run: `python -m pytest backend/tests/test_intent_classifier_ai.py backend/tests/test_pipecat_llm_brain.py -q`
Expected: PASS.
