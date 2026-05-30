# Frontend Backend Folder Split Design

## Goal

Keep this as one Git repository while separating the runnable Next.js frontend and FastAPI backend into two clear folders:

```text
stable-money-rumik/
  frontend/
  backend/
```

The split must not change product behavior. Existing frontend routes, backend API paths, database schema, persona data, and the HTTP boundary between the browser and Python backend remain the same.

## Architecture

The root becomes orchestration and documentation. The Next.js app owns its package files, TypeScript config, app router, components, CSS, public assets, frontend helpers, and Node tests. The FastAPI backend owns its Python package, migrations, backend env examples, and backend runtime settings.

The frontend continues to call the backend through `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`. The backend continues to serve API routes under `/api/...` and allows the frontend development origin through CORS.

## Folder Ownership

```text
frontend/
  app/
  components/
  lib/
  public/
  styles/
  assets/
  tests/
  package.json
  package-lock.json
  tsconfig.json
  next.config.ts
  next-env.d.ts
  .env.example

backend/
  app/
  migrations/
  pyproject.toml
  .env.example
```

Root keeps:

```text
README.md
.gitignore
.env.example
docs/
scripts/
package.json
```

The root `package.json` is orchestration only. It delegates frontend commands into `frontend/` and keeps the existing migration command available from the repo root.

## Environment Files

Tracked examples:

- `frontend/.env.example` documents browser/client-facing configuration, especially `NEXT_PUBLIC_API_BASE_URL`.
- `backend/.env.example` documents backend secrets and provider settings.
- root `.env.example` documents that local env files can remain at root for compatibility or be copied into each app folder.

Ignored local files:

- `frontend/.env.local`
- `backend/.env.local`
- root `.env.local`

The backend config loads backend-local env files first, then root env files as a compatibility fallback.

## Behavior Preservation

No API path, route path, persona data, session cookie name, database table, or frontend URL changes as part of this split.

The migration SQL moves under `backend/migrations/`, and the root migration script is updated to read that location.

## Testing

Verification is:

- `npm test` from the repo root, delegating to frontend tests.
- `npm --prefix frontend test` directly.
- `npx tsc --project frontend/tsconfig.json --noEmit`.

Tests that inspect source paths are updated to use the new frontend/backend roots without changing the behavior they assert.
