# ruff: noqa: E501
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from aftermath.core.changes import (
    AlignmentEdge,
    ApplicabilityChange,
    ChangeSet,
    ChangeSpan,
    PassageVersion,
    TimelineAlignment,
)
from aftermath.core.corpus import (
    CorpusRecord,
    Delivery,
    DeliveryResult,
    DocumentRecord,
    Snapshot,
    Version,
    WorkspaceRecord,
)
from aftermath.core.errors import DomainError
from aftermath.core.text import bytes_hash, canonical_json
from aftermath.ports.corpus import CorpusRepository


class PostgresCorpusStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[CorpusRepository]:
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout='10000ms'"))
                yield PostgresCorpusRepository(connection)
        except SQLAlchemyError:
            raise DomainError(
                "STORAGE_FAILURE", "Storage operation could not complete", 503
            ) from None


class PostgresCorpusRepository:
    def __init__(self, connection: Connection):
        self.db = connection

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(text(sql), params).mappings()]

    def run(self, sql: str, **params: Any) -> int:
        return self.db.execute(text(sql), params).rowcount

    def authorize(self, workspace: UUID, principal: str) -> None:
        if not self.rows(
            "SELECT 1 FROM workspace_members WHERE workspace_id=:w AND principal=:p",
            w=workspace,
            p=principal,
        ):
            raise DomainError("NOT_FOUND", "Workspace not found or not accessible", 404)

    def workspace(self, workspace: UUID) -> WorkspaceRecord:
        rows = self.rows("SELECT * FROM workspaces WHERE id=:w", w=workspace)
        if not rows:
            raise DomainError("NOT_FOUND", "Workspace not found", 404)
        return WorkspaceRecord.model_validate(rows[0])

    def workspaces(self, principal: str, limit: int, offset: int) -> list[WorkspaceRecord]:
        return [
            WorkspaceRecord.model_validate(row)
            for row in self.rows(
                "SELECT w.* FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id "
                "WHERE m.principal=:p ORDER BY w.created_at,w.id LIMIT :lim OFFSET :off",
                p=principal,
                lim=limit,
                off=offset,
            )
        ]

    def create_workspace(self, principal: str, name: str) -> WorkspaceRecord:
        identifier = uuid4()
        result = self.rows(
            "INSERT INTO workspaces(id,name) VALUES(:id,:name) RETURNING *",
            id=identifier,
            name=name,
        )[0]
        self.run("INSERT INTO workspace_members VALUES(:w,:p)", w=identifier, p=principal)
        return WorkspaceRecord.model_validate(result)

    def create_corpus(self, workspace: UUID, corpus: str, name: str) -> CorpusRecord:
        if self.rows(
            "SELECT 1 FROM corpora WHERE workspace_id=:w AND corpus_id=:c", w=workspace, c=corpus
        ):
            raise DomainError("CORPUS_EXISTS", "Corpus identifier already exists", 409)
        self.run(
            "INSERT INTO corpora(workspace_id,corpus_id,name) VALUES(:w,:c,:name)",
            w=workspace,
            c=corpus,
            name=name,
        )
        return self.corpus(workspace, corpus)

    def corpora(self, workspace: UUID, limit: int, offset: int) -> list[CorpusRecord]:
        return [
            self.corpus(workspace, row["corpus_id"])
            for row in self.rows(
                "SELECT corpus_id FROM corpora WHERE workspace_id=:w ORDER BY corpus_id "
                "LIMIT :lim OFFSET :off",
                w=workspace,
                lim=limit,
                off=offset,
            )
        ]

    def corpus(self, workspace: UUID, corpus: str, lock: bool = False) -> CorpusRecord:
        rows = self.rows(
            "SELECT * FROM corpora WHERE workspace_id=:w AND corpus_id=:c"
            + (" FOR UPDATE" if lock else ""),
            w=workspace,
            c=corpus,
        )
        if not rows:
            raise DomainError("NOT_FOUND", "Corpus not found", 404)
        counts = self.rows(
            """SELECT
          (SELECT count(*) FROM snapshot_documents m JOIN document_versions v
           USING(workspace_id,corpus_id,document_id,document_version_id)
           WHERE m.workspace_id=:w AND m.corpus_id=:c AND m.snapshot_id=:s AND NOT v.is_deletion)
          document_count,
          (SELECT count(*) FROM document_versions WHERE workspace_id=:w AND corpus_id=:c)
          version_count""",
            w=workspace,
            c=corpus,
            s=rows[0]["head_snapshot_id"],
        )[0]
        return CorpusRecord.model_validate({**rows[0], **counts})

    def versions(self, workspace: UUID, corpus: str, document: str) -> list[Version]:
        return [
            Version.model_validate(row)
            for row in self.rows(
                "SELECT * FROM document_versions WHERE workspace_id=:w AND corpus_id=:c "
                "AND document_id=:d ORDER BY source_seq",
                w=workspace,
                c=corpus,
                d=document,
            )
        ]

    def passages(self, workspace: UUID, corpus: str, document_version: str) -> list[PassageVersion]:
        values = self.rows(
            'SELECT *,start_offset start,end_offset "end" FROM passage_versions '
            "WHERE workspace_id=:w AND corpus_id=:c AND document_version_id=:v ORDER BY ordinal",
            w=workspace,
            c=corpus,
            v=document_version,
        )
        return [
            PassageVersion.model_validate(
                {k: v for k, v in row.items() if k not in ("start_offset", "end_offset")}
            )
            for row in values
        ]

    def update_events(
        self, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[dict[str, object]]:
        return self.rows(
            """SELECT e.delivery_id,e.update_event_id,e.as_of,e.expected_head,e.received_at,
            l.status,l.snapshot_id,l.error_code
            FROM update_events e JOIN LATERAL (
              SELECT status,snapshot_id,error_code FROM update_event_status_log
              WHERE workspace_id=e.workspace_id AND corpus_id=e.corpus_id
                AND delivery_id=e.delivery_id ORDER BY id DESC LIMIT 1
            ) l ON true WHERE e.workspace_id=:w AND e.corpus_id=:c
            ORDER BY e.received_at DESC,e.delivery_id LIMIT :lim OFFSET :off""",
            w=workspace,
            c=corpus,
            lim=limit,
            off=offset,
        )

    def changed_documents(
        self, workspace: UUID, corpus: str, delivery: str
    ) -> list[dict[str, object]]:
        return self.rows(
            """SELECT sc.document_id,sc.document_version_id new_version_id,
            (SELECT pv.document_version_id FROM passage_lineage_edges e
              JOIN passage_lineage_edge_members m
                USING(workspace_id,corpus_id,document_id,lineage_edge_id)
              JOIN passage_versions pv
                USING(workspace_id,corpus_id,document_id,passage_version_id)
              WHERE e.workspace_id=sc.workspace_id AND e.corpus_id=sc.corpus_id
                AND e.update_event_id=sc.update_event_id AND e.document_id=sc.document_id
                AND m.side='OLD' ORDER BY e.edge_ordinal,m.member_ordinal LIMIT 1) old_version_id,
            count(DISTINCT s.change_span_id)::integer span_count,
            count(DISTINCT a.applicability_change_id)::integer applicability_count
            FROM snapshot_changes sc
            LEFT JOIN change_spans s USING(workspace_id,corpus_id,update_event_id,document_id)
            LEFT JOIN applicability_changes a USING(workspace_id,corpus_id,update_event_id,document_id)
            WHERE sc.workspace_id=:w AND sc.corpus_id=:c AND sc.update_event_id=:event
            GROUP BY sc.workspace_id,sc.corpus_id,sc.update_event_id,sc.document_id,
              sc.document_version_id ORDER BY sc.document_id""",
            w=workspace,
            c=corpus,
            event="upd:" + delivery,
        )

    def lineage_edges(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[AlignmentEdge]:
        rows = self.rows(
            "SELECT e.* FROM passage_lineage_edges e WHERE workspace_id=:w AND corpus_id=:c "
            "AND update_event_id=:event AND (CAST(:doc AS TEXT) IS NULL OR document_id=:doc) "
            "AND NOT EXISTS (SELECT 1 FROM timeline_alignment_edges t WHERE "
            "t.workspace_id=e.workspace_id AND t.corpus_id=e.corpus_id "
            "AND t.legacy_lineage_edge_id=e.lineage_edge_id) "
            "ORDER BY edge_ordinal",
            w=workspace,
            c=corpus,
            event="upd:" + delivery,
            doc=document,
        )
        for row in rows:
            members = self.rows(
                "SELECT passage_version_id,side FROM passage_lineage_edge_members "
                "WHERE workspace_id=:w AND corpus_id=:c AND lineage_edge_id=:edge "
                "ORDER BY side,member_ordinal",
                w=workspace,
                c=corpus,
                edge=row["lineage_edge_id"],
            )
            row["from_passage_version_ids"] = tuple(
                item["passage_version_id"] for item in members if item["side"] == "OLD"
            )
            row["to_passage_version_ids"] = tuple(
                item["passage_version_id"] for item in members if item["side"] == "NEW"
            )
        return [AlignmentEdge.model_validate(row) for row in rows]

    def timeline_alignments(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[TimelineAlignment]:
        rows = self.rows(
            "SELECT * FROM timeline_alignment_edges WHERE workspace_id=:w AND corpus_id=:c "
            "AND update_event_id=:event AND (CAST(:doc AS TEXT) IS NULL OR document_id=:doc) "
            "ORDER BY alignment_ordinal",
            w=workspace,
            c=corpus,
            event="upd:" + delivery,
            doc=document,
        )
        for row in rows:
            members = self.rows(
                "SELECT passage_version_id,side FROM timeline_alignment_edge_members "
                "WHERE workspace_id=:w AND corpus_id=:c AND timeline_alignment_edge_id=:alignment "
                "ORDER BY side,member_ordinal",
                w=workspace,
                c=corpus,
                alignment=row["timeline_alignment_edge_id"],
            )
            row["from_passage_version_ids"] = tuple(
                item["passage_version_id"] for item in members if item["side"] == "OLD"
            )
            row["to_passage_version_ids"] = tuple(
                item["passage_version_id"] for item in members if item["side"] == "NEW"
            )
        return [TimelineAlignment.model_validate(row) for row in rows]

    def change_spans(
        self,
        workspace: UUID,
        corpus: str,
        delivery: str,
        document: str | None,
        limit: int,
        offset: int,
    ) -> list[ChangeSpan]:
        rows = self.rows(
            """SELECT *,old_start old_start_value,old_end old_end_value,
            new_start new_start_value,new_end new_end_value FROM change_spans
            WHERE workspace_id=:w AND corpus_id=:c AND update_event_id=:event
            AND (CAST(:doc AS TEXT) IS NULL OR document_id=:doc)
            ORDER BY span_ordinal LIMIT :lim OFFSET :off""",
            w=workspace,
            c=corpus,
            event="upd:" + delivery,
            doc=document,
            lim=limit,
            off=offset,
        )
        for row in rows:
            if row["origin"] == "TIMELINE" and row["lineage_edge_id"] is not None:
                reclassified = self.rows(
                    "SELECT timeline_alignment_edge_id FROM timeline_alignment_edges "
                    "WHERE workspace_id=:w AND corpus_id=:c "
                    "AND legacy_lineage_edge_id=:edge",
                    w=workspace,
                    c=corpus,
                    edge=row["lineage_edge_id"],
                )
                if reclassified:
                    row["timeline_alignment_edge_id"] = reclassified[0][
                        "timeline_alignment_edge_id"
                    ]
                    row["reclassified_lineage_edge_id"] = row["lineage_edge_id"]
        return [
            ChangeSpan.model_validate(
                {
                    **{k: v for k, v in row.items() if not k.endswith("_value")},
                    "old_start": row["old_start_value"],
                    "old_end": row["old_end_value"],
                    "new_start": row["new_start_value"],
                    "new_end": row["new_end_value"],
                }
            )
            for row in rows
        ]

    def applicability_changes(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[ApplicabilityChange]:
        return [
            ApplicabilityChange.model_validate(row)
            for row in self.rows(
                "SELECT * FROM applicability_changes WHERE workspace_id=:w AND corpus_id=:c "
                "AND update_event_id=:event AND (CAST(:doc AS TEXT) IS NULL OR document_id=:doc) "
                "ORDER BY change_ordinal",
                w=workspace,
                c=corpus,
                event="upd:" + delivery,
                doc=document,
            )
        ]

    def documents(
        self, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[DocumentRecord]:
        return [
            DocumentRecord.model_validate(row)
            for row in self.rows(
                """
          SELECT DISTINCT ON (document_id) document_id,document_version_id latest_version_id,
          source_seq,is_deletion,count(*) OVER (PARTITION BY document_id) version_count
          FROM document_versions WHERE workspace_id=:w AND corpus_id=:c
          ORDER BY document_id,source_seq DESC LIMIT :lim OFFSET :off""",
                w=workspace,
                c=corpus,
                lim=limit,
                off=offset,
            )
        ]

    def snapshots(self, workspace: UUID, corpus: str, limit: int, offset: int) -> list[Snapshot]:
        return [
            Snapshot.model_validate({k: v for k, v in row.items() if k != "created_txid"})
            for row in self.rows(
                "SELECT * FROM snapshots WHERE workspace_id=:w AND corpus_id=:c "
                "ORDER BY snapshot_seq DESC LIMIT :lim OFFSET :off",
                w=workspace,
                c=corpus,
                lim=limit,
                off=offset,
            )
        ]

    def snapshot(self, workspace: UUID, corpus: str, snapshot: str) -> Snapshot:
        rows = self.rows(
            "SELECT * FROM snapshots WHERE workspace_id=:w AND corpus_id=:c AND snapshot_id=:s",
            w=workspace,
            c=corpus,
            s=snapshot,
        )
        if not rows:
            raise DomainError("NOT_FOUND", "Snapshot not found", 404)
        return Snapshot.model_validate({k: v for k, v in rows[0].items() if k != "created_txid"})

    def event(
        self, workspace: UUID, corpus: str, delivery: str
    ) -> tuple[str, DeliveryResult] | None:
        rows = self.rows(
            """SELECT e.payload_hash,l.status,l.snapshot_id,l.error_code
          FROM update_events e JOIN update_event_status_log l
          USING(workspace_id,corpus_id,delivery_id)
          WHERE e.workspace_id=:w AND e.corpus_id=:c AND e.delivery_id=:d
          ORDER BY l.id DESC LIMIT 1""",
            w=workspace,
            c=corpus,
            d=delivery,
        )
        if not rows:
            return None
        value = rows[0]
        return value["payload_hash"], DeliveryResult(
            delivery_id=delivery,
            status=value["status"],
            snapshot_id=value["snapshot_id"],
            error_code=value["error_code"],
        )

    def _event(self, workspace: UUID, corpus: str, delivery: Delivery, payload_hash: str) -> None:
        self.run(
            """INSERT INTO update_events(workspace_id,corpus_id,delivery_id,update_event_id,
          payload_hash,as_of,expected_head) VALUES(:w,:c,:d,:event,:hash,:as_of,:head)
          ON CONFLICT DO NOTHING""",
            w=workspace,
            c=corpus,
            d=delivery.delivery_id,
            event="upd:" + delivery.delivery_id,
            hash=payload_hash,
            as_of=delivery.as_of,
            head=delivery.expected_head,
        )

    def attempt(
        self, workspace: UUID, corpus: str, delivery: str, payload_hash: str, outcome: str
    ) -> None:
        self.run(
            """INSERT INTO delivery_attempts
          (workspace_id,corpus_id,delivery_id,payload_hash,outcome)
          VALUES(:w,:c,:d,:hash,:outcome)""",
            w=workspace,
            c=corpus,
            d=delivery,
            hash=payload_hash,
            outcome=outcome,
        )

    def outcome(
        self,
        workspace: UUID,
        corpus: str,
        delivery: Delivery,
        payload_hash: str,
        result: DeliveryResult,
        attempt: str,
    ) -> None:
        self._event(workspace, corpus, delivery, payload_hash)
        self.run(
            """INSERT INTO update_event_status_log(workspace_id,corpus_id,delivery_id,status,
          snapshot_id,error_code) VALUES(:w,:c,:d,:status,:s,:error)""",
            w=workspace,
            c=corpus,
            d=delivery.delivery_id,
            status=result.status,
            s=result.snapshot_id,
            error=result.error_code,
        )
        self.attempt(workspace, corpus, delivery.delivery_id, payload_hash, attempt)

    def apply(
        self,
        workspace: UUID,
        corpus: str,
        delivery: Delivery,
        payload_hash: str,
        versions: list[Version],
        sizes: dict[str, int],
        changes: ChangeSet,
    ) -> DeliveryResult:
        self._event(workspace, corpus, delivery, payload_hash)
        seq = versions[0].known_at_seq
        snapshot_id = f"snap:{seq:06d}"
        for version in versions:
            self.run(
                "INSERT INTO documents(workspace_id,corpus_id,document_id) VALUES(:w,:c,:d) "
                "ON CONFLICT DO NOTHING",
                w=workspace,
                c=corpus,
                d=version.document_id,
            )
            self.run(
                "INSERT INTO source_objects VALUES(:w,:c,:key,:size) ON CONFLICT DO NOTHING",
                w=workspace,
                c=corpus,
                key=version.object_key,
                size=sizes[version.object_key],
            )
            data = version.model_dump()
            data["authority"] = json.dumps(data["authority"])
            columns = list(data)
            values = [
                f"CAST(:{key} AS jsonb)" if key == "authority" else f":{key}" for key in columns
            ]
            self.run(
                f"INSERT INTO document_versions ({','.join(columns)}) VALUES ({','.join(values)})",
                **data,
            )
        for passage in changes.passages:
            data = passage.model_dump()
            data["start_offset"] = data.pop("start")
            data["end_offset"] = data.pop("end")
            data["section_path"] = json.dumps(data["section_path"])
            columns = list(data)
            values = [
                f"CAST(:{key} AS jsonb)" if key == "section_path" else f":{key}" for key in columns
            ]
            self.run(
                f"INSERT INTO passage_versions ({','.join(columns)}) VALUES ({','.join(values)}) "
                "ON CONFLICT DO NOTHING",
                **data,
            )
        membership = {
            row["document_id"]: row["document_version_id"]
            for row in self.rows(
                "SELECT document_id,document_version_id FROM snapshot_documents "
                "WHERE workspace_id=:w AND corpus_id=:c AND snapshot_id=:s",
                w=workspace,
                c=corpus,
                s=delivery.expected_head,
            )
        }
        membership.update({v.document_id: v.document_version_id for v in versions})
        all_versions = self.rows(
            "SELECT document_version_id,is_deletion FROM document_versions "
            "WHERE workspace_id=:w AND corpus_id=:c",
            w=workspace,
            c=corpus,
        )
        deleted = {row["document_version_id"] for row in all_versions if row["is_deletion"]}
        active = sorted([d, v] for d, v in membership.items() if v not in deleted)
        self.run(
            """INSERT INTO snapshots(workspace_id,corpus_id,snapshot_id,snapshot_seq,
          parent_snapshot_id,update_event_id,manifest_hash,document_count,as_of)
          VALUES(:w,:c,:s,:seq,:parent,:event,:hash,:count,:as_of)""",
            w=workspace,
            c=corpus,
            s=snapshot_id,
            seq=seq,
            parent=delivery.expected_head,
            event="upd:" + delivery.delivery_id,
            hash=bytes_hash(canonical_json(active)),
            count=len(active),
            as_of=delivery.as_of,
        )
        for version in versions:
            self.run(
                "INSERT INTO snapshot_changes VALUES(:w,:c,:s,:event,:d,:v)",
                w=workspace,
                c=corpus,
                s=snapshot_id,
                event="upd:" + delivery.delivery_id,
                d=version.document_id,
                v=version.document_version_id,
            )
        for edge in changes.edges:
            data = edge.model_dump(exclude={"from_passage_version_ids", "to_passage_version_ids"})
            data["reason"] = json.dumps(data["reason"])
            columns = list(data)
            values = [f"CAST(:{key} AS jsonb)" if key == "reason" else f":{key}" for key in columns]
            self.run(
                f"INSERT INTO passage_lineage_edges ({','.join(columns)}) VALUES ({','.join(values)})",
                **data,
            )
            for side, member_ids in (
                ("OLD", edge.from_passage_version_ids),
                ("NEW", edge.to_passage_version_ids),
            ):
                for ordinal, passage_id in enumerate(member_ids, 1):
                    self.run(
                        "INSERT INTO passage_lineage_edge_members VALUES(:w,:c,:d,:edge,:passage,:side,:ordinal)",
                        w=workspace,
                        c=corpus,
                        d=edge.document_id,
                        edge=edge.lineage_edge_id,
                        passage=passage_id,
                        side=side,
                        ordinal=ordinal,
                    )
        for change in changes.applicability_changes:
            data = change.model_dump()
            self.run(
                f"INSERT INTO applicability_changes ({','.join(data)}) VALUES "
                f"({','.join(':' + key for key in data)})",
                **data,
            )
        for comparison in changes.timeline_alignments:
            data = comparison.model_dump(
                exclude={"from_passage_version_ids", "to_passage_version_ids"}
            )
            data["reason"] = json.dumps(data["reason"])
            columns = list(data)
            values = [f"CAST(:{key} AS jsonb)" if key == "reason" else f":{key}" for key in columns]
            self.run(
                f"INSERT INTO timeline_alignment_edges ({','.join(columns)}) "
                f"VALUES ({','.join(values)})",
                **data,
            )
            for side, member_ids in (
                ("OLD", comparison.from_passage_version_ids),
                ("NEW", comparison.to_passage_version_ids),
            ):
                for ordinal, passage_id in enumerate(member_ids, 1):
                    self.run(
                        "INSERT INTO timeline_alignment_edge_members "
                        "VALUES(:w,:c,:d,:alignment,:version,:passage,:side,:ordinal)",
                        w=workspace,
                        c=corpus,
                        d=comparison.document_id,
                        alignment=comparison.timeline_alignment_edge_id,
                        version=(
                            comparison.old_document_version_id
                            if side == "OLD"
                            else comparison.new_document_version_id
                        ),
                        passage=passage_id,
                        side=side,
                        ordinal=ordinal,
                    )
        for span in changes.spans:
            data = span.model_dump(exclude={"reclassified_lineage_edge_id"})
            data["features"] = json.dumps(data["features"])
            data["metadata"] = json.dumps(data["metadata"])
            columns = list(data)
            values = [
                f"CAST(:{key} AS jsonb)" if key in ("features", "metadata") else f":{key}"
                for key in columns
            ]
            self.run(
                f"INSERT INTO change_spans ({','.join(columns)}) VALUES ({','.join(values)})",
                **data,
            )
        for document, version_id in membership.items():
            self.run(
                "INSERT INTO snapshot_documents VALUES(:w,:c,:s,:d,:v)",
                w=workspace,
                c=corpus,
                s=snapshot_id,
                d=document,
                v=version_id,
            )
        changed = self.run(
            "UPDATE corpora SET head_snapshot_id=:new WHERE workspace_id=:w "
            "AND corpus_id=:c AND head_snapshot_id IS NOT DISTINCT FROM :old",
            w=workspace,
            c=corpus,
            new=snapshot_id,
            old=delivery.expected_head,
        )
        if changed != 1:
            raise DomainError("STALE_HEAD", "Corpus head changed; reload before retrying", 409)
        result = DeliveryResult(
            delivery_id=delivery.delivery_id, status="APPLIED", snapshot_id=snapshot_id
        )
        self.outcome(workspace, corpus, delivery, payload_hash, result, "APPLIED")
        return result
