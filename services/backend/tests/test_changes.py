import random
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

import pytest

from aftermath.application.changes import build_change_set
from aftermath.core.changes import (
    align_passages,
    assign_lineage,
    change_features,
    containing_sentence,
    locate_normalized,
    locate_normalized_all,
    materialize_passages,
    norm_v1_text,
    normalized_view,
    segment_text,
    spans_from_edges,
    timeline_changes,
)
from aftermath.core.corpus import ResolveRequest, Snapshot, Version, resolve_effective
from aftermath.core.errors import DomainError
from aftermath.core.text import bytes_hash

WORKSPACE = UUID("00000000-0000-0000-0000-000000000024")


def version(
    revision: str,
    sequence: int,
    text: str,
    effective: str,
    *,
    authority: dict[str, str | int | bool] | None = None,
    deleted: bool = False,
) -> Version:
    at = datetime.fromisoformat(effective.replace("Z", "T00:00:00+00:00"))
    digest = bytes_hash(text.encode())
    return Version(
        workspace_id=WORKSPACE,
        corpus_id="research",
        document_id="pricing",
        document_version_id=f"dv:pricing@{revision}",
        source_revision_id=revision,
        source_seq=sequence,
        text=text,
        content_hash=digest,
        source_bytes_hash=digest,
        object_key=digest,
        source_timestamp=datetime(2026, sequence, 1, tzinfo=UTC),
        declared_effective_from=at,
        effective_from=at,
        effective_from_source="DECLARED_METADATA",
        source_type="product_doc",
        authority=authority or {"tier": 1},
        is_deletion=deleted,
        created_at=datetime(2026, sequence, 1, tzinfo=UTC),
        known_at_seq=sequence,
        immutable_hash=digest,
    )


def test_seg_v1_paths_offsets_chunks_and_determinism():
    text = "# Top\nIntro 😀 e\u0301\ncontinued\n\n## Detail\n" + "Long. " * 250
    first = segment_text(text)
    second = segment_text(text)
    assert first == second
    assert first[0].section_path == ("Top",)
    assert first[0].text == "Intro 😀 e\u0301\ncontinued"
    assert all(text[item.start : item.end] == item.text for item in first)
    assert all(left.end <= right.start for left, right in zip(first, first[1:], strict=False))
    assert all(len(item.text) <= 1200 for item in first[1:])
    huge = "A" * 1201 + "."
    assert segment_text(huge)[0].text == huge


def test_norm_v1_compatibility_mapping_preserves_source_provenance():
    value = "  OﬃCE\t １２  "
    assert normalized_view(value).text == "office 12"
    location = locate_normalized(value, "OFFICE 12")
    assert location is not None
    assert value[location[0] : location[1]] == "OﬃCE\t １２"


def test_norm_v1_matches_whole_string_and_recovers_composed_and_expanded_spans():
    def oracle(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    expected = {
        "Straße": "strasse",
        "ﬁ": "fi",
        "ＦＯＯ １２": "foo 12",
        "a\u0315\u0300": "à\u0315",
        " \tA\n  B\u2003": "a b",
        "😀 𐐀": "😀 𐐨",
    }
    for source, normalized in expected.items():
        assert oracle(source) == normalized
        assert normalized_view(source).text == normalized
    for source, equivalent in [("Ａ\u030a", "Å"), ("e\u0301", "é")]:
        view = normalized_view(source)
        assert view.text == oracle(source) == oracle(equivalent)
        assert view.canonical_span(0, len(view.text)) == (0, len(source))
        assert locate_normalized(source, equivalent) == (0, len(source))

    expanded = normalized_view("ß")
    assert expanded.text == "ss"
    assert expanded.canonical_span(0, 2) == (0, 1)
    with pytest.raises(DomainError, match="splits a unit"):
        expanded.canonical_span(0, 1)
    assert locate_normalized("ß", "s") is None

    compatibility = "①\u2003ﬃ"
    view = normalized_view(compatibility)
    assert view.text == "1 ffi"
    assert locate_normalized(compatibility, "1 ffi") == (0, len(compatibility))

    spaced = "A\t \nB"
    view = normalized_view(spaced)
    assert view.text == "a b"
    assert view.canonical_span(1, 2) == (1, 4)

    canonical = "prefix Ａ\u030a  ß\t① suffix"
    recovered = locate_normalized(canonical, "Å ss 1")
    assert recovered is not None
    assert canonical[recovered[0] : recovered[1]] == "Ａ\u030a  ß\t①"
    assert oracle(canonical[recovered[0] : recovered[1]]) == "å ss 1"
    assert locate_normalized("xＡ\u030ay", "Å") == (1, 3)


def test_norm_v1_adversarial_equivalence_ambiguity_and_fuzz():
    def oracle(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    cases = (
        "Ａ\u030a",
        "e\u0301",
        "ß",
        "①\u2003ﬃ",
        "ﾊﾟ",
        "가",
        "가",
        "👩‍🔬",
        "ﬄ",
        "a\u0315\u0300",
        "\u00a0 x \t y ",
    )
    for source in cases:
        view = normalized_view(source)
        assert view.text == oracle(source)
        if view.text:
            start, end = view.canonical_span(0, len(view.text))
            assert norm_v1_text(source[start:end]) == view.text
    assert locate_normalized_all("é / e\u0301", "é") == ((0, 1), (4, 6))
    with pytest.raises(DomainError) as ambiguous:
        locate_normalized("é / e\u0301", "é")
    assert ambiguous.value.code == "AMBIGUOUS_NORMALIZED_MATCH"
    generator = random.Random(24)
    alphabet = "ＡÅeé\u0301ß①ﬃﾊﾟ가가 \t\n"
    for _ in range(250):
        source = "".join(generator.choice(alphabet) for _ in range(generator.randrange(1, 30)))
        assert normalized_view(source).text == oracle(source)


def test_diff_v1_relations_spans_and_features():
    old_version = version("r1", 1, "# Plan\nStarter costs 12 USD.\n\nKeep this.", "2026-01-01Z")
    new_version = version("r2", 2, "# Plan\nStarter costs 15 USD.\n\nKeep this.", "2026-02-01Z")
    old, new = materialize_passages(old_version), materialize_passages(new_version)
    old_lineage = [item.lineage_id for item in old]
    edges = align_passages(old, new, "prices")
    assert [item.lineage_id for item in old] == old_lineage
    new = assign_lineage(old, new, edges)
    assert [edge.relation for edge in edges] == ["IDENTICAL", "MODIFIED"]
    assert new[1].lineage_id == old[1].lineage_id
    spans = spans_from_edges(edges, old, new, old_version, new_version, "prices")
    changed = spans[0]
    assert changed.old_text == "12"
    assert changed.new_text == "15"
    assert old_version.text[changed.old_start : changed.old_end] == changed.old_text
    assert new_version.text[changed.new_start : changed.new_end] == changed.new_text
    assert changed.features.numeric_change
    features = change_features("not before January 2026, only 12", "after 2026-02-01, 15")
    assert features.date_change and features.negation_change and features.qualifier_change


def test_change_features_use_token_and_phrase_boundaries():
    assert not change_features("notice", "notice").negation_change
    assert not change_features("notice", "update").negation_change
    assert change_features("notice", "not allowed").negation_change

    for false_positive in ("small", "allowed"):
        features = change_features(false_positive, "ordinary")
        assert "all" not in features.qualifiers_old
        assert not features.qualifier_change

    all_users = change_features("users", "all users")
    assert all_users.qualifiers_new == ("all",)
    assert all_users.qualifier_change
    assert change_features("valid", "no longer valid").negation_change
    assert change_features("is allowed", "isn't allowed").negation_change
    assert change_features("is allowed", "isn’t allowed").negation_change

    phrases = change_features("limit", "at least 2, at most 5, up to 8")
    assert phrases.qualifiers_new == ("at least", "at most", "up to")


def test_feature_marker_regression_matrix_is_explicit():
    for value in ("notice", "notation"):
        features = change_features(value, "ordinary")
        assert not features.negation_change
    for value in ("small", "allowed", "onlyish"):
        features = change_features(value, "ordinary")
        assert features.qualifiers_old == ()
        assert not features.qualifier_change

    for phrase in (
        "not allowed",
        "no evidence",
        "never valid",
        "cannot proceed",
        "no longer valid",
        "isn't allowed",
        "wasn't valid",
        "can't proceed",
        "shouldn't continue",
        "isn’t allowed",
        "wasn’t valid",
        "can’t proceed",
        "shouldn’t continue",
    ):
        assert change_features("ordinary", phrase).negation_change, phrase

    expected_qualifiers = {
        "all users": ("all",),
        "only members": ("only",),
        "at least 10": ("at least",),
        "at most 20": ("at most",),
        "up to 5": ("up to",),
    }
    for phrase, expected in expected_qualifiers.items():
        features = change_features("ordinary", phrase)
        assert features.qualifiers_new == expected
        assert features.qualifier_change


def test_feature_sentence_selection_is_deterministic_at_passage_boundaries():
    text = "First has 12.  Second has 15! Last has no terminator"
    first = containing_sentence(text, text.index("12"), text.index("12") + 2)
    middle = containing_sentence(text, text.index("15"), text.index("15") + 2)
    last = containing_sentence(text, text.index("no terminator"), len(text))
    assert first == (0, 13, "First has 12.")
    assert middle == (15, 29, "Second has 15!")
    assert last == (30, len(text), "Last has no terminator")
    assert containing_sentence("No boundary here", 3, 11) == (0, 16, "No boundary here")


def test_span_features_use_only_the_containing_sentence_and_keep_local_offsets():
    def changed(old_text: str, new_text: str, identifier: str):
        old_version = version(identifier + "1", 1, old_text, "2026-01-01Z")
        new_version = version(identifier + "2", 2, new_text, "2026-02-01Z")
        old_passages = materialize_passages(old_version)
        new_passages = materialize_passages(new_version)
        edges = align_passages(old_passages, new_passages, identifier)
        return spans_from_edges(
            edges,
            old_passages,
            new_passages,
            old_version,
            new_version,
            identifier,
        )

    same_sentence = changed(
        "😀 Service is not allowed; limit is 12 users.",
        "😀 Service is allowed; limit is 15 users.",
        "same-sentence",
    )
    numeric = next(span for span in same_sentence if span.old_text == "12")
    assert numeric.new_text == "15"
    assert numeric.features.numeric_change
    assert numeric.features.negation_change
    assert numeric.old_start == 35 and numeric.old_end == 37
    assert numeric.new_start == 31 and numeric.new_end == 33
    assert numeric.metadata["feature_evidence"]["local"]["negation_change"] is False
    assert numeric.metadata["feature_evidence"]["containing_sentence"]["negation_change"] is True
    assert numeric.metadata["feature_evidence"]["old"]["context_start"] == 0
    assert numeric.metadata["feature_evidence"]["old"]["context_end"] == len(
        "😀 Service is not allowed; limit is 12 users."
    )

    other_sentence = changed(
        "Service is not allowed. Limit is 12 users.",
        "Service is allowed. Limit is 15 users.",
        "other-sentence",
    )
    numeric = next(span for span in other_sentence if span.old_text == "12")
    assert numeric.features.numeric_change
    assert not numeric.features.negation_change
    assert numeric.old_text == "12" and numeric.new_text == "15"
    assert numeric.metadata["feature_evidence"]["old"]["context_text"] == "Limit is 12 users."

    qualifier_guard = changed(
        "A small cohort has 12 seats.",
        "An allowed cohort has 15 seats.",
        "qualifier-guard",
    )
    numeric = next(span for span in qualifier_guard if span.old_text == "12")
    assert not numeric.features.qualifier_change
    assert "all" not in numeric.features.qualifiers_old
    assert "all" not in numeric.features.qualifiers_new


@pytest.mark.parametrize("reverse", [False, True], ids=["insert", "delete"])
@pytest.mark.parametrize(
    ("base", "extra", "numeric", "date", "negation", "qualifier"),
    [
        ("The plan is not available today.", "revised", False, False, False, False),
        (
            "The plan has only 12 seats until 2026-12-01 today.",
            "revised",
            False,
            False,
            False,
            False,
        ),
        ("The plan is available today.", "not", False, False, True, False),
        ("The plan is available today.", "12", True, False, False, False),
        ("The plan is available today.", "2026-12-01", True, True, False, False),
        ("The plan is available today.", "only", False, False, False, True),
        ("The plan is available today.", "all", False, False, False, True),
        ("The plan is available today.", "at least", False, False, False, True),
        ("The plan is available today.", "no longer", False, False, True, False),
        ("The plan has only 12 seats today.", "only", False, False, False, False),
        ("The plan has only 12 seats today.", "12", True, False, False, False),
        ("😀 The plan is not available — café today.", "revised", False, False, False, False),
    ],
)
def test_insert_delete_feature_context_is_symmetric(
    reverse, base, extra, numeric, date, negation, qualifier
):
    # An insertion after 'The' is token-only. All unchanged sentence markers
    # must be compared on BOTH sides, independently of the empty local slice.
    offset = base.index("The") + 4
    edited = base[:offset] + extra + " " + base[offset:]
    old_text, new_text = (edited, base) if reverse else (base, edited)
    old = version("ctx1", 1, old_text, "2026-01-01Z")
    new = version("ctx2", 2, new_text, "2026-02-01Z")
    left, right = materialize_passages(old), materialize_passages(new)
    spans = spans_from_edges(align_passages(left, right, "ctx"), left, right, old, new, "ctx")
    assert len(spans) == 1
    span = spans[0]
    assert span.metadata["opcode"] == ("delete" if reverse else "insert")
    assert (span.old_text, span.new_text) == ((extra, None) if reverse else (None, extra))
    assert (span.features.numeric_change, span.features.date_change) == (numeric, date)
    assert (span.features.negation_change, span.features.qualifier_change) == (negation, qualifier)
    evidence = span.metadata["feature_evidence"]
    assert evidence["old"]["context_text"] == old_text
    assert evidence["new"]["context_text"] == new_text
    assert evidence["implementation"] == "features-v1-symmetric-context-2026-11-04"
    for side, source in (("old", old_text), ("new", new_text)):
        start, end = getattr(span, side + "_start"), getattr(span, side + "_end")
        value = getattr(span, side + "_text")
        if value is None:
            assert start is None and end is None
            assert evidence[side]["opcode_boundary"] == offset
        else:
            assert (start, end) == (offset, offset + len(extra))
            assert source[start:end] == extra


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("base", "edited", "context"),
    [
        (
            "The plan is not available today.",
            "Revised The plan is not available today.",
            "The plan is not available today.",
        ),
        (
            "The plan is not available today",
            "The plan is not available today again",
            "The plan is not available today",
        ),
        (
            "Prior is not valid. The plan is available today.",
            "Prior is not valid. Revised The plan is available today.",
            "The plan is available today.",
        ),
        (
            "The plan is not available today . Next has 15 users.",
            "The plan is not available today again . Next has 15 users.",
            "The plan is not available today .",
        ),
        (
            'First is not valid. "The plan is available today."',
            'First is not valid. "The revised plan is available today."',
            '"The plan is available today."',
        ),
        (
            "😀 The plan is not available。 Next has 15 users.",
            "😀 The revised plan is not available。 Next has 15 users.",
            "😀 The plan is not available。 Next has 15 users.",
        ),
    ],
)
def test_insert_delete_sentence_boundaries_preserve_markers(reverse, base, edited, context):
    old_text, new_text = (edited, base) if reverse else (base, edited)
    old = version("b1", 1, old_text, "2026-01-01Z")
    new = version("b2", 2, new_text, "2026-02-01Z")
    left, right = materialize_passages(old), materialize_passages(new)
    spans = spans_from_edges(align_passages(left, right, "b"), left, right, old, new, "b")
    assert len(spans) == 1
    span = spans[0]
    assert not span.features.numeric_change
    assert not span.features.date_change
    assert not span.features.negation_change
    assert not span.features.qualifier_change
    unchanged = "new" if reverse else "old"
    assert span.metadata["feature_evidence"][unchanged]["context_text"] == context


@pytest.mark.parametrize("reverse", [False, True])
def test_insert_delete_excludes_changes_in_another_sentence(reverse):
    baseline = "Service is not available. The plan has 12 seats today."
    edited = "Service is available. The revised plan has 12 seats today."
    old_text, new_text = (edited, baseline) if reverse else (baseline, edited)
    old = version("apart1", 1, old_text, "2026-01-01Z")
    new = version("apart2", 2, new_text, "2026-02-01Z")
    left, right = materialize_passages(old), materialize_passages(new)
    spans = spans_from_edges(align_passages(left, right, "apart"), left, right, old, new, "apart")
    insertion = next(span for span in spans if "revised" in (span.old_text, span.new_text))
    assert not insertion.features.negation_change
    assert not insertion.features.numeric_change
    assert insertion.features.numbers_old == insertion.features.numbers_new == ("12",)
    assert insertion.metadata["feature_evidence"]["old"]["context_text"].startswith("The ")
    negation = next(span for span in spans if "not" in (span.old_text, span.new_text))
    assert negation.features.negation_change


def test_feature_empty_boundaries_and_spec_sentence_rules():
    source = "First not valid.  Second has 12."
    assert containing_sentence(source, 0, 0) == (0, 16, "First not valid.")
    # The first sentence ends at 16; whitespace separates it from Second at 18.
    for boundary in (16, 17, 18):
        assert containing_sentence(source, boundary, boundary, affinity="left")[2] == (
            "First not valid."
        )
        assert containing_sentence(source, boundary, boundary)[2] == "Second has 12."
    assert containing_sentence(source, len(source), len(source))[2] == "Second has 12."
    assert containing_sentence("Unicode。 Lower case", 9, 9)[2] == "Unicode。 Lower case"
    assert containing_sentence("First. lowercase follows", 8, 9)[2] == ("First. lowercase follows")


def test_whole_passage_feature_context_keeps_true_absent_sides():
    original = version("whole1", 1, "Only 12 users are not allowed.", "2026-01-01Z")
    removed = version("whole2", 2, "", "2026-02-01Z", deleted=True)
    passages = materialize_passages(original)
    added = spans_from_edges(
        align_passages([], passages, "added"), [], passages, None, original, "added"
    )[0]
    deleted = spans_from_edges(
        align_passages(passages, [], "deleted"), passages, [], original, removed, "deleted"
    )[0]
    assert added.metadata["feature_evidence"]["old"]["context_text"] is None
    assert deleted.metadata["feature_evidence"]["new"]["context_text"] is None
    assert added.features.numeric_change and deleted.features.numeric_change
    assert added.features.negation_change and deleted.features.negation_change


def test_diff_v1_move_reformat_add_delete_merge_split_and_expansion():
    moved_old = version("m1", 1, "First.\n\nSecond.", "2026-01-01Z")
    moved_new = version("m2", 2, "Second.\n\nFirst.", "2026-02-01Z")
    edges = align_passages(
        materialize_passages(moved_old), materialize_passages(moved_new), "moved"
    )
    assert [item.relation for item in edges] == ["MOVED", "MOVED"]

    formatted_old = version("f1", 1, "Office   HOURS", "2026-01-01Z")
    formatted_new = version("f2", 2, "office hours", "2026-02-01Z")
    assert (
        align_passages(
            materialize_passages(formatted_old), materialize_passages(formatted_new), "formatted"
        )[0].relation
        == "REFORMATTED"
    )

    assert align_passages(materialize_passages(formatted_old), [], "deleted")[0].relation == (
        "DELETED"
    )
    assert align_passages([], materialize_passages(formatted_new), "added")[0].relation == "ADDED"

    vocabulary = "a b c d e f g h i j k l m n o p"
    extras_a = " ".join(f"left{index}" for index in range(20))
    extras_b = " ".join(f"right{index}" for index in range(20))
    merged_old = version(
        "g1",
        1,
        f"a b c d e f g h {extras_a}\n\ni j k l m n o p {extras_b}",
        "2026-01-01Z",
    )
    merged_new = version("g2", 2, vocabulary, "2026-02-01Z")
    assert (
        align_passages(
            materialize_passages(merged_old), materialize_passages(merged_new), "merged"
        )[0].relation
        == "MERGED"
    )
    split_edges = align_passages(
        materialize_passages(merged_new), materialize_passages(merged_old), "split"
    )
    assert split_edges[0].relation == "SPLIT"

    uncertain_old = version("u1", 1, "alpha beta", "2026-01-01Z")
    uncertain_new = version("u2", 2, "alpha gamma", "2026-02-01Z")
    changes = build_change_set(
        "uncertain",
        "snap:000001",
        "snap:000002",
        [uncertain_new],
        lambda document: [uncertain_old],
        lambda version_id: [],
    )
    assert any(item.kind == "EXPANDED_UNCERTAIN" for item in changes.spans)


def test_as24_effective_only_change_emits_timeline_span_without_latest_text_span():
    r1 = version("r1", 1, "Starter costs 12 USD.", "2026-01-01Z")
    r2 = version("r2", 2, "Starter costs 15 USD.", "2026-12-01Z")
    r3 = version("r3", 3, "Starter costs 15 USD.", "2026-04-01Z")
    r1_passages = materialize_passages(r1)
    r2_passages = assign_lineage(
        r1_passages,
        materialize_passages(r2),
        align_passages(r1_passages, materialize_passages(r2), "prices-r2"),
    )
    stored = {
        r1.document_version_id: r1_passages,
        r2.document_version_id: r2_passages,
    }
    changes = build_change_set(
        "as24",
        "snap:000002",
        "snap:000003",
        [r3],
        lambda document: [r1, r2],
        lambda version_id: stored.get(version_id, []),
    )
    latest_edges = [
        edge for edge in changes.edges if "r2" in "".join(edge.from_passage_version_ids)
    ]
    assert len(changes.edges) == 1
    assert latest_edges[0].relation == "IDENTICAL"
    r3_passage = next(item for item in changes.passages if "@r3#" in item.passage_version_id)
    assert r3_passage.lineage_id == "lin:pricing:r1:p0001"
    assert not [span for span in changes.spans if span.origin == "LATEST_OBSERVED"]
    assert len(changes.applicability_changes) == 1
    applicability = changes.applicability_changes[0]
    assert applicability.interval_from == datetime(2026, 4, 1, tzinfo=UTC)
    assert applicability.interval_to == datetime(2026, 12, 1, tzinfo=UTC)
    timeline_span = next(span for span in changes.spans if span.origin == "TIMELINE")
    assert (timeline_span.old_text, timeline_span.new_text) == ("12", "15")
    assert timeline_span.features.numeric_change
    assert timeline_span.applicability_change_id == applicability.applicability_change_id
    assert timeline_span.lineage_edge_id is None
    assert timeline_span.timeline_alignment_edge_id is not None
    assert (timeline_span.old_start, timeline_span.old_end) == (14, 16)
    assert (timeline_span.new_start, timeline_span.new_end) == (14, 16)
    assert len(changes.timeline_alignments) == 1
    temporal = changes.timeline_alignments[0]
    assert "r1" in "".join(temporal.from_passage_version_ids)
    assert "r3" in "".join(temporal.to_passage_version_ids)
    assert temporal.applicability_change_id == applicability.applicability_change_id


def test_timeline_authority_and_supersession_rules():
    r1 = version("r1", 1, "Allowed", "2026-01-01Z", authority={"tier": 2})
    scheduled = version("r2", 2, "Blocked", "2026-12-01Z", authority={"tier": 2})
    earlier = version("r3", 3, "Allowed", "2026-04-01Z", authority={"tier": 2})
    cancel = version("r4", 4, "Allowed", "2026-12-01Z", authority={"tier": 2})
    snapshot = Snapshot(
        workspace_id=WORKSPACE,
        corpus_id="research",
        snapshot_id="snap:000004",
        snapshot_seq=4,
        parent_snapshot_id="snap:000003",
        update_event_id="upd:four",
        manifest_hash=bytes_hash(b"manifest"),
        document_count=1,
        as_of=datetime(2027, 1, 1, tzinfo=UTC),
    )
    request = ResolveRequest(
        snapshot_id=snapshot.snapshot_id,
        evaluation_time=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert (
        resolve_effective([r1, scheduled, earlier], snapshot, request).selected_version_id
        == "dv:pricing@r2"
    )
    assert (
        resolve_effective([r1, scheduled, earlier, cancel], snapshot, request).selected_version_id
        == "dv:pricing@r4"
    )
    authority = version("r5", 5, "Allowed", "2026-01-01Z", authority={"tier": 1})
    assert (
        timeline_changes([r1], [r1, authority], "authority", "snap:000001", "snap:000005")[0].reason
        == "AUTHORITY"
    )
