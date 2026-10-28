"""Immutable corpus knowledge and atomic delivery audit."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = [
    "workspace_members",
    "corpora",
    "documents",
    "update_events",
    "snapshots",
    "source_objects",
    "document_versions",
    "snapshot_documents",
    "update_event_status_log",
    "delivery_attempts",
]
IMMUTABLE = [name for name in TABLES if name != "corpora"]


def upgrade() -> None:
    op.execute("""
    CREATE TABLE workspace_members (
      workspace_id UUID NOT NULL REFERENCES workspaces(id), principal TEXT NOT NULL,
      PRIMARY KEY(workspace_id,principal));
    CREATE TABLE corpora (
      workspace_id UUID NOT NULL REFERENCES workspaces(id), corpus_id TEXT NOT NULL,
      name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120), head_snapshot_id TEXT,
      PRIMARY KEY(workspace_id,corpus_id),
      CHECK(corpus_id ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'));
    CREATE TABLE documents (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, document_id TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY(workspace_id,corpus_id,document_id),
      FOREIGN KEY(workspace_id,corpus_id) REFERENCES corpora(workspace_id,corpus_id),
      CHECK(document_id ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'));
    CREATE TABLE update_events (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, delivery_id TEXT NOT NULL,
      update_event_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
      as_of TIMESTAMPTZ NOT NULL, expected_head TEXT,
      received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY(workspace_id,corpus_id,delivery_id),
      UNIQUE(workspace_id,corpus_id,update_event_id),
      FOREIGN KEY(workspace_id,corpus_id) REFERENCES corpora(workspace_id,corpus_id),
      CHECK(delivery_id ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
      CHECK(update_event_id = 'upd:' || delivery_id),
      CHECK(payload_hash ~ '^sha256:[0-9a-f]{64}$'));
    CREATE TABLE snapshots (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
      snapshot_seq INTEGER NOT NULL CHECK(snapshot_seq>0), parent_snapshot_id TEXT,
      update_event_id TEXT NOT NULL, manifest_hash TEXT NOT NULL,
      document_count INTEGER NOT NULL CHECK(document_count>=0), as_of TIMESTAMPTZ NOT NULL,
      created_txid BIGINT NOT NULL DEFAULT txid_current(),
      PRIMARY KEY(workspace_id,corpus_id,snapshot_id),
      UNIQUE(workspace_id,corpus_id,snapshot_seq),
      UNIQUE(workspace_id,corpus_id,update_event_id),
      FOREIGN KEY(workspace_id,corpus_id) REFERENCES corpora(workspace_id,corpus_id),
      FOREIGN KEY(workspace_id,corpus_id,parent_snapshot_id)
        REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      FOREIGN KEY(workspace_id,corpus_id,update_event_id)
        REFERENCES update_events(workspace_id,corpus_id,update_event_id),
      CHECK(snapshot_id = 'snap:' || lpad(snapshot_seq::text,6,'0')),
      CHECK((snapshot_seq=1) = (parent_snapshot_id IS NULL)),
      CHECK(manifest_hash ~ '^sha256:[0-9a-f]{64}$'));
    ALTER TABLE corpora ADD CONSTRAINT corpus_head_fk
      FOREIGN KEY(workspace_id,corpus_id,head_snapshot_id)
      REFERENCES snapshots(workspace_id,corpus_id,snapshot_id) DEFERRABLE INITIALLY DEFERRED;
    CREATE TABLE source_objects (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, object_key TEXT NOT NULL,
      byte_length INTEGER NOT NULL CHECK(byte_length>=0),
      PRIMARY KEY(workspace_id,corpus_id,object_key),
      FOREIGN KEY(workspace_id,corpus_id) REFERENCES corpora(workspace_id,corpus_id),
      CHECK(object_key ~ '^sha256:[0-9a-f]{64}$'));
    CREATE TABLE document_versions (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, document_id TEXT NOT NULL,
      document_version_id TEXT NOT NULL, source_revision_id TEXT NOT NULL,
      source_seq INTEGER NOT NULL CHECK(source_seq>=0), text TEXT NOT NULL,
      content_hash TEXT NOT NULL CHECK(content_hash ~ '^sha256:[0-9a-f]{64}$'),
      source_bytes_hash TEXT NOT NULL CHECK(source_bytes_hash ~ '^sha256:[0-9a-f]{64}$'),
      object_key TEXT NOT NULL, normalization_version TEXT NOT NULL
      CHECK(normalization_version='canon-v1'),
      source_timestamp TIMESTAMPTZ NOT NULL, declared_effective_from TIMESTAMPTZ,
      effective_from TIMESTAMPTZ NOT NULL, effective_from_source TEXT NOT NULL,
      source_type TEXT NOT NULL, authority JSONB NOT NULL CHECK(jsonb_typeof(authority)='object'),
      is_deletion BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, known_at_seq INTEGER NOT NULL,
      immutable_hash TEXT NOT NULL CHECK(immutable_hash ~ '^sha256:[0-9a-f]{64}$'),
      PRIMARY KEY(workspace_id,corpus_id,document_version_id),
      UNIQUE(workspace_id,corpus_id,document_id,source_revision_id),
      UNIQUE(workspace_id,corpus_id,document_id,source_seq),
      UNIQUE(workspace_id,corpus_id,document_id,document_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id)
        REFERENCES documents(workspace_id,corpus_id,document_id),
      FOREIGN KEY(workspace_id,corpus_id,object_key)
        REFERENCES source_objects(workspace_id,corpus_id,object_key),
      FOREIGN KEY(workspace_id,corpus_id,known_at_seq)
        REFERENCES snapshots(workspace_id,corpus_id,snapshot_seq) DEFERRABLE INITIALLY DEFERRED,
      CHECK(source_revision_id ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
      CHECK(source_type ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'),
      CHECK(document_version_id = 'dv:' || document_id || '@' || source_revision_id),
      CHECK(source_bytes_hash=object_key),
      CHECK(NOT is_deletion OR text=''),
      CHECK(effective_from=coalesce(declared_effective_from,source_timestamp)),
      CHECK(effective_from_source = CASE WHEN declared_effective_from IS NULL
          THEN 'DEFAULT_SOURCE_TIMESTAMP' ELSE 'DECLARED_METADATA' END));
    CREATE TABLE snapshot_documents (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
      document_id TEXT NOT NULL, document_version_id TEXT NOT NULL,
      PRIMARY KEY(workspace_id,corpus_id,snapshot_id,document_id),
      FOREIGN KEY(workspace_id,corpus_id,snapshot_id)
        REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,document_version_id)
        REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id));
    CREATE TABLE update_event_status_log (
      id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL,
      delivery_id TEXT NOT NULL, status TEXT NOT NULL, snapshot_id TEXT, error_code TEXT,
      recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      FOREIGN KEY(workspace_id,corpus_id,delivery_id)
        REFERENCES update_events(workspace_id,corpus_id,delivery_id),
      FOREIGN KEY(workspace_id,corpus_id,snapshot_id)
        REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      CHECK(status IN ('APPLIED','NO_OP_UNCHANGED','PARKED_OUT_OF_ORDER',
      'REJECTED','FAILED_APPLY')),
      CHECK((status='APPLIED') = (snapshot_id IS NOT NULL)));
    CREATE TABLE delivery_attempts (
      id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL,
      delivery_id TEXT NOT NULL, payload_hash TEXT NOT NULL, outcome TEXT NOT NULL,
      recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      FOREIGN KEY(workspace_id,corpus_id,delivery_id)
        REFERENCES update_events(workspace_id,corpus_id,delivery_id),
      CHECK(payload_hash ~ '^sha256:[0-9a-f]{64}$'));
    CREATE INDEX version_knowledge_idx ON document_versions
      (workspace_id,corpus_id,document_id,known_at_seq);
    CREATE FUNCTION reject_corpus_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable corpus record'; END $$;
    CREATE FUNCTION check_snapshot_commit() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM update_event_status_log l JOIN update_events e
          USING(workspace_id,corpus_id,delivery_id)
          WHERE l.workspace_id=NEW.workspace_id AND l.corpus_id=NEW.corpus_id
            AND e.update_event_id=NEW.update_event_id AND l.status='APPLIED'
            AND l.snapshot_id=NEW.snapshot_id) THEN
          RAISE EXCEPTION 'snapshot must belong to applied delivery';
        END IF;
        RETURN NEW;
      END $$;
    CREATE CONSTRAINT TRIGGER snapshot_committed AFTER INSERT ON snapshots
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_snapshot_commit();
    CREATE FUNCTION check_knowledge_seal() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE owner_tx BIGINT;
      BEGIN
        IF TG_TABLE_NAME='document_versions' THEN
          SELECT created_txid INTO owner_tx FROM snapshots WHERE workspace_id=NEW.workspace_id
            AND corpus_id=NEW.corpus_id AND snapshot_seq=NEW.known_at_seq;
        ELSE
          SELECT created_txid INTO owner_tx FROM snapshots WHERE workspace_id=NEW.workspace_id
            AND corpus_id=NEW.corpus_id AND snapshot_id=NEW.snapshot_id;
        END IF;
        IF owner_tx IS DISTINCT FROM txid_current() THEN
          RAISE EXCEPTION 'snapshot knowledge is sealed';
        END IF;
        RETURN NEW;
      END $$;
    CREATE CONSTRAINT TRIGGER version_sealed AFTER INSERT ON document_versions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_knowledge_seal();
    CREATE CONSTRAINT TRIGGER membership_sealed AFTER INSERT ON snapshot_documents
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_knowledge_seal();
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for table in IMMUTABLE:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_corpus_mutation()"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE corpora DROP CONSTRAINT corpus_head_fk")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    for function in ["check_knowledge_seal", "check_snapshot_commit", "reject_corpus_mutation"]:
        op.execute(f"DROP FUNCTION {function}()")
