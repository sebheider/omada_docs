"""Synchronisation: collect from the controller, normalise, detect changes and persist atomically.

Guarantees:
* The controller is only ever read (GET requests, plus the OAuth token request).
* A failed synchronisation never modifies stored documentation: everything is written in one
  transaction after collection succeeded.
* If individual endpoints fail, the previously stored objects of the affected kinds/sites are
  carried forward and flagged ``stale`` instead of being deleted.
* Manual documentation tables are never touched.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import redact
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.system import ChangeLog, ConfigSnapshot, SyncHistory
from app.omada.client import OmadaAuthError, OmadaClient, OmadaConnectionError, OmadaError
from app.omada.collector import Collector
from app.omada.parsers import normalize
from app.services import search as search_service
from app.services.changes import UNTRACKED_KINDS, config_checksum, diff_datasets, tracked_view
from app.services.dataset import load_dataset, replace_dataset, row_index
from app.services.settings_store import ControllerSettings, get_value, load_controller_settings, set_value

log = logging.getLogger(__name__)

#: endpoint name -> entity kinds whose data depend on it
ENDPOINT_KINDS: dict[str, tuple[str, ...]] = {
    "devices": ("device", "switch_port"),
    "clients": ("client",),
    "lan_networks": ("network",),
    "lan_profiles": ("port_profile",),
    "wlan_groups": ("wlan",),
    "ssids": ("wlan",),
    "ssid_detail": ("wlan",),
    "gateway_acls": ("acl_rule",),
    "switch_acls": ("acl_rule",),
    "eap_acls": ("acl_rule",),
    "groups": ("ip_group",),
    "port_forwardings": ("nat_rule",),
    "one_to_one_nat": ("nat_rule",),
    "static_routes": ("route",),
    "dhcp_reservations": ("network",),
    "internet": ("wan",),
    "wan_status": ("wan",),
    "vpns": ("vpn",),
    "switch_ports": ("switch_port",),
    "switch_detail": ("switch_port",),
}

DEMO_MAX_REVISION = 2

_lock = asyncio.Lock()


def is_running() -> bool:
    return _lock.locked()


class SyncError(Exception):
    pass


def build_client(cs: ControllerSettings) -> OmadaClient:
    settings = get_settings()
    if settings.demo_mode:
        from app.omada.mock import DemoController

        with SessionLocal() as db:
            revision = int(get_value(db, "demo.revision", 0))
        demo = DemoController(revision=revision)
        return OmadaClient("https://demo.omada.local", "demo", "demo", transport=demo.transport(),
                           max_requests_per_second=1000)
    if not cs.configured:
        raise SyncError("The Omada controller connection is not configured.")
    return OmadaClient(cs.base_url, cs.client_id, cs.client_secret, omadac_id=cs.omadac_id,
                       api_version=cs.api_version or "v1", verify_ssl=cs.verify_ssl, timeout=cs.request_timeout,
                       max_requests_per_second=cs.max_requests_per_second)


async def test_connection(cs: ControllerSettings) -> dict[str, Any]:
    """Check reachability and credentials without storing anything."""
    started = time.monotonic()
    try:
        async with build_client(cs) as client:
            info = await client.get_info()
            await client.authenticate()
            sites = await client.get_all("/sites")
        return {
            "ok": True, "omadac_id": info.omadac_id, "controller_version": info.controller_version,
            "api_version": info.api_version,
            "sites": [{"id": s.get("siteId"), "name": s.get("name")} for s in sites],
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except (OmadaError, SyncError) as exc:
        return {"ok": False, "error": redact(str(exc)), "error_type": type(exc).__name__,
                "duration_ms": int((time.monotonic() - started) * 1000)}


def _failed_scopes(results: list[dict[str, Any]]) -> set[tuple[str, str | None]]:
    """(kind, site_id) pairs whose fresh data is incomplete because an endpoint errored."""
    failed: set[tuple[str, str | None]] = set()
    for r in results:
        if r.get("status") == "error":
            for kind in ENDPOINT_KINDS.get(r["endpoint"], ()):
                failed.add((kind, r.get("site_id")))
    return failed


def _merge(fresh: dict[str, list[dict]], db: Session, failed: set[tuple[str, str | None]],
           source: str, collected_at: datetime) -> tuple[dict[str, list[dict]], int]:
    """Attach metadata: keep ``updated_at`` of unchanged objects, carry forward data of failed scopes."""
    previous = row_index(db)
    carried = 0
    merged: dict[str, list[dict]] = {}
    for kind, items in fresh.items():
        out = []
        for ent in items:
            if (kind, ent.get("site_id")) in failed:
                continue
            prev = previous.get((kind, ent.get("site_id"), str(ent["key"])))
            meta: dict[str, Any] = {"source": source, "collected_at_dt": collected_at}
            if prev is not None and tracked_view(kind, prev.data or {}) == tracked_view(kind, ent):
                meta["updated_at_dt"] = prev.updated_at
            ent["_meta"] = meta
            out.append(ent)
        merged[kind] = out
    for (kind, site_id, _key), row in previous.items():
        if (kind, site_id) in failed:
            data = dict(row.data or {})
            data["_meta"] = {"source": row.source, "collected_at_dt": row.collected_at,
                             "updated_at_dt": row.updated_at, "validation_status": "stale"}
            merged.setdefault(kind, []).append(data)
            carried += 1
    return merged, carried


def _strip_meta(entities: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: [{f: v for f, v in e.items() if f != "_meta"} for e in items] for k, items in entities.items()}


def save_snapshot(db: Session, entities: dict[str, list[dict]], source: str, label: str | None,
                  controller_version: str | None, force: bool = False) -> ConfigSnapshot | None:
    """Store a snapshot when the configuration checksum differs from the latest snapshot."""
    checksum = config_checksum(entities)
    latest = db.scalars(select(ConfigSnapshot).where(ConfigSnapshot.source != "backup")
                        .order_by(ConfigSnapshot.id.desc()).limit(1)).first()
    if latest is not None and latest.checksum == checksum and not force:
        return latest
    snap = ConfigSnapshot(source=source, label=label, controller_version=controller_version, checksum=checksum,
                          object_count=sum(len(v) for v in entities.values()), data=entities)
    db.add(snap)
    db.flush()
    return snap


def prune_snapshots(db: Session, keep: int) -> None:
    keep = max(int(keep or 0), 2)
    ids = db.scalars(select(ConfigSnapshot.id).where(ConfigSnapshot.source != "backup")
                     .order_by(ConfigSnapshot.id.desc()).offset(keep)).all()
    if ids:
        db.execute(delete(ConfigSnapshot).where(ConfigSnapshot.id.in_(ids)))


async def run_sync(trigger: str = "manual") -> int:
    """Run one synchronisation and return the sync_history id. Raises ``SyncError`` if one is running."""
    if _lock.locked():
        raise SyncError("A synchronisation is already running.")
    async with _lock:
        return await _run_sync(trigger)


async def _run_sync(trigger: str) -> int:
    settings = get_settings()
    source = "demo" if settings.demo_mode else "api"
    started = time.monotonic()
    with SessionLocal() as db:
        cs = load_controller_settings(db)
        history = SyncHistory(trigger=trigger, status="running")
        db.add(history)
        db.commit()
        history_id = history.id

    raw: dict[str, Any] | None = None
    error: str | None = None
    try:
        async with build_client(cs) as client:
            raw = await Collector(client, cs.site_ids or None).collect()
            if not cs.omadac_id and client.omadac_id and not settings.demo_mode:
                with SessionLocal() as db:
                    set_value(db, "controller.omadac_id", client.omadac_id)
    except OmadaAuthError as exc:
        error = f"Authentication failed: {exc}"
    except OmadaConnectionError as exc:
        error = f"Controller not reachable: {exc}"
    except (OmadaError, SyncError) as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - never let a sync crash the app
        log.exception("Unexpected synchronisation error")
        error = f"Unexpected error: {type(exc).__name__}: {exc}"

    with SessionLocal() as db:
        history = db.get(SyncHistory, history_id)
        sites_failed = raw is not None and any(
            r["endpoint"] == "sites" and r["status"] != "ok" for r in raw.get("endpoint_results", []))
        if raw is None or sites_failed:
            if sites_failed and not error:
                error = next(r.get("error") for r in raw["endpoint_results"] if r["endpoint"] == "sites")
            history.status = "failed"
            history.error = redact(error or "The controller did not return any site.")
            history.finished_at = utcnow()
            history.duration_ms = int((time.monotonic() - started) * 1000)
            history.details = {"endpoints": (raw or {}).get("endpoint_results", [])}
            db.commit()
            log.warning("Synchronisation %s failed: %s", history_id, history.error)
            return history_id
        try:
            _persist(db, history, raw, cs, source, settings.demo_mode)
            history.duration_ms = int((time.monotonic() - started) * 1000)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.exception("Persisting synchronisation %s failed", history_id)
            history = db.get(SyncHistory, history_id)
            history.status = "failed"
            history.error = redact(f"Storing collected data failed: {type(exc).__name__}: {exc}")
            history.finished_at = utcnow()
            history.duration_ms = int((time.monotonic() - started) * 1000)
            db.commit()
            return history_id

    with SessionLocal() as db:
        search_service.rebuild(db)
        db.commit()
    if settings.demo_mode:
        with SessionLocal() as db:
            rev = int(get_value(db, "demo.revision", 0))
            if rev < DEMO_MAX_REVISION:
                set_value(db, "demo.revision", rev + 1)
    return history_id


def _persist(db: Session, history: SyncHistory, raw: dict[str, Any], cs: ControllerSettings, source: str,
             demo: bool) -> None:
    collected_at = datetime.fromisoformat(raw["collected_at"]) if raw.get("collected_at") else utcnow()
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)
    results = raw.get("endpoint_results", [])
    fresh = normalize(raw, cs.host or ("demo.omada.local" if demo else None))
    failed = _failed_scopes(results)

    previous = load_dataset(db)
    had_previous = any(previous.get(k) for k in previous if k != "controller")
    merged, carried = _merge(fresh, db, failed, source, collected_at)
    clean = _strip_meta(merged)

    changes = diff_datasets(previous if had_previous else None, clean)
    total = replace_dataset(db, merged, source, collected_at)

    controller_version = (raw.get("controller_info") or {}).get("controllerVer")
    snap = save_snapshot(db, clean, source, f"Sync #{history.id}", controller_version)
    prune_snapshots(db, cs.snapshot_retention)

    for c in changes:
        db.add(ChangeLog(kind="config", sync_id=history.id, site_id=c["site_id"], object_type=c["object_type"],
                         object_key=c["object_key"], object_name=(c["object_name"] or "")[:255] or None,
                         change_type=c["change_type"], field=c["field"], before=c["before"], after=c["after"]))

    errors = [r for r in results if r.get("status") == "error"]
    unsupported = [r for r in results if r.get("status") == "unsupported"]
    history.status = "partial" if errors else "success"
    history.finished_at = utcnow()
    history.total_objects = total
    history.new_objects = sum(1 for c in changes if c["change_type"] == "added")
    history.removed_objects = sum(1 for c in changes if c["change_type"] == "removed")
    history.changed_objects = len({(c["object_type"], c["site_id"], c["object_key"]) for c in changes
                                   if c["change_type"] == "modified"})
    history.snapshot_id = snap.id if snap else None
    if errors:
        history.error = redact("; ".join(f"{e['endpoint']}: {e.get('error')}" for e in errors[:10]))
    history.details = {
        "endpoints": results,
        "request_count": raw.get("request_count"),
        "carried_forward": carried,
        "unsupported": sorted({u["endpoint"] for u in unsupported}),
        "controller_version": controller_version,
        "first_sync": not had_previous,
        "tracked_change_count": len(changes),
        "untracked_kinds": sorted(UNTRACKED_KINDS),
    }


def sync_status(db: Session) -> dict[str, Any]:
    def row(h: SyncHistory | None) -> dict[str, Any] | None:
        return history_dict(h) if h else None

    last = db.scalars(select(SyncHistory).order_by(SyncHistory.id.desc()).limit(1)).first()
    ok = db.scalars(select(SyncHistory).where(SyncHistory.status.in_(("success", "partial")))
                    .order_by(SyncHistory.id.desc()).limit(1)).first()
    failed = db.scalars(select(SyncHistory).where(SyncHistory.status == "failed")
                        .order_by(SyncHistory.id.desc()).limit(1)).first()
    return {"running": is_running(), "last": row(last), "last_success": row(ok), "last_failure": row(failed),
            "total_runs": db.scalar(select(func.count(SyncHistory.id)))}


def history_dict(h: SyncHistory, with_details: bool = False) -> dict[str, Any]:
    out = {
        "id": h.id, "started_at": h.started_at, "finished_at": h.finished_at, "status": h.status,
        "trigger": h.trigger, "duration_ms": h.duration_ms, "new_objects": h.new_objects,
        "changed_objects": h.changed_objects, "removed_objects": h.removed_objects,
        "total_objects": h.total_objects, "error": h.error, "snapshot_id": h.snapshot_id,
    }
    if with_details:
        out["details"] = h.details
    return out
