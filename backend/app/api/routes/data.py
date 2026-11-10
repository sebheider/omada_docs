"""Read access to the technical documentation: dashboard, objects, ACL analysis, topology, search, quality."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.api.common import all_relationships, check_kind, manual_map, resolve_site
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.system import ChangeLog, SyncHistory, User
from app.services import scheduler, sync
from app.services.acl_analysis import analyze
from app.services.dataset import KINDS, load_dataset, load_entities, load_entity
from app.services.manual import description_dict, get_description, relationships_for
from app.services.quality import quality_report
from app.services.related import related
from app.services.search import search as search_service
from app.services.settings_store import load_controller_settings
from app.services.topology import build_topology

router = APIRouter(tags=["data"], dependencies=[Depends(get_current_user)])

SITE_SCOPED = tuple(k for k in KINDS if k not in ("controller", "site"))


@router.get("/sites")
def list_sites(db: Session = Depends(get_db)) -> dict:
    sites = load_entities(db, "site")
    m = manual_map(db)
    for s in sites:
        s["manual"] = m.get(("site", s["key"]))
    return {"items": sites, "default": resolve_site(db, None)}


@router.get("/dashboard")
def dashboard(site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    site_id = resolve_site(db, site_id)
    ds = load_dataset(db, site_id)
    devices = ds.get("device", [])
    clients = ds.get("client", [])
    acl = analyze(ds, site_id) if site_id else {"rules": []}
    since = datetime.now(timezone.utc) - timedelta(days=7)
    change_q = select(func.count(ChangeLog.id)).where(ChangeLog.ts >= since)
    recent = db.scalars(select(ChangeLog).order_by(ChangeLog.id.desc()).limit(8)).all()
    quality = quality_report(db, site_id)
    cs = load_controller_settings(db)
    by_type: dict[str, dict[str, int]] = {}
    for d in devices:
        t = by_type.setdefault(d.get("type") or "other", {"total": 0, "online": 0})
        t["total"] += 1
        t["online"] += 1 if d.get("status") == "online" else 0
    return {
        "site_id": site_id,
        "controller": (ds.get("controller") or [None])[0],
        "configured": cs.configured or get_settings().demo_mode,
        "demo_mode": get_settings().demo_mode,
        "version": __version__,
        "sync": {**sync.sync_status(db), "next_run": scheduler.next_run(), "interval": cs.sync_interval},
        "counts": {k: len(ds.get(k, [])) for k in SITE_SCOPED},
        "devices_by_type": by_type,
        "devices_offline": [{"key": d["key"], "name": d.get("name"), "type": d.get("type")}
                            for d in devices if d.get("status") not in ("online", None)],
        "clients": {"total": len(clients), "wireless": sum(1 for c in clients if c.get("wireless")),
                    "wired": sum(1 for c in clients if not c.get("wireless"))},
        "acl": {"total": len(acl["rules"]),
                "low_confidence": sum(1 for r in acl["rules"] if r.get("confidence") != "high"),
                "shadowed": sum(1 for r in acl["rules"] if r.get("shadowed_by"))},
        "changes_7d": {"config": db.scalar(change_q.where(ChangeLog.kind == "config")) or 0,
                       "manual": db.scalar(change_q.where(ChangeLog.kind == "manual")) or 0},
        "recent_changes": [_change_dict(c) for c in recent],
        "quality": {"total": sum(quality["summary"].values()), "sections": quality["summary"]},
        "syncs_total": db.scalar(select(func.count(SyncHistory.id))),
    }


def _change_dict(c: ChangeLog) -> dict:
    return {"id": c.id, "ts": c.ts, "kind": c.kind, "sync_id": c.sync_id, "site_id": c.site_id,
            "object_type": c.object_type, "object_key": c.object_key, "object_name": c.object_name,
            "change_type": c.change_type, "field": c.field, "before": c.before, "after": c.after,
            "username": c.username}


@router.get("/entities/{kind}")
def list_entities(kind: str, site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    check_kind(kind)
    if kind not in ("controller", "site"):
        site_id = resolve_site(db, site_id)
    items = load_entities(db, kind, site_id if kind not in ("controller", "site") else None)
    m = manual_map(db)
    for e in items:
        e["manual"] = m.get((kind, str(e.get("key"))))
    return {"kind": kind, "site_id": site_id, "items": items}


@router.get("/entities/{kind}/{key:path}")
def get_entity(kind: str, key: str, site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    check_kind(kind)
    entity = load_entity(db, kind, key, site_id)
    if entity is None:
        raise HTTPException(404, "Object not found")
    sid = entity.get("site_id") if kind not in ("controller", "site") else (key if kind == "site" else None)
    out = {"kind": kind, "entity": entity, "manual": description_dict(get_description(db, kind, key)),
           "relationships": relationships_for(db, kind, key), "related": {}, "analysis": None}
    if sid:
        ds = load_dataset(db, sid)
        out["related"] = related(ds, kind, entity)
        if kind == "acl_rule":
            out["analysis"] = next((r for r in analyze(ds, sid)["rules"] if r["key"] == key), None)
    out["changes"] = [_change_dict(c) for c in db.scalars(
        select(ChangeLog).where(ChangeLog.object_type == kind, ChangeLog.object_key == key)
        .order_by(ChangeLog.id.desc()).limit(100)).all()]
    return out


@router.get("/acl")
def acl(site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    site_id = resolve_site(db, site_id)
    if not site_id:
        return {"site_id": None, "rules": [], "matrix": {"segments": [], "cells": []},
                "graph": {"nodes": [], "edges": []}, "ip_groups": []}
    ds = load_dataset(db, site_id)
    result = analyze(ds, site_id)
    info = {r["key"]: r for r in result["rules"]}
    m = manual_map(db)
    rules = [{**r, "manual": m.get(("acl_rule", r["key"])), "analysis": info.get(r["key"])}
             for r in sorted(ds.get("acl_rule", []), key=lambda r: (r.get("acl_type") or "", r.get("index") or 0))]
    return {"site_id": site_id, "rules": rules, "matrix": result["matrix"], "graph": result["graph"],
            "ip_groups": ds.get("ip_group", [])}


@router.get("/topology")
def topology(site_id: str | None = None, clients: Literal["none", "important", "all"] = "important",
             db: Session = Depends(get_db)) -> dict:
    site_id = resolve_site(db, site_id)
    ds = load_dataset(db, site_id)
    return {"site_id": site_id, **build_topology(ds, site_id, manual_map(db), all_relationships(db), clients)}


@router.get("/search")
def search(q: str = Query("", max_length=200), site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    return search_service(db, q, site_id)


@router.get("/quality")
def quality(site_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    return quality_report(db, resolve_site(db, site_id))


@router.get("/dataset/export")
def export_dataset(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Response:
    """Download the normalised technical dataset (re-importable via backup import)."""
    now = datetime.now(timezone.utc)
    body = {"format": "omada-docs-dataset", "format_version": 1, "app_version": __version__,
            "exported_at": now.isoformat(), "entities": load_dataset(db)}
    return Response(json.dumps(body, indent=1, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="omada-dataset-{now:%Y%m%d-%H%M%S}.json"'})
