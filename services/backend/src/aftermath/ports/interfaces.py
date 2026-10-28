from collections.abc import Sequence
from types import TracebackType
from typing import Protocol
from uuid import UUID

from aftermath.core.answers import ProviderAnswer, RetrievedPassage
from aftermath.core.contracts import (
    AnswerRef,
    DocumentRevisionRef,
    EmbeddingResult,
    JobRequest,
    ResolvedVerdict,
    TransitionPrediction,
    VerificationInput,
    VerificationOutcome,
    WorkspaceId,
)


class EmbeddingModel(Protocol):
    def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...


class EvidenceVerifier(Protocol):
    def verify(self, request: VerificationInput) -> VerificationOutcome: ...


class AnswerProvider(Protocol):
    """Answer generation only. Not a verifier and not a policy-resolved verdict."""

    provider_id: str
    model_id: str
    prompt_version: str

    def answer(self, question: str, passages: Sequence[RetrievedPassage]) -> ProviderAnswer: ...


class TransitionPredictor(Protocol):
    def predict(
        self, before: VerificationInput, after: VerificationInput
    ) -> TransitionPrediction: ...


class DocumentRepository(Protocol):
    def canonical_text(self, revision: DocumentRevisionRef) -> str | None: ...


class AssessmentRepository(Protocol):
    def latest(self, answer: AnswerRef) -> ResolvedVerdict | None: ...


class JobQueue(Protocol):
    def enqueue(self, request: JobRequest) -> UUID:
        """Participates in the caller's UoW; same key/different input must fail."""
        ...


class UnitOfWork(Protocol):
    documents: DocumentRepository
    assessments: AssessmentRepository
    jobs: JobQueue

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class ObjectStore(Protocol):
    def get(self, workspace_id: WorkspaceId, key: str) -> bytes: ...
    def put(self, workspace_id: WorkspaceId, key: str, data: bytes) -> None: ...


class DatabaseProbe(Protocol):
    def ready(self) -> bool: ...
