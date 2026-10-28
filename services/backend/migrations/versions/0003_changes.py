# ruff: noqa: E501
"""Deterministic passages, source diffs, and applicability changes."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = [
    "passage_versions",
    "passage_lineage_edges",
    "passage_lineage_edge_members",
    "snapshot_changes",
    "applicability_changes",
    "change_spans",
]


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
    CREATE TABLE passage_versions (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, document_id TEXT NOT NULL,
      document_version_id TEXT NOT NULL, passage_version_id TEXT NOT NULL,
      ordinal INTEGER NOT NULL CHECK(ordinal>0), start_offset INTEGER NOT NULL CHECK(start_offset>=0),
      end_offset INTEGER NOT NULL CHECK(end_offset>start_offset), text TEXT NOT NULL,
      section_path JSONB NOT NULL CHECK(jsonb_typeof(section_path)='array'),
      content_hash TEXT NOT NULL CHECK(content_hash ~ '^sha256:[0-9a-f]{64}$'),
      norm_hash TEXT NOT NULL CHECK(norm_hash ~ '^sha256:[0-9a-f]{64}$'),
      lineage_id TEXT NOT NULL, segmentation_version TEXT NOT NULL CHECK(segmentation_version='seg-v1'),
      PRIMARY KEY(workspace_id,corpus_id,passage_version_id),
      UNIQUE(workspace_id,corpus_id,document_version_id,ordinal),
      UNIQUE(workspace_id,corpus_id,document_id,passage_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,document_version_id)
        REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id),
      CHECK(passage_version_id ~ '^pv:[a-z0-9][a-z0-9_.-]{0,63}@[a-z0-9][a-z0-9_.-]{0,63}#p[0-9]{4,}$'),
      CHECK(lineage_id ~ '^lin:[a-z0-9][a-z0-9_.-]{0,63}:[a-z0-9][a-z0-9_.-]{0,63}:p[0-9]{4,}$'),
      CHECK(char_length(text)=end_offset-start_offset));
    CREATE TABLE passage_lineage_edges (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, document_id TEXT NOT NULL,
      update_event_id TEXT NOT NULL, lineage_edge_id TEXT NOT NULL, edge_ordinal INTEGER NOT NULL,
      relation TEXT NOT NULL, alignment_score DOUBLE PRECISION,
      alignment_confidence TEXT NOT NULL, alignment_method TEXT NOT NULL,
      reason JSONB NOT NULL CHECK(jsonb_typeof(reason)='object'),
      PRIMARY KEY(workspace_id,corpus_id,lineage_edge_id),
      UNIQUE(workspace_id,corpus_id,update_event_id,edge_ordinal),
      UNIQUE(workspace_id,corpus_id,document_id,lineage_edge_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id) REFERENCES documents(workspace_id,corpus_id,document_id),
      FOREIGN KEY(workspace_id,corpus_id,update_event_id) REFERENCES update_events(workspace_id,corpus_id,update_event_id),
      CHECK(lineage_edge_id ~ '^le:[a-z0-9][a-z0-9_.-]{0,63}:[0-9]{4,}$'),
      CHECK(relation IN ('IDENTICAL','MOVED','REFORMATTED','MODIFIED','MERGED','SPLIT','ADDED','DELETED')),
      CHECK(alignment_score IS NULL OR alignment_score BETWEEN 0 AND 1),
      CHECK(alignment_confidence IN ('HIGH','LOW')),
      CHECK(alignment_method='diff-v1/dice-v1'));
    CREATE TABLE passage_lineage_edge_members (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, document_id TEXT NOT NULL,
      lineage_edge_id TEXT NOT NULL, passage_version_id TEXT NOT NULL,
      side TEXT NOT NULL CHECK(side IN ('OLD','NEW')), member_ordinal INTEGER NOT NULL CHECK(member_ordinal>0),
      PRIMARY KEY(workspace_id,corpus_id,lineage_edge_id,side,member_ordinal),
      UNIQUE(workspace_id,corpus_id,lineage_edge_id,side,passage_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,lineage_edge_id)
        REFERENCES passage_lineage_edges(workspace_id,corpus_id,document_id,lineage_edge_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,passage_version_id)
        REFERENCES passage_versions(workspace_id,corpus_id,document_id,passage_version_id));
    CREATE TABLE snapshot_changes (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
      update_event_id TEXT NOT NULL, document_id TEXT NOT NULL, document_version_id TEXT NOT NULL,
      PRIMARY KEY(workspace_id,corpus_id,snapshot_id,document_id),
      FOREIGN KEY(workspace_id,corpus_id,snapshot_id) REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      FOREIGN KEY(workspace_id,corpus_id,update_event_id) REFERENCES update_events(workspace_id,corpus_id,update_event_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,document_version_id)
        REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id));
    CREATE TABLE applicability_changes (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, update_event_id TEXT NOT NULL,
      document_id TEXT NOT NULL, applicability_change_id TEXT NOT NULL, change_ordinal INTEGER NOT NULL,
      parent_snapshot_id TEXT, result_snapshot_id TEXT NOT NULL,
      interval_from TIMESTAMPTZ NOT NULL, interval_to TIMESTAMPTZ,
      old_effective_version_id TEXT, new_effective_version_id TEXT,
      old_effective_fingerprint TEXT NOT NULL, new_effective_fingerprint TEXT NOT NULL,
      reason TEXT NOT NULL, text_diff_reused BOOLEAN NOT NULL,
      timeline_version TEXT NOT NULL CHECK(timeline_version='timeline-v1'),
      PRIMARY KEY(workspace_id,corpus_id,applicability_change_id),
      UNIQUE(workspace_id,corpus_id,update_event_id,change_ordinal),
      FOREIGN KEY(workspace_id,corpus_id,update_event_id) REFERENCES update_events(workspace_id,corpus_id,update_event_id),
      FOREIGN KEY(workspace_id,corpus_id,parent_snapshot_id) REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      FOREIGN KEY(workspace_id,corpus_id,result_snapshot_id) REFERENCES snapshots(workspace_id,corpus_id,snapshot_id),
      CHECK(applicability_change_id ~ '^ac:[a-z0-9][a-z0-9_.-]{0,63}:[0-9]{4,}$'),
      CHECK(interval_to IS NULL OR interval_to>interval_from),
      CHECK(old_effective_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
      CHECK(new_effective_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
      CHECK(reason IN ('CONTENT','AUTHORITY','APPLICABILITY','ADDITION','DELETION')));
    CREATE TABLE change_spans (
      workspace_id UUID NOT NULL, corpus_id TEXT NOT NULL, update_event_id TEXT NOT NULL,
      document_id TEXT NOT NULL, change_span_id TEXT NOT NULL, span_ordinal INTEGER NOT NULL,
      old_document_version_id TEXT, new_document_version_id TEXT,
      old_passage_version_id TEXT, new_passage_version_id TEXT,
      kind TEXT NOT NULL, lineage_edge_id TEXT,
      old_start INTEGER, old_end INTEGER, new_start INTEGER, new_end INTEGER,
      old_text TEXT, new_text TEXT, features JSONB NOT NULL CHECK(jsonb_typeof(features)='object'),
      alignment_confidence TEXT NOT NULL, effective_from TIMESTAMPTZ NOT NULL,
      effective_to TIMESTAMPTZ, applicability_change_id TEXT,
      text_diff_reused BOOLEAN NOT NULL, origin TEXT NOT NULL,
      metadata JSONB NOT NULL CHECK(jsonb_typeof(metadata)='object'),
      PRIMARY KEY(workspace_id,corpus_id,change_span_id),
      UNIQUE(workspace_id,corpus_id,update_event_id,span_ordinal),
      FOREIGN KEY(workspace_id,corpus_id,update_event_id) REFERENCES update_events(workspace_id,corpus_id,update_event_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,lineage_edge_id)
        REFERENCES passage_lineage_edges(workspace_id,corpus_id,document_id,lineage_edge_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,old_document_version_id)
        REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,new_document_version_id)
        REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,old_passage_version_id)
        REFERENCES passage_versions(workspace_id,corpus_id,document_id,passage_version_id),
      FOREIGN KEY(workspace_id,corpus_id,document_id,new_passage_version_id)
        REFERENCES passage_versions(workspace_id,corpus_id,document_id,passage_version_id),
      FOREIGN KEY(workspace_id,corpus_id,applicability_change_id)
        REFERENCES applicability_changes(workspace_id,corpus_id,applicability_change_id),
      CHECK(change_span_id ~ '^cs:[a-z0-9][a-z0-9_.-]{0,63}:[0-9]{4,}$'),
      CHECK(kind IN ('ADDED','DELETED','MODIFIED','MOVED','SPLIT','MERGED','REFORMATTED',
        'DOCUMENT_ADDED','DOCUMENT_DELETED','EXPANDED_UNCERTAIN','AUTHORITY_CHANGED')),
      CHECK(alignment_confidence IN ('HIGH','LOW')),
      CHECK(origin IN ('LATEST_OBSERVED','TIMELINE','EXPANSION','AUTHORITY')),
      CHECK((old_start IS NULL AND old_end IS NULL AND old_text IS NULL) OR
        (old_start>=0 AND old_end>old_start AND char_length(old_text)=old_end-old_start)),
      CHECK((new_start IS NULL AND new_end IS NULL AND new_text IS NULL) OR
        (new_start>=0 AND new_end>new_start AND char_length(new_text)=new_end-new_start)),
      CHECK(kind='AUTHORITY_CHANGED' OR old_text IS NOT NULL OR new_text IS NOT NULL),
      CHECK(effective_to IS NULL OR effective_to>effective_from));
    CREATE INDEX change_event_idx ON change_spans(workspace_id,corpus_id,update_event_id,span_ordinal);
    CREATE INDEX applicability_event_idx ON applicability_changes(workspace_id,corpus_id,update_event_id,change_ordinal);
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_corpus_mutation()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
