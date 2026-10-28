# ruff: noqa: E501
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from aftermath.adapters.persistence.corpus import PostgresCorpusRepository, PostgresCorpusStore
from aftermath.adapters.storage.local import LocalObjectStore
from aftermath.api.main import create_app
from aftermath.api.offsets import code_point_offset, utf16_offset
from aftermath.application.corpus import CorpusService
from aftermath.config import Settings
from aftermath.core.changes import AlignmentError, norm_v1_text
from aftermath.core.corpus import Delivery, ResolveRequest
from aftermath.core.errors import DomainError, InvalidEncodingError
from aftermath.core.text import bytes_hash, canonical_json, canonical_text, content_hash, exact_span


def revision(
    rev="r1", seq=1, content=b"Original evidence", effective=None, document="guide", **extra
):
    return dict(
        document_id=document,
        source_revision_id=rev,
        source_seq=seq,
        source_timestamp="2026-01-01T00:00:00Z",
        declared_effective_from=effective,
        source_type="product_doc",
        source_base64=base64.b64encode(content).decode(),
        **extra,
    )


def delivery(identifier="one", head=None, revisions=None):
    return Delivery.model_validate(
        dict(
            delivery_id=identifier,
            expected_head=head,
            as_of="2026-11-01T00:00:00Z",
            documents=revisions or [revision()],
        )
    )


@pytest.fixture
def setup_corpus(tmp_path):
    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    engine = create_engine(url)
    service = CorpusService(PostgresCorpusStore(engine), LocalObjectStore(tmp_path))
    principal = "test-" + uuid4().hex
    workspace = service.create_workspace(principal, "Integration corpus").id
    service.create_corpus(principal, workspace, "research", "Research")
    yield service, principal, workspace, engine
    engine.dispose()


def test_canonical_spans_utf16_roundtrip():
    value = canonical_text("\ufeffe\u0301\r\n😀\rZ".encode())
    assert value == "é\n😀\nZ"
    assert exact_span(value, 2, 3, "😀") == "😀"
    for offset in range(len(value) + 1):
        assert code_point_offset(value, utf16_offset(value, offset)) == offset
    with pytest.raises(ValueError):
        code_point_offset(value, 3)
    with pytest.raises(ValueError):
        exact_span(value, 2, 4, "😀")
    with pytest.raises(InvalidEncodingError):
        canonical_text(b"\xff")
    assert bytes_hash(b"a") == bytes_hash(b"a")
    assert canonical_text(b"\xef\xbb\xbf\xef\xbb\xbfA") == "\ufeffA"


def test_objects_idempotence_corruption_traversal(tmp_path):
    store = LocalObjectStore(tmp_path)
    workspace = uuid4()
    key = bytes_hash(b"original")
    store.put(workspace, key, b"original")
    store.put(workspace, key, b"original")
    assert store.get(workspace, key) == b"original"
    with pytest.raises(DomainError):
        store.put(workspace, "../../escape", b"original")
    (tmp_path / str(workspace) / key[7:]).write_bytes(b"corrupt")
    with pytest.raises(DomainError, match="hash verification"):
        store.get(workspace, key)
    other = uuid4()
    (tmp_path / str(other)).symlink_to(tmp_path / str(workspace), target_is_directory=True)
    with pytest.raises(DomainError):
        store.get(other, key)


@pytest.mark.integration
def test_atomic_delivery_duplicates_unchanged_and_conflicts(setup_corpus):
    service, p, w, engine = setup_corpus
    first = delivery(revisions=[revision(), revision(document="second")])
    result = service.ingest(p, w, "research", first)
    assert result.status == "APPLIED"
    assert result.snapshot_id == "snap:000001"
    assert service.ingest(p, w, "research", first).duplicate
    assert service.corpus(p, w, "research").version_count == 2
    with pytest.raises(DomainError) as failure:
        service.ingest(
            p, w, "research", delivery("one", revisions=[revision(content=b"different")])
        )
    assert failure.value.code == "IDEMPOTENCY_CONFLICT"
    second = service.ingest(
        p, w, "research", delivery("two", result.snapshot_id, [revision("r2", 2)])
    )
    assert second.snapshot_id == "snap:000002"
    assert len(service.versions(p, w, "research", "guide")) == 2
    no_op = service.ingest(
        p, w, "research", delivery("three", second.snapshot_id, [revision("r2", 2)])
    )
    assert no_op.status == "NO_OP_UNCHANGED"
    with pytest.raises(DomainError) as failure:
        service.ingest(
            p,
            w,
            "research",
            delivery("four", second.snapshot_id, [revision("r2", 2, authority={"tier": 1})]),
        )
    assert failure.value.code == "REVISION_CONFLICT"
    with engine.connect() as conn:
        members = conn.execute(
            text("""SELECT m.document_id,m.document_version_id FROM snapshot_documents m
            JOIN document_versions v USING(workspace_id,corpus_id,document_id,document_version_id)
            WHERE m.workspace_id=:w AND m.snapshot_id='snap:000002' AND NOT v.is_deletion
            ORDER BY m.document_id"""),
            {"w": w},
        ).all()
    snapshot = service.snapshots(p, w, "research")[0]
    assert snapshot.manifest_hash == bytes_hash(canonical_json([list(row) for row in members]))
    assert snapshot.document_count == 2


@pytest.mark.integration
def test_invalid_member_rolls_back_and_parks_whole_batch(setup_corpus):
    service, p, w, engine = setup_corpus
    with pytest.raises(DomainError) as failure:
        service.ingest(
            p,
            w,
            "research",
            delivery(revisions=[revision(), revision(content=b"\xff", document="bad")]),
        )
    assert failure.value.code == "INVALID_UTF8"
    assert service.corpus(p, w, "research").version_count == 0
    assert service.snapshots(p, w, "research") == []
    service.ingest(p, w, "research", delivery("valid", revisions=[revision("r3", 3)]))
    parked = service.ingest(
        p,
        w,
        "research",
        delivery("parked", "snap:000001", [revision("r2", 2), revision(document="new-doc")]),
    )
    assert parked.status == "PARKED_OUT_OF_ORDER"
    assert service.corpus(p, w, "research").version_count == 1
    assert len(service.documents(p, w, "research")) == 1
    assert (
        service.ingest(
            p,
            w,
            "research",
            delivery("parked", "snap:000001", [revision("r2", 2), revision(document="new-doc")]),
        ).status
        == "PARKED_OUT_OF_ORDER"
    )
    for flag, code in [
        ("mixed_effective", "MIXED_EFFECTIVE"),
        ("withdrawal", "CANCELLATION_UNSUPPORTED"),
    ]:
        with pytest.raises(DomainError) as failure:
            service.ingest(
                p, w, "research", delivery(flag, "snap:000001", [revision("r4", 4, **{flag: True})])
            )
        assert failure.value.code == code


@pytest.mark.integration
def test_stale_head_and_concurrent_writers(setup_corpus):
    service, p, w, engine = setup_corpus

    def submit(name):
        try:
            return service.ingest(p, w, "research", delivery(name)).status
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["a", "b"]))
    assert sorted(results) == ["APPLIED", "STALE_HEAD"]
    assert service.corpus(p, w, "research").version_count == 1
    assert len(service.snapshots(p, w, "research")) == 1


@pytest.mark.integration
def test_apply_exception_rolls_back_every_row(setup_corpus, monkeypatch):
    service, p, w, engine = setup_corpus
    original = PostgresCorpusRepository.apply

    def broken(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected after writes before commit")

    monkeypatch.setattr(PostgresCorpusRepository, "apply", broken)
    with pytest.raises(DomainError):
        service.ingest(p, w, "research", delivery())
    with engine.connect() as conn:
        for table in [
            "document_versions",
            "snapshots",
            "snapshot_documents",
            "documents",
            "source_objects",
        ]:
            assert (
                conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE workspace_id=:w"), {"w": w}
                ).scalar()
                == 0
            )
        assert (
            conn.execute(
                text("SELECT status FROM update_event_status_log WHERE workspace_id=:w"), {"w": w}
            ).scalar()
            == "FAILED_APPLY"
        )
    monkeypatch.setattr(PostgresCorpusRepository, "apply", original)
    assert service.ingest(p, w, "research", delivery()).status == "APPLIED"


@pytest.mark.integration
@pytest.mark.parametrize("failure_kind", ["alignment", "timeline"])
def test_step2b_planning_failure_is_operational_and_atomic(setup_corpus, monkeypatch, failure_kind):
    service, principal, workspace, engine = setup_corpus

    def broken(*args, **kwargs):
        if failure_kind == "alignment":
            raise AlignmentError("injected alignment inconsistency")
        raise DomainError("TIMELINE_LIMIT", "injected timeline failure", 413)

    monkeypatch.setattr("aftermath.application.corpus.build_change_set", broken)
    with pytest.raises(DomainError):
        service.ingest(principal, workspace, "research", delivery(failure_kind))
    with engine.connect() as connection:
        for table in [
            "document_versions",
            "passage_versions",
            "passage_lineage_edges",
            "timeline_alignment_edges",
            "change_spans",
            "applicability_changes",
            "snapshots",
            "snapshot_changes",
        ]:
            assert (
                connection.execute(
                    text(f"SELECT count(*) FROM {table} WHERE workspace_id=:w"),
                    {"w": workspace},
                ).scalar()
                == 0
            )
        assert (
            connection.execute(
                text("SELECT status FROM update_event_status_log WHERE workspace_id=:w"),
                {"w": workspace},
            ).scalar()
            == "FAILED_APPLY"
        )


@pytest.mark.integration
def test_step2b_text_as24_authority_deletion_and_read_models(setup_corpus):
    service, principal, workspace, engine = setup_corpus
    first = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "prices-r1",
            revisions=[revision("r1", 1, b"Starter costs 12 USD.", "2026-01-01T00:00:00Z")],
        ),
    )
    second = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "prices-r2",
            first.snapshot_id,
            [revision("r2", 2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z")],
        ),
    )
    text_comparison = service.comparison(principal, workspace, "research", "prices-r2", "guide")
    assert [(item.old_text, item.new_text) for item in text_comparison.spans] == [("12", "15")]
    assert [
        (item.old_start, item.old_end, item.new_start, item.new_end)
        for item in text_comparison.spans
    ] == [(14, 16, 14, 16)]
    assert text_comparison.spans[0].features.numeric_change
    third = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "prices-r3",
            second.snapshot_id,
            [revision("r3", 3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z")],
        ),
    )
    as24 = service.comparison(principal, workspace, "research", "prices-r3", "guide")
    assert len(as24.edges) == 1
    assert as24.edges[0].relation == "IDENTICAL"
    assert "r2" in "".join(as24.edges[0].from_passage_version_ids)
    assert "r3" in "".join(as24.edges[0].to_passage_version_ids)
    assert len(as24.timeline_alignments) == 1
    temporal = as24.timeline_alignments[0]
    assert "r1" in "".join(temporal.from_passage_version_ids)
    assert "r3" in "".join(temporal.to_passage_version_ids)
    timeline_spans = [item for item in as24.spans if item.origin == "TIMELINE"]
    assert [(item.old_text, item.new_text) for item in timeline_spans] == [("12", "15")]
    assert timeline_spans[0].lineage_edge_id is None
    assert timeline_spans[0].timeline_alignment_edge_id == temporal.timeline_alignment_edge_id
    assert as24.applicability_changes[0].interval_to.isoformat().startswith("2026-12-01")
    fourth = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "prices-r4",
            third.snapshot_id,
            [
                revision(
                    "r4",
                    4,
                    b"Starter costs 15 USD.",
                    "2026-04-01T00:00:00Z",
                    authority={"tier": 2},
                )
            ],
        ),
    )
    authority = service.comparison(principal, workspace, "research", "prices-r4", "guide")
    assert any(item.kind == "AUTHORITY_CHANGED" for item in authority.spans)
    assert any(item.reason == "AUTHORITY" for item in authority.applicability_changes)
    service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "prices-delete",
            fourth.snapshot_id,
            [
                revision(
                    "r5",
                    5,
                    b"",
                    "2027-01-01T00:00:00Z",
                    deleted=True,
                )
            ],
        ),
    )
    deletion = service.comparison(principal, workspace, "research", "prices-delete", "guide")
    assert any(item.kind == "DOCUMENT_DELETED" for item in deletion.spans)
    assert (
        service.update_events(principal, workspace, "research", 100, 0)[0].delivery_id
        == "prices-delete"
    )
    api = TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=SecretStr(engine.url.render_as_string(hide_password=False)),
                dev_identity=principal,
            )
        )
    )
    prefix = f"/api/v1/workspaces/{workspace}/corpora/research"
    assert api.get(prefix + "/updates").json()[0]["delivery_id"] == "prices-delete"
    response = api.get(prefix + "/updates/prices-r3/documents/guide/comparison")
    assert response.status_code == 200
    assert response.json()["applicability_changes"][0]["reason"] == "CONTENT"
    assert len(response.json()["edges"]) == 1
    assert len(response.json()["timeline_alignments"]) == 1
    assert response.json()["timeline_alignments"][0]["from_passage_version_ids"][0].endswith(
        "@r1#p0001"
    )
    assert response.json()["timeline_alignments"][0]["to_passage_version_ids"][0].endswith(
        "@r3#p0001"
    )
    assert api.get(f"/api/v1/workspaces/{uuid4()}/corpora/research/updates").status_code == 404
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM passage_versions WHERE workspace_id=:w"),
                {"w": workspace},
            ).scalar()
            == 4
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM snapshot_changes WHERE workspace_id=:w"),
                {"w": workspace},
            ).scalar()
            == 5
        )


@pytest.mark.integration
def test_temporal_knowledge_future_tie_authority_and_tombstone(setup_corpus):
    service, p, w, engine = setup_corpus
    service.ingest(p, w, "research", delivery())
    service.ingest(
        p,
        w,
        "research",
        delivery("two", "snap:000001", [revision("r2", 2, b"Future text", "2026-12-01T00:00:00Z")]),
    )

    def resolve(snapshot="snap:000002", scope="ROLLING_CURRENT", **params):
        return service.resolve(
            p, w, "research", "guide", ResolveRequest(snapshot_id=snapshot, scope=scope, **params)
        )

    assert resolve().selected_version_id == "dv:guide@r1"
    assert resolve(evaluation_time="2027-01-01T00:00:00Z").selected_version_id == "dv:guide@r2"
    assert (
        resolve("snap:000001", evaluation_time="2027-01-01T00:00:00Z").selected_version_id
        == "dv:guide@r1"
    )
    assert (
        resolve(scope="FIXED_TIME", fixed_time="2026-10-01T00:00:00Z").selected_version_id
        == "dv:guide@r1"
    )
    assert resolve(scope="FIXED_VERSION", version_id="dv:guide@r2").active
    with pytest.raises(DomainError):
        resolve("snap:000001", scope="FIXED_VERSION", version_id="dv:guide@r2")
    # AS-24 prerequisite: same content as future r2, but effective in November.
    service.ingest(
        p,
        w,
        "research",
        delivery(
            "three", "snap:000002", [revision("r3", 3, b"Future text", "2026-11-01T00:00:00Z")]
        ),
    )
    assert resolve("snap:000003").selected_version_id == "dv:guide@r3"
    assert (
        resolve("snap:000003", evaluation_time="2026-12-02T00:00:00Z").selected_version_id
        == "dv:guide@r2"
    )
    before = resolve("snap:000003")
    service.ingest(
        p,
        w,
        "research",
        delivery(
            "four",
            "snap:000003",
            [revision("r4", 4, b"Future text", "2026-11-01T00:00:00Z", authority={"tier": 1})],
        ),
    )
    after = resolve("snap:000004")
    assert after.selected_version_id == "dv:guide@r4"
    assert before.version.content_hash == after.version.content_hash
    assert before.fingerprint != after.fingerprint
    service.ingest(
        p,
        w,
        "research",
        delivery(
            "five", "snap:000004", [revision("r5", 5, b"", "2027-01-01T00:00:00Z", deleted=True)]
        ),
    )
    deleted = resolve("snap:000005", evaluation_time="2027-01-02T00:00:00Z")
    assert not deleted.active and deleted.version is None
    assert deleted.selected_version_id == "dv:guide@r5"
    assert resolve("snap:000004", evaluation_time="2027-01-02T00:00:00Z").active


@pytest.mark.integration
def test_immutability_tenant_corpus_isolation_and_sealed_snapshots(setup_corpus):
    service, p, w, engine = setup_corpus
    first = service.ingest(p, w, "research", delivery())
    second = service.ingest(
        p,
        w,
        "research",
        delivery(
            "future",
            first.snapshot_id,
            [revision("r2", 2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z")],
        ),
    )
    service.ingest(
        p,
        w,
        "research",
        delivery(
            "as24",
            second.snapshot_id,
            [revision("r3", 3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z")],
        ),
    )
    with pytest.raises(DomainError):
        service.corpus("another-user", w, "research")
    service.create_corpus(p, w, "other", "Other")
    with pytest.raises(DomainError):
        service.versions(p, w, "other", "guide")
    for sql in [
        "UPDATE document_versions SET text='overwrite' WHERE workspace_id=:w",
        "DELETE FROM snapshots WHERE workspace_id=:w",
        "UPDATE update_event_status_log SET status='FAILED_APPLY' WHERE workspace_id=:w",
        "UPDATE delivery_attempts SET outcome='fake' WHERE workspace_id=:w",
        "UPDATE passage_versions SET text='overwrite' WHERE workspace_id=:w",
        "DELETE FROM passage_lineage_edges WHERE workspace_id=:w",
        "UPDATE change_spans SET kind='ADDED' WHERE workspace_id=:w",
        "DELETE FROM applicability_changes WHERE workspace_id=:w",
        "DELETE FROM timeline_alignment_edges WHERE workspace_id=:w",
        "DELETE FROM timeline_alignment_edge_members WHERE workspace_id=:w",
    ]:
        with pytest.raises(SQLAlchemyError), engine.begin() as conn:
            conn.execute(text(sql), {"w": w})
    with pytest.raises(SQLAlchemyError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents(workspace_id,corpus_id,document_id) VALUES(:w,'absent','x')"
            ),
            {"w": w},
        )
    # An existing snapshot cannot gain knowledge later, even via a direct DB insert.
    with pytest.raises(SQLAlchemyError), engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO snapshot_documents
                VALUES(:w,'research','snap:000001','wrong','dv:guide@r1')"""
            ),
            {"w": w},
        )


@pytest.mark.integration
def test_applicability_references_are_fully_workspace_document_scoped(setup_corpus):
    service, principal, workspace, engine = setup_corpus
    service.ingest(
        principal,
        workspace,
        "research",
        delivery(revisions=[revision(), revision(document="other")]),
    )
    outside_principal = "outside-" + uuid4().hex
    outside_workspace = service.create_workspace(outside_principal, "Outside").id
    service.create_corpus(outside_principal, outside_workspace, "research", "Outside")
    service.ingest(
        outside_principal,
        outside_workspace,
        "research",
        delivery("outside", revisions=[revision(document="outside")]),
    )
    service.create_corpus(principal, workspace, "other-scope", "Other scope")
    service.ingest(
        principal,
        workspace,
        "other-scope",
        delivery("other-scope", revisions=[revision(document="cross")]),
    )

    insert = text("""
      INSERT INTO applicability_changes (
        workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,
        change_ordinal,parent_snapshot_id,result_snapshot_id,interval_from,interval_to,
        old_effective_version_id,new_effective_version_id,old_effective_fingerprint,
        new_effective_fingerprint,reason,text_diff_reused,timeline_version)
      SELECT workspace_id,corpus_id,update_event_id,:document,:identifier,99,
        parent_snapshot_id,result_snapshot_id,interval_from,interval_to,
        :old_version,:new_version,old_effective_fingerprint,
        new_effective_fingerprint,reason,text_diff_reused,timeline_version
      FROM applicability_changes
      WHERE workspace_id=:workspace AND corpus_id='research' AND document_id='guide'
      ORDER BY change_ordinal LIMIT 1
    """)
    invalid = [
        ("missing", "dv:guide@r1", "dv:guide@r1", "ac:missing-doc:0001"),
        ("guide", "dv:guide@missing", "dv:guide@r1", "ac:missing-old:0001"),
        ("guide", "dv:guide@r1", "dv:guide@missing", "ac:missing-new:0001"),
        ("guide", "dv:other@r1", "dv:guide@r1", "ac:crossdoc-old:0001"),
        ("guide", "dv:guide@r1", "dv:other@r1", "ac:crossdoc-new:0001"),
        ("guide", "dv:cross@r1", "dv:guide@r1", "ac:crosscorpus:0001"),
        ("guide", "dv:guide@r1", "dv:outside@r1", "ac:crossworkspace:0001"),
    ]
    for document_id, old_version_id, new_version_id, identifier in invalid:
        with pytest.raises(SQLAlchemyError), engine.begin() as connection:
            connection.execute(
                insert,
                {
                    "workspace": workspace,
                    "document": document_id,
                    "old_version": old_version_id,
                    "new_version": new_version_id,
                    "identifier": identifier,
                },
            )

    nullable = text("""
      INSERT INTO applicability_changes (
        workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,
        change_ordinal,parent_snapshot_id,result_snapshot_id,interval_from,interval_to,
        old_effective_version_id,new_effective_version_id,old_effective_fingerprint,
        new_effective_fingerprint,reason,text_diff_reused,timeline_version)
      SELECT workspace_id,corpus_id,update_event_id,document_id,:identifier,:ordinal,
        parent_snapshot_id,result_snapshot_id,interval_from,interval_to,
        :old_version,:new_version,old_effective_fingerprint,new_effective_fingerprint,
        :reason,text_diff_reused,timeline_version
      FROM applicability_changes
      WHERE workspace_id=:workspace AND corpus_id='research' AND document_id='guide'
      ORDER BY change_ordinal LIMIT 1
    """)
    with engine.begin() as connection:
        connection.execute(
            nullable,
            {
                "workspace": workspace,
                "identifier": "ac:null-addition:0100",
                "ordinal": 100,
                "old_version": None,
                "new_version": "dv:guide@r1",
                "reason": "ADDITION",
            },
        )
        connection.execute(
            nullable,
            {
                "workspace": workspace,
                "identifier": "ac:null-deletion:0101",
                "ordinal": 101,
                "old_version": "dv:guide@r1",
                "new_version": None,
                "reason": "DELETION",
            },
        )


@pytest.mark.integration
def test_timeline_span_references_include_event_and_all_tenant_scopes(setup_corpus):
    service, principal, workspace, engine = setup_corpus
    first = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "scope-r1",
            revisions=[
                revision(content=b"Starter costs 12 USD."),
                revision(content=b"Other text", document="other"),
            ],
        ),
    )
    second = service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "scope-r2",
            first.snapshot_id,
            [revision("r2", 2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z")],
        ),
    )
    service.ingest(
        principal,
        workspace,
        "research",
        delivery(
            "scope-r3",
            second.snapshot_id,
            [revision("r3", 3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z")],
        ),
    )
    service.create_corpus(principal, workspace, "scope-two", "Scope two")
    service.ingest(
        principal,
        workspace,
        "scope-two",
        delivery("scope-two-r1", revisions=[revision(document="guide")]),
    )
    outside_principal = "timeline-outside-" + uuid4().hex
    outside_workspace = service.create_workspace(outside_principal, "Timeline outside").id
    service.create_corpus(outside_principal, outside_workspace, "research", "Outside")
    service.ingest(outside_principal, outside_workspace, "research", delivery("outside-r1"))

    with engine.connect() as connection:
        alignment = connection.execute(
            text(
                "SELECT timeline_alignment_edge_id FROM timeline_alignment_edges "
                "WHERE workspace_id=:w AND corpus_id='research' AND update_event_id='upd:scope-r3'"
            ),
            {"w": workspace},
        ).scalar_one()

    insert = text("""
      INSERT INTO change_spans(
        workspace_id,corpus_id,update_event_id,document_id,change_span_id,span_ordinal,
        old_document_version_id,new_document_version_id,old_passage_version_id,
        new_passage_version_id,kind,lineage_edge_id,timeline_alignment_edge_id,
        old_start,old_end,new_start,new_end,old_text,new_text,features,
        alignment_confidence,effective_from,effective_to,applicability_change_id,
        text_diff_reused,feature_version,origin,metadata)
      VALUES(:w,:c,:event,:document,:span,999,NULL,NULL,NULL,NULL,'AUTHORITY_CHANGED',
        NULL,:alignment,NULL,NULL,NULL,NULL,NULL,NULL,'{}','HIGH',
        '2026-04-01T00:00:00Z',NULL,NULL,FALSE,'features-v1','TIMELINE','{}')
    """)
    invalid = [
        (workspace, "research", "upd:scope-r3", "guide", "ta:missing:9999", "arbitrary"),
        (workspace, "research", "upd:scope-r1", "guide", alignment, "wrong-event"),
        (workspace, "research", "upd:scope-r3", "other", alignment, "wrong-document"),
        (workspace, "scope-two", "upd:scope-two-r1", "guide", alignment, "wrong-corpus"),
        (outside_workspace, "research", "upd:outside-r1", "guide", alignment, "wrong-workspace"),
    ]
    for target_workspace, corpus, event, document, target_alignment, suffix in invalid:
        with pytest.raises(SQLAlchemyError), engine.begin() as connection:
            connection.execute(
                insert,
                {
                    "w": target_workspace,
                    "c": corpus,
                    "event": event,
                    "document": document,
                    "span": f"cs:scope-{suffix}:9999",
                    "alignment": target_alignment,
                },
            )

    with engine.connect() as connection:
        source = (
            connection.execute(
                text(
                    "SELECT * FROM timeline_alignment_edges WHERE workspace_id=:w "
                    "AND timeline_alignment_edge_id=:alignment"
                ),
                {"w": workspace, "alignment": alignment},
            )
            .mappings()
            .one()
        )
    copied = text("""
      INSERT INTO timeline_alignment_edges(
        workspace_id,corpus_id,document_id,update_event_id,timeline_alignment_edge_id,
        alignment_ordinal,applicability_change_id,old_document_version_id,
        new_document_version_id,relation,alignment_score,alignment_confidence,
        alignment_method,reason,recorded_by,legacy_lineage_edge_id)
      VALUES(:workspace_id,:corpus_id,:document_id,:update_event_id,:identifier,999,
        :applicability_change_id,:old_document_version_id,:new_document_version_id,
        :relation,:alignment_score,:alignment_confidence,:alignment_method,CAST(:reason AS jsonb),
        :recorded_by,:legacy)
    """)
    with pytest.raises(SQLAlchemyError), engine.begin() as connection:
        connection.execute(
            copied,
            {
                **source,
                "identifier": "ta:misclassified:9999",
                "reason": json.dumps(source["reason"]),
                "recorded_by": "timeline-v1",
                "legacy": "le:scope-r3:0001",
            },
        )
    with pytest.raises(SQLAlchemyError), engine.begin() as connection:
        connection.execute(
            copied,
            {
                **source,
                "identifier": "ta:orphan-legacy:9999",
                "reason": json.dumps(source["reason"]),
                "recorded_by": "migration-0004-reclassification",
                "legacy": "le:missing:9999",
            },
        )


@pytest.mark.integration
def test_api_validation_auth_limits_and_real_storage(setup_corpus, tmp_path):
    service, p, w, engine = setup_corpus
    settings = Settings(
        database_url=SecretStr(str(engine.url.render_as_string(hide_password=False))),
        dev_identity=p,
        data_dir=tmp_path,
        max_body_bytes=4096,
        max_source_bytes=32,
    )
    with TestClient(create_app(settings)) as client:
        root = f"/api/v1/workspaces/{w}/corpora/research"
        assert client.get("/api/v1/workspaces").status_code == 200
        assert client.get(f"/api/v1/workspaces/{w}").status_code == 200
        assert client.get(f"/api/v1/workspaces/{uuid4()}/corpora").status_code == 404
        assert (
            client.post(root + "/deliveries", json={"garbage": "secret-marker"}).json()["error"][
                "code"
            ]
            == "INVALID_INPUT"
        )
        assert (
            "secret-marker"
            not in client.post(root + "/deliveries", json={"garbage": "secret-marker"}).text
        )
        assert client.post(root + "/deliveries", content=b"x" * 4097).status_code == 413
        assert (
            client.post(root + "/deliveries", json=delivery().model_dump(mode="json")).json()[
                "status"
            ]
            == "APPLIED"
        )
        assert client.get(root + "/documents").json()[0]["document_id"] == "guide"
        assert client.get(root + "/documents/guide/versions").status_code == 200
        assert client.post(
            root + "/documents/guide/resolve", json={"snapshot_id": "snap:000001"}
        ).json()["active"]
        assert client.get(root + "/documents?limit=101").status_code == 422
        assert (
            client.post(
                root + "/deliveries",
                json=delivery("large", "snap:000001", [revision("r2", 2, b"x" * 33)]).model_dump(
                    mode="json"
                ),
            ).status_code
            == 413
        )
    with TestClient(create_app(settings.model_copy(update={"dev_identity": None}))) as client:
        assert client.get("/api/v1/workspaces").status_code == 503
    # _env_file=None isolates these from the developer's .env (which sets a dev identity);
    # otherwise the production validator rejects the inherited identity before the app builds.
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=settings.database_url,
            environment="production",
            cors_origins=[],
            dev_identity="bypass",
        )
    with TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_url=settings.database_url,
                environment="production",
                cors_origins=[],
            )
        )
    ) as client:
        assert client.get("/api/v1/workspaces").status_code == 503


def _legacy_0003_as24(workspace_id) -> str:
    """0003-only SQL. Column lists match 0003 exactly; timestamps are explicit UTC."""
    guide_r1, guide_r2 = "Starter costs 12 USD.", "Starter costs 15 USD."
    alpha, omega = "alpha unique words here", "omega completely different"
    sha = content_hash
    digest = {
        "guide_r1": sha(guide_r1),
        "guide_r2": sha(guide_r2),
        "alpha": sha(alpha),
        "omega": sha(omega),
    }
    norm = {
        key: bytes_hash(norm_v1_text(text).encode())
        for key, text in (
            ("guide_r1", guide_r1),
            ("guide_r2", guide_r2),
            ("alpha", alpha),
            ("omega", omega),
        )
    }

    def fp(text: str, authority: dict | None = None) -> str:
        return bytes_hash(
            canonical_json(
                {
                    "content_hash": sha(text),
                    "source_type": "product_doc",
                    "authority": authority or {},
                }
            )
        )

    w = str(workspace_id)
    ts = {
        "jan": "2026-01-01T00:00:00+00:00",
        "feb": "2026-02-01T00:00:00+00:00",
        "apr": "2026-04-01T00:00:00+00:00",
        "nov": "2026-11-01T00:00:00+00:00",
        "dec": "2026-12-01T00:00:00+00:00",
    }
    # 0003 table column counts: passage_versions 14, passage_lineage_edges 11,
    # members 7, snapshot_changes 6, applicability_changes 17, change_spans 26.
    return f"""
    INSERT INTO workspaces(id,name,created_at) VALUES('{w}','Legacy 0003','{ts["jan"]}');
    INSERT INTO workspace_members(workspace_id,principal) VALUES('{w}','legacy-owner');
    INSERT INTO corpora(workspace_id,corpus_id,name,head_snapshot_id) VALUES('{w}','research','Research',NULL);
    INSERT INTO documents(workspace_id,corpus_id,document_id,created_at) VALUES
      ('{w}','research','guide','{ts["jan"]}'),('{w}','research','two','{ts["jan"]}'),('{w}','research','three','{ts["jan"]}');
    INSERT INTO update_events(workspace_id,corpus_id,delivery_id,update_event_id,payload_hash,as_of,expected_head,received_at) VALUES
      ('{w}','research','load-r1','upd:load-r1','{bytes_hash(b"load-r1")}','{ts["nov"]}',NULL,'{ts["nov"]}'),
      ('{w}','research','load-r2','upd:load-r2','{bytes_hash(b"load-r2")}','{ts["nov"]}','snap:000001','{ts["nov"]}'),
      ('{w}','research','load-r3','upd:load-r3','{bytes_hash(b"load-r3")}','{ts["nov"]}','snap:000002','{ts["nov"]}'),
      ('{w}','research','load-r4','upd:load-r4','{bytes_hash(b"load-r4")}','{ts["nov"]}','snap:000003','{ts["nov"]}');
    INSERT INTO snapshots(workspace_id,corpus_id,snapshot_id,snapshot_seq,parent_snapshot_id,update_event_id,manifest_hash,document_count,as_of) VALUES
      ('{w}','research','snap:000001',1,NULL,'upd:load-r1','{bytes_hash(b"snap1")}',3,'{ts["nov"]}'),
      ('{w}','research','snap:000002',2,'snap:000001','upd:load-r2','{bytes_hash(b"snap2")}',3,'{ts["nov"]}'),
      ('{w}','research','snap:000003',3,'snap:000002','upd:load-r3','{bytes_hash(b"snap3")}',3,'{ts["nov"]}'),
      ('{w}','research','snap:000004',4,'snap:000003','upd:load-r4','{bytes_hash(b"snap4")}',3,'{ts["nov"]}');
    INSERT INTO source_objects(workspace_id,corpus_id,object_key,byte_length) VALUES
      ('{w}','research','{digest["guide_r1"]}',{len(guide_r1)}),
      ('{w}','research','{digest["guide_r2"]}',{len(guide_r2)}),
      ('{w}','research','{digest["alpha"]}',{len(alpha)}),
      ('{w}','research','{digest["omega"]}',{len(omega)});
    INSERT INTO document_versions(workspace_id,corpus_id,document_id,document_version_id,source_revision_id,source_seq,text,content_hash,source_bytes_hash,object_key,normalization_version,source_timestamp,declared_effective_from,effective_from,effective_from_source,source_type,authority,is_deletion,created_at,known_at_seq,immutable_hash) VALUES
      ('{w}','research','guide','dv:guide@r1','r1',1,'{guide_r1}','{digest["guide_r1"]}','{digest["guide_r1"]}','{digest["guide_r1"]}','canon-v1','{ts["jan"]}','{ts["jan"]}','{ts["jan"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["jan"]}',1,'{bytes_hash(b"dv:guide@r1")}'),
      ('{w}','research','guide','dv:guide@r2','r2',2,'{guide_r2}','{digest["guide_r2"]}','{digest["guide_r2"]}','{digest["guide_r2"]}','canon-v1','{ts["dec"]}','{ts["dec"]}','{ts["dec"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["dec"]}',2,'{bytes_hash(b"dv:guide@r2")}'),
      ('{w}','research','guide','dv:guide@r3','r3',3,'{guide_r2}','{digest["guide_r2"]}','{digest["guide_r2"]}','{digest["guide_r2"]}','canon-v1','{ts["apr"]}','{ts["apr"]}','{ts["apr"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["apr"]}',3,'{bytes_hash(b"dv:guide@r3")}'),
      ('{w}','research','guide','dv:guide@r4','r4',4,'{guide_r2}','{digest["guide_r2"]}','{digest["guide_r2"]}','{digest["guide_r2"]}','canon-v1','{ts["apr"]}','{ts["apr"]}','{ts["apr"]}','DECLARED_METADATA','product_doc','{{"tier": 2}}',FALSE,'{ts["apr"]}',4,'{bytes_hash(b"dv:guide@r4")}'),
      ('{w}','research','two','dv:two@r1','r1',1,'{alpha}','{digest["alpha"]}','{digest["alpha"]}','{digest["alpha"]}','canon-v1','{ts["jan"]}','{ts["jan"]}','{ts["jan"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["jan"]}',1,'{bytes_hash(b"dv:two@r1")}'),
      ('{w}','research','two','dv:two@r2','r2',2,'{omega}','{digest["omega"]}','{digest["omega"]}','{digest["omega"]}','canon-v1','{ts["feb"]}','{ts["feb"]}','{ts["feb"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["feb"]}',2,'{bytes_hash(b"dv:two@r2")}'),
      ('{w}','research','three','dv:three@r1','r1',1,'{alpha}','{digest["alpha"]}','{digest["alpha"]}','{digest["alpha"]}','canon-v1','{ts["jan"]}','{ts["jan"]}','{ts["jan"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["jan"]}',1,'{bytes_hash(b"dv:three@r1")}'),
      ('{w}','research','three','dv:three@r2','r2',2,'{omega}','{digest["omega"]}','{digest["omega"]}','{digest["omega"]}','canon-v1','{ts["dec"]}','{ts["dec"]}','{ts["dec"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["dec"]}',2,'{bytes_hash(b"dv:three@r2")}'),
      ('{w}','research','three','dv:three@r3','r3',3,'{omega}','{digest["omega"]}','{digest["omega"]}','{digest["omega"]}','canon-v1','{ts["apr"]}','{ts["apr"]}','{ts["apr"]}','DECLARED_METADATA','product_doc','{{}}',FALSE,'{ts["apr"]}',3,'{bytes_hash(b"dv:three@r3")}');
    INSERT INTO snapshot_documents(workspace_id,corpus_id,snapshot_id,document_id,document_version_id) VALUES
      ('{w}','research','snap:000001','guide','dv:guide@r1'),('{w}','research','snap:000001','two','dv:two@r1'),('{w}','research','snap:000001','three','dv:three@r1'),
      ('{w}','research','snap:000002','guide','dv:guide@r2'),('{w}','research','snap:000002','two','dv:two@r2'),('{w}','research','snap:000002','three','dv:three@r2'),
      ('{w}','research','snap:000003','guide','dv:guide@r3'),('{w}','research','snap:000003','two','dv:two@r2'),('{w}','research','snap:000003','three','dv:three@r3'),
      ('{w}','research','snap:000004','guide','dv:guide@r4'),('{w}','research','snap:000004','two','dv:two@r2'),('{w}','research','snap:000004','three','dv:three@r3');
    INSERT INTO snapshot_changes(workspace_id,corpus_id,snapshot_id,update_event_id,document_id,document_version_id) VALUES
      ('{w}','research','snap:000001','upd:load-r1','guide','dv:guide@r1'),('{w}','research','snap:000001','upd:load-r1','two','dv:two@r1'),('{w}','research','snap:000001','upd:load-r1','three','dv:three@r1'),
      ('{w}','research','snap:000002','upd:load-r2','guide','dv:guide@r2'),('{w}','research','snap:000002','upd:load-r2','two','dv:two@r2'),('{w}','research','snap:000002','upd:load-r2','three','dv:three@r2'),
      ('{w}','research','snap:000003','upd:load-r3','guide','dv:guide@r3'),('{w}','research','snap:000003','upd:load-r3','three','dv:three@r3'),
      ('{w}','research','snap:000004','upd:load-r4','guide','dv:guide@r4');
    INSERT INTO update_event_status_log(workspace_id,corpus_id,delivery_id,status,snapshot_id,error_code,recorded_at) VALUES
      ('{w}','research','load-r1','APPLIED','snap:000001',NULL,'{ts["nov"]}'),
      ('{w}','research','load-r2','APPLIED','snap:000002',NULL,'{ts["nov"]}'),
      ('{w}','research','load-r3','APPLIED','snap:000003',NULL,'{ts["nov"]}'),
      ('{w}','research','load-r4','APPLIED','snap:000004',NULL,'{ts["nov"]}');
    UPDATE corpora SET head_snapshot_id='snap:000004' WHERE workspace_id='{w}' AND corpus_id='research';
    INSERT INTO passage_versions(workspace_id,corpus_id,document_id,document_version_id,passage_version_id,ordinal,start_offset,end_offset,text,section_path,content_hash,norm_hash,lineage_id,segmentation_version) VALUES
      ('{w}','research','guide','dv:guide@r1','pv:guide@r1#p0001',1,0,{len(guide_r1)},'{guide_r1}','[]','{digest["guide_r1"]}','{norm["guide_r1"]}','lin:guide:r1:p0001','seg-v1'),
      ('{w}','research','guide','dv:guide@r2','pv:guide@r2#p0001',1,0,{len(guide_r2)},'{guide_r2}','[]','{digest["guide_r2"]}','{norm["guide_r2"]}','lin:guide:r1:p0001','seg-v1'),
      ('{w}','research','guide','dv:guide@r3','pv:guide@r3#p0001',1,0,{len(guide_r2)},'{guide_r2}','[]','{digest["guide_r2"]}','{norm["guide_r2"]}','lin:guide:r1:p0001','seg-v1'),
      ('{w}','research','guide','dv:guide@r4','pv:guide@r4#p0001',1,0,{len(guide_r2)},'{guide_r2}','[]','{digest["guide_r2"]}','{norm["guide_r2"]}','lin:guide:r1:p0001','seg-v1'),
      ('{w}','research','two','dv:two@r1','pv:two@r1#p0001',1,0,{len(alpha)},'{alpha}','[]','{digest["alpha"]}','{norm["alpha"]}','lin:two:r1:p0001','seg-v1'),
      ('{w}','research','two','dv:two@r2','pv:two@r2#p0001',1,0,{len(omega)},'{omega}','[]','{digest["omega"]}','{norm["omega"]}','lin:two:r2:p0001','seg-v1'),
      ('{w}','research','three','dv:three@r1','pv:three@r1#p0001',1,0,{len(alpha)},'{alpha}','[]','{digest["alpha"]}','{norm["alpha"]}','lin:three:r1:p0001','seg-v1'),
      ('{w}','research','three','dv:three@r2','pv:three@r2#p0001',1,0,{len(omega)},'{omega}','[]','{digest["omega"]}','{norm["omega"]}','lin:three:r2:p0001','seg-v1'),
      ('{w}','research','three','dv:three@r3','pv:three@r3#p0001',1,0,{len(omega)},'{omega}','[]','{digest["omega"]}','{norm["omega"]}','lin:three:r2:p0001','seg-v1');
    INSERT INTO passage_lineage_edges(workspace_id,corpus_id,document_id,update_event_id,lineage_edge_id,edge_ordinal,relation,alignment_score,alignment_confidence,alignment_method,reason) VALUES
      ('{w}','research','guide','upd:load-r1','le:load-r1:0001',1,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','two','upd:load-r1','le:load-r1:0002',2,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r1','le:load-r1:0003',3,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','guide','upd:load-r2','le:load-r2:0001',1,'MODIFIED',0.8,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','two','upd:load-r2','le:load-r2:0002',2,'DELETED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','two','upd:load-r2','le:load-r2:0003',3,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r2','le:load-r2:0004',4,'DELETED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r2','le:load-r2:0005',5,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','guide','upd:load-r3','le:load-r3:0001',1,'IDENTICAL',1.0,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','guide','upd:load-r3','le:load-r3:0002',2,'MODIFIED',0.8,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r3','le:load-r3:0003',3,'IDENTICAL',1.0,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r3','le:load-r3:0004',4,'DELETED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','three','upd:load-r3','le:load-r3:0005',5,'ADDED',NULL,'HIGH','diff-v1/dice-v1','{{}}'),
      ('{w}','research','guide','upd:load-r4','le:load-r4:0001',1,'IDENTICAL',1.0,'HIGH','diff-v1/dice-v1','{{}}');
    INSERT INTO passage_lineage_edge_members(workspace_id,corpus_id,document_id,lineage_edge_id,passage_version_id,side,member_ordinal) VALUES
      ('{w}','research','guide','le:load-r1:0001','pv:guide@r1#p0001','NEW',1),
      ('{w}','research','two','le:load-r1:0002','pv:two@r1#p0001','NEW',1),
      ('{w}','research','three','le:load-r1:0003','pv:three@r1#p0001','NEW',1),
      ('{w}','research','guide','le:load-r2:0001','pv:guide@r1#p0001','OLD',1),
      ('{w}','research','guide','le:load-r2:0001','pv:guide@r2#p0001','NEW',1),
      ('{w}','research','two','le:load-r2:0002','pv:two@r1#p0001','OLD',1),
      ('{w}','research','two','le:load-r2:0003','pv:two@r2#p0001','NEW',1),
      ('{w}','research','three','le:load-r2:0004','pv:three@r1#p0001','OLD',1),
      ('{w}','research','three','le:load-r2:0005','pv:three@r2#p0001','NEW',1),
      ('{w}','research','guide','le:load-r3:0001','pv:guide@r2#p0001','OLD',1),
      ('{w}','research','guide','le:load-r3:0001','pv:guide@r3#p0001','NEW',1),
      ('{w}','research','guide','le:load-r3:0002','pv:guide@r1#p0001','OLD',1),
      ('{w}','research','guide','le:load-r3:0002','pv:guide@r3#p0001','NEW',1),
      ('{w}','research','three','le:load-r3:0003','pv:three@r2#p0001','OLD',1),
      ('{w}','research','three','le:load-r3:0003','pv:three@r3#p0001','NEW',1),
      ('{w}','research','three','le:load-r3:0004','pv:three@r1#p0001','OLD',1),
      ('{w}','research','three','le:load-r3:0005','pv:three@r3#p0001','NEW',1),
      ('{w}','research','guide','le:load-r4:0001','pv:guide@r3#p0001','OLD',1),
      ('{w}','research','guide','le:load-r4:0001','pv:guide@r4#p0001','NEW',1);
    INSERT INTO applicability_changes(workspace_id,corpus_id,update_event_id,document_id,applicability_change_id,change_ordinal,parent_snapshot_id,result_snapshot_id,interval_from,interval_to,old_effective_version_id,new_effective_version_id,old_effective_fingerprint,new_effective_fingerprint,reason,text_diff_reused,timeline_version) VALUES
      ('{w}','research','upd:load-r3','guide','ac:load-r3:0001',1,'snap:000002','snap:000003','{ts["apr"]}','{ts["dec"]}','dv:guide@r1','dv:guide@r3','{fp(guide_r1)}','{fp(guide_r2)}','CONTENT',FALSE,'timeline-v1'),
      ('{w}','research','upd:load-r3','three','ac:load-r3:0002',2,'snap:000002','snap:000003','{ts["apr"]}','{ts["dec"]}','dv:three@r1','dv:three@r3','{fp(alpha)}','{fp(omega)}','CONTENT',FALSE,'timeline-v1'),
      ('{w}','research','upd:load-r4','guide','ac:load-r4:0001',1,'snap:000003','snap:000004','{ts["apr"]}','{ts["dec"]}','dv:guide@r3','dv:guide@r4','{fp(guide_r2)}','{fp(guide_r2, {"tier": 2})}','AUTHORITY',FALSE,'timeline-v1');
    INSERT INTO change_spans(workspace_id,corpus_id,update_event_id,document_id,change_span_id,span_ordinal,old_document_version_id,new_document_version_id,old_passage_version_id,new_passage_version_id,kind,lineage_edge_id,old_start,old_end,new_start,new_end,old_text,new_text,features,alignment_confidence,effective_from,effective_to,applicability_change_id,text_diff_reused,origin,metadata) VALUES
      ('{w}','research','upd:load-r3','guide','cs:load-r3:0001',1,'dv:guide@r1','dv:guide@r3','pv:guide@r1#p0001','pv:guide@r3#p0001','MODIFIED','le:load-r3:0002',14,16,14,16,'12','15','{{}}','HIGH','{ts["apr"]}','{ts["dec"]}','ac:load-r3:0001',FALSE,'TIMELINE','{{}}'),
      ('{w}','research','upd:load-r3','three','cs:load-r3:0002',2,'dv:three@r1','dv:three@r3','pv:three@r1#p0001',NULL,'DELETED','le:load-r3:0004',0,{len(alpha)},NULL,NULL,'{alpha}',NULL,'{{}}','HIGH','{ts["apr"]}','{ts["dec"]}','ac:load-r3:0002',FALSE,'TIMELINE','{{}}'),
      ('{w}','research','upd:load-r3','three','cs:load-r3:0003',3,'dv:three@r1','dv:three@r3',NULL,'pv:three@r3#p0001','ADDED','le:load-r3:0005',NULL,NULL,0,{len(omega)},NULL,'{omega}','{{}}','HIGH','{ts["apr"]}','{ts["dec"]}','ac:load-r3:0002',FALSE,'TIMELINE','{{}}'),
      ('{w}','research','upd:load-r4','guide','cs:load-r4:0001',1,'dv:guide@r3','dv:guide@r4',NULL,NULL,'AUTHORITY_CHANGED',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'{{}}','HIGH','{ts["apr"]}','{ts["dec"]}','ac:load-r4:0001',FALSE,'AUTHORITY','{{}}');
    """


def test_migration_legacy_0003_as24_replay():
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    name = "migration_legacy_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    workspace = uuid4()
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        binary = str(Path(sys.executable).parent / "alembic")
        env = {**os.environ, "AFTERMATH_DATABASE_URL": target}

        def migrate(*args):
            result = subprocess.run(
                [binary, *args], env=env, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0, result.stderr

        migrate("upgrade", "0003")
        db = create_engine(target)
        sql = _legacy_0003_as24(workspace)
        assert "passage_versions(" in sql
        assert sql.count("INSERT INTO passage_versions") == 1
        with db.begin() as connection:
            connection.exec_driver_sql(sql)
            lineage_before = [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM passage_lineage_edges "
                        "ORDER BY workspace_id,corpus_id,update_event_id,edge_ordinal"
                    )
                ).mappings()
            ]
            members_before = [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM passage_lineage_edge_members "
                        "ORDER BY workspace_id,corpus_id,lineage_edge_id,side,member_ordinal"
                    )
                ).mappings()
            ]
            assert (
                connection.execute(
                    text("SELECT count(*) FROM change_spans WHERE origin='TIMELINE'")
                ).scalar()
                == 3
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM passage_lineage_edges WHERE update_event_id='upd:load-r3' AND document_id='three'"
                    )
                ).scalar()
                == 3
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM passage_lineage_edges WHERE update_event_id='upd:load-r2' AND document_id='two'"
                    )
                ).scalar()
                == 2
            )
        migrate("upgrade", "0004")
        with db.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0004"
            )
            assert (
                connection.execute(text("SELECT count(*) FROM timeline_alignment_edges")).scalar()
                == 3
            )
            assert [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM passage_lineage_edges "
                        "ORDER BY workspace_id,corpus_id,update_event_id,edge_ordinal"
                    )
                ).mappings()
            ] == lineage_before
            assert [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM passage_lineage_edge_members "
                        "ORDER BY workspace_id,corpus_id,lineage_edge_id,side,member_ordinal"
                    )
                ).mappings()
            ] == members_before
            assert (
                connection.execute(
                    text("SELECT count(*) FROM timeline_alignment_edges WHERE document_id='guide'")
                ).scalar()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM timeline_alignment_edges WHERE document_id='three'")
                ).scalar()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM timeline_alignment_edges WHERE update_event_id='upd:load-r2'"
                    )
                ).scalar()
                == 0
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM timeline_alignment_edges WHERE update_event_id='upd:load-r4'"
                    )
                ).scalar()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT recorded_by FROM timeline_alignment_edges GROUP BY recorded_by")
                ).scalar()
                == "migration-0004-reclassification"
            )
            assert (
                connection.execute(
                    text(
                        """SELECT count(*) FROM passage_lineage_edges e
                    WHERE e.update_event_id='upd:load-r3' AND e.document_id='guide'
                    AND NOT EXISTS (SELECT 1 FROM timeline_alignment_edges t
                      WHERE t.workspace_id=e.workspace_id AND t.corpus_id=e.corpus_id
                      AND t.legacy_lineage_edge_id=e.lineage_edge_id)"""
                    )
                ).scalar()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM change_spans WHERE origin='TIMELINE' AND lineage_edge_id IS NOT NULL"
                    )
                ).scalar()
                == 3
            )
            repository = PostgresCorpusRepository(connection)
            lineage = repository.lineage_edges(workspace, "research", "load-r3", "guide")
            temporal = repository.timeline_alignments(workspace, "research", "load-r3", "guide")
            assert len(lineage) == 1
            assert lineage[0].relation == "IDENTICAL"
            assert "@r2" in "".join(lineage[0].from_passage_version_ids)
            assert len(temporal) == 1
            assert temporal[0].relation == "MODIFIED"
            assert temporal[0].legacy_lineage_edge_id == "le:load-r3:0002"
            with pytest.raises(SQLAlchemyError), connection.begin_nested():
                connection.execute(
                    text(
                        """INSERT INTO passage_versions(
                          workspace_id,corpus_id,document_id,document_version_id,passage_version_id,
                          ordinal,start_offset,end_offset,text,section_path,content_hash,norm_hash,
                          lineage_id,segmentation_version,norm_version)
                        SELECT workspace_id,corpus_id,document_id,document_version_id,'pv:guide@r1#p0002',
                          2,start_offset,end_offset,text,section_path,content_hash,norm_hash,
                          lineage_id,segmentation_version,NULL
                        FROM passage_versions WHERE passage_version_id='pv:guide@r1#p0001' LIMIT 1"""
                    )
                )
        migrate("upgrade", "0005")
        with db.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0005"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='change_span_timeline_fk_v3'"
                    )
                ).scalar()
                == 1
            )
            timeline_before = [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM timeline_alignment_edges "
                        "ORDER BY workspace_id,corpus_id,update_event_id,alignment_ordinal"
                    )
                ).mappings()
            ]
        migrate("downgrade", "0004")
        migrate("upgrade", "0005")
        migrate("downgrade", "0003")
        migrate("upgrade", "0005")
        with db.connect() as connection:
            assert [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT * FROM timeline_alignment_edges "
                        "ORDER BY workspace_id,corpus_id,update_event_id,alignment_ordinal"
                    )
                ).mappings()
            ] == timeline_before
        db.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migration_0004_rejects_orphan_legacy_applicability_and_stays_at_0003():
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    name = "migration_orphan_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    workspace = uuid4()
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        binary = str(Path(sys.executable).parent / "alembic")
        env = {**os.environ, "AFTERMATH_DATABASE_URL": target}

        def migrate(*args, succeeds=True):
            result = subprocess.run(
                [binary, *args], env=env, capture_output=True, text=True, timeout=30
            )
            assert (result.returncode == 0) is succeeds, result.stderr
            return result

        migrate("upgrade", "0003")
        db = create_engine(target)
        with db.begin() as connection:
            connection.exec_driver_sql(_legacy_0003_as24(workspace))
            connection.execute(
                text(
                    """INSERT INTO applicability_changes(
                    workspace_id,corpus_id,update_event_id,document_id,
                    applicability_change_id,change_ordinal,parent_snapshot_id,
                    result_snapshot_id,interval_from,interval_to,
                    old_effective_version_id,new_effective_version_id,
                    old_effective_fingerprint,new_effective_fingerprint,
                    reason,text_diff_reused,timeline_version)
                    SELECT workspace_id,corpus_id,update_event_id,document_id,
                    'ac:orphan:0099',99,parent_snapshot_id,result_snapshot_id,
                    interval_from,interval_to,'dv:guide@orphan',new_effective_version_id,
                    old_effective_fingerprint,new_effective_fingerprint,reason,
                    text_diff_reused,timeline_version
                    FROM applicability_changes
                    WHERE document_id='guide' LIMIT 1"""
                )
            )
        failed = migrate("upgrade", "0004", succeeds=False)
        assert "CONSTRAINT_AUDIT:applicability_old_version_fk=1" in failed.stderr
        with db.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0003"
            )
            assert (
                connection.execute(
                    text("SELECT to_regclass('public.timeline_alignment_edges')")
                ).scalar()
                is None
            )
        db.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migration_fresh_foundation_upgrade_and_round_trip():
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    name = "migration_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        binary = str(Path(sys.executable).parent / "alembic")
        env = {**os.environ, "AFTERMATH_DATABASE_URL": target}

        def migrate(*args):
            result = subprocess.run(
                [binary, *args], env=env, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0, result.stderr

        migrate("upgrade", "0001")
        db = create_engine(target)
        preserved = uuid4()
        with db.begin() as connection:
            connection.execute(
                text("INSERT INTO workspaces(id,name) VALUES(:id,'Preserved foundation')"),
                {"id": preserved},
            )
        migrate("upgrade", "0003")
        with db.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0003"
            )
        migrate("upgrade", "0005")
        with db.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "0005"
            assert (
                connection.execute(
                    text("SELECT name FROM workspaces WHERE id=:id"), {"id": preserved}
                ).scalar()
                == "Preserved foundation"
            )
        db.dispose()
        migrate("downgrade", "0003")
        migrate("upgrade", "0005")
        migrate("downgrade", "0001")
        migrate("upgrade", "0005")
        migrate("downgrade", "base")
        migrate("upgrade", "head")
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migration_0005_audit_failure_keeps_0004_revision(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    name = "migration_audit_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        binary = str(Path(sys.executable).parent / "alembic")
        env = {**os.environ, "AFTERMATH_DATABASE_URL": target}

        def migrate(*args, succeeds=True):
            result = subprocess.run(
                [binary, *args], env=env, capture_output=True, text=True, timeout=30
            )
            assert (result.returncode == 0) is succeeds, result.stderr
            return result

        migrate("upgrade", "0004")
        db = create_engine(target)
        service = CorpusService(PostgresCorpusStore(db), LocalObjectStore(tmp_path))
        principal = "audit-owner"
        workspace = service.create_workspace(principal, "Audit migration").id
        service.create_corpus(principal, workspace, "research", "Research")
        first = service.ingest(
            principal,
            workspace,
            "research",
            delivery("audit-r1", revisions=[revision(content=b"Starter costs 12 USD.")]),
        )
        second = service.ingest(
            principal,
            workspace,
            "research",
            delivery(
                "audit-r2",
                first.snapshot_id,
                [revision("r2", 2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z")],
            ),
        )
        service.ingest(
            principal,
            workspace,
            "research",
            delivery(
                "audit-r3",
                second.snapshot_id,
                [revision("r3", 3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z")],
            ),
        )
        with db.begin() as connection:
            alignment = connection.execute(
                text(
                    "SELECT timeline_alignment_edge_id FROM timeline_alignment_edges "
                    "WHERE workspace_id=:w AND update_event_id='upd:audit-r3'"
                ),
                {"w": workspace},
            ).scalar_one()
            connection.execute(
                text(
                    """INSERT INTO change_spans(
                    workspace_id,corpus_id,update_event_id,document_id,change_span_id,
                    span_ordinal,kind,timeline_alignment_edge_id,features,
                    alignment_confidence,effective_from,text_diff_reused,feature_version,
                    origin,metadata)
                    VALUES(:w,'research','upd:audit-r1','guide','cs:audit-bad:9999',999,
                    'AUTHORITY_CHANGED',:alignment,'{}','HIGH','2026-04-01T00:00:00Z',
                    FALSE,'features-v1','TIMELINE','{}')"""
                ),
                {"w": workspace, "alignment": alignment},
            )
        failed = migrate("upgrade", "0005", succeeds=False)
        assert "TIMELINE_SPAN_SCOPE_AUDIT:count=1" in failed.stderr
        with db.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0004"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='change_span_timeline_fk_v2'"
                    )
                ).scalar()
                == 1
            )
        db.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migration_0005_guarded_downgrade_preserves_native_timeline(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    name = "migration_guard_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        binary = str(Path(sys.executable).parent / "alembic")
        env = {**os.environ, "AFTERMATH_DATABASE_URL": target}

        def migrate(*args, succeeds=True):
            result = subprocess.run(
                [binary, *args], env=env, capture_output=True, text=True, timeout=30
            )
            assert (result.returncode == 0) is succeeds, result.stderr
            return result

        migrate("upgrade", "0004")
        migrate("upgrade", "0005")
        db = create_engine(target)
        service = CorpusService(PostgresCorpusStore(db), LocalObjectStore(tmp_path))
        principal = "guard-owner"
        workspace = service.create_workspace(principal, "Guard migration").id
        service.create_corpus(principal, workspace, "research", "Research")
        first = service.ingest(
            principal,
            workspace,
            "research",
            delivery("guard-r1", revisions=[revision(content=b"Starter costs 12 USD.")]),
        )
        second = service.ingest(
            principal,
            workspace,
            "research",
            delivery(
                "guard-r2",
                first.snapshot_id,
                [revision("r2", 2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z")],
            ),
        )
        service.ingest(
            principal,
            workspace,
            "research",
            delivery(
                "guard-r3",
                second.snapshot_id,
                [revision("r3", 3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z")],
            ),
        )
        with db.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM timeline_alignment_edges "
                        "WHERE recorded_by='timeline-v1'"
                    )
                ).scalar()
                == 1
            )
        failed = migrate("downgrade", "0004", succeeds=False)
        assert "UNSAFE_DOWNGRADE_NATIVE_TIMELINE_ALIGNMENT:count=1" in failed.stderr
        with db.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0005"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM timeline_alignment_edges "
                        "WHERE recorded_by='timeline-v1'"
                    )
                ).scalar()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='change_span_timeline_fk_v3'"
                    )
                ).scalar()
                == 1
            )
        migrate("upgrade", "head")
        db.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
