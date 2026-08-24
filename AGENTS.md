# Engineering instructions

Foundation only. No working semantic revalidation pipeline or research performance result is claimed.

Scope includes the user's Step 1 handoff and subsequent frontend refinement request. The latter authorizes labeled deterministic example fixtures and inspection interactions, not a semantic pipeline. Preserve the research Markdown and archive. Do not implement ingestion, retrieval, semantic resolution, real model adapters, training, a full queue, deployment, or the final dashboard without a new request.

- Read `AFTERMATH_Research_Plan.md` and implementation spec v1.1.1. Deployment adaptations are explicit in `docs/architecture-decisions.md`.
- Python core owns contracts. It may import standard library and Pydantic, never FastAPI, SQLAlchemy, provider SDKs, or outer layers. Application imports core and ports only. Adapters implement ports. API, worker, and experiment CLI invoke shared application use cases.
- Never import evaluation gold into production inference. No gold data exists in the foundation. Import allowlists and negative tests live in `tests/test_boundaries.py`; dynamic imports and runtime gold reads must not bypass them.
- Provider judgments and transition predictions are not final verdicts. Authority policy belongs in future shared application/core code. An absent transition predictor must route selected work to the verifier; never synthesize predictions.
- Every repository operation must be workspace-scoped; a client-supplied ID is not authorization. No data endpoints exist yet.
- Canonical offsets are Unicode code points, half-open. Browser UTF-16 conversion belongs at the API boundary. Timestamps must be aware and normalize to UTC.
- Never log credentials, raw configuration, provider payloads, or validation inputs. No secret goes in `NEXT_PUBLIC_` variables. No authentication bypass exists.
- npm is the frontend package manager; uv is the Python manager. Keep both lockfiles. Do not add dependencies without a concrete need.
- Checks from backend: `uv run pytest -q`, `uv run ruff check src tests migrations`, `uv run ruff format --check src tests migrations`, `uv run mypy src`. Set `AFTERMATH_TEST_DATABASE_URL` for PostgreSQL integration tests; skips do not satisfy integration acceptance.
- Checks from frontend: `npm ci`, `npm run typecheck`, `npm run build`. CI must migrate real PostgreSQL with pgvector; SQLite is not equivalent.
- Record exact check outcomes and limitations in `docs/implementation-status.md`. Do not conflate engineering checks with M0/M1 research completion.
