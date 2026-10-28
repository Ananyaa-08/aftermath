from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from aftermath.core.changes import (
    AlignmentEdge,
    ApplicabilityChange,
    ChangeSet,
    ChangeSpan,
    PassageVersion,
    TimelineAlignment,
    align_passages,
    assign_lineage,
    change_features,
    materialize_passages,
    spans_from_edges,
    timeline_alignments_from_edges,
    timeline_changes,
    uncertain_expansions,
)
from aftermath.core.corpus import Version
from aftermath.core.errors import DomainError


def _document_span(
    old: Version | None,
    new: Version,
    delivery_id: str,
    ordinal: int,
    kind: Literal["DOCUMENT_ADDED", "DOCUMENT_DELETED", "AUTHORITY_CHANGED"],
) -> ChangeSpan:
    old_text = old.text if old and old.text else None
    new_text = new.text if new.text else None
    if kind == "AUTHORITY_CHANGED":
        old_text = new_text = None
    return ChangeSpan(
        workspace_id=new.workspace_id,
        corpus_id=new.corpus_id,
        update_event_id=f"upd:{delivery_id}",
        document_id=new.document_id,
        change_span_id=f"cs:{delivery_id}:{ordinal:04d}",
        span_ordinal=ordinal,
        old_document_version_id=old.document_version_id if old else None,
        new_document_version_id=new.document_version_id,
        old_passage_version_id=None,
        new_passage_version_id=None,
        kind=kind,
        lineage_edge_id=None,
        old_start=0 if old_text else None,
        old_end=len(old_text) if old_text else None,
        new_start=0 if new_text else None,
        new_end=len(new_text) if new_text else None,
        old_text=old_text,
        new_text=new_text,
        features=change_features(old_text, new_text),
        alignment_confidence="HIGH",
        effective_from=new.effective_from,
        origin="AUTHORITY" if kind == "AUTHORITY_CHANGED" else "LATEST_OBSERVED",
        metadata=(
            {
                "old_source_type": old.source_type if old else None,
                "new_source_type": new.source_type,
                "old_authority": old.authority if old else None,
                "new_authority": new.authority,
            }
            if kind == "AUTHORITY_CHANGED"
            else {}
        ),
    )


def build_change_set(
    delivery_id: str,
    parent_snapshot_id: str | None,
    result_snapshot_id: str,
    planned: list[Version],
    history_for: Callable[[str], list[Version]],
    stored_passages_for: Callable[[str], list[PassageVersion]],
    *,
    max_passages_per_document: int = 500,
    max_passage_length: int = 100000,
    max_candidate_pairs: int = 20000,
    max_timeline_breakpoints: int = 1000,
) -> ChangeSet:
    new_passage_ids: set[str] = set()
    edges: list[AlignmentEdge] = []
    timeline_alignments: list[TimelineAlignment] = []
    spans: list[ChangeSpan] = []
    applicability: list[ApplicabilityChange] = []
    passage_cache: dict[str, list[PassageVersion]] = {}

    def materialize(version: Version) -> list[PassageVersion]:
        if version.document_version_id in passage_cache:
            return passage_cache[version.document_version_id]
        existing = stored_passages_for(version.document_version_id)
        values = existing or materialize_passages(version)
        if len(values) > max_passages_per_document:
            raise DomainError("PASSAGE_LIMIT", "Document passage limit exceeded", 413)
        if any(len(item.text) > max_passage_length for item in values):
            raise DomainError("PASSAGE_LENGTH_LIMIT", "Passage length limit exceeded", 413)
        if not existing:
            new_passage_ids.update(item.passage_version_id for item in values)
        passage_cache[version.document_version_id] = values
        return values

    for new_version in sorted(planned, key=lambda item: item.document_id):
        history = history_for(new_version.document_id)
        for historical in history:
            materialize(historical)
        latest = history[-1] if history else None
        if latest and latest.is_deletion:
            latest = next((item for item in reversed(history) if not item.is_deletion), latest)
        old_passages = materialize(latest) if latest and not latest.is_deletion else []
        new_passages = materialize(new_version) if not new_version.is_deletion else []
        doc_edges = align_passages(
            old_passages,
            new_passages,
            delivery_id,
            max_candidate_pairs=max_candidate_pairs,
            edge_start_ordinal=len(edges) + 1,
        )
        new_passages = assign_lineage(old_passages, new_passages, doc_edges)
        passage_cache[new_version.document_version_id] = new_passages
        edges.extend(doc_edges)
        if not history and new_version.is_deletion:
            raise DomainError("INVALID_TOMBSTONE", "Cannot delete an unknown document")
        if not history:
            spans.append(
                _document_span(None, new_version, delivery_id, len(spans) + 1, "DOCUMENT_ADDED")
            )
        elif new_version.is_deletion:
            spans.append(
                _document_span(latest, new_version, delivery_id, len(spans) + 1, "DOCUMENT_DELETED")
            )
        else:
            spans.extend(
                spans_from_edges(
                    doc_edges,
                    old_passages,
                    new_passages,
                    latest,
                    new_version,
                    delivery_id,
                    span_start_ordinal=len(spans) + 1,
                )
            )
            if latest and (
                latest.source_type != new_version.source_type
                or latest.authority != new_version.authority
            ):
                spans.append(
                    _document_span(
                        latest,
                        new_version,
                        delivery_id,
                        len(spans) + 1,
                        "AUTHORITY_CHANGED",
                    )
                )
            spans.extend(
                uncertain_expansions(
                    doc_edges,
                    old_passages,
                    new_passages,
                    latest,
                    new_version,
                    delivery_id,
                    len(spans) + 1,
                )
            )

        document_applicability = timeline_changes(
            history,
            [*history, new_version],
            delivery_id,
            parent_snapshot_id,
            result_snapshot_id,
            max_timeline_breakpoints,
            len(applicability) + 1,
        )
        version_by_id = {item.document_version_id: item for item in [*history, new_version]}
        latest_pair = (
            latest.document_version_id if latest and not latest.is_deletion else None,
            new_version.document_version_id if not new_version.is_deletion else None,
        )
        for change in document_applicability:
            pair = (change.old_effective_version_id, change.new_effective_version_id)
            if pair == latest_pair:
                related = [
                    index
                    for index, span in enumerate(spans)
                    if span.document_id == new_version.document_id
                    and span.origin in ("LATEST_OBSERVED", "AUTHORITY")
                    and span.old_document_version_id == pair[0]
                    and span.new_document_version_id == (pair[1] or new_version.document_version_id)
                ]
                if related:
                    reusable = any(spans[index].origin == "LATEST_OBSERVED" for index in related)
                    change = change.model_copy(update={"text_diff_reused": reusable})
                    for index in related:
                        spans[index] = spans[index].model_copy(
                            update={
                                "applicability_change_id": change.applicability_change_id,
                                "text_diff_reused": reusable
                                and spans[index].origin == "LATEST_OBSERVED",
                                "effective_from": change.interval_from,
                                "effective_to": change.interval_to,
                            }
                        )
            elif pair[0] and pair[1]:
                timeline_old, timeline_new = version_by_id[pair[0]], version_by_id[pair[1]]
                timeline_old_passages = materialize(timeline_old)
                timeline_new_passages = materialize(timeline_new)
                timeline_edges = align_passages(
                    timeline_old_passages,
                    timeline_new_passages,
                    delivery_id,
                    max_candidate_pairs=max_candidate_pairs,
                    edge_start_ordinal=1,
                )
                comparisons = timeline_alignments_from_edges(
                    timeline_edges,
                    change.applicability_change_id,
                    pair[0],
                    pair[1],
                    len(timeline_alignments) + 1,
                )
                timeline_alignments.extend(comparisons)
                timeline_spans = spans_from_edges(
                    comparisons,
                    timeline_old_passages,
                    timeline_new_passages,
                    timeline_old,
                    timeline_new,
                    delivery_id,
                    "TIMELINE",
                    change.applicability_change_id,
                    change.interval_from,
                    change.interval_to,
                    len(spans) + 1,
                )
                spans.extend(timeline_spans)
            applicability.append(change)
    final_passages = {
        passage.passage_version_id: passage
        for values in passage_cache.values()
        for passage in values
        if passage.passage_version_id in new_passage_ids
    }
    return ChangeSet(
        passages=tuple(final_passages[key] for key in sorted(final_passages)),
        edges=tuple(edges),
        timeline_alignments=tuple(timeline_alignments),
        spans=tuple(spans),
        applicability_changes=tuple(applicability),
    )
