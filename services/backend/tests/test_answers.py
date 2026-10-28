from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aftermath.application.answers import AnswerService, ground_answer
from aftermath.core.answers import ProviderAnswer, ProviderCitation, RetrievedPassage
from aftermath.core.contracts import Usage
from aftermath.core.demo_fallback import V1, V2, canned_answer
from aftermath.core.errors import DomainError
from aftermath.core.review import (
    ArchivedAnswer,
    ArchivedCitation,
    ArchivedClaim,
    PassageChange,
    SourceChangeView,
    changed_passage_ids,
    changes_for_answer,
    select_candidates,
)

STARTER = "The Starter plan costs 12 USD per month."


def passage(
    workspace,
    corpus="research",
    document="guide",
    revision="r1",
    text=STARTER,
):
    return RetrievedPassage(
        workspace_id=workspace,
        corpus_id=corpus,
        document_id=document,
        document_version_id=f"dv:{document}@{revision}",
        passage_version_id=f"pv:{document}@{revision}#p0001",
        start=0,
        end=len(text),
        text=text,
    )


class FakeAnswerAdapter:
    provider_id = "fake"
    model_id = "fake-answer"
    prompt_version = "answer-grounded-v1"

    def __init__(self, citations: tuple[ProviderCitation, ...], text: str = STARTER):
        self._citations = citations
        self._text = text

    def answer(self, question: str, passages: list[RetrievedPassage]) -> ProviderAnswer:
        return ProviderAnswer(
            answer_text=self._text,
            citations=self._citations,
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            usage=Usage(),
        )


def test_citation_validation_accepts_home_passage_and_rejects_foreign_corpus():
    home_workspace, foreign_workspace = uuid4(), uuid4()
    home = passage(home_workspace, "research")
    foreign = passage(foreign_workspace, "other", document="billing")
    question = "What does Starter cost?"
    valid = ground_answer(
        question,
        "snap:000001",
        home_workspace,
        "research",
        [home],
        FakeAnswerAdapter(
            (ProviderCitation(passage_version_id=home.passage_version_id, quote=STARTER),)
        ),
    )
    assert valid.status == "ANSWERED"
    assert valid.citations[0].passage_version_id == home.passage_version_id
    assert valid.citations[0].quote == STARTER
    rejected = ground_answer(
        question,
        "snap:000001",
        home_workspace,
        "research",
        [home, foreign],
        FakeAnswerAdapter(
            (ProviderCitation(passage_version_id=foreign.passage_version_id, quote=STARTER),)
        ),
    )
    assert rejected.status == "INSUFFICIENT_GROUNDING"
    assert rejected.citations == ()
    assert rejected.error is not None
    assert rejected.error["code"] == "INSUFFICIENT_GROUNDING"


class RateLimited:
    provider_id = "fake"
    model_id = "gemini-3.6-flash"
    prompt_version = "answer-grounded-v1"

    def answer(self, question: str, passages: list[RetrievedPassage]) -> ProviderAnswer:
        raise DomainError("PROVIDER_ERROR", "Gemini call failed: 429 RESOURCE_EXHAUSTED", 503)


def demo_passages(workspace, sentences=V1):
    values = []
    for index, text in enumerate(sentences, start=1):
        values.append(
            RetrievedPassage(
                workspace_id=workspace,
                corpus_id="research",
                document_id="plans",
                document_version_id="dv:plans@r1",
                passage_version_id=f"pv:plans@r1#p{index:04d}",
                start=0,
                end=len(text),
                text=text,
            )
        )
    return values


class ExplodingProvider:
    provider_id = "fake"
    model_id = "gemini-3.6-flash"
    prompt_version = "answer-grounded-v2"

    def answer(self, question: str, passages: list[RetrievedPassage]) -> ProviderAnswer:
        raise AssertionError("Gemini must not be called")


def test_force_fallback_skips_gemini_and_still_returns_not_found():
    workspace = uuid4()
    demo = demo_passages(workspace)
    grounded = ground_answer(
        "What does Starter cost?",
        "snap:000001",
        workspace,
        "research",
        demo,
        ExplodingProvider(),
        force_fallback=True,
    )
    assert grounded.status == "ANSWERED"
    assert grounded.answer_source == "DEMO_FALLBACK"
    assert grounded.answer_type == "grounded"
    assert grounded.answer_text == V1[0]
    missing = ground_answer(
        "Does it include VIP service?",
        "snap:000001",
        workspace,
        "research",
        demo,
        ExplodingProvider(),
        force_fallback=True,
    )
    assert missing.status == "ANSWERED"
    assert missing.answer_source == "DEMO_FALLBACK"
    assert missing.answer_type == "not_found"
    assert missing.citations == ()
    other_text = "Starter cost is listed in another document."
    other = RetrievedPassage(
        workspace_id=workspace,
        corpus_id="research",
        document_id="notes",
        document_version_id="dv:notes@r1",
        passage_version_id="pv:notes@r1#p0001",
        start=0,
        end=len(other_text),
        text=other_text,
    )
    with pytest.raises(DomainError) as failure:
        ground_answer(
            "What does Starter cost?",
            "snap:000001",
            workspace,
            "research",
            [other],
            ExplodingProvider(),
            force_fallback=True,
        )
    assert failure.value.code == "PROVIDER_ERROR"


def test_demo_fallback_fires_only_for_the_demo_document_on_429():
    workspace = uuid4()
    demo = demo_passages(workspace)
    grounded = ground_answer(
        "What does Starter cost?", "snap:000001", workspace, "research", demo, RateLimited()
    )
    assert grounded.status == "ANSWERED"
    assert grounded.answer_source == "DEMO_FALLBACK"
    assert grounded.answer_text == V1[0]
    assert "12 USD" in (grounded.answer_text or "")
    assert "15 USD" not in (grounded.answer_text or "")
    assert grounded.citations[0].quote == V1[0]
    assert grounded.citations[0].passage_version_id == demo[0].passage_version_id
    revised = demo_passages(workspace, V2)
    revised_answer = ground_answer(
        "What does Starter cost?", "snap:000001", workspace, "research", revised, RateLimited()
    )
    assert revised_answer.answer_text == V2[0]
    assert revised_answer.citations[0].quote == revised[0].text
    other_text = "Starter cost is listed in another document."
    other = RetrievedPassage(
        workspace_id=workspace,
        corpus_id="research",
        document_id="notes",
        document_version_id="dv:notes@r1",
        passage_version_id="pv:notes@r1#p0001",
        start=0,
        end=len(other_text),
        text=other_text,
    )
    with pytest.raises(DomainError) as failure:
        ground_answer(
            "What does Starter cost?",
            "snap:000001",
            workspace,
            "research",
            [other],
            RateLimited(),
        )
    assert failure.value.code == "PROVIDER_ERROR"


def archived(answer_id, passage_id, question):
    workspace = uuid4()
    return ArchivedAnswer(
        answer_id=answer_id,
        workspace_id=workspace,
        corpus_id="research",
        question=question,
        answer_text=question,
        snapshot_id="snap:000001",
        claims=(
            ArchivedClaim(
                claim_id=f"{answer_id}-c01",
                text=question,
                start=0,
                end=len(question),
                citations=(
                    ArchivedCitation(
                        passage_version_id=passage_id,
                        document_id="plans",
                        document_version_id="dv:plans@r1",
                        quote="quoted",
                        start=0,
                        end=6,
                    ),
                ),
            ),
        ),
        model_id="gemini-3.6-flash",
        prompt_version="answer-grounded-v1",
        answer_source="LIVE",
        created_at=datetime.now(UTC),
    )


def test_candidate_selection_keeps_changed_citations_and_drops_unrelated_answers():
    changed = changed_passage_ids(
        [
            PassageChange("pv:plans@r1#p0001", "12", "15"),
            PassageChange("pv:plans@r1#p0003", "same", "same"),
        ]
    )
    assert changed == {"pv:plans@r1#p0001"}
    price = archived("ans-price", "pv:plans@r1#p0001", "What does Starter cost?")
    other = archived("ans-other", "pv:notes@r1#p0001", "What is the weather?")
    selected = select_candidates([price, other], changed)
    assert [item.answer_id for item in selected] == ["ans-price"]
    assert selected[0].algorithm_version == "cite-passage-v1"
    assert "pv:plans@r1#p0001" in selected[0].reason


class NotFoundProvider:
    provider_id = "fake"
    model_id = "fake-answer"
    prompt_version = "answer-grounded-v2"

    def answer(self, question: str, passages: list[RetrievedPassage]) -> ProviderAnswer:
        return ProviderAnswer(
            answer_text="The documents don't mention VIP service.",
            citations=(),
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            answer_type="not_found",
        )


class _MemoryArchive:
    def __init__(self) -> None:
        self.rows: list[ArchivedAnswer] = []

    def add_answer(self, record: ArchivedAnswer) -> None:
        self.rows.append(record)


def test_vip_question_against_plans_is_not_found_and_archived():
    workspace = uuid4()
    result = ground_answer(
        "Does it include VIP service?",
        "snap:000001",
        workspace,
        "research",
        demo_passages(workspace),
        NotFoundProvider(),
    )
    assert result.status == "ANSWERED"
    assert result.answer_type == "not_found"
    assert result.citations == ()
    assert result.answer_text
    archive = _MemoryArchive()
    service = AnswerService(None, None, None, archive)  # type: ignore[arg-type]
    saved = service._archive_answer(workspace, "research", result, None)
    assert saved.answer_type == "not_found"
    assert archive.rows[0].answer_id == saved.answer_id
    assert all(not claim.citations for claim in saved.claims)


def test_demo_fallback_returns_not_found_when_no_passage_scores():
    workspace = uuid4()
    passages = demo_passages(workspace)
    canned = canned_answer("Does it include VIP service?", passages)
    assert canned is not None
    assert canned.answer_type == "not_found"
    assert canned.citations == ()
    grounded = ground_answer(
        "What does the Starter plan say about VIP service?",
        "snap:000001",
        workspace,
        "research",
        passages,
        RateLimited(),
    )
    assert grounded.status == "ANSWERED"
    assert grounded.answer_source == "DEMO_FALLBACK"
    assert grounded.answer_type == "not_found"
    assert grounded.citations == ()


def test_fabricated_citation_stays_insufficient_grounding():
    workspace = uuid4()
    home = passage(workspace)
    rejected = ground_answer(
        "What does Starter cost?",
        "snap:000001",
        workspace,
        "research",
        [home],
        FakeAnswerAdapter(
            (
                ProviderCitation(
                    passage_version_id=home.passage_version_id,
                    quote="VIP service is included.",
                ),
            )
        ),
    )
    assert rejected.status == "INSUFFICIENT_GROUNDING"
    assert rejected.answer_type == "grounded"
    assert rejected.citations == ()
    assert rejected.error is not None
    assert rejected.error["code"] == "INSUFFICIENT_GROUNDING"


def _change(passage_id: str, old: str, new: str) -> SourceChangeView:
    return SourceChangeView(
        document_id="plans",
        old_passage_version_id=passage_id,
        new_passage_version_id=passage_id.replace("@r1", "@r2"),
        old_text=old,
        new_text=new,
    )


def test_each_affected_answer_carries_only_its_own_passage_diff():
    price = archived("ans-price", "pv:plans@r1#p0001", "What does Starter cost?")
    export = archived("ans-export", "pv:plans@r1#p0002", "Does Starter include bulk export?")
    enterprise = archived("ans-enterprise", "pv:plans@r1#p0003", "What does Enterprise include?")
    changed = changed_passage_ids(
        [
            PassageChange("pv:plans@r1#p0001", V1[0], V2[0]),
            PassageChange("pv:plans@r1#p0002", V1[1], V2[1]),
            PassageChange("pv:plans@r1#p0003", V1[2], V2[2]),
        ]
    )
    assert changed == {"pv:plans@r1#p0001", "pv:plans@r1#p0002"}
    selected = select_candidates([price, export, enterprise], changed)
    assert [item.answer_id for item in selected] == ["ans-price", "ans-export"]
    views = (
        _change("pv:plans@r1#p0001", V1[0], V2[0]),
        _change("pv:plans@r1#p0002", V1[1], V2[1]),
    )
    price_diff = changes_for_answer(price, views)
    export_diff = changes_for_answer(export, views)
    assert len(price_diff) == 1
    assert price_diff[0].old_text == V1[0]
    assert price_diff[0].new_text == V2[0]
    assert "12" in (price_diff[0].old_text or "")
    assert "15" in (price_diff[0].new_text or "")
    assert "bulk" not in (price_diff[0].old_text or "")
    assert len(export_diff) == 1
    assert export_diff[0].old_text == V1[1]
    assert "does not include" in (export_diff[0].new_text or "")
    assert "12" not in (export_diff[0].old_text or "")
    assert changes_for_answer(enterprise, views) == ()
