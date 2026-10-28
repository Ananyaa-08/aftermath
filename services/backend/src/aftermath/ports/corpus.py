from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

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


class CorpusRepository(Protocol):
    def authorize(self, workspace: UUID, principal: str) -> None: ...
    def workspace(self, workspace: UUID) -> WorkspaceRecord: ...
    def workspaces(self, principal: str, limit: int, offset: int) -> list[WorkspaceRecord]: ...
    def create_workspace(self, principal: str, name: str) -> WorkspaceRecord: ...
    def create_corpus(self, workspace: UUID, corpus: str, name: str) -> CorpusRecord: ...
    def corpora(self, workspace: UUID, limit: int, offset: int) -> list[CorpusRecord]: ...
    def corpus(self, workspace: UUID, corpus: str, lock: bool = False) -> CorpusRecord: ...
    def versions(self, workspace: UUID, corpus: str, document: str) -> list[Version]: ...
    def documents(
        self, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[DocumentRecord]: ...
    def snapshots(
        self, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[Snapshot]: ...
    def snapshot(self, workspace: UUID, corpus: str, snapshot: str) -> Snapshot: ...
    def event(
        self, workspace: UUID, corpus: str, delivery: str
    ) -> tuple[str, DeliveryResult] | None: ...
    def passages(
        self, workspace: UUID, corpus: str, document_version: str
    ) -> list[PassageVersion]: ...
    def update_events(
        self, workspace: UUID, corpus: str, limit: int, offset: int
    ) -> list[dict[str, object]]: ...
    def changed_documents(
        self, workspace: UUID, corpus: str, delivery: str
    ) -> list[dict[str, object]]: ...
    def lineage_edges(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[AlignmentEdge]: ...
    def timeline_alignments(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[TimelineAlignment]: ...
    def change_spans(
        self,
        workspace: UUID,
        corpus: str,
        delivery: str,
        document: str | None,
        limit: int,
        offset: int,
    ) -> list[ChangeSpan]: ...
    def applicability_changes(
        self, workspace: UUID, corpus: str, delivery: str, document: str | None
    ) -> list[ApplicabilityChange]: ...
    def outcome(
        self,
        workspace: UUID,
        corpus: str,
        delivery: Delivery,
        payload_hash: str,
        result: DeliveryResult,
        attempt: str,
    ) -> None: ...
    def attempt(
        self, workspace: UUID, corpus: str, delivery: str, payload_hash: str, outcome: str
    ) -> None: ...
    def apply(
        self,
        workspace: UUID,
        corpus: str,
        delivery: Delivery,
        payload_hash: str,
        versions: list[Version],
        sizes: dict[str, int],
        changes: ChangeSet,
    ) -> DeliveryResult: ...


class CorpusStore(Protocol):
    def transaction(self) -> AbstractContextManager[CorpusRepository]: ...
