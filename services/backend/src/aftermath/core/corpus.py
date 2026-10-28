import base64
import binascii
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from aftermath.core.contracts import Contract, Hash, Name, ScopeKind, UtcTime
from aftermath.core.errors import DomainError
from aftermath.core.text import bytes_hash, canonical_json

SnapshotId = Annotated[str, Field(pattern=r"^snap:[0-9]{6,}$")]


class WorkspaceCreate(Contract):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceRecord(WorkspaceCreate):
    id: UUID
    created_at: UtcTime


class CorpusCreate(WorkspaceCreate):
    corpus_id: Name


class CorpusRecord(CorpusCreate):
    workspace_id: UUID
    head_snapshot_id: SnapshotId | None
    document_count: int
    version_count: int


class RevisionInput(Contract):
    document_id: Name
    source_revision_id: Name
    source_seq: int = Field(ge=0, le=2147483647)
    source_timestamp: UtcTime
    declared_effective_from: UtcTime | None = None
    source_type: Name
    authority: dict[str, str | int | bool] = Field(default_factory=dict)
    source_base64: str
    deleted: bool = False
    mixed_effective: bool = False
    withdrawal: bool = False

    def original_bytes(self) -> bytes:
        try:
            return base64.b64decode(self.source_base64, validate=True)
        except (ValueError, binascii.Error):
            raise DomainError("INVALID_BASE64", "Source bytes must be base64 encoded") from None


class Delivery(Contract):
    delivery_id: Name
    expected_head: SnapshotId | None
    as_of: UtcTime
    documents: tuple[RevisionInput, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def distinct_documents(self) -> Self:
        if len({d.document_id for d in self.documents}) != len(self.documents):
            raise ValueError("Only one revision per document is allowed in a delivery")
        return self


class Version(Contract):
    workspace_id: UUID
    corpus_id: Name
    document_id: Name
    document_version_id: str
    source_revision_id: Name
    source_seq: int
    text: str
    content_hash: Hash
    source_bytes_hash: Hash
    object_key: Hash
    normalization_version: Literal["canon-v1"] = "canon-v1"
    source_timestamp: UtcTime
    declared_effective_from: UtcTime | None
    effective_from: UtcTime
    effective_from_source: Literal["DECLARED_METADATA", "DEFAULT_SOURCE_TIMESTAMP"]
    source_type: Name
    authority: dict[str, str | int | bool]
    is_deletion: bool
    created_at: UtcTime
    known_at_seq: int
    immutable_hash: Hash


class Snapshot(Contract):
    workspace_id: UUID
    corpus_id: Name
    snapshot_id: SnapshotId
    snapshot_seq: int
    parent_snapshot_id: SnapshotId | None
    update_event_id: str
    manifest_hash: Hash
    document_count: int
    as_of: UtcTime


class DocumentRecord(Contract):
    document_id: Name
    latest_version_id: str
    source_seq: int
    is_deletion: bool
    version_count: int


class DeliveryResult(Contract):
    delivery_id: Name
    status: Literal["APPLIED", "NO_OP_UNCHANGED", "PARKED_OUT_OF_ORDER", "REJECTED", "FAILED_APPLY"]
    snapshot_id: SnapshotId | None
    duplicate: bool = False
    error_code: str | None = None


class ResolveRequest(Contract):
    snapshot_id: SnapshotId
    scope: ScopeKind = ScopeKind.ROLLING_CURRENT
    evaluation_time: UtcTime | None = None
    fixed_time: UtcTime | None = None
    version_id: str | None = None

    @model_validator(mode="after")
    def scope_parameters(self) -> Self:
        if self.scope == ScopeKind.FIXED_VERSION:
            if not self.version_id or self.fixed_time or self.evaluation_time:
                raise ValueError("FIXED_VERSION needs only version_id")
        elif self.scope == ScopeKind.FIXED_TIME:
            if self.fixed_time is None or self.version_id or self.evaluation_time:
                raise ValueError("FIXED_TIME needs only fixed_time")
        elif self.version_id or self.fixed_time:
            raise ValueError("ROLLING_CURRENT uses optional evaluation_time")
        return self


class EffectiveResult(Contract):
    snapshot_id: SnapshotId
    scope: ScopeKind
    evaluation_time: UtcTime | None
    selected_version_id: str | None
    active: bool
    version: Version | None
    effective_to: UtcTime | None
    fingerprint: Hash


def resolve_effective(
    versions: list[Version], snapshot: Snapshot, request: ResolveRequest
) -> EffectiveResult:
    known = [v for v in versions if v.known_at_seq <= snapshot.snapshot_seq]
    at = (
        request.fixed_time
        if request.scope == ScopeKind.FIXED_TIME
        else (request.evaluation_time or snapshot.as_of)
    )
    chosen: Version | None
    if request.scope == ScopeKind.FIXED_VERSION:
        candidates = [v for v in known if v.document_version_id == request.version_id]
        if not candidates:
            raise DomainError("VERSION_NOT_KNOWN", "Version is not known at this snapshot", 404)
        chosen = candidates[0]
        at = None
    else:
        candidates = [v for v in known if v.effective_from <= at] if at else []
        chosen = max(candidates, key=lambda v: (v.effective_from, v.source_seq), default=None)
    end = (
        min(
            (
                v.effective_from
                for v in known
                if chosen and v.effective_from > chosen.effective_from
            ),
            default=None,
        )
        if request.scope != ScopeKind.FIXED_VERSION
        else None
    )
    identity = {
        "snapshot": snapshot.snapshot_id,
        "scope": request.scope,
        "version": chosen.model_dump(mode="json") if chosen else None,
        "effective_to": end.isoformat() if end else None,
    }
    # Exclude measured operational time from evidence identity.
    if isinstance(identity["version"], dict):
        identity["version"].pop("created_at", None)
    return EffectiveResult(
        snapshot_id=snapshot.snapshot_id,
        scope=request.scope,
        evaluation_time=at,
        selected_version_id=chosen.document_version_id if chosen else None,
        active=bool(chosen and not chosen.is_deletion),
        version=chosen if chosen and not chosen.is_deletion else None,
        effective_to=end,
        fingerprint=bytes_hash(canonical_json(identity)),
    )
