# ruff: noqa: E501
"""Scope applicability FKs and reclassify 0003 timeline alignments out of lineage."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, NoReturn

from alembic import op
from sqlalchemy import text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in op.get_bind().execute(text(sql), params).mappings()]


def _abort(code: str, details: list[str]) -> NoReturn:
    suffix = ",".join(details)
    raise RuntimeError(f"{code}:{suffix}" if suffix else code)


def _audit_constraints() -> None:
    checks = {
        "applicability_document_fk": "SELECT count(*) n FROM applicability_changes a LEFT JOIN documents d USING(workspace_id,corpus_id,document_id) WHERE d.document_id IS NULL",
        "applicability_old_version_fk": "SELECT count(*) n FROM applicability_changes a LEFT JOIN document_versions v ON v.workspace_id=a.workspace_id AND v.corpus_id=a.corpus_id AND v.document_id=a.document_id AND v.document_version_id=a.old_effective_version_id WHERE a.old_effective_version_id IS NOT NULL AND v.document_version_id IS NULL",
        "applicability_new_version_fk": "SELECT count(*) n FROM applicability_changes a LEFT JOIN document_versions v ON v.workspace_id=a.workspace_id AND v.corpus_id=a.corpus_id AND v.document_id=a.document_id AND v.document_version_id=a.new_effective_version_id WHERE a.new_effective_version_id IS NOT NULL AND v.document_version_id IS NULL",
        "applicability_event_document_uq": "SELECT count(*) n FROM (SELECT 1 FROM applicability_changes GROUP BY workspace_id,corpus_id,update_event_id,document_id,applicability_change_id HAVING count(*)>1) q",
        "lineage_event_document_uq": "SELECT count(*) n FROM (SELECT 1 FROM passage_lineage_edges GROUP BY workspace_id,corpus_id,update_event_id,document_id,lineage_edge_id HAVING count(*)>1) q",
        "passage_document_version_uq": "SELECT count(*) n FROM (SELECT 1 FROM passage_versions GROUP BY workspace_id,corpus_id,document_id,document_version_id,passage_version_id HAVING count(*)>1) q",
        "change_span_applicability_fk_v2": "SELECT count(*) n FROM change_spans s LEFT JOIN applicability_changes a ON a.workspace_id=s.workspace_id AND a.corpus_id=s.corpus_id AND a.update_event_id=s.update_event_id AND a.document_id=s.document_id AND a.applicability_change_id=s.applicability_change_id WHERE s.applicability_change_id IS NOT NULL AND a.applicability_change_id IS NULL",
        "change_span_lineage_fk_v2": "SELECT count(*) n FROM change_spans s LEFT JOIN passage_lineage_edges e ON e.workspace_id=s.workspace_id AND e.corpus_id=s.corpus_id AND e.update_event_id=s.update_event_id AND e.document_id=s.document_id AND e.lineage_edge_id=s.lineage_edge_id WHERE s.lineage_edge_id IS NOT NULL AND e.lineage_edge_id IS NULL",
    }
    failures: list[str] = []
    for name, sql in checks.items():
        count = _rows(sql)[0]["n"]
        if count:
            failures.append(f"{name}={count}")
    if failures:
        _abort("CONSTRAINT_AUDIT", failures)


def _members(edge: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(
        """SELECT m.side,m.member_ordinal,m.passage_version_id,p.document_version_id,p.lineage_id
        FROM passage_lineage_edge_members m
        JOIN passage_versions p USING(workspace_id,corpus_id,document_id,passage_version_id)
        WHERE m.workspace_id=:w AND m.corpus_id=:c AND m.lineage_edge_id=:edge
        ORDER BY m.side,m.member_ordinal""",
        w=edge["workspace_id"],
        c=edge["corpus_id"],
        edge=edge["lineage_edge_id"],
    )


def _passages(workspace: Any, corpus: str, version: str | None) -> set[str]:
    if version is None:
        return set()
    return {
        row["passage_version_id"]
        for row in _rows(
            "SELECT passage_version_id FROM passage_versions WHERE workspace_id=:w AND corpus_id=:c AND document_version_id=:v",
            w=workspace,
            c=corpus,
            v=version,
        )
    }


def _consume(
    edges: list[dict[str, Any]], start: int, old_ids: set[str], new_ids: set[str]
) -> tuple[int, list[tuple[dict[str, Any], list[dict[str, Any]]]]]:
    seen = {"OLD": set(), "NEW": set()}
    expected = {"OLD": old_ids, "NEW": new_ids}
    block: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    position = start
    while position < len(edges) and (seen["OLD"] != old_ids or seen["NEW"] != new_ids):
        edge = edges[position]
        members = _members(edge)
        for member in members:
            side, passage = member["side"], member["passage_version_id"]
            if passage not in expected[side] or passage in seen[side]:
                _abort("TIMELINE_LAYOUT", [edge["lineage_edge_id"], "coverage=1"])
            seen[side].add(passage)
        block.append((edge, members))
        position += 1
    if seen["OLD"] != old_ids or seen["NEW"] != new_ids:
        _abort("TIMELINE_LAYOUT", [f"edge_start={start}", "coverage=1"])
    return position, block


def _latest_pair(group: dict[str, Any]) -> tuple[str | None, str | None]:
    params = {
        "w": group["workspace_id"],
        "c": group["corpus_id"],
        "e": group["update_event_id"],
        "d": group["document_id"],
    }
    new_rows = _rows(
        "SELECT document_version_id FROM snapshot_changes WHERE workspace_id=:w AND corpus_id=:c AND update_event_id=:e AND document_id=:d",
        **params,
    )
    if len(new_rows) != 1:
        _abort(
            "TIMELINE_LAYOUT",
            [group["update_event_id"], group["document_id"], f"snapshot_change={len(new_rows)}"],
        )
    delivered = _rows(
        """SELECT document_version_id,is_deletion,known_at_seq FROM document_versions
        WHERE workspace_id=:w AND corpus_id=:c AND document_id=:d AND document_version_id=:v""",
        w=group["workspace_id"],
        c=group["corpus_id"],
        d=group["document_id"],
        v=new_rows[0]["document_version_id"],
    )
    if not delivered:
        _abort(
            "TIMELINE_LAYOUT",
            [group["update_event_id"], group["document_id"], "delivered_version=0"],
        )
    current = delivered[0]
    new_side = None if current["is_deletion"] else current["document_version_id"]
    prior = _rows(
        """SELECT document_version_id FROM document_versions
        WHERE workspace_id=:w AND corpus_id=:c AND document_id=:d
          AND known_at_seq<:seq AND NOT is_deletion
        ORDER BY source_seq DESC LIMIT 1""",
        w=group["workspace_id"],
        c=group["corpus_id"],
        d=group["document_id"],
        seq=current["known_at_seq"],
    )
    old_side = prior[0]["document_version_id"] if prior else None
    return old_side, new_side


def _reclassify_legacy() -> None:
    groups = _rows(
        "SELECT DISTINCT workspace_id,corpus_id,update_event_id,document_id FROM passage_lineage_edges ORDER BY workspace_id,corpus_id,update_event_id,document_id"
    )
    ordinals: dict[tuple[Any, str, str], int] = defaultdict(int)
    classified: dict[tuple[Any, str, str, str], tuple[str, str]] = {}
    for group in groups:
        params = {
            "w": group["workspace_id"],
            "c": group["corpus_id"],
            "e": group["update_event_id"],
            "d": group["document_id"],
        }
        edges = _rows(
            "SELECT * FROM passage_lineage_edges WHERE workspace_id=:w AND corpus_id=:c AND update_event_id=:e AND document_id=:d ORDER BY edge_ordinal",
            **params,
        )
        old_side, new_side = _latest_pair(group)
        position, latest = _consume(
            edges,
            0,
            _passages(group["workspace_id"], group["corpus_id"], old_side),
            _passages(group["workspace_id"], group["corpus_id"], new_side),
        )
        for edge, members in latest:
            if edge["relation"] in ("IDENTICAL", "MOVED", "REFORMATTED", "MODIFIED"):
                old_member = next(item for item in members if item["side"] == "OLD")
                new_member = next(item for item in members if item["side"] == "NEW")
                if old_member["lineage_id"] != new_member["lineage_id"]:
                    _abort("LINEAGE_OVERWRITE", [edge["lineage_edge_id"], "count=1"])
        latest_pair = (old_side, new_side)
        changes = _rows(
            """SELECT applicability_change_id,old_effective_version_id,new_effective_version_id
            FROM applicability_changes
            WHERE workspace_id=:w AND corpus_id=:c AND update_event_id=:e AND document_id=:d
              AND old_effective_version_id IS NOT NULL AND new_effective_version_id IS NOT NULL
            ORDER BY change_ordinal""",
            **params,
        )
        for change in changes:
            pair = (change["old_effective_version_id"], change["new_effective_version_id"])
            if pair == latest_pair:
                continue
            position, block = _consume(
                edges,
                position,
                _passages(group["workspace_id"], group["corpus_id"], pair[0]),
                _passages(group["workspace_id"], group["corpus_id"], pair[1]),
            )
            for edge, members in block:
                key = (group["workspace_id"], group["corpus_id"], group["update_event_id"])
                ordinals[key] += 1
                identifier = (
                    f"ta:{group['update_event_id'].removeprefix('upd:')}:{ordinals[key]:04d}"
                )
                reason = edge["reason"]
                reason_json = reason if isinstance(reason, str) else json.dumps(reason)
                op.get_bind().execute(
                    text(
                        """INSERT INTO timeline_alignment_edges(
                        workspace_id,corpus_id,document_id,update_event_id,timeline_alignment_edge_id,
                        alignment_ordinal,applicability_change_id,old_document_version_id,
                        new_document_version_id,relation,alignment_score,alignment_confidence,
                        alignment_method,reason,recorded_by,legacy_lineage_edge_id)
                        VALUES(:workspace_id,:corpus_id,:document_id,:update_event_id,:identifier,
                        :ordinal,:applicability_change_id,:old_version,:new_version,:relation,
                        :alignment_score,:alignment_confidence,:alignment_method,
                        CAST(:reason_json AS jsonb),'migration-0004-reclassification',:legacy)"""
                    ),
                    {
                        "workspace_id": edge["workspace_id"],
                        "corpus_id": edge["corpus_id"],
                        "document_id": edge["document_id"],
                        "update_event_id": edge["update_event_id"],
                        "identifier": identifier,
                        "ordinal": ordinals[key],
                        "applicability_change_id": change["applicability_change_id"],
                        "old_version": change["old_effective_version_id"],
                        "new_version": change["new_effective_version_id"],
                        "relation": edge["relation"],
                        "alignment_score": edge["alignment_score"],
                        "alignment_confidence": edge["alignment_confidence"],
                        "alignment_method": edge["alignment_method"],
                        "reason_json": reason_json,
                        "legacy": edge["lineage_edge_id"],
                    },
                )
                for member in members:
                    op.get_bind().execute(
                        text(
                            """INSERT INTO timeline_alignment_edge_members(
                            workspace_id,corpus_id,document_id,timeline_alignment_edge_id,
                            document_version_id,passage_version_id,side,member_ordinal)
                            VALUES(:w,:c,:d,:edge,:version,:passage,:side,:ordinal)"""
                        ),
                        {
                            "w": group["workspace_id"],
                            "c": group["corpus_id"],
                            "d": group["document_id"],
                            "edge": identifier,
                            "version": member["document_version_id"],
                            "passage": member["passage_version_id"],
                            "side": member["side"],
                            "ordinal": member["member_ordinal"],
                        },
                    )
                classified[
                    (
                        group["workspace_id"],
                        group["corpus_id"],
                        group["update_event_id"],
                        edge["lineage_edge_id"],
                    )
                ] = (identifier, change["applicability_change_id"])
        if position != len(edges):
            _abort(
                "TIMELINE_LAYOUT",
                [
                    group["update_event_id"],
                    group["document_id"],
                    f"unclassified={len(edges) - position}",
                ],
            )
    unexplained: list[str] = []
    for span in _rows(
        "SELECT workspace_id,corpus_id,update_event_id,change_span_id,lineage_edge_id,applicability_change_id FROM change_spans WHERE origin='TIMELINE'"
    ):
        value = classified.get(
            (
                span["workspace_id"],
                span["corpus_id"],
                span["update_event_id"],
                span["lineage_edge_id"],
            )
        )
        if value is None or value[1] != span["applicability_change_id"]:
            unexplained.append(span["change_span_id"])
    if unexplained:
        _abort("UNEXPLAINED_TIMELINE_SPAN", [*unexplained, f"count={len(unexplained)}"])


def upgrade() -> None:
    _audit_constraints()
    op.get_bind().exec_driver_sql("""
    ALTER TABLE passage_versions ADD COLUMN norm_version TEXT;
    ALTER TABLE change_spans ADD COLUMN timeline_alignment_edge_id TEXT;
    ALTER TABLE change_spans ADD COLUMN feature_version TEXT;
    ALTER TABLE applicability_changes ADD CONSTRAINT applicability_event_document_uq UNIQUE(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id), ADD CONSTRAINT applicability_event_document_versions_uq UNIQUE(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,old_effective_version_id,new_effective_version_id), ADD CONSTRAINT applicability_document_fk FOREIGN KEY(workspace_id,corpus_id,document_id) REFERENCES documents(workspace_id,corpus_id,document_id), ADD CONSTRAINT applicability_old_version_fk FOREIGN KEY(workspace_id,corpus_id,document_id,old_effective_version_id) REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id), ADD CONSTRAINT applicability_new_version_fk FOREIGN KEY(workspace_id,corpus_id,document_id,new_effective_version_id) REFERENCES document_versions(workspace_id,corpus_id,document_id,document_version_id);
    ALTER TABLE passage_lineage_edges ADD CONSTRAINT lineage_event_document_uq UNIQUE(workspace_id,corpus_id,update_event_id,document_id,lineage_edge_id);
    ALTER TABLE passage_versions ADD CONSTRAINT passage_document_version_uq UNIQUE(workspace_id,corpus_id,document_id,document_version_id,passage_version_id);
    ALTER TABLE change_spans ADD CONSTRAINT change_span_applicability_fk_v2 FOREIGN KEY(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id) REFERENCES applicability_changes(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id), ADD CONSTRAINT change_span_lineage_fk_v2 FOREIGN KEY(workspace_id,corpus_id,update_event_id,document_id,lineage_edge_id) REFERENCES passage_lineage_edges(workspace_id,corpus_id,update_event_id,document_id,lineage_edge_id);
    CREATE TABLE timeline_alignment_edges (workspace_id UUID NOT NULL,corpus_id TEXT NOT NULL,document_id TEXT NOT NULL,update_event_id TEXT NOT NULL,timeline_alignment_edge_id TEXT NOT NULL,alignment_ordinal INTEGER NOT NULL CHECK(alignment_ordinal>0),applicability_change_id TEXT NOT NULL,old_document_version_id TEXT NOT NULL,new_document_version_id TEXT NOT NULL,relation TEXT NOT NULL,alignment_score DOUBLE PRECISION,alignment_confidence TEXT NOT NULL,alignment_method TEXT NOT NULL,reason JSONB NOT NULL CHECK(jsonb_typeof(reason)='object'),recorded_by TEXT NOT NULL CHECK(recorded_by IN ('timeline-v1','migration-0004-reclassification')),legacy_lineage_edge_id TEXT,PRIMARY KEY(workspace_id,corpus_id,timeline_alignment_edge_id),UNIQUE(workspace_id,corpus_id,update_event_id,alignment_ordinal),UNIQUE(workspace_id,corpus_id,document_id,timeline_alignment_edge_id),FOREIGN KEY(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,old_document_version_id,new_document_version_id) REFERENCES applicability_changes(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,old_effective_version_id,new_effective_version_id),FOREIGN KEY(workspace_id,corpus_id,update_event_id,document_id,legacy_lineage_edge_id) REFERENCES passage_lineage_edges(workspace_id,corpus_id,update_event_id,document_id,lineage_edge_id),CHECK(timeline_alignment_edge_id ~ '^ta:[a-z0-9][a-z0-9_.-]{0,63}:[0-9]{4,}$'));
    CREATE TABLE timeline_alignment_edge_members (workspace_id UUID NOT NULL,corpus_id TEXT NOT NULL,document_id TEXT NOT NULL,timeline_alignment_edge_id TEXT NOT NULL,document_version_id TEXT NOT NULL,passage_version_id TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN ('OLD','NEW')),member_ordinal INTEGER NOT NULL CHECK(member_ordinal>0),PRIMARY KEY(workspace_id,corpus_id,timeline_alignment_edge_id,side,member_ordinal),UNIQUE(workspace_id,corpus_id,timeline_alignment_edge_id,side,passage_version_id),FOREIGN KEY(workspace_id,corpus_id,document_id,timeline_alignment_edge_id) REFERENCES timeline_alignment_edges(workspace_id,corpus_id,document_id,timeline_alignment_edge_id),FOREIGN KEY(workspace_id,corpus_id,document_id,document_version_id,passage_version_id) REFERENCES passage_versions(workspace_id,corpus_id,document_id,document_version_id,passage_version_id));
    ALTER TABLE change_spans ADD CONSTRAINT change_span_timeline_fk_v2 FOREIGN KEY(workspace_id,corpus_id,document_id,timeline_alignment_edge_id) REFERENCES timeline_alignment_edges(workspace_id,corpus_id,document_id,timeline_alignment_edge_id);
    ALTER TABLE passage_versions ADD CONSTRAINT passage_norm_version_ck CHECK(norm_version IS NOT NULL AND norm_version='norm-v1') NOT VALID;
    ALTER TABLE change_spans ADD CONSTRAINT change_span_feature_version_ck CHECK(feature_version IS NOT NULL AND feature_version='features-v1') NOT VALID;
    ALTER TABLE change_spans ADD CONSTRAINT change_span_timeline_alignment_ck CHECK(origin<>'TIMELINE' OR (lineage_edge_id IS NULL AND timeline_alignment_edge_id IS NOT NULL)) NOT VALID;
    ALTER TABLE timeline_alignment_edges ENABLE ROW LEVEL SECURITY; ALTER TABLE timeline_alignment_edge_members ENABLE ROW LEVEL SECURITY;
    CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON timeline_alignment_edges FOR EACH ROW EXECUTE FUNCTION reject_corpus_mutation(); CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON timeline_alignment_edge_members FOR EACH ROW EXECUTE FUNCTION reject_corpus_mutation();
    """)
    _reclassify_legacy()


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
    ALTER TABLE change_spans DROP CONSTRAINT change_span_timeline_fk_v2;
    DROP TABLE timeline_alignment_edge_members; DROP TABLE timeline_alignment_edges;
    ALTER TABLE change_spans DROP CONSTRAINT change_span_timeline_alignment_ck,DROP CONSTRAINT change_span_feature_version_ck,DROP CONSTRAINT change_span_lineage_fk_v2,DROP CONSTRAINT change_span_applicability_fk_v2,DROP COLUMN feature_version,DROP COLUMN timeline_alignment_edge_id;
    ALTER TABLE passage_versions DROP CONSTRAINT passage_norm_version_ck,DROP CONSTRAINT passage_document_version_uq,DROP COLUMN norm_version;
    ALTER TABLE passage_lineage_edges DROP CONSTRAINT lineage_event_document_uq;
    ALTER TABLE applicability_changes DROP CONSTRAINT applicability_new_version_fk,DROP CONSTRAINT applicability_old_version_fk,DROP CONSTRAINT applicability_document_fk,DROP CONSTRAINT applicability_event_document_versions_uq,DROP CONSTRAINT applicability_event_document_uq;
    """)
