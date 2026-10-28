from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from aftermath.core.contracts import Contract, Hash, Name, UtcTime
from aftermath.core.corpus import Version
from aftermath.core.errors import DomainError
from aftermath.core.text import bytes_hash, canonical_json

Relation = Literal[
    "IDENTICAL", "MOVED", "REFORMATTED", "MODIFIED", "MERGED", "SPLIT", "ADDED", "DELETED"
]
ChangeKind = Literal[
    "ADDED",
    "DELETED",
    "MODIFIED",
    "MOVED",
    "SPLIT",
    "MERGED",
    "REFORMATTED",
    "DOCUMENT_ADDED",
    "DOCUMENT_DELETED",
    "EXPANDED_UNCERTAIN",
    "AUTHORITY_CHANGED",
]
Confidence = Literal["HIGH", "LOW"]
Offset = Annotated[int, Field(ge=0)]

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
SENTENCE_END = re.compile(r"[.!?]\s+(?=[A-Z0-9\"'\[(])")
TOKEN = re.compile(r"\S+")
WORD = re.compile(r"\w+", re.UNICODE)
FEATURE_TOKEN = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MONTH_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+\d{1,2}(?:,\s*\d{4})?|\s+\d{4})\b",
    re.IGNORECASE,
)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
QUALIFIERS = (
    "only",
    "all",
    "every",
    "except",
    "until",
    "starting",
    "effective",
    "before",
    "after",
    "at least",
    "at most",
    "up to",
)


class AlignmentError(DomainError):
    def __init__(self, message: str):
        super().__init__("ALIGNMENT_ERROR", message, 500)


class NormalizedView(Contract):
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]
    units: tuple[tuple[int, int], ...]

    def canonical_span(self, start: int, end: int) -> tuple[int, int]:
        if start < 0 or end <= start or end > len(self.text):
            raise DomainError("INVALID_NORMALIZED_SPAN", "Normalized span is outside the view")
        if any(
            unit_start < end and start < unit_end and (start > unit_start or end < unit_end)
            for unit_start, unit_end in self.units
        ):
            raise DomainError("INVALID_NORMALIZED_SPAN", "Normalized span splits a unit")
        return min(self.starts[start:end]), max(self.ends[start:end])


def norm_v1_text(text: str) -> str:
    """Exact norm-v1: whole-string NFKC, case-fold, collapse whitespace runs, strip."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _canonical_order(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
    # Canonical reordering over the WHOLE decomposed string, not per source character.
    ordered: list[tuple[str, int]] = []
    run: list[tuple[str, int]] = []
    for item in items:
        if unicodedata.combining(item[0]):
            run.append(item)
            continue
        ordered.extend(sorted(run, key=lambda value: unicodedata.combining(value[0])))
        run = []
        ordered.append(item)
    ordered.extend(sorted(run, key=lambda value: unicodedata.combining(value[0])))
    return ordered


def _normalization_groups(text: str) -> list[tuple[str, tuple[int, ...]]]:
    """Whole-string NFKC groups: (normalized casefolded text, source code-point indices).

    Each source code point is NFKD-decomposed with its index kept, the full result is
    canonically reordered, split into units at starters, and adjacent units are merged
    whenever composing them together differs from composing them apart (Hangul jamo,
    halfwidth voiced marks, two-part vowels, a starter plus marks from later code points).
    Concatenating the groups reproduces norm_v1_text(text) exactly.
    """
    decomposed = [
        (item, index)
        for index, character in enumerate(text)
        for item in unicodedata.normalize("NFKD", character)
    ]
    units: list[list[tuple[str, int]]] = []
    for item in _canonical_order(decomposed):
        if units and unicodedata.combining(item[0]):
            units[-1].append(item)
        else:
            units.append([item])
    groups: list[list[tuple[str, int]]] = []
    for unit in units:
        if groups:
            left = "".join(value for value, _ in groups[-1])
            right = "".join(value for value, _ in unit)
            if unicodedata.normalize("NFC", left + right) != unicodedata.normalize(
                "NFC", left
            ) + unicodedata.normalize("NFC", right):
                groups[-1].extend(unit)
                continue
        groups.append(list(unit))
    return [
        (
            unicodedata.normalize("NFC", "".join(value for value, _ in group)).casefold(),
            tuple(index for _, index in group),
        )
        for group in groups
    ]


def normalized_view(text: str) -> NormalizedView:
    # Whitespace handling matches norm_v1_text exactly: collapse runs to one space and
    # strip the ends. Each emitted character is tagged with a unit id (its group, or a
    # fresh id for a collapsed space); units are the contiguous same-id output ranges,
    # so canonical_span can refuse a span that would split one group.
    output: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    unit_ids: list[int] = []
    pending_space: tuple[int, int] | None = None
    next_unit = 0
    for derived, indices in _normalization_groups(text):
        low, high = min(indices), max(indices) + 1
        group_unit = next_unit
        next_unit += 1
        for item in derived:
            if item.isspace():
                pending_space = (pending_space[0] if pending_space else low, high)
                continue
            if pending_space and output:
                output.append(" ")
                starts.append(pending_space[0])
                ends.append(pending_space[1])
                unit_ids.append(next_unit)
                next_unit += 1
            pending_space = None
            output.append(item)
            starts.append(low)
            ends.append(high)
            unit_ids.append(group_unit)
    units: list[tuple[int, int]] = []
    index = 0
    while index < len(unit_ids):
        end = index + 1
        while end < len(unit_ids) and unit_ids[end] == unit_ids[index]:
            end += 1
        units.append((index, end))
        index = end
    value = "".join(output)
    if value != norm_v1_text(text):
        raise DomainError("NORMALIZATION_ERROR", "norm-v1 mapping diverged from whole-string text")
    return NormalizedView(
        text=value,
        starts=tuple(starts),
        ends=tuple(ends),
        units=tuple(units),
    )


def locate_normalized_all(text: str, query: str) -> tuple[tuple[int, int], ...]:
    source = normalized_view(text)
    needle = norm_v1_text(query)
    if not needle:
        return ()
    matches: list[tuple[int, int]] = []
    position = 0
    while True:
        found = source.text.find(needle, position)
        if found < 0:
            break
        try:
            span = source.canonical_span(found, found + len(needle))
        except DomainError:
            position = found + 1
            continue
        if norm_v1_text(text[span[0] : span[1]]) == needle and span not in matches:
            matches.append(span)
        position = found + 1
    return tuple(matches)


def locate_normalized(text: str, query: str) -> tuple[int, int] | None:
    matches = locate_normalized_all(text, query)
    if len(matches) > 1:
        raise DomainError(
            "AMBIGUOUS_NORMALIZED_MATCH", "Normalized query has multiple matches", 409
        )
    return matches[0] if matches else None


class SegmentedPassage(Contract):
    ordinal: int = Field(ge=1)
    start: Offset
    end: Offset
    text: str
    section_path: tuple[str, ...]
    content_hash: Hash
    norm_hash: Hash

    @model_validator(mode="after")
    def valid_span(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Passage span must be nonempty")
        return self


def _chunks(start: int, end: int, text: str, limit: int) -> list[tuple[int, int]]:
    if end - start <= limit:
        return [(start, end)]
    relative = text[start:end]
    boundaries = [0, *(match.end() for match in SENTENCE_END.finditer(relative)), len(relative)]
    sentences = [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]
    chunks: list[tuple[int, int]] = []
    chunk_start, chunk_end = sentences[0]
    for sentence_start, sentence_end in sentences[1:]:
        if sentence_end - chunk_start <= limit:
            chunk_end = sentence_end
        else:
            chunks.append((start + chunk_start, start + chunk_end))
            chunk_start, chunk_end = sentence_start, sentence_end
    chunks.append((start + chunk_start, start + chunk_end))
    return chunks


def segment_text(text: str, max_passage_length: int = 1200) -> list[SegmentedPassage]:
    passages: list[SegmentedPassage] = []
    sections: list[str | None] = [None] * 6
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    paragraph_section: tuple[str, ...] = ()
    position = 0

    def flush() -> None:
        nonlocal paragraph_start, paragraph_end
        if paragraph_start is None or paragraph_end is None:
            return
        for chunk_start, chunk_end in _chunks(
            paragraph_start, paragraph_end, text, max_passage_length
        ):
            value = text[chunk_start:chunk_end]
            passages.append(
                SegmentedPassage(
                    ordinal=len(passages) + 1,
                    start=chunk_start,
                    end=chunk_end,
                    text=value,
                    section_path=paragraph_section,
                    content_hash=bytes_hash(value.encode()),
                    norm_hash=bytes_hash(norm_v1_text(value).encode()),
                )
            )
        paragraph_start = paragraph_end = None

    for line in text.split("\n"):
        line_start, line_end = position, position + len(line)
        heading = HEADING.fullmatch(line)
        if heading:
            flush()
            level = len(heading.group(1))
            sections[level - 1] = heading.group(2)
            sections[level:] = [None] * (6 - level)
        elif not line:
            flush()
        else:
            if paragraph_start is None:
                paragraph_start = line_start
                paragraph_section = tuple(section for section in sections if section is not None)
            paragraph_end = line_end
        position = line_end + 1
    flush()
    return passages


class PassageVersion(Contract):
    workspace_id: UUID
    corpus_id: Name
    document_id: Name
    document_version_id: str
    passage_version_id: str
    ordinal: int = Field(ge=1)
    start: Offset
    end: Offset
    text: str
    section_path: tuple[str, ...]
    content_hash: Hash
    norm_hash: Hash
    lineage_id: str
    segmentation_version: Literal["seg-v1"] = "seg-v1"
    norm_version: Literal["norm-v1"] | None = "norm-v1"

    @model_validator(mode="after")
    def identity(self) -> Self:
        expected = (
            f"pv:{self.document_id}@{self.document_version_id.split('@', 1)[1]}#p{self.ordinal:04d}"
        )
        if self.passage_version_id != expected:
            raise ValueError("Passage version ID does not match its immutable identity")
        if self.end <= self.start or len(self.text) != self.end - self.start:
            raise ValueError("Passage offsets must reproduce passage text")
        return self


class AlignmentEdge(Contract):
    workspace_id: UUID
    corpus_id: Name
    document_id: Name
    update_event_id: str
    lineage_edge_id: str
    edge_ordinal: int = Field(ge=1)
    from_passage_version_ids: tuple[str, ...]
    to_passage_version_ids: tuple[str, ...]
    relation: Relation
    alignment_score: float | None = Field(default=None, ge=0, le=1)
    alignment_confidence: Confidence
    alignment_method: Literal["diff-v1/dice-v1"] = "diff-v1/dice-v1"
    reason: dict[str, Any] = Field(default_factory=dict)


class TimelineAlignment(Contract):
    workspace_id: UUID
    corpus_id: Name
    document_id: Name
    update_event_id: str
    timeline_alignment_edge_id: str
    alignment_ordinal: int = Field(ge=1)
    applicability_change_id: str
    old_document_version_id: str
    new_document_version_id: str
    from_passage_version_ids: tuple[str, ...]
    to_passage_version_ids: tuple[str, ...]
    relation: Relation
    alignment_score: float | None = Field(default=None, ge=0, le=1)
    alignment_confidence: Confidence
    alignment_method: Literal["diff-v1/dice-v1"] = "diff-v1/dice-v1"
    reason: dict[str, Any] = Field(default_factory=dict)
    recorded_by: Literal["timeline-v1", "migration-0004-reclassification"] = "timeline-v1"
    legacy_lineage_edge_id: str | None = None


class ChangeFeatures(Contract):
    numeric_change: bool = False
    numbers_old: tuple[str, ...] = ()
    numbers_new: tuple[str, ...] = ()
    date_change: bool = False
    dates_old: tuple[str, ...] = ()
    dates_new: tuple[str, ...] = ()
    negation_change: bool = False
    qualifiers_old: tuple[str, ...] = ()
    qualifiers_new: tuple[str, ...] = ()
    qualifier_change: bool = False


class ChangeSpan(Contract):
    workspace_id: UUID
    corpus_id: Name
    update_event_id: str
    document_id: Name
    change_span_id: str
    span_ordinal: int = Field(ge=1)
    old_document_version_id: str | None
    new_document_version_id: str | None
    old_passage_version_id: str | None
    new_passage_version_id: str | None
    kind: ChangeKind
    lineage_edge_id: str | None
    timeline_alignment_edge_id: str | None = None
    reclassified_lineage_edge_id: str | None = None
    old_start: Offset | None
    old_end: Offset | None
    new_start: Offset | None
    new_end: Offset | None
    old_text: str | None
    new_text: str | None
    features: ChangeFeatures
    alignment_confidence: Confidence
    effective_from: UtcTime
    effective_to: UtcTime | None = None
    applicability_change_id: str | None = None
    text_diff_reused: bool = False
    feature_version: Literal["features-v1"] | None = "features-v1"
    origin: Literal["LATEST_OBSERVED", "TIMELINE", "EXPANSION", "AUTHORITY"]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sides(self) -> Self:
        for prefix in ("old", "new"):
            start = getattr(self, f"{prefix}_start")
            end = getattr(self, f"{prefix}_end")
            value = getattr(self, f"{prefix}_text")
            if (start is None) != (end is None):
                raise ValueError("Both offsets on a span side must be present")
            if start is not None and (end <= start or value is None or len(value) != end - start):
                raise ValueError("Span offsets must reproduce exact canonical text")
        if self.kind != "AUTHORITY_CHANGED" and self.old_text is None and self.new_text is None:
            raise ValueError("A textual change span requires at least one side")
        if self.origin == "TIMELINE":
            current = self.lineage_edge_id is None and self.timeline_alignment_edge_id is not None
            legacy = (
                self.lineage_edge_id is not None
                and self.reclassified_lineage_edge_id == self.lineage_edge_id
                and self.timeline_alignment_edge_id is not None
            )
            if not (current or legacy):
                raise ValueError("Timeline spans require a timeline alignment")
        elif self.timeline_alignment_edge_id is not None:
            raise ValueError("Only timeline spans may reference a timeline alignment")
        return self


class ApplicabilityChange(Contract):
    workspace_id: UUID
    corpus_id: Name
    update_event_id: str
    document_id: Name
    applicability_change_id: str
    change_ordinal: int = Field(ge=1)
    parent_snapshot_id: str | None
    result_snapshot_id: str
    interval_from: UtcTime
    interval_to: UtcTime | None
    old_effective_version_id: str | None
    new_effective_version_id: str | None
    old_effective_fingerprint: Hash
    new_effective_fingerprint: Hash
    reason: Literal["CONTENT", "AUTHORITY", "APPLICABILITY", "ADDITION", "DELETION"]
    text_diff_reused: bool
    timeline_version: Literal["timeline-v1"] = "timeline-v1"


class ChangeSet(Contract):
    passages: tuple[PassageVersion, ...] = ()
    edges: tuple[AlignmentEdge, ...] = ()
    timeline_alignments: tuple[TimelineAlignment, ...] = ()
    spans: tuple[ChangeSpan, ...] = ()
    applicability_changes: tuple[ApplicabilityChange, ...] = ()


class UpdateEventView(Contract):
    delivery_id: Name
    update_event_id: str
    as_of: UtcTime
    expected_head: str | None
    received_at: UtcTime
    status: str
    snapshot_id: str | None
    error_code: str | None


class ChangedDocumentView(Contract):
    document_id: Name
    old_version_id: str | None
    new_version_id: str
    span_count: int
    applicability_count: int


class DocumentComparison(Contract):
    delivery_id: Name
    document_id: Name
    parent_snapshot_id: str | None
    result_snapshot_id: str
    old_version: Version | None
    new_version: Version
    old_passages: tuple[PassageVersion, ...]
    new_passages: tuple[PassageVersion, ...]
    edges: tuple[AlignmentEdge, ...]
    timeline_alignments: tuple[TimelineAlignment, ...]
    spans: tuple[ChangeSpan, ...]
    applicability_changes: tuple[ApplicabilityChange, ...]


class TimelineInterval(Contract):
    snapshot_id: str
    interval_from: UtcTime
    interval_to: UtcTime | None
    version_id: str | None
    fingerprint: Hash
    active: bool


class TimelineCompareRequest(Contract):
    from_snapshot_id: str
    to_snapshot_id: str


def materialize_passages(version: Version) -> list[PassageVersion]:
    values = []
    revision = version.source_revision_id
    for passage in segment_text(version.text):
        values.append(
            PassageVersion(
                workspace_id=version.workspace_id,
                corpus_id=version.corpus_id,
                document_id=version.document_id,
                document_version_id=version.document_version_id,
                passage_version_id=f"pv:{version.document_id}@{revision}#p{passage.ordinal:04d}",
                ordinal=passage.ordinal,
                start=passage.start,
                end=passage.end,
                text=passage.text,
                section_path=passage.section_path,
                content_hash=passage.content_hash,
                norm_hash=passage.norm_hash,
                lineage_id=f"lin:{version.document_id}:{revision}:p{passage.ordinal:04d}",
            )
        )
    return values


def _tokens(value: str) -> list[str]:
    return WORD.findall(normalized_view(value).text)


def dice(old: str, new: str) -> float:
    left, right = Counter(_tokens(old)), Counter(_tokens(new))
    total = sum(left.values()) + sum(right.values())
    return 1.0 if total == 0 else 2 * sum((left & right).values()) / total


def containment(container: str, contained: str) -> float:
    outer, inner = Counter(_tokens(container)), Counter(_tokens(contained))
    return 1.0 if not inner else sum((outer & inner).values()) / sum(inner.values())


def _consecutive(passages: list[PassageVersion]) -> bool:
    return all(b.ordinal == a.ordinal + 1 for a, b in zip(passages, passages[1:], strict=False))


def align_passages(
    old: list[PassageVersion],
    new: list[PassageVersion],
    delivery_id: str,
    modification_threshold: float = 0.50,
    high_confidence_threshold: float = 0.70,
    ambiguity_margin: float = 0.05,
    containment_threshold: float = 0.80,
    max_candidate_pairs: int = 20000,
    edge_start_ordinal: int = 1,
) -> list[AlignmentEdge]:
    if len(old) * len(new) > max_candidate_pairs:
        raise DomainError("ALIGNMENT_LIMIT", "Passage alignment candidate limit exceeded", 413)
    used_old: set[str] = set()
    used_new: set[str] = set()
    drafts: list[
        tuple[
            Relation,
            list[PassageVersion],
            list[PassageVersion],
            float | None,
            Confidence,
            dict[str, Any],
        ]
    ] = []

    def add(
        relation: Relation,
        left: list[PassageVersion],
        right: list[PassageVersion],
        score: float | None,
        confidence: Confidence = "HIGH",
        reason: dict[str, Any] | None = None,
    ) -> None:
        if any(item.passage_version_id in used_old for item in left) or any(
            item.passage_version_id in used_new for item in right
        ):
            raise AlignmentError("A passage was consumed by more than one edge")
        used_old.update(item.passage_version_id for item in left)
        used_new.update(item.passage_version_id for item in right)
        drafts.append((relation, left, right, score, confidence, reason or {}))

    for current in new:
        candidates = [
            item
            for item in old
            if item.content_hash == current.content_hash and item.passage_version_id not in used_old
        ]
        candidates.sort(
            key=lambda item: (
                item.ordinal != current.ordinal,
                item.ordinal,
                item.passage_version_id,
            )
        )
        if candidates:
            prior = candidates[0]
            same = prior.ordinal == current.ordinal and prior.section_path == current.section_path
            add("IDENTICAL" if same else "MOVED", [prior], [current], 1.0)

    for current in new:
        if current.passage_version_id in used_new:
            continue
        candidates = [
            item
            for item in old
            if norm_v1_text(item.text) == norm_v1_text(current.text)
            and item.passage_version_id not in used_old
        ]
        candidates.sort(
            key=lambda item: (
                item.ordinal != current.ordinal,
                item.ordinal,
                item.passage_version_id,
            )
        )
        if candidates:
            add("REFORMATTED", [candidates[0]], [current], 1.0)

    pairs = sorted(
        (
            (dice(left.text, right.text), left, right)
            for left in old
            if left.passage_version_id not in used_old
            for right in new
            if right.passage_version_id not in used_new
        ),
        key=lambda item: (-item[0], item[1].ordinal, item[2].ordinal, item[1].passage_version_id),
    )
    for score, left, right in pairs:
        if (
            score < modification_threshold
            or left.passage_version_id in used_old
            or right.passage_version_id in used_new
        ):
            continue
        runners = [
            value
            for value, other_left, other_right in pairs
            if (other_left == left or other_right == right)
            and not (other_left == left and other_right == right)
        ]
        runner = max(runners, default=0.0)
        confidence: Confidence = (
            "LOW"
            if score < high_confidence_threshold or score - runner < ambiguity_margin
            else "HIGH"
        )
        add("MODIFIED", [left], [right], score, confidence, {"runner_up": runner})

    remaining_old = [item for item in old if item.passage_version_id not in used_old]
    remaining_new = [item for item in new if item.passage_version_id not in used_new]
    merge_options: list[tuple[float, int, PassageVersion, list[PassageVersion]]] = []
    for target in remaining_new:
        for size in (2, 3):
            for index in range(len(remaining_old) - size + 1):
                group = remaining_old[index : index + size]
                if _consecutive(group):
                    score = containment(" ".join(item.text for item in group), target.text)
                    if score >= containment_threshold:
                        merge_options.append((score, target.ordinal, target, group))
    for score, _, target, group in sorted(
        merge_options, key=lambda item: (-item[0], item[1], item[3][0].ordinal)
    ):
        if target.passage_version_id not in used_new and not any(
            item.passage_version_id in used_old for item in group
        ):
            add("MERGED", group, [target], score)

    remaining_old = [item for item in old if item.passage_version_id not in used_old]
    remaining_new = [item for item in new if item.passage_version_id not in used_new]
    split_options: list[tuple[float, int, PassageVersion, list[PassageVersion]]] = []
    for source in remaining_old:
        for size in (2, 3):
            for index in range(len(remaining_new) - size + 1):
                group = remaining_new[index : index + size]
                if _consecutive(group):
                    score = containment(" ".join(item.text for item in group), source.text)
                    if score >= containment_threshold:
                        split_options.append((score, source.ordinal, source, group))
    for score, _, source, group in sorted(
        split_options, key=lambda item: (-item[0], item[1], item[3][0].ordinal)
    ):
        if source.passage_version_id not in used_old and not any(
            item.passage_version_id in used_new for item in group
        ):
            add("SPLIT", [source], group, score)

    for item in old:
        if item.passage_version_id not in used_old:
            add("DELETED", [item], [], None)
    for item in new:
        if item.passage_version_id not in used_new:
            add("ADDED", [], [item], None)

    if used_old != {item.passage_version_id for item in old} or used_new != {
        item.passage_version_id for item in new
    }:
        raise AlignmentError("Alignment did not cover every passage exactly once")

    edges: list[AlignmentEdge] = []
    for ordinal, (relation, edge_old, edge_new, edge_score, confidence, reason) in enumerate(
        drafts, edge_start_ordinal
    ):
        edge = AlignmentEdge(
            workspace_id=(edge_old or edge_new)[0].workspace_id,
            corpus_id=(edge_old or edge_new)[0].corpus_id,
            document_id=(edge_old or edge_new)[0].document_id,
            update_event_id=f"upd:{delivery_id}",
            lineage_edge_id=f"le:{delivery_id}:{ordinal:04d}",
            edge_ordinal=ordinal,
            from_passage_version_ids=tuple(item.passage_version_id for item in edge_old),
            to_passage_version_ids=tuple(item.passage_version_id for item in edge_new),
            relation=relation,
            alignment_score=edge_score,
            alignment_confidence=confidence,
            reason=reason,
        )
        edges.append(edge)
    return edges


def assign_lineage(
    old: list[PassageVersion], new: list[PassageVersion], edges: list[AlignmentEdge]
) -> list[PassageVersion]:
    old_by_id = {item.passage_version_id: item for item in old}
    inherited: dict[str, str] = {}
    for edge in edges:
        if edge.relation in ("IDENTICAL", "MOVED", "REFORMATTED", "MODIFIED"):
            inherited[edge.to_passage_version_ids[0]] = old_by_id[
                edge.from_passage_version_ids[0]
            ].lineage_id
    return [
        item.model_copy(update={"lineage_id": inherited[item.passage_version_id]})
        if item.passage_version_id in inherited
        else item
        for item in new
    ]


def timeline_alignments_from_edges(
    edges: list[AlignmentEdge],
    applicability_change_id: str,
    old_document_version_id: str,
    new_document_version_id: str,
    comparison_start_ordinal: int = 1,
) -> list[TimelineAlignment]:
    comparisons: list[TimelineAlignment] = []
    delivery_id = edges[0].update_event_id.removeprefix("upd:") if edges else ""
    for ordinal, edge in enumerate(edges, comparison_start_ordinal):
        comparisons.append(
            TimelineAlignment(
                workspace_id=edge.workspace_id,
                corpus_id=edge.corpus_id,
                document_id=edge.document_id,
                update_event_id=edge.update_event_id,
                timeline_alignment_edge_id=f"ta:{delivery_id}:{ordinal:04d}",
                alignment_ordinal=ordinal,
                applicability_change_id=applicability_change_id,
                old_document_version_id=old_document_version_id,
                new_document_version_id=new_document_version_id,
                from_passage_version_ids=edge.from_passage_version_ids,
                to_passage_version_ids=edge.to_passage_version_ids,
                relation=edge.relation,
                alignment_score=edge.alignment_score,
                alignment_confidence=edge.alignment_confidence,
                alignment_method=edge.alignment_method,
                reason=edge.reason,
            )
        )
    return comparisons


def _feature_tokens(value: str) -> tuple[str, ...]:
    folded = value.replace("’", "'").replace("ʼ", "'").replace("＇", "'")
    return tuple(match.group() for match in FEATURE_TOKEN.finditer(norm_v1_text(folded)))


def _phrase_count(tokens: tuple[str, ...], phrase: str) -> int:
    expected = tuple(phrase.split())
    size = len(expected)
    return sum(tokens[index : index + size] == expected for index in range(len(tokens) - size + 1))


def _negation_markers(value: str) -> tuple[str, ...]:
    tokens = _feature_tokens(value)
    markers: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index : index + 2] == ("no", "longer"):
            markers.append("no longer")
            index += 2
            continue
        token = tokens[index]
        if token in {"not", "no", "never", "none", "cannot"}:
            markers.append(token)
        elif token.endswith("n't"):
            markers.append("n't")
        index += 1
    return tuple(markers)


def change_features(old: str | None, new: str | None) -> ChangeFeatures:
    left, right = old or "", new or ""
    numbers_old, numbers_new = tuple(NUMBER.findall(left)), tuple(NUMBER.findall(right))
    dates_old = tuple(ISO_DATE.findall(left) + MONTH_DATE.findall(left) + YEAR.findall(left))
    dates_new = tuple(ISO_DATE.findall(right) + MONTH_DATE.findall(right) + YEAR.findall(right))
    tokens_old, tokens_new = _feature_tokens(left), _feature_tokens(right)
    qualifiers_old = tuple(item for item in QUALIFIERS if _phrase_count(tokens_old, item))
    qualifiers_new = tuple(item for item in QUALIFIERS if _phrase_count(tokens_new, item))
    return ChangeFeatures(
        numeric_change=Counter(numbers_old) != Counter(numbers_new),
        numbers_old=numbers_old,
        numbers_new=numbers_new,
        date_change=Counter(dates_old) != Counter(dates_new),
        dates_old=dates_old,
        dates_new=dates_new,
        negation_change=Counter(_negation_markers(left)) != Counter(_negation_markers(right)),
        qualifiers_old=qualifiers_old,
        qualifiers_new=qualifiers_new,
        qualifier_change=set(qualifiers_old) != set(qualifiers_new),
    )


def containing_sentence(
    text: str, start: int, end: int, *, affinity: Literal["left", "right"] = "right"
) -> tuple[int, int, str]:
    """Return the smallest complete sentence window containing a code-point span.

    Use spec sentences-v1: punctuation followed by whitespace and an uppercase
    letter, digit, or opening quote/bracket. Boundary whitespace is excluded.
    Empty opcode sides select the adjacent sentence using explicit affinity;
    passage endpoints clamp to the first/last sentence, never an absent side.
    """
    if start < 0 or end < start or end > len(text):
        raise DomainError("INVALID_FEATURE_SPAN", "Feature span is outside the passage")
    windows: list[tuple[int, int]] = []
    sentence_start = 0
    for match in SENTENCE_END.finditer(text):
        sentence_end = match.start() + 1
        if sentence_start < sentence_end:
            windows.append((sentence_start, sentence_end))
        sentence_start = match.end()
    if sentence_start < len(text):
        windows.append((sentence_start, len(text)))
    if start == end:
        if not windows:
            return start, end, ""
        if affinity == "left":
            selected = next(
                (window for window in reversed(windows) if window[0] < start), windows[0]
            )
        else:
            selected = next((window for window in windows if start < window[1]), windows[-1])
        return selected[0], selected[1], text[selected[0] : selected[1]]
    touched = [
        (window_start, window_end)
        for window_start, window_end in windows
        if window_start < end and start < window_end
    ]
    if not touched:
        # Token spans do not normally point at inter-sentence whitespace, but a
        # deterministic passage-local fallback keeps the helper total.
        return start, end, text[start:end]
    window_start, window_end = touched[0][0], touched[-1][1]
    return window_start, window_end, text[window_start:window_end]


def _side(
    passage: PassageVersion | None,
    start: int | None,
    end: int | None,
    document_text: str | None = None,
) -> dict[str, Any]:
    if passage is None or start is None or end is None:
        return {
            "start": None,
            "end": None,
            "text": None,
            "passage": None,
            "context_start": None,
            "context_end": None,
            "context_text": None,
        }
    if passage.start <= start < end <= passage.end:
        relative_start, relative_end, context_text = containing_sentence(
            passage.text, start - passage.start, end - passage.start
        )
        context_start = passage.start + relative_start
        context_end = passage.start + relative_end
    else:
        # SPLIT/MERGE sides may cover multiple complete passages. Their exact
        # changed side is already the smallest deterministic context available.
        context_start, context_end = start, end
        context_text = (
            document_text[start:end]
            if document_text is not None
            else passage.text[start - passage.start : end - passage.start]
        )
    return {
        "start": start,
        "end": end,
        "text": (
            document_text[start:end]
            if document_text is not None
            else passage.text[start - passage.start : end - passage.start]
        ),
        "passage": passage.passage_version_id,
        "context_start": context_start,
        "context_end": context_end,
        "context_text": context_text,
    }


def _token_span(
    passage: PassageVersion,
    tokens: list[re.Match[str]],
    start: int,
    end: int,
    *,
    affinity: Literal["left", "right"] = "right",
) -> dict[str, Any]:
    if start == end:
        boundary = tokens[start].start() if start < len(tokens) else len(passage.text)
        low, high, context = containing_sentence(
            passage.text, boundary, boundary, affinity=affinity
        )
        return {
            **_side(None, None, None),
            "context_start": passage.start + low,
            "context_end": passage.start + high,
            "context_text": context,
            "context_passage": passage.passage_version_id,
            "opcode_boundary": passage.start + boundary,
            "boundary_affinity": affinity,
        }
    return _side(
        passage,
        passage.start + tokens[start].start(),
        passage.start + tokens[end - 1].end(),
    )


def spans_from_edges(
    edges: list[AlignmentEdge] | list[TimelineAlignment],
    old: list[PassageVersion],
    new: list[PassageVersion],
    old_version: Version | None,
    new_version: Version,
    delivery_id: str,
    origin: Literal["LATEST_OBSERVED", "TIMELINE"] = "LATEST_OBSERVED",
    applicability_change_id: str | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    span_start_ordinal: int = 1,
) -> list[ChangeSpan]:
    old_by_id = {item.passage_version_id: item for item in old}
    new_by_id = {item.passage_version_id: item for item in new}
    drafts: list[
        tuple[
            ChangeKind,
            AlignmentEdge | TimelineAlignment,
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ]
    ] = []
    for edge in edges:
        left = [old_by_id[value] for value in edge.from_passage_version_ids]
        right = [new_by_id[value] for value in edge.to_passage_version_ids]
        if edge.relation == "IDENTICAL":
            continue
        if edge.relation == "MODIFIED":
            left_tokens, right_tokens = (
                list(TOKEN.finditer(left[0].text)),
                list(TOKEN.finditer(right[0].text)),
            )
            matcher = SequenceMatcher(
                None,
                [item.group() for item in left_tokens],
                [item.group() for item in right_tokens],
                autojunk=False,
            )
            for opcode, a, b, c, d in matcher.get_opcodes():
                if opcode != "equal":
                    old_side = _token_span(left[0], left_tokens, a, b)
                    new_side = _token_span(right[0], right_tokens, c, d)
                    # At a sentence boundary, use the unchanged neighbor that
                    # belongs to the nonempty side's sentence. This avoids
                    # comparing an insertion at one sentence's end to the next.
                    if opcode == "insert":
                        follows = d < len(right_tokens) and (
                            right[0].start + right_tokens[d].start() < new_side["context_end"]
                        )
                        old_side = _token_span(
                            left[0], left_tokens, a, b, affinity="right" if follows else "left"
                        )
                    elif opcode == "delete":
                        follows = b < len(left_tokens) and (
                            left[0].start + left_tokens[b].start() < old_side["context_end"]
                        )
                        new_side = _token_span(
                            right[0], right_tokens, c, d, affinity="right" if follows else "left"
                        )
                    drafts.append(
                        (
                            "MODIFIED",
                            edge,
                            old_side,
                            new_side,
                            {"opcode": opcode},
                        )
                    )
            continue
        old_side = (
            _side(
                left[0],
                min(item.start for item in left),
                max(item.end for item in left),
                old_version.text if old_version else None,
            )
            if left
            else _side(None, None, None)
        )
        new_side = (
            _side(
                right[0],
                min(item.start for item in right),
                max(item.end for item in right),
                new_version.text,
            )
            if right
            else _side(None, None, None)
        )
        drafts.append((edge.relation, edge, old_side, new_side, {}))

    spans: list[ChangeSpan] = []
    for kind, edge, old_side, new_side, metadata in drafts:
        ordinal = span_start_ordinal + len(spans)
        local_features = change_features(old_side["text"], new_side["text"])
        context_features = change_features(old_side["context_text"], new_side["context_text"])
        feature_evidence = {
            "implementation": "features-v1-symmetric-context-2026-11-04",
            "selection": "smallest containing sentence within each passage",
            "boundary": "sentences-v1; empty opcode uses corresponding neighbor affinity",
            "old": {
                "span_start": old_side["start"],
                "span_end": old_side["end"],
                "context_start": old_side["context_start"],
                "context_end": old_side["context_end"],
                "context_text": old_side["context_text"],
                "opcode_boundary": old_side.get("opcode_boundary"),
                "boundary_affinity": old_side.get("boundary_affinity"),
                "context_passage": old_side.get("context_passage", old_side["passage"]),
            },
            "new": {
                "span_start": new_side["start"],
                "span_end": new_side["end"],
                "context_start": new_side["context_start"],
                "context_end": new_side["context_end"],
                "context_text": new_side["context_text"],
                "opcode_boundary": new_side.get("opcode_boundary"),
                "boundary_affinity": new_side.get("boundary_affinity"),
                "context_passage": new_side.get("context_passage", new_side["passage"]),
            },
            "local": local_features.model_dump(mode="json"),
            "containing_sentence": context_features.model_dump(mode="json"),
        }
        spans.append(
            ChangeSpan(
                workspace_id=new_version.workspace_id,
                corpus_id=new_version.corpus_id,
                update_event_id=f"upd:{delivery_id}",
                document_id=new_version.document_id,
                change_span_id=f"cs:{delivery_id}:{ordinal:04d}",
                span_ordinal=ordinal,
                old_document_version_id=old_version.document_version_id if old_version else None,
                new_document_version_id=new_version.document_version_id,
                old_passage_version_id=old_side["passage"],
                new_passage_version_id=new_side["passage"],
                kind=kind,
                lineage_edge_id=(edge.lineage_edge_id if isinstance(edge, AlignmentEdge) else None),
                timeline_alignment_edge_id=(
                    edge.timeline_alignment_edge_id if isinstance(edge, TimelineAlignment) else None
                ),
                old_start=old_side["start"],
                old_end=old_side["end"],
                new_start=new_side["start"],
                new_end=new_side["end"],
                old_text=old_side["text"],
                new_text=new_side["text"],
                features=context_features,
                alignment_confidence=edge.alignment_confidence,
                effective_from=effective_from or new_version.effective_from,
                effective_to=effective_to,
                applicability_change_id=applicability_change_id,
                origin=origin,
                metadata={**metadata, "feature_evidence": feature_evidence},
            )
        )
    return spans


def uncertain_expansions(
    edges: list[AlignmentEdge],
    old: list[PassageVersion],
    new: list[PassageVersion],
    old_version: Version | None,
    new_version: Version,
    delivery_id: str,
    span_start_ordinal: int = 1,
) -> list[ChangeSpan]:
    uncertain_ids = {
        value
        for edge in edges
        if edge.alignment_confidence == "LOW" or edge.relation in ("ADDED", "DELETED")
        for value in (*edge.from_passage_version_ids, *edge.to_passage_version_ids)
    }
    sections: dict[tuple[str, ...], dict[str, list[PassageVersion]]] = {}
    for item in old:
        sections.setdefault(item.section_path, {"old": [], "new": []})["old"].append(item)
    for item in new:
        sections.setdefault(item.section_path, {"old": [], "new": []})["new"].append(item)
    whole_document = bool(old or new) and len(uncertain_ids) > (len(old) + len(new)) / 2
    targets: list[tuple[tuple[str, ...], list[PassageVersion], list[PassageVersion], str]] = []
    for section, sides in sorted(sections.items()):
        section_edges = [
            edge
            for edge in edges
            if any(
                value in {p.passage_version_id for p in (*sides["old"], *sides["new"])}
                for value in (*edge.from_passage_version_ids, *edge.to_passage_version_ids)
            )
        ]
        low = any(edge.alignment_confidence == "LOW" for edge in section_edges)
        unmatched_old = any(edge.relation == "DELETED" for edge in section_edges)
        unmatched_new = any(edge.relation == "ADDED" for edge in section_edges)
        if whole_document:
            continue
        if low or (unmatched_old and unmatched_new):
            targets.append(
                (
                    section,
                    sides["old"],
                    sides["new"],
                    "LOW_CONFIDENCE" if low else "BILATERAL_UNMATCHED",
                )
            )
    if whole_document:
        targets = [((), old, new, "DOCUMENT_MAJORITY_UNCERTAIN")]
    spans: list[ChangeSpan] = []
    for section, left, right, reason in targets:
        ordinal = span_start_ordinal + len(spans)
        old_start = min((item.start for item in left), default=None)
        old_end = max((item.end for item in left), default=None)
        new_start = min((item.start for item in right), default=None)
        new_end = max((item.end for item in right), default=None)
        old_text = (
            old_version.text[old_start:old_end]
            if old_version and old_start is not None and old_end is not None
            else None
        )
        new_text = (
            new_version.text[new_start:new_end]
            if new_start is not None and new_end is not None
            else None
        )
        spans.append(
            ChangeSpan(
                workspace_id=new_version.workspace_id,
                corpus_id=new_version.corpus_id,
                update_event_id=f"upd:{delivery_id}",
                document_id=new_version.document_id,
                change_span_id=f"cs:{delivery_id}:{ordinal:04d}",
                span_ordinal=ordinal,
                old_document_version_id=old_version.document_version_id if old_version else None,
                new_document_version_id=new_version.document_version_id,
                old_passage_version_id=left[0].passage_version_id if len(left) == 1 else None,
                new_passage_version_id=right[0].passage_version_id if len(right) == 1 else None,
                kind="EXPANDED_UNCERTAIN",
                lineage_edge_id=None,
                old_start=old_start,
                old_end=old_end,
                new_start=new_start,
                new_end=new_end,
                old_text=old_text,
                new_text=new_text,
                features=change_features(old_text, new_text),
                alignment_confidence="LOW",
                effective_from=new_version.effective_from,
                origin="EXPANSION",
                metadata={"reason": reason, "section_path": list(section)},
            )
        )
    return spans


def evidence_fingerprint(version: Version | None) -> str:
    state = (
        None
        if version is None or version.is_deletion
        else {
            "content_hash": version.content_hash,
            "source_type": version.source_type,
            "authority": version.authority,
        }
    )
    return bytes_hash(canonical_json(state))


def effective_version(versions: list[Version], at: datetime) -> Version | None:
    candidates = [item for item in versions if item.effective_from <= at]
    chosen = max(candidates, key=lambda item: (item.effective_from, item.source_seq), default=None)
    return None if chosen is None or chosen.is_deletion else chosen


def timeline_changes(
    before: list[Version],
    after: list[Version],
    delivery_id: str,
    parent_snapshot_id: str | None,
    result_snapshot_id: str,
    max_breakpoints: int = 1000,
    change_start_ordinal: int = 1,
) -> list[ApplicabilityChange]:
    if not after:
        return []
    points = sorted({item.effective_from for item in [*before, *after]})
    if len(points) > max_breakpoints:
        raise DomainError("TIMELINE_LIMIT", "Timeline breakpoint limit exceeded", 413)
    drafts: list[tuple[datetime, datetime | None, Version | None, Version | None]] = []
    for index, start in enumerate(points):
        end = points[index + 1] if index + 1 < len(points) else None
        old, new = effective_version(before, start), effective_version(after, start)
        if evidence_fingerprint(old) != evidence_fingerprint(new):
            if (
                drafts
                and drafts[-1][1] == start
                and evidence_fingerprint(drafts[-1][2]) == evidence_fingerprint(old)
                and evidence_fingerprint(drafts[-1][3]) == evidence_fingerprint(new)
            ):
                previous = drafts[-1]
                drafts[-1] = (previous[0], end, old, new)
            else:
                drafts.append((start, end, old, new))
    values: list[ApplicabilityChange] = []
    document = after[-1].document_id
    for ordinal, (start, end, old, new) in enumerate(drafts, change_start_ordinal):
        reason: Literal["CONTENT", "AUTHORITY", "APPLICABILITY", "ADDITION", "DELETION"]
        if old is None:
            reason = "ADDITION"
        elif new is None:
            reason = "DELETION"
        elif old.content_hash != new.content_hash:
            reason = "CONTENT"
        elif old.source_type != new.source_type or old.authority != new.authority:
            reason = "AUTHORITY"
        else:
            reason = "APPLICABILITY"
        values.append(
            ApplicabilityChange(
                workspace_id=after[-1].workspace_id,
                corpus_id=after[-1].corpus_id,
                update_event_id=f"upd:{delivery_id}",
                document_id=document,
                applicability_change_id=f"ac:{delivery_id}:{ordinal:04d}",
                change_ordinal=ordinal,
                parent_snapshot_id=parent_snapshot_id,
                result_snapshot_id=result_snapshot_id,
                interval_from=start,
                interval_to=end,
                old_effective_version_id=old.document_version_id if old else None,
                new_effective_version_id=new.document_version_id if new else None,
                old_effective_fingerprint=evidence_fingerprint(old),
                new_effective_fingerprint=evidence_fingerprint(new),
                reason=reason,
                text_diff_reused=False,
            )
        )
    return values
