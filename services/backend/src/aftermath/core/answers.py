"""Grounded-answer contracts. Generation is not verification and is not a verdict."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from aftermath.core.changes import PassageVersion
from aftermath.core.contracts import Contract, Name, Usage
from aftermath.core.corpus import DeliveryResult, SnapshotId


class ProviderCitation(Contract):
    passage_version_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class RetrievedPassage(Contract):
    workspace_id: UUID
    corpus_id: Name
    document_id: Name
    document_version_id: str
    passage_version_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str
    score: float = 0.0


class RetrievalHit(Contract):
    item_id: str
    score: float


class ValidatedCitation(Contract):
    passage_version_id: str
    document_id: Name
    document_version_id: str
    quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    passage_start: int = Field(ge=0)
    passage_end: int = Field(gt=0)


class ProviderAnswer(Contract):
    answer_text: str
    citations: tuple[ProviderCitation, ...]
    model_id: str
    prompt_version: str
    usage: Usage = Field(default_factory=Usage)
    answer_type: Literal["grounded", "not_found"] = "grounded"


class SourceUpload(Contract):
    filename: str | None = Field(default=None, max_length=255)
    document_id: Name | None = None
    text: str | None = Field(default=None, max_length=1048576)
    source_base64: str | None = None


class AnswerAsk(Contract):
    question: str = Field(min_length=1, max_length=4000)
    snapshot_id: SnapshotId | None = None


class GroundedAnswer(Contract):
    status: Literal["ANSWERED", "INSUFFICIENT_GROUNDING"]
    answer_type: Literal["grounded", "not_found"] = "grounded"
    question: str
    snapshot_id: SnapshotId
    answer_text: str | None
    citations: tuple[ValidatedCitation, ...] = ()
    retrieved: tuple[RetrievedPassage, ...] = ()
    returned_citations: tuple[ProviderCitation, ...] = ()
    model_id: str
    prompt_version: str
    usage: Usage = Field(default_factory=Usage)
    answer_source: Literal["LIVE", "DEMO_FALLBACK"] = "LIVE"
    answer_id: str | None = None
    error: dict[str, str] | None = None


class UploadedSource(Contract):
    document_id: Name
    document_version_id: str | None
    source_revision_id: Name
    snapshot_id: SnapshotId | None
    preview: str
    text: str
    passages: tuple[PassageVersion, ...] = ()
    delivery: DeliveryResult
