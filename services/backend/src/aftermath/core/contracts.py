"""Foundation contracts; no semantic inference or policy resolution is implemented."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcTime = Annotated[
    AwareDatetime,
    AfterValidator(utc),
    PlainSerializer(
        lambda value: value.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        return_type=str,
        when_used="json",
    ),
]
Name = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
Hash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
WorkspaceId = UUID


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class DocumentRevisionRef(Contract):
    workspace_id: WorkspaceId
    document_id: Name
    revision_id: Name


class CorpusSnapshotRef(Contract):
    workspace_id: WorkspaceId
    snapshot_id: Annotated[str, Field(pattern=r"^snap:[0-9]{6,}$")]


class AnswerRef(Contract):
    workspace_id: WorkspaceId
    answer_id: Name
    version: int = Field(ge=1)


class ClaimRef(Contract):
    answer: AnswerRef
    ordinal: int = Field(ge=1)


class ScopeKind(StrEnum):
    ROLLING_CURRENT = "ROLLING_CURRENT"
    FIXED_TIME = "FIXED_TIME"
    FIXED_VERSION = "FIXED_VERSION"


class QuestionScope(Contract):
    kind: ScopeKind
    time: UtcTime | None = None
    versions: tuple[DocumentRevisionRef, ...] = ()

    @model_validator(mode="after")
    def valid_parameters(self) -> Self:
        if (self.kind == ScopeKind.FIXED_TIME) != (self.time is not None):
            raise ValueError("time is required only for FIXED_TIME")
        if (self.kind == ScopeKind.FIXED_VERSION) != bool(self.versions):
            raise ValueError("versions are required only for FIXED_VERSION")
        if len({v.workspace_id for v in self.versions}) > 1:
            raise ValueError("scope cannot span workspaces")
        return self


class SemanticStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"


class AssessmentWorkflowState(StrEnum):
    UNASSESSED = "UNASSESSED"
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WITHHELD = "WITHHELD"


class EvidenceRef(Contract):
    revision: DocumentRevisionRef
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    authority_tier: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("evidence must have a nonempty half-open span")
        return self


class EvidenceJudgment(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class Judgment(Contract):
    claim: ClaimRef
    evidence: EvidenceRef
    stance: EvidenceJudgment

    @model_validator(mode="after")
    def same_workspace(self) -> Self:
        if self.claim.answer.workspace_id != self.evidence.revision.workspace_id:
            raise ValueError("judgment cannot span workspaces")
        return self


class ModelIdentity(Contract):
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    config_hash: Hash
    prompt_version: str | None = None
    is_mock: bool = False


class Usage(Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)


class StructuredError(Contract):
    code: str = Field(min_length=1)
    message: str = Field(
        min_length=1, description="Sanitized message; no secrets/provider payloads"
    )
    retryable: bool = False


class VerificationOutcome(Contract):
    """Provider output is evidence judgment only, never a policy-resolved verdict."""

    outcome: Literal["OK", "FAILED"]
    model: ModelIdentity
    judgments: tuple[Judgment, ...] = ()
    error: StructuredError | None = None
    usage: Usage = Field(default_factory=Usage)

    @model_validator(mode="after")
    def failure_has_no_judgments(self) -> Self:
        if self.outcome == "FAILED" and (self.error is None or self.judgments):
            raise ValueError("failure requires an error and cannot carry judgments")
        if self.outcome == "OK" and self.error is not None:
            raise ValueError("success cannot carry an error")
        return self


class ResolvedVerdict(Contract):
    answer: AnswerRef
    snapshot: CorpusSnapshotRef
    evaluation_time: UtcTime
    source_policy_version: str = Field(min_length=1)
    semantic_status: SemanticStatus

    @model_validator(mode="after")
    def same_workspace(self) -> Self:
        if self.answer.workspace_id != self.snapshot.workspace_id:
            raise ValueError("verdict cannot span workspaces")
        return self


class VerificationInput(Contract):
    claim: ClaimRef
    claim_text: str
    question: str
    scope: QuestionScope
    snapshot: CorpusSnapshotRef
    evaluation_time: UtcTime
    evidence: tuple[EvidenceRef, ...]

    @model_validator(mode="after")
    def same_workspace(self) -> Self:
        workspace = self.claim.answer.workspace_id
        referenced = [self.snapshot.workspace_id]
        referenced.extend(item.revision.workspace_id for item in self.evidence)
        referenced.extend(item.workspace_id for item in self.scope.versions)
        if any(value != workspace for value in referenced):
            raise ValueError("verification input cannot span workspaces")
        return self


class TransitionPrediction(Contract):
    model: ModelIdentity
    predicted_status: SemanticStatus
    requires_verification: bool
    usage: Usage = Field(default_factory=Usage)


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobRequest(Contract):
    workspace_id: WorkspaceId
    idempotency_key: str = Field(min_length=1, max_length=200)
    input_snapshot: CorpusSnapshotRef

    @model_validator(mode="after")
    def same_workspace(self) -> Self:
        if self.workspace_id != self.input_snapshot.workspace_id:
            raise ValueError("job cannot span workspaces")
        return self


class EmbeddingResult(Contract):
    model: ModelIdentity
    vectors: tuple[tuple[float, ...], ...]
    usage: Usage = Field(default_factory=Usage)


class DurableJob(Contract):
    job_id: UUID
    request: JobRequest
    state: JobState = JobState.QUEUED
    attempts: int = Field(default=0, ge=0)
    lease_owner: str | None = None
    lease_expires_at: UtcTime | None = None
    error: StructuredError | None = None
    created_at: UtcTime
    updated_at: UtcTime

    @model_validator(mode="after")
    def state_fields(self) -> Self:
        running = self.state == JobState.RUNNING
        if running and (not self.lease_owner or self.lease_expires_at is None):
            raise ValueError("running job requires a lease")
        if not running and (self.lease_owner is not None or self.lease_expires_at is not None):
            raise ValueError("non-running job cannot hold a lease")
        if (self.state == JobState.FAILED) != (self.error is not None):
            raise ValueError("only failed jobs require an error")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at precedes creation")
        return self
