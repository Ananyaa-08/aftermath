# Deployment adaptations and foundation decisions

The research plan and implementation specification v1.1.1 remain the semantic authority. The user's Step 1 handoff explicitly authorizes these adaptations:

1. Next.js App Router/TypeScript frontend, intended for Vercel; FastAPI and Python worker are separate deployment processes. Deployment is deferred.
2. PostgreSQL with pgvector replaces deployed SQLite. Supabase will provide PostgreSQL, authentication and object storage. Local Docker PostgreSQL needs no cloud credentials. Supabase integrations are not implemented yet.
3. The application and experiment runner share one Python core and application layer. No parallel UI semantic implementation. Environment variables configure infrastructure, while future hashed experiment configuration remains separate from secrets (adapting spec §7.6).
4. Existing models will be used initially behind small ports. A later trained transition model is optional. Its absence must cause verifier escalation for selected answers; there is no cheap prediction fallback. Model calls and routing are deferred.
5. Foundation engineering precedes M0. No feasibility gate, natural-data audit, training, benchmark, empirical result, or M1 vertical slice is claimed.
6. Workspace and job UUIDs support deployed tenancy and operations. Research deterministic identifiers and method-run isolation will be added explicitly, not replaced by these UUIDs.
7. Queue infrastructure uses QUEUED/RUNNING/SUCCEEDED/FAILED, with attempts and leases. Assessment workflow independently retains UNASSESSED/QUEUED/IN_PROGRESS/COMPLETED/FAILED/WITHHELD. This minimal job table is not the complete research AssessmentJob schema.
8. Synchronous SQLAlchemy/psycopg runs in FastAPI synchronous handlers (threadpool); the worker is synchronous. Health checks use bounded connection/query timeouts. No speculative async stack or extra brokers.
9. Pydantic schemas are foundational references, not a mechanical transcription of §6.5. Full record envelopes, schema export, evidence coverage, workflow transition validation, policy resolution, immutable record migrations, and reproducibility manifests remain later work.
10. The initial frontend used marine/bright red/butter/paper colors. The subsequent user-authorized refinement replaces these with sky/ganache/butter/paper and deeper blue accents, using local heavy display and readable system fonts with centralized Tailwind/CSS tokens. No font network dependency. Deeper blue marks decorative accents and focus; semantic colors always have readable text labels. Framer Motion and Lucide are unnecessary for this small shell and are not installed.

Attention before Step 2: select membership/RLS design, method-run namespace, immutable revision schema and guarded pointers; settle input fingerprint/idempotency conflict behavior and lease fencing. None requires implementing the full pipeline now.
