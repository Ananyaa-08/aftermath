"""Bind timeline spans to their update event and guard destructive downgrade."""

from __future__ import annotations

from typing import NoReturn

from alembic import op
from sqlalchemy import text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _abort(code: str, count: int) -> NoReturn:
    raise RuntimeError(f"{code}:count={count}")


def _audit_timeline_span_scope() -> None:
    count = (
        op.get_bind()
        .execute(
            text(
                """SELECT count(*)
            FROM change_spans s
            LEFT JOIN timeline_alignment_edges t
              ON t.workspace_id=s.workspace_id
             AND t.corpus_id=s.corpus_id
             AND t.update_event_id=s.update_event_id
             AND t.document_id=s.document_id
             AND t.timeline_alignment_edge_id=s.timeline_alignment_edge_id
            WHERE s.timeline_alignment_edge_id IS NOT NULL
              AND t.timeline_alignment_edge_id IS NULL"""
            )
        )
        .scalar_one()
    )
    if count:
        _abort("TIMELINE_SPAN_SCOPE_AUDIT", count)


def _audit_timeline_classification() -> None:
    count = (
        op.get_bind()
        .execute(
            text(
                """SELECT count(*) FROM timeline_alignment_edges
            WHERE (recorded_by='timeline-v1' AND legacy_lineage_edge_id IS NOT NULL)
               OR (recorded_by='migration-0004-reclassification'
                   AND legacy_lineage_edge_id IS NULL)"""
            )
        )
        .scalar_one()
    )
    if count:
        _abort("TIMELINE_CLASSIFICATION_AUDIT", count)


def upgrade() -> None:
    _audit_timeline_span_scope()
    _audit_timeline_classification()
    op.get_bind().exec_driver_sql("""
    ALTER TABLE timeline_alignment_edges
      ADD CONSTRAINT timeline_event_document_uq
      UNIQUE(workspace_id,corpus_id,update_event_id,document_id,timeline_alignment_edge_id),
      ADD CONSTRAINT timeline_recording_classification_ck
      CHECK(
        (recorded_by='timeline-v1' AND legacy_lineage_edge_id IS NULL)
        OR
        (recorded_by='migration-0004-reclassification' AND legacy_lineage_edge_id IS NOT NULL)
      );
    ALTER TABLE change_spans
      DROP CONSTRAINT change_span_timeline_fk_v2,
      ADD CONSTRAINT change_span_timeline_fk_v3
      FOREIGN KEY(
        workspace_id,corpus_id,update_event_id,document_id,timeline_alignment_edge_id
      ) REFERENCES timeline_alignment_edges(
        workspace_id,corpus_id,update_event_id,document_id,timeline_alignment_edge_id
      );
    """)


def downgrade() -> None:
    native = (
        op.get_bind()
        .execute(
            text("SELECT count(*) FROM timeline_alignment_edges WHERE recorded_by='timeline-v1'")
        )
        .scalar_one()
    )
    if native:
        _abort("UNSAFE_DOWNGRADE_NATIVE_TIMELINE_ALIGNMENT", native)
    op.get_bind().exec_driver_sql("""
    ALTER TABLE change_spans
      DROP CONSTRAINT change_span_timeline_fk_v3,
      ADD CONSTRAINT change_span_timeline_fk_v2
      FOREIGN KEY(workspace_id,corpus_id,document_id,timeline_alignment_edge_id)
      REFERENCES timeline_alignment_edges(
        workspace_id,corpus_id,document_id,timeline_alignment_edge_id
      );
    ALTER TABLE timeline_alignment_edges
      DROP CONSTRAINT timeline_recording_classification_ck,
      DROP CONSTRAINT timeline_event_document_uq;
    """)
