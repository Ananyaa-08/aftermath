from datetime import UTC, datetime
from uuid import UUID

from aftermath.application.changes import build_change_set
from aftermath.core.changes import (
    AlignmentEdge,
    ApplicabilityChange,
    ChangedDocumentView,
    ChangeSpan,
    DocumentComparison,
    TimelineAlignment,
    TimelineInterval,
    UpdateEventView,
    effective_version,
    evidence_fingerprint,
    timeline_changes,
)
from aftermath.core.corpus import (
    CorpusRecord,
    Delivery,
    DeliveryResult,
    DocumentRecord,
    EffectiveResult,
    ResolveRequest,
    Snapshot,
    Version,
    WorkspaceRecord,
    resolve_effective,
)
from aftermath.core.errors import DomainError, InvalidEncodingError
from aftermath.core.text import bytes_hash, canonical_json, canonical_text, content_hash
from aftermath.ports.corpus import CorpusStore
from aftermath.ports.interfaces import ObjectStore


class CorpusService:
    def __init__(
        self,
        store: CorpusStore,
        objects: ObjectStore,
        max_source_bytes: int = 262144,
        max_corpus_versions: int = 2000,
        max_passages_per_document: int = 500,
        max_passage_length: int = 100000,
        max_alignment_candidate_pairs: int = 20000,
        max_timeline_breakpoints: int = 1000,
        max_documents_per_delivery: int = 32,
    ):
        self.store, self.objects = store, objects
        self.max_source_bytes, self.max_corpus_versions = max_source_bytes, max_corpus_versions
        self.max_passages_per_document = max_passages_per_document
        self.max_passage_length = max_passage_length
        self.max_alignment_candidate_pairs = max_alignment_candidate_pairs
        self.max_timeline_breakpoints = max_timeline_breakpoints
        self.max_documents_per_delivery = max_documents_per_delivery

    def update_events(
        self, principal: str, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[UpdateEventView]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            repo.corpus(workspace, corpus)
            return [
                UpdateEventView.model_validate(row)
                for row in repo.update_events(workspace, corpus, limit, offset)
            ]

    def changed_documents(
        self, principal: str, workspace: UUID, corpus: str, delivery: str
    ) -> list[ChangedDocumentView]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            if not repo.event(workspace, corpus, delivery):
                raise DomainError("NOT_FOUND", "Update event not found", 404)
            return [
                ChangedDocumentView.model_validate(row)
                for row in repo.changed_documents(workspace, corpus, delivery)
            ]

    def update_event(
        self, principal: str, workspace: UUID, corpus: str, delivery: str
    ) -> UpdateEventView:
        events = self.update_events(principal, workspace, corpus, 100, 0)
        value = next((item for item in events if item.delivery_id == delivery), None)
        if value is None:
            raise DomainError("NOT_FOUND", "Update event not found", 404)
        return value

    def comparison(
        self, principal: str, workspace: UUID, corpus: str, delivery: str, document: str
    ) -> DocumentComparison:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            event = repo.event(workspace, corpus, delivery)
            if not event or not event[1].snapshot_id:
                raise DomainError("NOT_FOUND", "Applied update event not found", 404)
            changed = next(
                (
                    row
                    for row in repo.changed_documents(workspace, corpus, delivery)
                    if row["document_id"] == document
                ),
                None,
            )
            if not changed:
                raise DomainError("NOT_FOUND", "Changed document not found", 404)
            versions = repo.versions(workspace, corpus, document)
            by_id = {item.document_version_id: item for item in versions}
            new_version = by_id[str(changed["new_version_id"])]
            old_version = (
                by_id.get(str(changed["old_version_id"])) if changed["old_version_id"] else None
            )
            snapshot = repo.snapshot(workspace, corpus, event[1].snapshot_id)
            return DocumentComparison(
                delivery_id=delivery,
                document_id=document,
                parent_snapshot_id=snapshot.parent_snapshot_id,
                result_snapshot_id=snapshot.snapshot_id,
                old_version=old_version,
                new_version=new_version,
                old_passages=tuple(
                    repo.passages(workspace, corpus, old_version.document_version_id)
                )
                if old_version
                else (),
                new_passages=tuple(
                    repo.passages(workspace, corpus, new_version.document_version_id)
                ),
                edges=tuple(repo.lineage_edges(workspace, corpus, delivery, document)),
                timeline_alignments=tuple(
                    repo.timeline_alignments(workspace, corpus, delivery, document)
                ),
                spans=tuple(repo.change_spans(workspace, corpus, delivery, document, 500, 0)),
                applicability_changes=tuple(
                    repo.applicability_changes(workspace, corpus, delivery, document)
                ),
            )

    def timeline(
        self, principal: str, workspace: UUID, corpus: str, document: str, snapshot_id: str
    ) -> list[TimelineInterval]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            snapshot = repo.snapshot(workspace, corpus, snapshot_id)
            versions = [
                item
                for item in repo.versions(workspace, corpus, document)
                if item.known_at_seq <= snapshot.snapshot_seq
            ]
            if not versions:
                raise DomainError("NOT_FOUND", "Document not known at snapshot", 404)
            points = sorted({item.effective_from for item in versions})
            values: list[TimelineInterval] = []
            for index, start in enumerate(points):
                selected = effective_version(versions, start)
                values.append(
                    TimelineInterval(
                        snapshot_id=snapshot_id,
                        interval_from=start,
                        interval_to=points[index + 1] if index + 1 < len(points) else None,
                        version_id=selected.document_version_id if selected else None,
                        fingerprint=evidence_fingerprint(selected),
                        active=selected is not None,
                    )
                )
            return values

    def compare_timelines(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        document: str,
        from_snapshot: str,
        to_snapshot: str,
    ) -> list[ApplicabilityChange]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            before_snapshot = repo.snapshot(workspace, corpus, from_snapshot)
            after_snapshot = repo.snapshot(workspace, corpus, to_snapshot)
            versions = repo.versions(workspace, corpus, document)
            before = [
                item for item in versions if item.known_at_seq <= before_snapshot.snapshot_seq
            ]
            after = [item for item in versions if item.known_at_seq <= after_snapshot.snapshot_seq]
            if not after:
                raise DomainError("NOT_FOUND", "Document not known at snapshot", 404)
            return timeline_changes(
                before,
                after,
                "comparison",
                from_snapshot,
                to_snapshot,
                self.max_timeline_breakpoints,
            )

    def lineage_edges(
        self, principal: str, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[AlignmentEdge]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            if not repo.event(workspace, corpus, delivery):
                raise DomainError("NOT_FOUND", "Update event not found", 404)
            return repo.lineage_edges(workspace, corpus, delivery, document)

    def timeline_alignments(
        self, principal: str, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[TimelineAlignment]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            if not repo.event(workspace, corpus, delivery):
                raise DomainError("NOT_FOUND", "Update event not found", 404)
            return repo.timeline_alignments(workspace, corpus, delivery, document)

    def change_spans(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        delivery: str,
        document: str | None,
        limit: int,
        offset: int,
    ) -> list[ChangeSpan]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            if not repo.event(workspace, corpus, delivery):
                raise DomainError("NOT_FOUND", "Update event not found", 404)
            return repo.change_spans(workspace, corpus, delivery, document, limit, offset)

    def applicability_changes(
        self, principal: str, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[ApplicabilityChange]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            if not repo.event(workspace, corpus, delivery):
                raise DomainError("NOT_FOUND", "Update event not found", 404)
            return repo.applicability_changes(workspace, corpus, delivery, document)

    def workspace(self, principal: str, workspace: UUID) -> WorkspaceRecord:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            return repo.workspace(workspace)

    def workspaces(
        self, principal: str, limit: int = 100, offset: int = 0
    ) -> list[WorkspaceRecord]:
        with self.store.transaction() as repo:
            return repo.workspaces(principal, limit, offset)

    def create_workspace(self, principal: str, name: str) -> WorkspaceRecord:
        with self.store.transaction() as repo:
            return repo.create_workspace(principal, name)

    def create_corpus(
        self, principal: str, workspace: UUID, corpus: str, name: str
    ) -> CorpusRecord:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            return repo.create_corpus(workspace, corpus, name)

    def corpora(
        self, principal: str, workspace: UUID, limit: int = 100, offset: int = 0
    ) -> list[CorpusRecord]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            return repo.corpora(workspace, limit, offset)

    def corpus(self, principal: str, workspace: UUID, corpus: str) -> CorpusRecord:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            return repo.corpus(workspace, corpus)

    def documents(
        self, principal: str, workspace: UUID, corpus: str, limit: int = 100, offset: int = 0
    ) -> list[DocumentRecord]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            repo.corpus(workspace, corpus)
            return repo.documents(workspace, corpus, limit, offset)

    def versions(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        document: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Version]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            repo.corpus(workspace, corpus)
            versions = repo.versions(workspace, corpus, document)
            if not versions:
                raise DomainError("NOT_FOUND", "Document not found", 404)
            return versions[offset : offset + limit]

    def snapshots(
        self, principal: str, workspace: UUID, corpus: str, limit: int = 100, offset: int = 0
    ) -> list[Snapshot]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            repo.corpus(workspace, corpus)
            return repo.snapshots(workspace, corpus, limit, offset)

    def resolve(
        self, principal: str, workspace: UUID, corpus: str, document: str, request: ResolveRequest
    ) -> EffectiveResult:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            snapshot = repo.snapshot(workspace, corpus, request.snapshot_id)
            versions = repo.versions(workspace, corpus, document)
            if not versions:
                raise DomainError("NOT_FOUND", "Document not found", 404)
            return resolve_effective(versions, snapshot, request)

    def ingest(
        self, principal: str, workspace: UUID, corpus: str, delivery: Delivery
    ) -> DeliveryResult:
        payload_hash = bytes_hash(canonical_json(delivery.model_dump(mode="json")))
        if len(delivery.documents) > self.max_documents_per_delivery:
            raise DomainError("DELIVERY_LIMIT", "Delivery document limit exceeded", 413)
        phase_two = False
        authorized = False
        try:
            with self.store.transaction() as repo:
                repo.authorize(workspace, principal)
                current = repo.corpus(workspace, corpus, lock=True)
                authorized = True
                prior = repo.event(workspace, corpus, delivery.delivery_id)
                if prior:
                    if prior[0] != payload_hash:
                        raise DomainError(
                            "IDEMPOTENCY_CONFLICT", "Delivery ID has a different payload", 409
                        )
                    if prior[1].status not in ("FAILED_APPLY", "PARKED_OUT_OF_ORDER"):
                        repo.attempt(
                            workspace, corpus, delivery.delivery_id, payload_hash, "DUPLICATE"
                        )
                        return prior[1].model_copy(update={"duplicate": True})
                if current.head_snapshot_id != delivery.expected_head:
                    raise DomainError(
                        "STALE_HEAD", "Corpus head changed; reload before retrying", 409
                    )
                seq = (
                    int(current.head_snapshot_id.split(":")[1]) + 1
                    if current.head_snapshot_id
                    else 1
                )
                planned: list[Version] = []
                blobs: dict[str, bytes] = {}
                parked = False
                for revision in delivery.documents:
                    if revision.mixed_effective:
                        raise DomainError(
                            "MIXED_EFFECTIVE", "Mixed effective dates require a later pipeline"
                        )
                    if revision.withdrawal:
                        raise DomainError(
                            "CANCELLATION_UNSUPPORTED", "Withdrawal requires a replacement revision"
                        )
                    raw = revision.original_bytes()
                    if len(raw) > self.max_source_bytes:
                        raise DomainError(
                            "SOURCE_TOO_LARGE", "Source exceeds configured byte limit", 413
                        )
                    try:
                        canonical = canonical_text(raw)
                    except InvalidEncodingError:
                        raise DomainError("INVALID_UTF8", "Source must be strict UTF-8") from None
                    if "\x00" in canonical:
                        raise DomainError("INVALID_TEXT", "PostgreSQL text cannot contain U+0000")
                    if revision.deleted and canonical:
                        raise DomainError(
                            "INVALID_TOMBSTONE", "Tombstones require empty canonical text"
                        )
                    immutable = revision.model_dump(
                        mode="json", exclude={"source_base64", "mixed_effective", "withdrawal"}
                    )
                    immutable.update(
                        content_hash=content_hash(canonical), source_bytes_hash=bytes_hash(raw)
                    )
                    identity_hash = bytes_hash(canonical_json(immutable))
                    known = repo.versions(workspace, corpus, revision.document_id)
                    existing = next(
                        (v for v in known if v.source_revision_id == revision.source_revision_id),
                        None,
                    )
                    if existing:
                        if existing.immutable_hash != identity_hash:
                            raise DomainError(
                                "REVISION_CONFLICT", "Source revision identity is immutable", 409
                            )
                        continue
                    if known and revision.source_seq <= max(v.source_seq for v in known):
                        parked = True
                    key = bytes_hash(raw)
                    blobs[key] = raw
                    planned.append(
                        Version(
                            workspace_id=workspace,
                            corpus_id=corpus,
                            document_id=revision.document_id,
                            document_version_id=f"dv:{revision.document_id}@{revision.source_revision_id}",
                            source_revision_id=revision.source_revision_id,
                            source_seq=revision.source_seq,
                            text=canonical,
                            content_hash=content_hash(canonical),
                            source_bytes_hash=key,
                            object_key=key,
                            source_timestamp=revision.source_timestamp,
                            declared_effective_from=revision.declared_effective_from,
                            effective_from=revision.declared_effective_from
                            or revision.source_timestamp,
                            effective_from_source="DECLARED_METADATA"
                            if revision.declared_effective_from
                            else "DEFAULT_SOURCE_TIMESTAMP",
                            source_type=revision.source_type,
                            authority=revision.authority,
                            is_deletion=revision.deleted,
                            created_at=datetime.now(UTC),
                            known_at_seq=seq,
                            immutable_hash=identity_hash,
                        )
                    )
                if current.version_count + len(planned) > self.max_corpus_versions:
                    raise DomainError("CORPUS_LIMIT", "Corpus version limit reached", 413)
                if parked or not planned:
                    result = DeliveryResult(
                        delivery_id=delivery.delivery_id,
                        status="PARKED_OUT_OF_ORDER" if parked else "NO_OP_UNCHANGED",
                        snapshot_id=None,
                    )
                    repo.outcome(workspace, corpus, delivery, payload_hash, result, result.status)
                    return result
                phase_two = True
                snapshot_id = f"snap:{seq:06d}"
                changes = build_change_set(
                    delivery.delivery_id,
                    delivery.expected_head,
                    snapshot_id,
                    planned,
                    lambda document: repo.versions(workspace, corpus, document),
                    lambda version_id: repo.passages(workspace, corpus, version_id),
                    max_passages_per_document=self.max_passages_per_document,
                    max_passage_length=self.max_passage_length,
                    max_candidate_pairs=self.max_alignment_candidate_pairs,
                    max_timeline_breakpoints=self.max_timeline_breakpoints,
                )
                for key, raw in blobs.items():
                    self.objects.put(workspace, key, raw)
                return repo.apply(
                    workspace,
                    corpus,
                    delivery,
                    payload_hash,
                    planned,
                    {k: len(v) for k, v in blobs.items()},
                    changes,
                )
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError("APPLY_FAILED", "Delivery could not be applied", 503)
            )
            if authorized:
                try:
                    with self.store.transaction() as repo:
                        repo.authorize(workspace, principal)
                        repo.corpus(workspace, corpus, lock=True)
                        prior = repo.event(workspace, corpus, delivery.delivery_id)
                        if prior and (prior[0] != payload_hash or prior[1].status == "APPLIED"):
                            repo.attempt(
                                workspace,
                                corpus,
                                delivery.delivery_id,
                                payload_hash,
                                "CONFLICT_REJECTED",
                            )
                        else:
                            repo.outcome(
                                workspace,
                                corpus,
                                delivery,
                                payload_hash,
                                DeliveryResult(
                                    delivery_id=delivery.delivery_id,
                                    status="FAILED_APPLY"
                                    if phase_two or error.code == "STALE_HEAD"
                                    else "REJECTED",
                                    snapshot_id=None,
                                    error_code=error.code,
                                ),
                                error.code,
                            )
                except Exception:
                    pass  # Preserve original safe error if the audit store is also unavailable.
            raise error from None
