from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aftermath.api.offsets import utf16_offset
from aftermath.core.contracts import (
    AnswerRef,
    CorpusSnapshotRef,
    DocumentRevisionRef,
    EvidenceRef,
    JobRequest,
    ModelIdentity,
    QuestionScope,
    ResolvedVerdict,
    StructuredError,
    Usage,
    VerificationOutcome,
)
from aftermath.core.text import canonical_json, canonical_text, content_hash


def test_time_requires_timezone_and_serializes_utc() -> None:
    with pytest.raises(ValidationError):
        QuestionScope(kind="FIXED_TIME", time=datetime(2026, 1, 1))
    scope = QuestionScope(kind="FIXED_TIME", time="2026-01-01T05:30:00+05:30")
    assert scope.time == datetime(2026, 1, 1, tzinfo=UTC)
    assert scope.model_dump(mode="json")["time"] == "2026-01-01T00:00:00.000Z"


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "FIXED_TIME"},
        {"kind": "FIXED_VERSION"},
        {"kind": "ROLLING_CURRENT", "time": "2026-01-01T00:00:00Z"},
    ],
)
def test_scope_parameters(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        QuestionScope.model_validate(values)


def test_failed_verifier_cannot_create_semantic_verdict() -> None:
    model = ModelIdentity(provider="test", model_id="test", config_hash="sha256:" + "a" * 64)
    result = VerificationOutcome(
        outcome="FAILED", model=model, error=StructuredError(code="TIMEOUT", message="Timed out")
    )
    assert result.judgments == ()
    assert "semantic_status" not in result.model_dump()
    with pytest.raises(ValidationError):
        VerificationOutcome.model_validate(
            {**result.model_dump(), "semantic_status": "CONTRADICTED"}
        )
    with pytest.raises(ValidationError):
        VerificationOutcome(outcome="FAILED", model=model)
    with pytest.raises(ValidationError):
        VerificationOutcome(outcome="OK", model=model, error=result.error)


def test_unknown_cost_is_not_zero() -> None:
    assert Usage().model_dump(mode="json") == {
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
        "cost_usd": None,
    }
    with pytest.raises(ValidationError):
        Usage(latency_ms=float("nan"))
    with pytest.raises(ValidationError):
        Usage(input_tokens=-1)


def test_canonical_unicode_and_boundary_offsets() -> None:
    text = canonical_text("\ufeffCafe\u0301\r\n😀x\r".encode())
    assert text == "Café\n😀x\n"
    assert utf16_offset(text, 6) == 7
    assert text[5:6] == "😀"
    assert content_hash(text) == content_hash(canonical_text(text.encode()))
    assert canonical_json({"z": 1, "a": "é"}) == '{"a":"é","z":1}'.encode()
    with pytest.raises(UnicodeDecodeError):
        canonical_text(b"\xff")
    with pytest.raises(ValueError):
        utf16_offset(text, len(text) + 1)
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_reference_isolation_and_span_validation() -> None:
    workspace = uuid4()
    snapshot = CorpusSnapshotRef(workspace_id=uuid4(), snapshot_id="snap:000001")
    with pytest.raises(ValidationError):
        JobRequest(workspace_id=workspace, idempotency_key="one", input_snapshot=snapshot)
    with pytest.raises(ValidationError):
        ResolvedVerdict(
            answer=AnswerRef(workspace_id=workspace, answer_id="a", version=1),
            snapshot=snapshot,
            evaluation_time=datetime.now(UTC),
            source_policy_version="v1",
            semantic_status="SUPPORTED",
        )
    revision = DocumentRevisionRef(workspace_id=workspace, document_id="doc", revision_id="r1")
    with pytest.raises(ValidationError):
        EvidenceRef(revision=revision, start=4, end=3, authority_tier=1)


def test_durable_job_requires_lease_and_failure_error() -> None:
    from aftermath.core.contracts import DurableJob

    workspace = uuid4()
    job = DurableJob(
        job_id=uuid4(),
        request=JobRequest(
            workspace_id=workspace,
            idempotency_key="one",
            input_snapshot=CorpusSnapshotRef(workspace_id=workspace, snapshot_id="snap:000001"),
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    for invalid in ({"state": "RUNNING"}, {"state": "FAILED"}, {"lease_owner": "orphan"}):
        with pytest.raises(ValidationError):
            DurableJob.model_validate({**job.model_dump(), **invalid})
    running = DurableJob.model_validate(
        {
            **job.model_dump(),
            "state": "RUNNING",
            "lease_owner": "worker-1",
            "lease_expires_at": datetime.now(UTC),
            "attempts": 1,
        }
    )
    assert running.attempts == 1
