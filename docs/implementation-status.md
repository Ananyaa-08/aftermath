# Step 1 verification record

Verified locally on 1 November 2026. Foundation only. No working semantic revalidation pipeline or research performance result is claimed.

## Implemented

- Next.js/TypeScript/Tailwind shell with design tokens, accessible textual connectivity states and a server-only backend health proxy.
- One Python package: foundational domain contracts, eight requested small ports plus a health probe, shared application health use cases, PostgreSQL readiness adapter, FastAPI, idle worker and validation-only experiment CLI.
- UTC normalization, strict canonical Unicode text, SHA-256/canonical JSON helpers, UTF-16 API boundary conversion, workspace consistency checks, explicit unknown usage and separate provider output/final verdict types.
- Alembic migration: vector extension, workspaces, durable jobs, workspace-scoped idempotency, job-state/lease/error constraints, deny-by-default RLS for non-owner roles.
- Typed configuration, local environment examples, import-boundary tests, CI using PostgreSQL/pgvector, architecture and security documentation.

## Actual versions

Host: macOS arm64; Node 20.20.2; npm 10.8.2; Python **3.13.1** selected by uv (the shell's default Python was 3.11.9); uv **0.13.6**. Docker client **29.2.1**, Compose **5.0.2**. Container: PostgreSQL **17.11**, pgvector **0.8.7** (`pgvector/pgvector:pg17`).

Backend locked: FastAPI **0.162.0**, Pydantic **2.14.2**, pydantic-settings **2.16.2**, SQLAlchemy **2.1.6**, psycopg/psycopg-binary **3.3.6**, Alembic **1.20.1**, Uvicorn **0.54.0**. Checks: pytest **9.2.0**, Ruff **0.17.3**, mypy **1.20.2**, httpx **0.28.1**. All transitive resolutions are in `services/backend/uv.lock`.

Frontend locked: Next.js **16.4.3**, React/react-dom **19.3.1**, Tailwind/@tailwindcss/postcss **4.3.3**, TypeScript **5.9.3**, @types/node **22.20.5**, @types/react/@types/react-dom **19.3.0**. All transitive resolutions are in `apps/web/package-lock.json`. Framer Motion and Lucide are deferred until needed.

Version choice consulted official [Next.js installation guidance](https://nextjs.org/docs/pages/getting-started/installation), [uv installation guidance](https://docs.astral.sh/uv/getting-started/installation/), and [FastAPI's package metadata](https://pypi.org/project/fastapi/). Versions above were observed from installed packages/commands, not inferred from those pages.

## Commands actually run and outcomes

Backend commands ran from `services/backend`; frontend commands from `apps/web`; Compose commands from repository root. The uv executable used here was `/private/tmp/aftermath-tools/bin/uv`, with `UV_CACHE_DIR=/private/tmp/aftermath-uv-cache`; documentation abbreviates this to `uv`.

1. `docker info`: initially failed because the daemon was stopped. `docker desktop start` succeeded. `docker compose -f infra/compose.yaml up -d --wait`: passed, created a new PostgreSQL volume/database.
2. `uv sync`: sandbox DNS failure; retried with network approval and resolved/installed dependencies and generated `uv.lock`. The regular-wheel workaround below was needed on this host.
3. `AFTERMATH_DATABASE_URL=postgresql+psycopg://aftermath:local-only@localhost:54329/aftermath .venv/bin/alembic upgrade head`: initially blocked by sandbox TCP restrictions; approved retry passed on the fresh PostgreSQL database.
4. `.venv/bin/ruff check src tests migrations`: final **pass**. Initial formatting/import findings were fixed. `.venv/bin/ruff format --check src tests migrations`: **24 files already formatted**. `.venv/bin/mypy src`: **success, 19 source files**.
5. `AFTERMATH_TEST_DATABASE_URL=postgresql+psycopg://aftermath:local-only@localhost:54329/aftermath .venv/bin/pytest -q`: final **16 passed in 3.67s**, no skips. Includes schema/time/failure tests, import boundaries and negative guard tests, PostgreSQL vector query, migration check, durable job insert/constraints, live=200, ready=200 with DB, ready=503 with unavailable DB, CLI help/valid/invalid config, and worker startup/SIGTERM/clean exit. One non-failing Starlette warning deprecates its httpx TestClient integration in favor of httpx2.
6. `npm install --cache /private/tmp/aftermath-npm-cache`: sandbox DNS failure, approved retry passed. `npm ci --cache /private/tmp/aftermath-npm-cache --offline`: **passed**, 49 packages, audit reported zero vulnerabilities.
7. `npm run typecheck`: **passed**. `npm run build` (`next build --webpack`): **passed**, generated `/`, `/_not-found`, and dynamic `/api/connectivity`. Repeated after `npm ci`; passed again.
8. Started `.venv/bin/uvicorn aftermath.api.main:create_app --factory --host 127.0.0.1 --port 8000` with the local database URL and `BACKEND_URL=http://127.0.0.1:8000 npm run start -- --hostname 127.0.0.1`. Both required local socket approval and then started successfully.
9. Chrome inspection: shell rendered and displayed **API connected · PostgreSQL foundation ready**. `docker compose -f infra/compose.yaml stop postgres`, then “Check again”: **API responded · database readiness unavailable**. `docker compose -f infra/compose.yaml start --wait postgres`, then “Check again”: **ready restored**. Desktop screenshot inspected; mobile browser QA was not performed.
10. PostgreSQL queries confirmed PostgreSQL **17.11**, vector **0.8.7**; integration tests exercised an actual vector distance operation, not SQLite.

## Resolved environment failures and remaining limits

Python 3.13 ignored the editable package `.pth` because macOS marked it hidden. Clearing the flag worked briefly but it recurred. Verified workaround: `uv sync --locked --no-editable --reinstall-package aftermath` (final rebuild also passed with `--offline`). Run installed `.venv/bin/` entrypoints, or preserve `--no-editable` with `uv run`; rebuild after edits. The smoke tests now locate console scripts next to `sys.executable`, so they do not depend on shell activation. Earlier collection/PATH failures are resolved, not counted as passing runs.

No remaining required check failure. Hosted CI has not run. Browser mobile/accessibility automation was not run; desktop visual and accessibility-tree inspection were performed. No cloud integration, deployment, performance, or research milestone validation occurred. One test-library deprecation warning remains.

No Git repository existed and none was initialized; no commit SHA exists. Both lockfiles are present but are **not committed**. Commit/version-control handoff remains outstanding if a committed repository is required before closing Step 1.

## Deferred and decisions requiring attention

No ingestion, embeddings/provider calls, retrieval, authority resolution, routing, revalidation, training, experiment execution, evaluation gold, full durable queue, final dashboard or deployment. There are no fake results or mocked product endpoints. Model/storage adapters and their empty directories were deliberately not created.

Before Step 2: review Supabase membership/JWT/RLS design, immutable revisions/verdicts and CAS current pointers, method-run isolation, transactional enqueue with input fingerprint conflict detection, lease fencing/retry behavior, and absent-predictor verifier escalation. See `architecture-decisions.md` for explicit research adaptations. Foundation checks do not satisfy M0 or M1.

## Final source structure

```text
AFTERMATH_Research_Plan.md                 preserved
AFTERMATH_IMPLEMENTATION_SPEC.md          preserved, v1.1.1
aftermath_spec_build_v1.1.1.zip            preserved
README.md
AGENTS.md
.gitignore
.github/workflows/checks.yml
apps/web/
  .env.example
  package.json, package-lock.json
  tsconfig.json, next-env.d.ts, postcss.config.mjs
  app/
    layout.tsx, page.tsx, globals.css, connectivity.tsx
    api/connectivity/route.ts
services/backend/
  .env.example, .python-version
  pyproject.toml, uv.lock, alembic.ini
  src/aftermath/
    config.py
    core/contracts.py, text.py
    ports/interfaces.py
    application/health.py
    adapters/persistence/database.py
    api/main.py, offsets.py
    worker/main.py
    experiments/cli.py
  migrations/
    env.py, script.py.mako
    versions/0001_foundation.py
  tests/
    test_contracts.py, test_boundaries.py, test_services.py
docs/
  architecture.md
  architecture-decisions.md
  implementation-status.md
  environment.md
infra/compose.yaml
```

Python package `__init__.py` files and ignored local dependencies/build outputs are omitted from the tree.

## Exact reviewer files

Start with `services/backend/src/aftermath/core/contracts.py`, `ports/interfaces.py`, `application/health.py`, `adapters/persistence/database.py`, `api/main.py`, and `config.py` (paths after the first are relative to `src/aftermath`). Inspect `services/backend/migrations/versions/0001_foundation.py` and all three `services/backend/tests/test_*.py` files for integrity and acceptance coverage. Inspect `apps/web/app/page.tsx`, `connectivity.tsx`, `globals.css`, and `api/connectivity/route.ts` for UI scope and backend status handling. Finally review `.github/workflows/checks.yml`, both lockfiles, README, and the architecture/environment documents.


## Subsequent frontend refinement

The later user request authorizes a visual/interaction foundation and explicitly labeled deterministic example workspace. See [frontend-refinement.md](frontend-refinement.md) for current UI scope, verification, screenshots and changed files. Backend contracts and inference boundaries are preserved. Git initialization was declined; there remains no repository or foundation commit.
