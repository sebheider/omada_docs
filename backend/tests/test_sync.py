"""Change detection, synchronisation, partial failures and preservation of manual documentation."""

from __future__ import annotations

from sqlalchemy import select

from app.models.system import ChangeLog, SyncHistory, User
from app.omada.client import OmadaClient
from app.omada.mock import DemoController
from app.services import manual as manual_service
from app.services import sync as sync_service
from app.services.changes import diff_datasets
from app.services.dataset import load_dataset, load_entities

from .conftest import run


def test_diff_detects_added_removed_modified_and_ignores_volatile():
    before = {"device": [{"key": "a", "site_id": "s", "name": "A", "ip": "10.0.0.1", "uptime_seconds": 1},
                         {"key": "b", "site_id": "s", "name": "B"}],
              "client": [{"key": "c1", "site_id": "s", "name": "Phone"}]}
    after = {"device": [{"key": "a", "site_id": "s", "name": "A", "ip": "10.0.0.2", "uptime_seconds": 999},
                        {"key": "n", "site_id": "s", "name": "New"}],
             "client": []}
    changes = {(c["object_key"], c["change_type"], c["field"]): c for c in diff_datasets(before, after)}
    assert set(changes) == {("a", "modified", "ip"), ("b", "removed", None), ("n", "added", None)}
    assert changes[("a", "modified", "ip")]["before"] == "10.0.0.1"
    assert diff_datasets(None, after) == [], "the first import must not produce change entries"
    assert any(c["object_type"] == "client" for c in diff_datasets(before, after, include_untracked=True))


def test_sync_stores_data_and_tracks_changes(db):
    first = run(sync_service.run_sync("manual"))
    h1 = db.get(SyncHistory, first)
    assert h1.status == "success" and h1.total_objects > 0 and h1.snapshot_id
    assert not db.scalars(select(ChangeLog).where(ChangeLog.sync_id == first)).all()

    second = run(sync_service.run_sync("manual"))
    db.expire_all()
    h2 = db.get(SyncHistory, second)
    assert h2.status == "success"
    logged = db.scalars(select(ChangeLog).where(ChangeLog.sync_id == second)).all()
    assert logged and h2.new_objects + h2.changed_objects + h2.removed_objects > 0
    assert all(c.object_type != "client" for c in logged)


def test_manual_description_survives_sync(db):
    run(sync_service.run_sync("manual"))
    device = load_entities(db, "device")[0]
    user = User(username="t", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    manual_service.upsert_description(db, user, "device", device["key"], {"description": "Core switch in rack"})
    db.commit()
    run(sync_service.run_sync("manual"))
    db.expire_all()
    assert manual_service.get_description(db, "device", device["key"]).description == "Core switch in rack"


def test_partial_failure_keeps_previous_data(db, monkeypatch):
    run(sync_service.run_sync("manual"))
    networks_before = {n["key"] for n in load_dataset(db)["network"]}

    def failing_client(cs):
        demo = DemoController(fail_paths=("/lan-networks",))
        return OmadaClient("https://demo.omada.local", "demo", "demo", transport=demo.transport(),
                           max_requests_per_second=1000, max_retries=0)

    monkeypatch.setattr(sync_service, "build_client", failing_client)
    hid = run(sync_service.run_sync("manual"))
    db.expire_all()
    h = db.get(SyncHistory, hid)
    assert h.status == "partial" and "lan" in (h.error or "")
    assert h.details["carried_forward"] > 0
    networks = load_entities(db, "network")
    assert {n["key"] for n in networks} == networks_before
    assert all(n["_meta"]["validation_status"] == "stale" for n in networks)
    removed = db.scalars(select(ChangeLog).where(ChangeLog.sync_id == hid, ChangeLog.object_type == "network",
                                                 ChangeLog.change_type == "removed")).all()
    assert not removed, "a failed endpoint must not be reported as deleted objects"


def test_bad_credentials_fail_without_touching_data(db, monkeypatch):
    run(sync_service.run_sync("manual"))
    count = len(load_dataset(db)["device"])

    def bad_client(cs):
        demo = DemoController()
        return OmadaClient("https://demo.omada.local", "wrong", "wrong", transport=demo.transport(),
                           max_requests_per_second=1000)

    monkeypatch.setattr(sync_service, "build_client", bad_client)
    hid = run(sync_service.run_sync("manual"))
    db.expire_all()
    h = db.get(SyncHistory, hid)
    assert h.status == "failed" and "Authentication" in h.error
    assert "wrong" not in h.error
    assert len(load_dataset(db)["device"]) == count
