# Foundation architecture

Foundation only. No working semantic revalidation pipeline or research performance result is claimed.

`apps/web` is a Next.js App Router workspace. The subsequent frontend refinement adds an explicitly labeled, isolated example inspection mode; see `frontend-refinement.md`. Its server-only `/api/connectivity` handler calls FastAPI `/health/ready`; the browser receives only a sanitized status. The backend URL and credentials never enter client bundles. The shell makes a real request on load and on “Check again”.

`services/backend` is one installable Python package shared by FastAPI, the worker, and the experiment CLI. Each entrypoint wires a PostgreSQL adapter and calls `application.health`. The worker validates configuration and dependencies, then waits for SIGINT/SIGTERM; it does not claim or fabricate jobs. The experiment CLI validates configuration and DB readiness only.

Dependency direction: core ← ports ← application; adapters depend on ports/core; entrypoints compose adapters and application. `config.py` is composition infrastructure. AST tests enforce direct and relative import allowlists and forbid evaluation imports; runtime file access is additionally a code-review boundary, not an OS security sandbox.

Core schemas distinguish evidence judgments, provisional transition predictions, and policy-resolved verdicts. Only the last contains a final semantic status bound to an answer, snapshot, evaluation time, and policy version. A failed verifier carries an error, no judgments or verdict. Workflow state is a separate six-state enum from spec §5.3. State transition orchestration is deferred. The operational queue uses four infrastructure states; these are not assessment workflow states.

## Persistence and jobs

Migration 0001 installs pgvector and creates only workspaces and durable job envelopes. The PostgreSQL readiness adapter checks connectivity, vector extension, migration version and foundational tables. Tables enable RLS with no public policies, so Supabase anonymous/authenticated roles have no direct access. The local owner/migration role bypasses RLS; this is not a tenant-isolation proof.

Future enqueue must occur in the same SQLAlchemy transaction as the associated application state change through a UnitOfWork. The unique `(workspace_id, idempotency_key)` constraint is the concurrency guard; matching keys must compare immutable input fingerprints and reject mismatched payloads. No enqueue implementation exists yet.

Future claiming uses a short transaction: select eligible queued/expired-lease rows with `FOR UPDATE SKIP LOCKED`, update state, lease owner/expiry and attempt count, then commit before external work. Completion/heartbeat must compare the lease owner plus attempt/fencing token; an expired worker cannot commit. Retry limits and recovery remain deferred. No Redis is needed.

Future revisions and verdicts are append-only. Guard mutable corpus/answer current pointers with snapshot-bound compare-and-swap in the same transaction as verdict insertion. An assessment for a stale snapshot requeues rather than overwriting the current result. Research method runs also need separate operational namespaces; workspace scope alone is insufficient.

## Text, identity and clocks

`canon-v1`: strict UTF-8 decode, remove leading BOM, normalize CRLF/CR to LF, then NFC. Offsets index canonical Python strings as Unicode code points in `[start,end)`. Never store UTF-16 offsets. `api.offsets.utf16_offset` converts only at the browser boundary and is tested with a supplementary-plane emoji. Span bounds against actual text must be checked when evidence is materialized.

Content hashes are `sha256:` plus SHA-256 of canonical UTF-8; canonical JSON sorts keys and rejects nonfinite numbers. Content equality does not imply revision identity. Revision references retain external document/revision names. Workspace/job UUIDs are operational identifiers, never content hashes. Snapshot/answer references are workspace-scoped; research operational ID derivation remains deferred.

Experiment logical time comes from datasets, never wall-clock `now()`. UTC wall-clock timestamps and measured runtime (use a monotonic timer for durations) are accounting only and excluded from future deterministic digests. Unknown cost/tokens/latency serialize as null, not zero. Current database job timestamps are operational wall-clock time.

## Authorization boundary

Health routes are public and expose no tenant data. Before adding any data route, FastAPI must validate Supabase JWT signature via configured JWKS, pinned issuer/audience, expiry and allowed algorithms, then resolve server-side workspace membership. A workspace ID supplied by a request never grants access. Repositories must scope every query and storage key. Worker jobs require trusted workspace context. Use least-privilege runtime roles, migration credentials separately, and tenant-aware RLS policies before deployment. No auth bypass is implemented.
