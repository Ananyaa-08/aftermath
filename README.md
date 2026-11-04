# aftermath

Revalidating archived grounded answers when their source documents change.

## What it is

AFTERMATH is a research prototype. A user uploads documents into a corpus and asks questions. Each answer is grounded: it cites the exact passage it came from, and is archived with that citation at a specific corpus snapshot.

When a document is later revised, AFTERMATH detects which stored passages changed, finds only the archived answers whose cited passage changed, and flags them for reassessment. Answers whose evidence did not change are left alone.



![Homepage](docs/screenshots/home-desktop.jpg)

![Live workspace overview](docs/screenshots/overview-desktop.jpg)

![Inspecting what a document update changed](docs/screenshots/inspection-desktop.jpg)

## Architecture

The browser talks to the Next.js app in `apps/web`. That app proxies storage and answer requests to the FastAPI service in `services/backend`.

HTTP routes call application use cases. Use cases depend on core and on ports. Adapters implement those ports. Core holds retrieval, answer and citation checks, change detection, and review. The Gemini adapter produces grounded answers. When Gemini is unavailable, or when the demo fallback is forced, `core/demo_fallback` builds the answer from retrieved passages of the demo documents `plans` and `plans-v2`.

PostgreSQL, with the pgvector extension installed, stores workspaces, corpora, documents, passage versions, snapshots, and change records. Alembic migrations in `services/backend/migrations` manage that schema. Archived answers and reassessments are append-only JSON files written by the archive adapter.

```mermaid
flowchart TB
  browser[Browser]
  web["Next.js app<br/>apps/web"]
  browser --> web

  subgraph backend ["services/backend"]
    direction TB
    api["api<br/>HTTP routes"]
    application["application<br/>use cases"]
    core["core<br/>retrieval, answers, citations,<br/>change detection, review"]
    ports["ports<br/>interfaces"]
    adapters["adapters<br/>persistence, storage,<br/>providers, archive"]
    fallback["core/demo_fallback<br/>passage-built answers"]
    api --> application
    application --> core
    application --> ports
    adapters -.->|implements| ports
    application -->|"Gemini unavailable<br/>or fallback forced"| fallback
  end

  web -->|proxies requests| api
  db["PostgreSQL + pgvector<br/>corpora, documents, passages,<br/>snapshots, change records"]
  gemini["Gemini provider<br/>adapters/providers"]
  archive["Answer archive<br/>append-only JSON"]
  adapters --> db
  adapters --> gemini
  adapters --> archive
```

## Tech stack

| Part | Choice |
| --- | --- |
| Frontend | Next.js 16 + React 19 (TypeScript) |
| Backend | FastAPI (Python 3.13) |
| Database | PostgreSQL + pgvector |
| Migrations | Alembic |
| LLM | Google Gemini (with deterministic fallback) |
| Package managers | npm and uv |

## Repository structure

```text
.
├── apps/web/                 Next.js frontend
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── tests/
│   └── scripts/
├── services/backend/         FastAPI service
│   ├── src/aftermath/
│   │   ├── api/
│   │   ├── application/
│   │   ├── core/
│   │   ├── adapters/
│   │   ├── ports/
│   │   ├── experiments/
│   │   ├── worker/
│   │   └── config.py
│   ├── migrations/
│   └── tests/
├── infra/                    Docker Compose for Postgres with pgvector, on 127.0.0.1:54329
└── docs/                     architecture notes, demo runbook, screenshots
```
