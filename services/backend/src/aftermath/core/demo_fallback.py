"""Labelled fallback answers after a Gemini rate limit.

The answer text is the retrieved passage itself. Nothing here substitutes a fixed revision.
"""

import re
from collections import Counter
from collections.abc import Sequence

from aftermath.core.answers import ProviderAnswer, ProviderCitation, RetrievedPassage
from aftermath.core.changes import norm_v1_text
from aftermath.core.contracts import Usage

_TOKEN = re.compile(r"\w+", re.UNICODE)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "at",
        "from",
        "as",
        "that",
        "this",
        "it",
        "its",
        "what",
        "which",
        "who",
        "does",
        "do",
        "did",
        "how",
        "when",
        "where",
        "why",
        "can",
    }
)
_COST = frozenset({"cost", "costs", "price", "priced", "usd", "dollar", "dollars"})

V1 = (
    "The Starter plan costs 12 USD per month.",
    "The Starter plan includes bulk export.",
    "Enterprise plans include priority support.",
)
V2 = (
    "The Starter plan costs 15 USD per month.",
    "The Starter plan does not include bulk export.",
    "Enterprise plans include priority support.",
)
DEMO_DOCUMENT_IDS = frozenset({"plans", "plans-v2"})


def is_demo_document(passages: Sequence[RetrievedPassage]) -> bool:
    return any(item.document_id in DEMO_DOCUMENT_IDS for item in passages)


def is_rate_limited(message: str) -> bool:
    text = message.lower()
    if "no text" in text or "not installed" in text:
        return False
    markers = (
        "429",
        "503",
        "timeout",
        "timed out",
        "deadline",
        "resource_exhausted",
        "rate limit",
        "rate-limit",
        "too many requests",
        "unavailable",
    )
    return any(marker in text for marker in markers)


def _stem(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        _stem(token)
        for token in _TOKEN.findall(norm_v1_text(text))
        if token not in _STOP and _stem(token) not in _STOP
    )


def _asks_cost(question: str) -> bool:
    tokens = set(_TOKEN.findall(norm_v1_text(question)))
    return bool(tokens & _COST) or "how much" in norm_v1_text(question)


def _has_amount(text: str) -> bool:
    for token in _TOKEN.findall(norm_v1_text(text)):
        if token in {"usd", "dollar", "dollars"} or any(char.isdigit() for char in token):
            return True
    return False


def best_passage(question: str, passages: Sequence[RetrievedPassage]) -> RetrievedPassage | None:
    """Overlap on distinctive question tokens. Cost ties prefer a price passage."""
    if not passages:
        return None
    passage_tokens = [set(_tokens(item.text)) for item in passages]
    counts: Counter[str] = Counter()
    for tokens in passage_tokens:
        counts.update(tokens)
    half = len(passages) / 2
    question_tokens = [token for token in _tokens(question) if counts[token] <= half]
    ranked: list[tuple[int, RetrievedPassage]] = []
    for passage, tokens in zip(passages, passage_tokens, strict=True):
        score = sum(1 for token in question_tokens if token in tokens)
        ranked.append((score, passage))
    best_score = max(score for score, _passage in ranked)
    if best_score <= 0:
        return None
    tied = [passage for score, passage in ranked if score == best_score]
    if _asks_cost(question):
        for passage in tied:
            if _has_amount(passage.text):
                return passage
    return tied[0]


def _not_found_answer() -> ProviderAnswer:
    return ProviderAnswer(
        answer_text="The documents don't cover that.",
        citations=(),
        model_id="demo-fallback",
        prompt_version="demo-fallback-v1",
        usage=Usage(),
        answer_type="not_found",
    )


def canned_answer(question: str, passages: Sequence[RetrievedPassage]) -> ProviderAnswer | None:
    demo = [item for item in passages if item.document_id in DEMO_DOCUMENT_IDS]
    if not demo:
        return None
    passage = best_passage(question, demo)
    if passage is None:
        return _not_found_answer()
    return ProviderAnswer(
        answer_text=passage.text,
        citations=(
            ProviderCitation(passage_version_id=passage.passage_version_id, quote=passage.text),
        ),
        model_id="demo-fallback",
        prompt_version="demo-fallback-v1",
        usage=Usage(),
        answer_type="grounded",
    )


def canned_verdict(
    claim_text: str, passages: Sequence[RetrievedPassage]
) -> tuple[str, RetrievedPassage] | None:
    """Compare the claim with the overlapping passage from this snapshot. Not a fixed price."""
    demo = [item for item in passages if item.document_id in DEMO_DOCUMENT_IDS]
    passage = best_passage(claim_text, demo)
    if passage is None:
        return None
    claim = norm_v1_text(claim_text)
    fresh = norm_v1_text(passage.text)
    if claim == fresh or claim in fresh or fresh in claim:
        return "SUPPORTED", passage
    return "CONTRADICTED", passage
