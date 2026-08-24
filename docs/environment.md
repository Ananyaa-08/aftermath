# Environment

Local commands run Python services on the host and PostgreSQL in Docker. Copy the backend `.env.example` to `.env` and web `.env.example` to `.env.local`. Both are ignored. Examples contain only local development placeholders, no real credentials.

Backend typed settings (prefix `AFTERMATH_`):
- `DATABASE_URL`: required `postgresql+psycopg://...` URL. Local placeholder is `postgresql+psycopg://aftermath:local-only@localhost:54329/aftermath`.
- `ENVIRONMENT`: development (default), test, or production. Production rejects localhost CORS origins.
- `CORS_ORIGINS`: JSON array, default `["http://localhost:3000"]`. Wildcards are rejected.
- `AFTERMATH_TEST_DATABASE_URL`: read by integration tests only; must name a migrated PostgreSQL database. Tests roll back inserted records.

Web: `BACKEND_URL` is server-only, e.g. `http://127.0.0.1:8000`. Missing URL is reported as unconfigured. No `NEXT_PUBLIC_` variable is needed. Backend CORS is explicit even though the shell currently uses a same-origin server proxy.

Future deployed configuration (not consumed yet): Supabase JWKS URL, issuer and audience; workspace membership policies; server-only storage/service credentials; provider model keys; versioned model configuration. Do not add unused keys to runtime `.env` files: unknown settings are rejected. Never put database, service-role or model keys in public frontend variables. No authentication bypass flag exists.

Future deployment must use TLS, separate migration/runtime roles, workspace-aware RLS, explicit CORS origins, and an approved Supabase JWT validation boundary before serving tenant data. Local credentials are not production credentials.
