# Stable Money Rumik

Demo application for a Stable Money voice assistant powered by a Next.js frontend and a Python FastAPI backend with a Pipecat voice pipeline.

## Project Structure

```text
frontend/  Next.js web application
backend/   FastAPI API and Pipecat voice pipeline
docs/      Design notes and implementation plans
```

## Prerequisites

- Node.js and npm
- Python 3.11+

## Setup

Install the frontend dependencies:

```bash
cd frontend
npm install
```

Create a Python virtual environment and install the backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Create `backend/.env.local` for local configuration:

```dotenv
OPENAI_API_KEY=
RUMIK_API_KEY=
DATABASE_URL=
NEXT_PUBLIC_APP_URL=http://localhost:3000
PYTHON_BACKEND_CORS_ORIGIN=http://localhost:3000
```

For the frontend, create `frontend/.env.local` if you need to override the API URL:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Run Locally

Start the backend:

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Start the frontend in a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`.

## Tests

Run the backend tests:

```bash
cd backend
pytest
```

Run the frontend tests:

```bash
cd frontend
npm test
```

## Deployment

Pipecat Cloud deployment settings live in `pcc-deploy.toml`.
