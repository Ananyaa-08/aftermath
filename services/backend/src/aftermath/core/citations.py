"""Citation location and snapshot-scoped validation. Quotes are untrusted model output."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from aftermath.core.answers import ProviderCitation, RetrievedPassage, ValidatedCitation
from aftermath.core.changes import locate_normalized
from aftermath.core.errors import DomainError


def locate_quote(passage_text: str, quote: str) -> tuple[int, int] | None:
    if not quote or not passage_text:
        return None
    found = passage_text.find(quote)
    if found >= 0:
        return found, found + len(quote)
    try:
        return locate_normalized(passage_text, quote)
    except DomainError:
        return None


def validate_citations(
    citations: Sequence[ProviderCitation],
    eligible: Mapping[str, RetrievedPassage],
    workspace_id: UUID,
    corpus_id: str,
) -> tuple[ValidatedCitation, ...] | None:
    if not citations:
        return None
    accepted: list[ValidatedCitation] = []
    for item in citations:
        passage = eligible.get(item.passage_version_id)
        if (
            passage is None
            or passage.workspace_id != workspace_id
            or passage.corpus_id != corpus_id
        ):
            return None
        span = locate_quote(passage.text, item.quote)
        if span is None:
            return None
        start, end = span
        accepted.append(
            ValidatedCitation(
                passage_version_id=passage.passage_version_id,
                document_id=passage.document_id,
                document_version_id=passage.document_version_id,
                quote=passage.text[start:end],
                start=passage.start + start,
                end=passage.start + end,
                passage_start=start,
                passage_end=end,
            )
        )
    return tuple(accepted)
