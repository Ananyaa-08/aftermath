from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from aftermath.application.answers import AnswerService
from aftermath.application.corpus import CorpusService
from aftermath.config import Settings
from aftermath.core.answers import AnswerAsk, GroundedAnswer, SourceUpload, UploadedSource
from aftermath.core.changes import (
    AlignmentEdge,
    ApplicabilityChange,
    ChangedDocumentView,
    ChangeSpan,
    DocumentComparison,
    TimelineCompareRequest,
    TimelineInterval,
    UpdateEventView,
)
from aftermath.core.contracts import Name
from aftermath.core.corpus import (
    CorpusCreate,
    CorpusRecord,
    Delivery,
    DeliveryResult,
    DocumentRecord,
    EffectiveResult,
    ResolveRequest,
    Snapshot,
    Version,
    WorkspaceCreate,
    WorkspaceRecord,
)
from aftermath.core.errors import DomainError
from aftermath.core.review import ActivityDetail, ActivityIndex, ArchivedAnswer

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]


def corpus_router(service: CorpusService, answers: AnswerService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def identity() -> str:
        if settings.environment == "production" or not settings.dev_identity:
            raise DomainError(
                "AUTH_UNAVAILABLE",
                "Explicit development identity required; production authentication unavailable",
                503,
            )
        return settings.dev_identity

    Principal = Annotated[str, Depends(identity)]

    @router.post("/workspaces", response_model=WorkspaceRecord, status_code=201)
    def create_workspace(body: WorkspaceCreate, principal: Principal) -> WorkspaceRecord:
        return service.create_workspace(principal, body.name)

    @router.get("/workspaces", response_model=list[WorkspaceRecord])
    def workspaces(
        principal: Principal, limit: Limit = 100, offset: Offset = 0
    ) -> list[WorkspaceRecord]:
        return service.workspaces(principal, limit, offset)

    @router.get("/workspaces/{workspace_id}", response_model=WorkspaceRecord)
    def workspace(workspace_id: UUID, principal: Principal) -> WorkspaceRecord:
        return service.workspace(principal, workspace_id)

    prefix = "/workspaces/{workspace_id}/corpora"

    @router.post(prefix, response_model=CorpusRecord, status_code=201)
    def create_corpus(workspace_id: UUID, body: CorpusCreate, principal: Principal) -> CorpusRecord:
        return service.create_corpus(principal, workspace_id, body.corpus_id, body.name)

    @router.get(prefix, response_model=list[CorpusRecord])
    def corpora(
        workspace_id: UUID, principal: Principal, limit: Limit = 100, offset: Offset = 0
    ) -> list[CorpusRecord]:
        return service.corpora(principal, workspace_id, limit, offset)

    @router.get(prefix + "/{corpus_id}", response_model=CorpusRecord)
    def corpus(workspace_id: UUID, corpus_id: Name, principal: Principal) -> CorpusRecord:
        return service.corpus(principal, workspace_id, corpus_id)

    @router.post(prefix + "/{corpus_id}/deliveries", response_model=DeliveryResult)
    def deliver(
        workspace_id: UUID, corpus_id: Name, body: Delivery, principal: Principal
    ) -> DeliveryResult:
        result = service.ingest(principal, workspace_id, corpus_id, body)
        if result.status == "APPLIED":
            answers.observe(principal, workspace_id, corpus_id, result.delivery_id)
        return result

    @router.post(prefix + "/{corpus_id}/uploads", response_model=UploadedSource)
    def upload(
        workspace_id: UUID, corpus_id: Name, body: SourceUpload, principal: Principal
    ) -> UploadedSource:
        return answers.upload(principal, workspace_id, corpus_id, body)

    @router.get(prefix + "/{corpus_id}/answers", response_model=list[ArchivedAnswer])
    def archived_answers(
        workspace_id: UUID, corpus_id: Name, principal: Principal
    ) -> list[ArchivedAnswer]:
        return answers.archived_answers(principal, workspace_id, corpus_id)

    @router.post(prefix + "/{corpus_id}/answers", response_model=GroundedAnswer)
    def ask(
        workspace_id: UUID, corpus_id: Name, body: AnswerAsk, principal: Principal
    ) -> GroundedAnswer:
        return answers.answer(principal, workspace_id, corpus_id, body)

    @router.post(prefix + "/{corpus_id}/answers/{answer_id}/updates", response_model=GroundedAnswer)
    def revise(
        workspace_id: UUID, corpus_id: Name, answer_id: Name, principal: Principal
    ) -> GroundedAnswer:
        return answers.revise(principal, workspace_id, corpus_id, answer_id)

    @router.get(prefix + "/{corpus_id}/activity", response_model=list[ActivityIndex])
    def activity_list(
        workspace_id: UUID, corpus_id: Name, principal: Principal
    ) -> list[ActivityIndex]:
        return answers.activities(principal, workspace_id, corpus_id)

    @router.get(prefix + "/{corpus_id}/activity/{delivery_id}", response_model=ActivityDetail)
    def activity_detail(
        workspace_id: UUID, corpus_id: Name, delivery_id: Name, principal: Principal
    ) -> ActivityDetail:
        return answers.activity(principal, workspace_id, corpus_id, delivery_id)

    @router.get(prefix + "/{corpus_id}/snapshots", response_model=list[Snapshot])
    def snapshots(
        workspace_id: UUID,
        corpus_id: Name,
        principal: Principal,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> list[Snapshot]:
        return service.snapshots(principal, workspace_id, corpus_id, limit, offset)

    @router.get(prefix + "/{corpus_id}/documents", response_model=list[DocumentRecord])
    def documents(
        workspace_id: UUID,
        corpus_id: Name,
        principal: Principal,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> list[DocumentRecord]:
        return service.documents(principal, workspace_id, corpus_id, limit, offset)

    @router.get(prefix + "/{corpus_id}/documents/{document_id}", response_model=DocumentRecord)
    def document(
        workspace_id: UUID, corpus_id: Name, document_id: Name, principal: Principal
    ) -> DocumentRecord:
        versions = service.versions(
            principal, workspace_id, corpus_id, document_id, settings.max_corpus_versions
        )
        latest = versions[-1]
        return DocumentRecord(
            document_id=document_id,
            latest_version_id=latest.document_version_id,
            source_seq=latest.source_seq,
            is_deletion=latest.is_deletion,
            version_count=len(versions),
        )

    @router.get(
        prefix + "/{corpus_id}/documents/{document_id}/versions", response_model=list[Version]
    )
    def versions(
        workspace_id: UUID,
        corpus_id: Name,
        document_id: Name,
        principal: Principal,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> list[Version]:
        return service.versions(principal, workspace_id, corpus_id, document_id, limit, offset)

    @router.post(
        prefix + "/{corpus_id}/documents/{document_id}/resolve", response_model=EffectiveResult
    )
    def resolve(
        workspace_id: UUID,
        corpus_id: Name,
        document_id: Name,
        body: ResolveRequest,
        principal: Principal,
    ) -> EffectiveResult:
        return service.resolve(principal, workspace_id, corpus_id, document_id, body)

    updates = prefix + "/{corpus_id}/updates"

    @router.get(updates, response_model=list[UpdateEventView])
    def update_events(
        workspace_id: UUID,
        corpus_id: Name,
        principal: Principal,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> list[UpdateEventView]:
        return service.update_events(principal, workspace_id, corpus_id, limit, offset)

    @router.get(updates + "/{delivery_id}", response_model=UpdateEventView)
    def update_event(
        workspace_id: UUID, corpus_id: Name, delivery_id: Name, principal: Principal
    ) -> UpdateEventView:
        return service.update_event(principal, workspace_id, corpus_id, delivery_id)

    @router.get(updates + "/{delivery_id}/documents", response_model=list[ChangedDocumentView])
    def changed_documents(
        workspace_id: UUID, corpus_id: Name, delivery_id: Name, principal: Principal
    ) -> list[ChangedDocumentView]:
        return service.changed_documents(principal, workspace_id, corpus_id, delivery_id)

    @router.get(
        updates + "/{delivery_id}/documents/{document_id}/comparison",
        response_model=DocumentComparison,
    )
    def comparison(
        workspace_id: UUID,
        corpus_id: Name,
        delivery_id: Name,
        document_id: Name,
        principal: Principal,
    ) -> DocumentComparison:
        return service.comparison(principal, workspace_id, corpus_id, delivery_id, document_id)

    @router.get(updates + "/{delivery_id}/lineage", response_model=list[AlignmentEdge])
    def lineage(
        workspace_id: UUID,
        corpus_id: Name,
        delivery_id: Name,
        principal: Principal,
        document_id: Name | None = None,
    ) -> list[AlignmentEdge]:
        return service.lineage_edges(principal, workspace_id, corpus_id, delivery_id, document_id)

    @router.get(updates + "/{delivery_id}/spans", response_model=list[ChangeSpan])
    def change_spans(
        workspace_id: UUID,
        corpus_id: Name,
        delivery_id: Name,
        principal: Principal,
        document_id: Name | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> list[ChangeSpan]:
        if limit > settings.max_returned_spans:
            raise DomainError("PAGE_LIMIT", "Span page exceeds configured limit", 413)
        return service.change_spans(
            principal, workspace_id, corpus_id, delivery_id, document_id, limit, offset
        )

    @router.get(updates + "/{delivery_id}/applicability", response_model=list[ApplicabilityChange])
    def applicability(
        workspace_id: UUID,
        corpus_id: Name,
        delivery_id: Name,
        principal: Principal,
        document_id: Name | None = None,
    ) -> list[ApplicabilityChange]:
        return service.applicability_changes(
            principal, workspace_id, corpus_id, delivery_id, document_id
        )

    document_prefix = prefix + "/{corpus_id}/documents/{document_id}"

    @router.get(document_prefix + "/timeline", response_model=list[TimelineInterval])
    def timeline(
        workspace_id: UUID,
        corpus_id: Name,
        document_id: Name,
        snapshot_id: str,
        principal: Principal,
    ) -> list[TimelineInterval]:
        return service.timeline(principal, workspace_id, corpus_id, document_id, snapshot_id)

    @router.post(document_prefix + "/timeline/compare", response_model=list[ApplicabilityChange])
    def compare_timelines(
        workspace_id: UUID,
        corpus_id: Name,
        document_id: Name,
        body: TimelineCompareRequest,
        principal: Principal,
    ) -> list[ApplicabilityChange]:
        return service.compare_timelines(
            principal,
            workspace_id,
            corpus_id,
            document_id,
            body.from_snapshot_id,
            body.to_snapshot_id,
        )

    return router
