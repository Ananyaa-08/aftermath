# AFTERMATH

Foundation only. No working semantic revalidation pipeline or research performance result is claimed.

The frontend now provides an editorial research workspace with live readiness and a clearly labeled Example workspace. Example source diffs, answer filtering, claim inspection and history use isolated authored fixtures; none are model outputs or live corpus records. See [frontend verification and screenshots](docs/frontend-refinement.md).

Step 1 provides a Next.js shell, FastAPI health endpoints, shared Python contracts/ports, an idle worker, a configuration-validation CLI, and PostgreSQL/pgvector migrations. There are no semantic assessment endpoints or model calls.

## Local setup

Prerequisites: Docker running, Python 3.13, uv, Node 20.9+ and npm. This build was verified with Python 3.13.1, uv 0.13.6, Node 20.20.2 and npm 10.8.2. See [the verification record](docs/implementation-status.md) for exact versions, outcomes and environment workarounds.

From the repository root:

```sh
docker compose -f infra/compose.yaml up -d --wait
cd services/backend
cp .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run uvicorn aftermath.api.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd apps/web
cp .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:3000. “Check again” requests actual readiness via the Next.js server. Liveness is http://127.0.0.1:8000/health/live; readiness is http://127.0.0.1:8000/health/ready. Readiness returns HTTP 503 when the database, vector extension, or foundation migration is unavailable.

Worker and CLI, from `services/backend`:

```sh
uv run aftermath-worker --check
uv run aftermath-worker
# Stop with Ctrl+C; it stays idle and executes no jobs.
uv run aftermath-experiment --help
uv run aftermath-experiment --validate-config
```

## Checks

From `services/backend`:

```sh
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run mypy src
AFTERMATH_TEST_DATABASE_URL=postgresql+psycopg://aftermath:local-only@localhost:54329/aftermath uv run pytest -q
```

Without `AFTERMATH_TEST_DATABASE_URL`, two integration tests skip; that is not full verification. Run migrations before integration tests. Tests exercise actual PostgreSQL vector operations and roll back their inserted records.

From `apps/web`:

```sh
npm test
npm run typecheck
npm run build
npm run start
```

The documented setup is the normal editable development path. On this macOS host, an inherited hidden flag on the editable `.pth` file made Python ignore it. The verified workaround is `uv sync --locked --no-editable --reinstall-package aftermath`, followed by commands through `.venv/bin/` (or `uv run --no-editable`). Reinstall the package after source edits in this mode. Do not add another project's path to `PYTHONPATH`.

Stop local infrastructure without deleting its volume:

```sh
docker compose -f infra/compose.yaml stop
```

## Review map

- [Architecture and security boundaries](docs/architecture.md)
- [Explicit research/deployment adaptations](docs/architecture-decisions.md)
- [Implemented, verified and deferred work](docs/implementation-status.md)
- [Environment configuration](docs/environment.md)
- [Engineering rules](AGENTS.md)

The two supplied research Markdown files and spec archive are preserved. No README or AGENTS.md existed initially. No Git repository or commit was created; lockfiles are supplied for version control. CI is configured but has not run on a hosted runner.
