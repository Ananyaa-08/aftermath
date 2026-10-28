"""Candidate selection and archived assessment records. Not a research verdict pipeline."""

from collections.abc import Sequence
from typing import Literal, NamedTuple
from uuid import UUID

from pydantic import Field

from aftermath.core.contracts import Contract, Name, UtcTime
from aftermath.core.corpus import SnapshotId

AnswerSource = Literal["LIVE", "DEMO_FALLBACK"]
VerdictStatus = Literal[
    "SUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT_SUPPORT",
    "UNRESOLVED_CONFLICT",
    "PROVIDER_ERROR",
]
ALGORITHM_VERSION = "cite-passage-v1"
POLICY_VERSION = "policy-demo-v1"

EXPLANATION = {
    "SUPPORTED": "Policy policy-demo-v1: the current snapshot still supports this claim.",
    "CONTRADICTED": (
        "Policy policy-demo-v1: the cited passage changed and the current snapshot "
        "contradicts this claim."
    ),
    "INSUFFICIENT_SUPPORT": (
        "Policy policy-demo-v1: no eligible quote supports or contradicts this claim."
    ),
    "UNRESOLVED_CONFLICT": (
        "Policy policy-demo-v1: eligible passages both support and contradict this claim."
    ),
    "PROVIDER_ERROR": "The model failed. This is not a semantic verdict.",
}


class ArchivedCitation(Contract):
    passage_version_id: str
    document_id: Name
    document_version_id: str
    quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ArchivedClaim(Contract):
    claim_id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    citations: tuple[ArchivedCitation, ...] = ()


class ArchivedAnswer(Contract):
    answer_id: Name
    workspace_id: UUID
    corpus_id: Name
    question: str
    answer_text: str
    snapshot_id: SnapshotId
    scope: Literal["ROLLING_CURRENT", "FIXED_TIME", "FIXED_VERSION"] = "ROLLING_CURRENT"
    evaluation_time: UtcTime | None = None
    claims: tuple[ArchivedClaim, ...]
    model_id: str
    prompt_version: str
    answer_source: AnswerSource
    answer_type: Literal["grounded", "not_found"] = "grounded"
    previous_answer_id: Name | None = None
    created_at: UtcTime


class ClaimVerdict(Contract):
    claim_id: str
    claim_text: str
    status: VerdictStatus
    explanation: str
    old_evidence: tuple[ArchivedCitation, ...] = ()
    new_evidence: tuple[ArchivedCitation, ...] = ()
    answer_source: Literal["LIVE", "DEMO_FALLBACK", "NONE"] = "NONE"


class AssessmentRecord(Contract):
    assessment_id: Name
    answer_id: Name
    workspace_id: UUID
    corpus_id: Name
    delivery_id: Name
    parent_snapshot_id: SnapshotId | None
    snapshot_id: SnapshotId
    scope: Literal["ROLLING_CURRENT", "FIXED_TIME", "FIXED_VERSION"]
    policy_version: str
    model_id: str
    prompt_version: str
    algorithm_version: str
    selection_reason: str
    semantic_status: VerdictStatus | None
    answer_source: Literal["LIVE", "DEMO_FALLBACK", "NONE"]
    claims: tuple[ClaimVerdict, ...]


class ActivityIndex(Contract):
    workspace_id: UUID
    corpus_id: Name
    delivery_id: Name
    document_id: Name
    parent_snapshot_id: SnapshotId | None
    snapshot_id: SnapshotId
    selected: int = Field(ge=0)
    queued: int = Field(ge=0)
    completed: int = Field(ge=0)


class SourceChangeView(Contract):
    document_id: Name
    old_passage_version_id: str | None
    new_passage_version_id: str | None
    old_text: str | None
    new_text: str | None


class AnswerPreview(Contract):
    answer_id: Name
    question: str
    answer_text: str
    snapshot_id: SnapshotId
    scope: Literal["ROLLING_CURRENT", "FIXED_TIME", "FIXED_VERSION"]
    state: Literal["SELECTED", "NOT_REASSESSED"]
    selection_reason: str | None = None
    algorithm_version: str | None = None
    previous_answer_id: Name | None = None
    assessment: AssessmentRecord | None = None
    changes: tuple[SourceChangeView, ...] = ()


class ActivityDetail(Contract):
    delivery_id: Name
    document_id: Name
    parent_snapshot_id: SnapshotId | None
    snapshot_id: SnapshotId
    selected: int
    queued: int
    completed: int
    changes: tuple[SourceChangeView, ...] = ()
    answers: tuple[AnswerPreview, ...] = ()


class Candidate(Contract):
    answer_id: Name
    reason: str
    algorithm_version: str
    changed_passage_ids: tuple[str, ...]


class PassageChange(NamedTuple):
    old_passage_version_id: str | None
    old_text: str | None
    new_text: str | None


def changes_for_answer(
    answer: ArchivedAnswer, changes: Sequence[SourceChangeView]
) -> tuple[SourceChangeView, ...]:
    """Keep only spans whose old passage is cited by this answer."""
    cited = {citation.passage_version_id for claim in answer.claims for citation in claim.citations}
    return tuple(change for change in changes if change.old_passage_version_id in cited)


def changed_passage_ids(spans: Sequence[PassageChange]) -> set[str]:
    changed: set[str] = set()
    for span in spans:
        passage_id = span.old_passage_version_id
        if passage_id and span.old_text != span.new_text:
            changed.add(passage_id)
    return changed


def select_candidates(answers: Sequence[ArchivedAnswer], changed: set[str]) -> list[Candidate]:
    selected: list[Candidate] = []
    for answer in answers:
        cited: list[str] = []
        for claim in answer.claims:
            for citation in claim.citations:
                passage_id = citation.passage_version_id
                if passage_id in changed and passage_id not in cited:
                    cited.append(passage_id)
        if not cited:
            continue
        selected.append(
            Candidate(
                answer_id=answer.answer_id,
                reason="Cited passage changed: " + ", ".join(cited),
                algorithm_version=ALGORITHM_VERSION,
                changed_passage_ids=tuple(cited),
            )
        )
    return selected


def overall_status(claims: Sequence[ClaimVerdict]) -> VerdictStatus | None:
    statuses = [item.status for item in claims]
    if not statuses:
        return None
    if any(status == "PROVIDER_ERROR" for status in statuses):
        return "PROVIDER_ERROR"
    if any(status == "CONTRADICTED" for status in statuses):
        return "CONTRADICTED"
    if any(status == "UNRESOLVED_CONFLICT" for status in statuses):
        return "UNRESOLVED_CONFLICT"
    if any(status == "INSUFFICIENT_SUPPORT" for status in statuses):
        return "INSUFFICIENT_SUPPORT"
    if all(status == "SUPPORTED" for status in statuses):
        return "SUPPORTED"
    return None
