"""Bind each span passage to the document version on the same side."""

from alembic import op
from sqlalchemy import text

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    failures = []
    for side in ("old", "new"):
        count = (
            op.get_bind()
            .execute(
                text(f"""
                SELECT count(*) FROM change_spans s
                WHERE s.{side}_passage_version_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM passage_versions p
                  WHERE p.workspace_id=s.workspace_id AND p.corpus_id=s.corpus_id
                    AND p.document_id=s.document_id
                    AND p.document_version_id=s.{side}_document_version_id
                    AND p.passage_version_id=s.{side}_passage_version_id
                )
                """)
            )
            .scalar_one()
        )
        if count:
            failures.append(f"change_span_{side}_passage_version_fk:count={count}")
    if failures:
        raise RuntimeError("SPAN_PASSAGE_VERSION_AUDIT " + "; ".join(failures))

    # passage_document_version_uq was introduced in 0004 with this exact order.
    # MATCH SIMPLE permits genuinely absent passages (including authority spans).
    # The accompanying check prevents a non-null passage bypassing the FK with
    # a null version. Existing rows and immutable triggers are left untouched.
    for side in ("old", "new"):
        op.execute(f"""
            ALTER TABLE change_spans
              ADD CONSTRAINT change_span_{side}_passage_version_fk
              FOREIGN KEY(workspace_id,corpus_id,document_id,
                {side}_document_version_id,{side}_passage_version_id)
              REFERENCES passage_versions(workspace_id,corpus_id,document_id,
                document_version_id,passage_version_id),
              ADD CONSTRAINT change_span_{side}_passage_requires_version_ck
              CHECK({side}_passage_version_id IS NULL OR
                {side}_document_version_id IS NOT NULL)
        """)


def downgrade() -> None:
    for side in ("old", "new"):
        op.execute(f"""
            ALTER TABLE change_spans
              DROP CONSTRAINT change_span_{side}_passage_version_fk,
              DROP CONSTRAINT change_span_{side}_passage_requires_version_ck
        """)
