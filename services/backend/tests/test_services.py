import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from aftermath.api.main import create_app
from aftermath.config import Settings

BIN = Path(sys.executable).parent

BAD_URL = "postgresql+psycopg://test:test@127.0.0.1:1/missing"


def test_config_rejects_non_postgres_and_production_local_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=SecretStr("sqlite://"))
    with pytest.raises(ValidationError):
        Settings(database_url=SecretStr(BAD_URL), environment="production")


def test_live_and_unavailable_ready() -> None:
    with TestClient(create_app(Settings(database_url=SecretStr(BAD_URL)))) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["dependencies"]["postgresql"] == "unavailable"
        assert "test:test" not in response.text
        assert client.post("/assess").status_code == 404


def test_cli_help_and_invalid_config() -> None:
    assert (
        subprocess.run(
            [str(BIN / "aftermath-experiment"), "--help"], capture_output=True
        ).returncode
        == 0
    )
    env = {**os.environ, "AFTERMATH_DATABASE_URL": "invalid-secret-value"}
    for command in [
        [str(BIN / "aftermath-experiment"), "--validate-config"],
        [str(BIN / "aftermath-worker"), "--check"],
    ]:
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert "invalid-secret-value" not in result.stderr


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("AFTERMATH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set AFTERMATH_TEST_DATABASE_URL to a migrated PostgreSQL database")
    return url


@pytest.mark.integration
def test_migration_pgvector_jobs_and_ready(database_url: str) -> None:
    engine = create_engine(database_url)
    workspace, job = uuid4(), uuid4()
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            assert (
                conn.execute(text("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector")).scalar() == 0
            )
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
            conn.execute(
                text("INSERT INTO workspaces (id,name) VALUES (:id, :name)"),
                {"id": workspace, "name": "integration test"},
            )
            insert = text("""INSERT INTO jobs (id,workspace_id,idempotency_key,input_snapshot_id)
                             VALUES (:id,:workspace,'test','snap:000001')""")
            conn.execute(insert, {"id": job, "workspace": workspace})
            assert (
                conn.execute(text("SELECT state FROM jobs WHERE id=:id"), {"id": job}).scalar()
                == "QUEUED"
            )
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(insert, {"id": uuid4(), "workspace": workspace})
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(text("UPDATE jobs SET state='RUNNING' WHERE id=:id"), {"id": job})
            transaction.rollback()
        with TestClient(create_app(Settings(database_url=SecretStr(database_url)))) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
    finally:
        engine.dispose()


@pytest.mark.integration
def test_worker_shutdown_and_experiment_validation(database_url: str) -> None:
    env = {**os.environ, "AFTERMATH_DATABASE_URL": database_url}
    result = subprocess.run(
        [str(BIN / "aftermath-experiment"), "--validate-config"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    process = subprocess.Popen(
        [str(BIN / "aftermath-worker")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        import select

        ready, _, _ = select.select([process.stdout], [], [], 15)
        assert ready, "Worker failed to start within 15 seconds"
        assert "Worker ready" in process.stdout.readline()
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, err
        assert "stopped cleanly" in out
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
