"""Collects everything needed for a documentation export into one structure."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.models.manual import ManualDescription, ManualDocument, ManualRelationship
from app.models.system import ChangeLog, ConfigSnapshot, SyncHistory
from app.services.acl_analysis import analyze
from app.services.dataset import load_dataset
from app.services.topology import build_topology

CHAPTERS = {
    "overview": "Network overview",
    "vlans": "VLAN documentation",
    "devices": "Device overview",
    "ports": "Switch port documentation",
    "wlans": "WLAN documentation",
    "acl": "ACL rules",
    "matrix": "ACL communication matrix",
    "nat": "NAT rules",
    "clients": "Clients",
    "manual": "Manual documentation",
    "changes": "Change overview",
}
DEFAULT_CHAPTERS = [c for c in CHAPTERS if c != "clients"]


def _anon_mac(mac: str | None) -> str | None:
    if not mac:
        return mac
    parts = mac.split("-")
    return "-".join(parts[:3] + ["XX"] * (len(parts) - 3)) if len(parts) == 6 else "XX"


def _anon_ip(ip: str | None) -> str | None:
    if not ip or "." not in ip:
        return ip
    return ".".join(ip.split(".")[:3] + ["x"])


def build_report(db: Session, site_id: str | None, chapters: list[str] | None = None,
                 anonymize_clients: bool = True, change_days: int = 90) -> dict[str, Any]:
    chapters = [c for c in (chapters or DEFAULT_CHAPTERS) if c in CHAPTERS]
    ds = load_dataset(db, site_id)
    sites = ds.get("site", [])
    if site_id is None and sites:
        site_id = sites[0]["key"]
        ds = load_dataset(db, site_id)
    site = next((s for s in ds.get("site", []) if s["key"] == site_id), None)

    descs = {(m.object_type, m.object_key): m for m in db.scalars(select(ManualDescription)).all()}

    def manual(kind: str, key: str) -> dict[str, Any]:
        m = descs.get((kind, str(key)))
        if not m:
            return {}
        return {"display_name": m.display_name, "description": m.description, "location": m.location,
                "responsible": m.responsible, "notes": m.notes, "tags": m.tags or []}

    for kind, items in ds.items():
        for e in items:
            e["manual"] = manual(kind, e.get("key"))

    clients = ds.get("client", [])
    if anonymize_clients:
        for c in clients:
            if not c["manual"]:
                c["name"] = c.get("vendor") and f"{c['vendor']} device" or "Client"
            c["mac"] = _anon_mac(c.get("mac"))
            c["ip"] = _anon_ip(c.get("ip"))
            c["hostname"] = None
        for p in ds.get("switch_port", []):
            for conn in p.get("connected") or []:
                if conn.get("type") == "client":
                    conn["mac"] = _anon_mac(conn.get("mac"))

    rels = [{"id": r.id, "relation": r.relation, "source_type": r.source_type, "source_key": r.source_key,
             "target_type": r.target_type, "target_key": r.target_key, "description": r.description}
            for r in db.scalars(select(ManualRelationship)).all()]
    topo = build_topology(ds, site_id, {k: manual(*k) for k in descs}, rels, include_clients="none")
    analysis = analyze(ds, site_id) if site_id else {"rules": [], "matrix": {"segments": [], "cells": []},
                                                     "graph": {"nodes": [], "edges": []}}
    rule_info = {r["key"]: r for r in analysis["rules"]}
    acl_rules = []
    for r in sorted(ds.get("acl_rule", []), key=lambda r: (r.get("acl_type") or "", r.get("index") or 0)):
        acl_rules.append({**r, "analysis": rule_info.get(r["key"], {})})

    snapshot = db.scalars(select(ConfigSnapshot).where(ConfigSnapshot.source != "backup")
                          .order_by(ConfigSnapshot.id.desc()).limit(1)).first()
    last_sync = db.scalars(select(SyncHistory).where(SyncHistory.status.in_(("success", "partial")))
                           .order_by(SyncHistory.id.desc()).limit(1)).first()
    changes = []
    if "changes" in chapters:
        since = datetime.now(timezone.utc).timestamp() - change_days * 86400
        rows = db.scalars(select(ChangeLog).order_by(ChangeLog.id.desc()).limit(1000)).all()
        changes = [{"ts": c.ts, "kind": c.kind, "object_type": c.object_type, "object_name": c.object_name or c.object_key,
                    "change_type": c.change_type, "field": c.field, "before": c.before, "after": c.after,
                    "username": c.username}
                   for c in rows if c.ts.timestamp() >= since and (c.site_id in (None, site_id))]

    docs = []
    if "manual" in chapters:
        for d in db.scalars(select(ManualDocument).order_by(ManualDocument.category, ManualDocument.title)).all():
            docs.append({"id": d.id, "title": d.title, "category": d.category, "tags": d.tags or [], "body": d.body,
                         "created_at": d.created_at, "updated_at": d.updated_at, "updated_by": d.updated_by})

    switches = [d for d in ds.get("device", []) if d.get("type") == "switch"]
    ports_by_switch = {s["mac"]: sorted([p for p in ds.get("switch_port", []) if p.get("switch_mac") == s["mac"]],
                                        key=lambda p: p.get("port") or 0) for s in switches}
    controller = (ds.get("controller") or [{}])[0]
    return {
        "title": f"Network documentation – {(site or {}).get('name') or 'Omada'}",
        "generated_at": datetime.now(timezone.utc),
        "app_version": __version__,
        "chapters": chapters,
        "chapter_titles": {c: CHAPTERS[c] for c in chapters},
        "site": site,
        "site_manual": manual("site", site_id) if site_id else {},
        "controller": controller,
        "snapshot": {"id": snapshot.id, "created_at": snapshot.created_at, "checksum": snapshot.checksum[:12],
                     "source": snapshot.source} if snapshot else None,
        "last_sync": {"id": last_sync.id, "finished_at": last_sync.finished_at,
                      "status": last_sync.status} if last_sync else None,
        "anonymized": anonymize_clients,
        "devices": sorted(ds.get("device", []), key=lambda d: ({"gateway": 0, "switch": 1, "ap": 2}.get(d.get("type"), 3),
                                                              d.get("name") or "")),
        "networks": sorted(ds.get("network", []), key=lambda n: n.get("vlan_id") or 0),
        "wlans": ds.get("wlan", []),
        "wans": ds.get("wan", []),
        "switches": switches,
        "ports_by_switch": ports_by_switch,
        "acl_rules": acl_rules,
        "matrix": analysis["matrix"],
        "nat_rules": ds.get("nat_rule", []),
        "routes": ds.get("route", []),
        "vpns": ds.get("vpn", []),
        "ip_groups": ds.get("ip_group", []),
        "clients": sorted(clients, key=lambda c: (c.get("network_name") or "", c.get("name") or "")),
        "topology": topo,
        "documents": docs,
        "changes": changes,
        "change_days": change_days,
    }
