# EmiMind — Context-Aware Financial AI for the Indonesian Stock Exchange (IDX)

> **Core Product Thesis:** An AI research analyst that deeply understands the longitudinal context, accounting nuances, and operating history of Indonesian publicly listed companies — grounded in verifiable primary documents with zero hallucinations.

---

## Architecture Overview

```
Database calculates reality → Memory stores context → Retrieval selects evidence → LLM reasons over evidence → User gets a challengeable, cited answer.
```

- **Backend:** FastAPI (Python 3.11+ async monorepo managed with `uv`)
- **Database:** PostgreSQL 16 + `pgvector` + `pg_trgm` + `uuid-ossp`
- **Object Storage:** MinIO (S3-compatible) for raw PDF storage and XBRL sidecars
- **Queue / Worker:** Redis + `arq` background workers
- **Frontend:** Next.js 14 (App Router, TypeScript, Tailwind CSS, TanStack Query)

---

## Prerequisites

- **Python:** 3.11 or 3.12 with [`uv`](https://docs.astral.sh/uv/) installed
- **Node.js:** v20+ with [`pnpm`](https://pnpm.io/)
- **Infrastructure:** Docker & Docker Compose (or local Postgres 16+, MinIO, Redis)

---

## Quickstart

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env with your LLM API keys (e.g. Anthropic, OpenAI, DeepSeek, or Moonshot)
```

### 2. Start Infrastructure
```bash
docker compose up -d
```

### 3. Install Python Dependencies
```bash
uv sync
```

### 4. Apply Database Migrations & Seeds
```bash
make migrate
make seed
```

### 5. Start Development Services

In **Terminal 1** (API Server):
```bash
make api
```
*API available at http://localhost:8000 (OpenAPI docs at http://localhost:8000/docs).*

In **Terminal 2** (Background Ingestion Worker):
```bash
make worker
```

In **Terminal 3** (Next.js Web UI):
```bash
cd web
pnpm install
pnpm dev
```
*Web application available at http://localhost:3000.*

---

## Development Commands

| Command | Action |
|:---|:---|
| `make up` | Start Postgres, MinIO, and Redis in Docker |
| `make down` | Stop Docker containers |
| `make migrate` | Apply forward-only database migrations from `db/schema/` |
| `make seed` | Load curated concept map seeds (Banks + Mining) into PostgreSQL |
| `make api` | Launch FastAPI uvicorn development server on `:8000` |
| `make worker` | Launch `arq` background worker |
| `make test` | Run unit tests (`pytest -m "not integration"`) |
| `make lint` | Run Ruff on Python services & ESLint on Next.js |
| `make typecheck` | Run MyPy strict checks & TypeScript typecheck |
| `make fmt` | Format Python code with Ruff & web code with Prettier |

---

## Project Structure & Documentation

- [`BLUEPRINT.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/BLUEPRINT.md) — System design, financial data pipeline, and architectural north star.
- [`TASKS.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/TASKS.md) — Master implementation index (Milestones M1 through M7).
- [`TASK_TRACKER.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/TASK_TRACKER.md) — Live milestone progress and execution checklist.
- [`tasks/00-conventions.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/tasks/00-conventions.md) — Architectural rules, folder layout, and coding standards.
- [`tasks/01-M1-skeleton.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/tasks/01-M1-skeleton.md) — Milestone 1 specification.
