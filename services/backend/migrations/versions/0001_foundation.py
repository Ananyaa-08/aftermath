"""Workspace and durable job envelope only."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE workspaces (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL CHECK (length(name) > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE jobs (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id),
            idempotency_key VARCHAR(200) NOT NULL CHECK (length(idempotency_key) > 0),
            state TEXT NOT NULL DEFAULT 'QUEUED'
                CHECK (state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            lease_owner TEXT,
            lease_expires_at TIMESTAMPTZ,
            error JSONB,
            input_snapshot_id TEXT NOT NULL CHECK (input_snapshot_id ~ '^snap:[0-9]{6,}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, idempotency_key),
            CHECK ((state = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
                OR (state <> 'RUNNING' AND lease_owner IS NULL AND lease_expires_at IS NULL)),
            CHECK (error IS NULL OR (jsonb_typeof(error) = 'object'
                AND error ? 'code' AND error ? 'message' AND error ? 'retryable')),
            CHECK ((state = 'FAILED') = (error IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX jobs_claim_idx ON jobs (state, created_at)")
    op.execute("CREATE INDEX jobs_workspace_idx ON jobs (workspace_id)")
    # Deny direct anonymous/authenticated access when deployed through Supabase.
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE jobs")
    op.execute("DROP TABLE workspaces")
    # Extension may be shared by other applications; do not remove it.
