"""Shared test fixtures: isolated data directory, migrated database, API client and demo data."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("OMADA_DOCS_DATA_DIR", "/tmp/omada-docs-tests-unused")
os.environ["OMADA_DOCS_DEMO_MODE"] = "true"
os.environ["OMADA_DOCS_ALLOWED_NETWORKS"] = "127.0.0.0/8"
os.environ["OMADA_DOCS_SECRET_KEY"] = "test-secret-key-for-encryption-only"

from app.core import config, crypto  # noqa: E402
from app.db import session as db_session  # noqa: E402

ADMIN = {"username": "admin", "password": "admin-password-1"}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch) -> Iterator[None]:
    """Every test gets its own data directory and a freshly migrated SQLite database."""
    monkeypatch.setenv("OMADA_DOCS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    crypto.master_secret.cache_clear()
    crypto._fernet.cache_clear()
    get = config.get_settings()
    get.ensure_dirs()
    db_session.init_engine()
    from app.db.migrate import upgrade_to_head

    upgrade_to_head()
    yield
    db_session.get_engine().dispose()
    config.get_settings.cache_clear()


@pytest.fixture
def db():
    with db_session.SessionLocal() as s:
        yield s


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def synced() -> int:
    """Run one demo synchronisation and return its history id."""
    from app.services.sync import run_sync

    return run(run_sync("manual"))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver", client=("127.0.0.1", 50000)) as c:
        _wait_for_sync(c)
        yield c


def _wait_for_sync(c) -> None:
    """Demo mode starts an initial synchronisation on startup; wait until it has finished."""
    import time

    from sqlalchemy import func, select

    from app.models.system import SyncHistory

    for _ in range(200):
        with db_session.SessionLocal() as s:
            finished = s.scalar(select(func.count()).select_from(SyncHistory)
                                .where(SyncHistory.status != "running"))
        if finished and not c.get("/api/health").json().get("sync_running"):
            return
        time.sleep(0.05)
    raise AssertionError("initial demo synchronisation did not finish")


@pytest.fixture
def admin(client) -> dict[str, str]:
    """Create the first administrator; returns headers with the CSRF token."""
    r = client.post("/api/auth/setup", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}
