# Frontend Backend Folder Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the existing project into `frontend/` and `backend/` folders inside one Git repository while preserving runtime behavior.

**Architecture:** The repo root becomes an orchestration layer. The frontend folder owns the Next.js application and TypeScript test suite. The backend folder owns the FastAPI application, Python configuration, and SQL migrations.

**Tech Stack:** Next.js 15, React 19, TypeScript, Node test runner, FastAPI, asyncpg, PostgreSQL.

---

### Task 1: Move Frontend-Owned Files

**Files:**
- Move: `app/` to `frontend/app/`
- Move: `components/` to `frontend/components/`
- Move: `lib/` to `frontend/lib/`
- Move: `public/` to `frontend/public/`
- Move: `styles/` to `frontend/styles/`
- Move: `assets/` to `frontend/assets/`
- Move: `tests/` to `frontend/tests/`
- Move: `package-lock.json` to `frontend/package-lock.json`
- Move: `tsconfig.json` to `frontend/tsconfig.json`
- Move: `next.config.ts` to `frontend/next.config.ts`
- Move: `next-env.d.ts` to `frontend/next-env.d.ts`

- [ ] **Step 1: Create `frontend/` if needed**

Run: `New-Item -ItemType Directory -Force frontend`

- [ ] **Step 2: Move frontend directories and files**

Run explicit `Move-Item` commands for each path so unrelated root files are not moved.

- [ ] **Step 3: Keep TypeScript alias unchanged**

In `frontend/tsconfig.json`, keep:

```json
"paths": { "@/*": ["./*"] }
```

This preserves every current `@/...` import because `frontend/` becomes the TypeScript project root.

### Task 2: Move Backend-Owned Files

**Files:**
- Move: `python_backend/` to `backend/`
- Move: `migrations/` to `backend/migrations/`

- [ ] **Step 1: Rename `python_backend/`**

Run: `Move-Item python_backend backend`

- [ ] **Step 2: Move SQL migrations**

Run: `Move-Item migrations backend/migrations`

### Task 3: Split Environment Examples

**Files:**
- Create: `frontend/.env.example`
- Create: `backend/.env.example`
- Modify: `.env.example`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add frontend env example**

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

- [ ] **Step 2: Add backend env example**

```dotenv
DATABASE_URL=
OPENAI_API_KEY=
OPENAI_AGENT_MODEL=gpt-4o-mini
OPENAI_INTENT_MODEL=
OPENAI_STT_MODEL=gpt-4o-mini-transcribe
OPENAI_REALTIME_TRANSCRIBE_MODEL=
RUMIK_API_KEY=
RUMIK_BASE_URL=https://silk-api.rumik.ai
RUMIK_TTS_MODEL=muga
APP_BASE_URL=http://localhost:3000
PYTHON_BACKEND_CORS_ORIGIN=http://localhost:3000
GMAIL_USER=
GMAIL_APP_PASSWORD=
GMAIL_FROM_NAME=Stable Assist
DEBUG_LOG_ALL=
```

- [ ] **Step 3: Preserve root env compatibility**

Update `backend/app/core/config.py` so it loads `backend/.env.local`, `backend/.env`, root `.env.local`, then root `.env`.

### Task 4: Update Root Orchestration

**Files:**
- Modify: `package.json`
- Modify: `scripts/migrate.cjs`
- Modify: `.gitignore`

- [ ] **Step 1: Make root package scripts delegate**

Use:

```json
{
  "name": "stable-money-rumik",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "npm --prefix frontend run dev",
    "build": "npm --prefix frontend run build",
    "test": "npm --prefix frontend test",
    "start": "npm --prefix frontend start",
    "lint": "npm --prefix frontend run lint",
    "migrate": "node scripts/migrate.cjs",
    "backend:dev": "cd backend && py -3 -m uvicorn app.main:app --reload"
  },
  "dependencies": {
    "pg": "^8.20.0"
  }
}
```

- [ ] **Step 2: Keep frontend package scripts unchanged**

The moved `frontend/package.json` remains the existing app package.

- [ ] **Step 3: Update migration paths**

In `scripts/migrate.cjs`, check env files in root and `backend/`, then read `backend/migrations/001_demo_users.sql`.

### Task 5: Update Path-Sensitive Tests

**Files:**
- Modify: `frontend/tests/select-persona-route.test.ts`
- Modify: `frontend/tests/no-legacy-provider.test.ts`
- Modify: `frontend/tests/debug-logging.test.ts`

- [ ] **Step 1: Update source path tests**

Path-sensitive tests should read from `process.cwd()` because tests run inside `frontend/`.

- [ ] **Step 2: Update select-persona test to inspect backend**

Use `path.join(process.cwd(), '..', 'backend', 'app', 'api', 'onboarding.py')` and assert it clears `demo_call_verifications` and `demo_call_mobile_verifications`.

### Task 6: Update Documentation and Verify

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update project structure and commands**

Document `frontend/`, `backend/`, root delegation scripts, and split env files.

- [ ] **Step 2: Run verification**

Run:

```bash
npm test
npm --prefix frontend test
npx tsc --project frontend/tsconfig.json --noEmit
```

Expected: all commands exit 0.
