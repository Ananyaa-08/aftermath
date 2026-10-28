"""Independent span/version constraints and disposable 0006 migration checks."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from test_corpus import _legacy_0003_as24, delivery, revision

from aftermath.adapters.persistence.corpus import PostgresCorpusStore
from aftermath.adapters.persistence.database import PostgresProbe
from aftermath.adapters.storage.local import LocalObjectStore
from aftermath.application.corpus import CorpusService

pytestmark = pytest.mark.integration


def required_url():
    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL required")
    return url


@contextmanager
def disposable_database():
    url = required_url()
    name = "span_0006_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    target = make_url(url).set(database=name).render_as_string(hide_password=False)
    db = create_engine(target, hide_parameters=True)
    probe = PostgresProbe(target)
    binary = str(Path(sys.executable).parent / "alembic")

    def migrate(*args, succeeds=True):
        result = subprocess.run(
            [binary, *args],
            env={**os.environ, "AFTERMATH_DATABASE_URL": target},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result

    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield db, probe, migrate
    finally:
        probe.close()
        db.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def seed_pairs(engine, tmp_path):
    service = CorpusService(PostgresCorpusStore(engine), LocalObjectStore(tmp_path))
    principal = "span-" + uuid4().hex
    workspace = service.create_workspace(principal, "Span integrity").id
    service.create_corpus(principal, workspace, "research", "Research")
    head = None
    for number, price, effective, extra in [
        (1, b"Starter costs 12 USD.", "2026-01-01T00:00:00Z", {}),
        (2, b"Starter costs 15 USD.", "2026-12-01T00:00:00Z", {}),
        (3, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z", {}),
        (4, b"Starter costs 15 USD.", "2026-04-01T00:00:00Z", {"authority": {"tier": 2}}),
        (5, b"", "2027-01-01T00:00:00Z", {"deleted": True}),
    ]:
        result = service.ingest(
            principal,
            workspace,
            "research",
            delivery(
                f"pair-r{number}",
                head,
                [revision(f"r{number}", number, price, effective, **extra)],
            ),
        )
        assert result.status == "APPLIED"
        head = result.snapshot_id
    service.ingest(
        principal,
        workspace,
        "research",
        delivery("other", head, [revision(document="other")]),
    )
    service.create_corpus(principal, workspace, "elsewhere", "Elsewhere")
    service.ingest(
        principal, workspace, "elsewhere", delivery("foreign", revisions=[revision("foreign", 1)])
    )
    outside = service.create_workspace(principal, "Outside").id
    service.create_corpus(principal, outside, "research", "Research")
    service.ingest(
        principal, outside, "research", delivery("outside", revisions=[revision("outside", 1)])
    )
    return workspace


def copy_span(connection, workspace, source, **patch):
    # Copy a REAL valid span; only explicit adversarial fields differ. Every
    # caller checks rowcount so a missing fixture cannot masquerade as rejection.
    result = connection.execute(
        text("""
            INSERT INTO change_spans
            SELECT (jsonb_populate_record(NULL::change_spans,
              to_jsonb(s) || CAST(:patch AS jsonb))).*
            FROM change_spans s WHERE workspace_id=:w AND corpus_id='research'
              AND change_span_id=:source
        """),
        {
            "w": workspace,
            "source": source,
            "patch": json.dumps(
                {"change_span_id": "cs:pair-probe:9999", "span_ordinal": 9999, **patch}
            ),
        },
    )
    assert result.rowcount == 1


def stored_rows(connection):
    tables = (
        "document_versions",
        "passage_versions",
        "passage_lineage_edges",
        "timeline_alignment_edges",
        "timeline_alignment_edge_members",
        "change_spans",
        "applicability_changes",
    )
    return {
        table: connection.execute(
            text(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY to_jsonb(t)::text")
        )
        .scalars()
        .all()
        for table in tables
    }


def new_constraint_count(connection):
    return connection.execute(
        text("""
            SELECT count(*) FROM pg_constraint
            WHERE conname LIKE 'change_span_%_passage_version_fk'
               OR conname LIKE 'change_span_%_passage_requires_version_ck'
        """)
    ).scalar_one()


def test_span_passage_document_version_constraints(tmp_path):
    engine = create_engine(required_url(), hide_parameters=True)
    try:
        workspace = seed_pairs(engine, tmp_path)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0006"
            )
            sources = (
                connection.execute(
                    text("""
                    SELECT change_span_id,kind,origin FROM change_spans
                    WHERE workspace_id=:w AND corpus_id='research'
                    """),
                    {"w": workspace},
                )
                .mappings()
                .all()
            )
        lineage = next(
            s["change_span_id"]
            for s in sources
            if s["kind"] == "MODIFIED" and s["origin"] == "LATEST_OBSERVED"
        )
        timeline = next(s["change_span_id"] for s in sources if s["origin"] == "TIMELINE")

        # Both directions, both span origins, both sides, with exact constraint
        # assertions: same-document version swaps previously passed all FKs.
        for source in (lineage, timeline):
            for side in ("old", "new"):
                for claimed, actual in (("r1", "r2"), ("r2", "r1")):
                    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
                        copy_span(
                            connection,
                            workspace,
                            source,
                            **{
                                f"{side}_document_version_id": f"dv:guide@{claimed}",
                                f"{side}_passage_version_id": f"pv:guide@{actual}#p0001",
                            },
                        )
                    assert caught.value.orig.diag.constraint_name == (
                        f"change_span_{side}_passage_version_fk"
                    )
        for side in ("old", "new"):
            for passage in (
                "pv:other@r1#p0001",
                "pv:guide@foreign#p0001",
                "pv:guide@outside#p0001",
                "pv:guide@missing#p0001",
            ):
                with pytest.raises(IntegrityError), engine.begin() as connection:
                    copy_span(
                        connection, workspace, lineage, **{f"{side}_passage_version_id": passage}
                    )
            for version_id in ("dv:guide@missing", None):
                with pytest.raises(IntegrityError), engine.begin() as connection:
                    copy_span(
                        connection,
                        workspace,
                        lineage,
                        **{f"{side}_document_version_id": version_id},
                    )

        # Positive controls are rolled back, retaining immutable fixture data.
        for source in sources:
            with engine.connect() as connection:
                transaction = connection.begin()
                copy_span(connection, workspace, source["change_span_id"])
                transaction.rollback()
        with engine.connect() as connection:
            transaction = connection.begin()
            copy_span(
                connection,
                workspace,
                lineage,
                old_document_version_id=None,
                old_passage_version_id=None,
                old_start=None,
                old_end=None,
                old_text=None,
                kind="ADDED",
            )
            transaction.rollback()
        with engine.connect() as connection:
            transaction = connection.begin()
            copy_span(
                connection,
                workspace,
                lineage,
                new_document_version_id=None,
                new_passage_version_id=None,
                new_start=None,
                new_end=None,
                new_text=None,
                kind="DELETED",
            )
            transaction.rollback()
        assert any(s["kind"] == "AUTHORITY_CHANGED" for s in sources)
        assert any(s["kind"] == "DOCUMENT_DELETED" for s in sources)
    finally:
        engine.dispose()


@pytest.mark.parametrize("start", ["base", "0003", "0004", "0005"])
def test_migration_0006_matrix_and_native_round_trip(tmp_path, start):
    with disposable_database() as (db, probe, migrate):
        if start != "base":
            migrate("upgrade", start)
        assert not probe.ready()
        # Seed real native rows at 0005, then prove 0006 changes only constraints.
        if start == "0005":
            seed_pairs(db, tmp_path)
        with db.connect() as connection:
            before = stored_rows(connection) if start == "0005" else None
        migrate("upgrade", "0006")
        assert probe.ready()
        assert "0006 (head)" in migrate("current").stdout
        assert "0006 (head)" in migrate("heads").stdout
        if before is None:
            seed_pairs(db, tmp_path)
            with db.connect() as connection:
                before = stored_rows(connection)
        with db.connect() as connection:
            assert stored_rows(connection) == before
            assert new_constraint_count(connection) == 4
        migrate("downgrade", "0005")
        assert not probe.ready()
        with db.connect() as connection:
            assert stored_rows(connection) == before
            assert new_constraint_count(connection) == 0
        migrate("upgrade", "head")
        assert probe.ready()
        with db.connect() as connection:
            assert stored_rows(connection) == before


@pytest.mark.parametrize("side", ["old", "new", "both", "old-null", "new-null"])
def test_migration_0006_refuses_mismatches_before_ddl(tmp_path, side):
    with disposable_database() as (db, probe, migrate):
        migrate("upgrade", "0005")
        workspace = seed_pairs(db, tmp_path)
        patch = {}
        if side in ("old", "both"):
            patch["old_passage_version_id"] = "pv:guide@r2#p0001"
        if side in ("new", "both"):
            patch["new_passage_version_id"] = "pv:guide@r1#p0001"
        if side.endswith("-null"):
            patch[f"{side.split('-')[0]}_document_version_id"] = None
        with db.begin() as connection:
            source = connection.execute(
                text(
                    "SELECT change_span_id FROM change_spans "
                    "WHERE workspace_id=:w AND kind='MODIFIED' "
                    "AND origin='LATEST_OBSERVED'"
                ),
                {"w": workspace},
            ).scalar_one()
            copy_span(connection, workspace, source, **patch)
            before = stored_rows(connection)
        failed = migrate("upgrade", "0006", succeeds=False)
        assert "SPAN_PASSAGE_VERSION_AUDIT" in failed.stderr
        for selected in ("old", "new") if side == "both" else (side.split("-")[0],):
            assert f"change_span_{selected}_passage_version_fk:count=1" in failed.stderr
        assert "Starter costs" not in failed.stderr
        assert not probe.ready()
        with db.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0005"
            )
            assert stored_rows(connection) == before
            assert new_constraint_count(connection) == 0


def test_migration_0003_legacy_rows_survive_through_0006():
    with disposable_database() as (db, probe, migrate):
        migrate("upgrade", "0003")
        with db.begin() as connection:
            connection.exec_driver_sql(_legacy_0003_as24(uuid4()))
            old_features = connection.execute(
                text("SELECT change_span_id,features FROM change_spans ORDER BY change_span_id")
            ).all()
        migrate("upgrade", "head")
        assert probe.ready()
        with db.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT change_span_id,features FROM change_spans ORDER BY change_span_id")
                ).all()
                == old_features
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM change_spans WHERE feature_version IS NOT NULL")
                ).scalar()
                == 0
            )
