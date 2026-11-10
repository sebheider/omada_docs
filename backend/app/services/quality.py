"""Data quality overview: gaps, unresolved references, stale data and source conflicts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.manual import ManualDescription, ManualRelationship
from app.models.system import BackupImport, SyncHistory
from app.services.acl_analysis import analyze
from app.services.dataset import load_dataset, row_index
from app.services.topology import build_topology


def _item(object_type: str, key: str, name: Any, detail: str, site_id: str | None = None) -> dict[str, Any]:
    return {"object_type": object_type, "object_key": key, "name": name, "detail": detail, "site_id": site_id}


def quality_report(db: Session, site_id: str | None = None) -> dict[str, Any]:
    ds = load_dataset(db, site_id)
    manual = {(m.object_type, m.object_key): m for m in db.scalars(select(ManualDescription)).all()}
    rels = db.scalars(select(ManualRelationship)).all()

    sections: dict[str, list[dict[str, Any]]] = {k: [] for k in (
        "unassigned_devices", "unknown_port_connections", "vlans_without_description", "unreliable_acl_rules",
        "devices_without_location", "unresolved_connections", "source_conflicts", "stale_data",
        "unsupported_endpoints")}

    # Unassigned / unplaced devices and clients
    topo = build_topology(ds, site_id, {k: {"display_name": v.display_name, "location": v.location,
                                            "tags": v.tags} for k, v in manual.items()},
                          [{"id": r.id, "relation": r.relation, "source_type": r.source_type,
                            "source_key": r.source_key, "target_type": r.target_type, "target_key": r.target_key}
                           for r in rels], include_clients="none")
    manual_connected = {(r.source_type, r.source_key) for r in rels if r.relation == "connected_to"} | {
        (r.target_type, r.target_key) for r in rels if r.relation == "connected_to"}
    for u in topo["unresolved"]:
        if (u["object_type"], u["object_key"]) not in manual_connected:
            sections["unassigned_devices"].append(_item(u["object_type"], u["object_key"], u["name"], u["reason"]))
    for c in ds.get("client", []):
        if not c.get("network_id") and c.get("vlan_id") is None:
            sections["unassigned_devices"].append(_item("client", c["key"], c.get("name"),
                                                        "Client is not assigned to a known network", c.get("site_id")))

    # Switch ports with a link but no identified peer
    for p in ds.get("switch_port", []):
        if p.get("link_status") == "up" and not p.get("connected") and not p.get("lldp") \
                and ("switch_port", p["key"]) not in manual:
            sections["unknown_port_connections"].append(_item(
                "switch_port", p["key"], f"{p.get('switch_name')} port {p.get('port')}",
                "Link is up but the connected device is unknown (no client, uplink or LLDP data)", p.get("site_id")))

    for n in ds.get("network", []):
        m = manual.get(("network", n["key"]))
        if not m or not (m.description or "").strip():
            sections["vlans_without_description"].append(_item(
                "network", n["key"], n.get("name"), f"VLAN {n.get('vlan_id')} has no manual description",
                n.get("site_id")))

    sites = [s["key"] for s in ds.get("site", [])] if site_id is None else [site_id]
    for sid in sites:
        analysis = analyze(ds, sid)
        for r in analysis["rules"]:
            if r["confidence"] != "high":
                sections["unreliable_acl_rules"].append(_item(
                    "acl_rule", r["key"], r.get("name") or r["technical"],
                    "; ".join(r.get("confidence_reasons") or []) or "Interpretation is not fully reliable", sid))

    for d in ds.get("device", []):
        m = manual.get(("device", d["key"]))
        if not m or not (m.location or "").strip():
            sections["devices_without_location"].append(_item("device", d["key"], d.get("name"),
                                                               "No location documented", d.get("site_id")))

    # Unresolved references
    existing = {(k, str(e.get("key"))) for k, items in ds.items() for e in items}
    for r in ds.get("acl_rule", []):
        for side in ("source", "destination"):
            for ref in (r.get(side) or {}).get("refs") or []:
                if not ref.get("resolved"):
                    sections["unresolved_connections"].append(_item(
                        "acl_rule", r["key"], r.get("name"), f"{side.title()} reference '{ref.get('id')}' could not "
                        "be resolved to a known network or group", r.get("site_id")))
    for w in ds.get("wlan", []):
        if w.get("vlan_enabled") and not w.get("network_id"):
            sections["unresolved_connections"].append(_item(
                "wlan", w["key"], w.get("ssid"), f"SSID uses VLAN {w.get('vlan_id')} which does not map to exactly "
                "one known network", w.get("site_id")))
    for rel in rels:
        for t, k in ((rel.source_type, rel.source_key), (rel.target_type, rel.target_key)):
            if t in ("location", "connection", "document"):
                continue
            if (t, k) not in existing:
                sections["unresolved_connections"].append(_item(
                    "relationship", str(rel.id), f"{rel.source_type}:{rel.source_key} → {rel.target_type}:"
                    f"{rel.target_key}", f"Manual relationship references {t} '{k}' which is not present in the "
                    "current data"))
    for (t, k), m in manual.items():
        if t not in ("location", "connection") and (t, k) not in existing:
            sections["unresolved_connections"].append(_item(
                t, k, m.display_name or k, "Manual description refers to an object that is not present in the current "
                "data (it is kept and will reappear when the object returns)", m.site_id))

    # Conflicts between latest backup import and current API data
    latest_import = db.scalars(select(BackupImport).where(BackupImport.status == "imported")
                               .order_by(BackupImport.id.desc()).limit(1)).first()
    if latest_import and latest_import.summary:
        for c in (latest_import.summary.get("comparison") or {}).get("conflicts", [])[:500]:
            sections["source_conflicts"].append(_item(
                c["object_type"], c["object_key"], c.get("object_name"),
                f"{c['field']}: API = {c.get('api_value')!r} ({c.get('api_collected_at')}) vs backup = "
                f"{c.get('backup_value')!r} ({latest_import.imported_at:%Y-%m-%d %H:%M})", c.get("site_id")))

    for (kind, sid, key), row in row_index(db).items():
        if row.validation_status == "stale" and (site_id is None or sid == site_id):
            sections["stale_data"].append(_item(kind, key, row.name, f"Last collected {row.collected_at:%Y-%m-%d %H:%M} "
                                                "– the latest synchronisation could not refresh it", sid))

    last = db.scalars(select(SyncHistory).where(SyncHistory.status.in_(("success", "partial")))
                      .order_by(SyncHistory.id.desc()).limit(1)).first()
    if last and last.details:
        seen = set()
        for e in last.details.get("endpoints") or []:
            if e.get("status") == "unsupported" and e["endpoint"] not in seen:
                seen.add(e["endpoint"])
                sections["unsupported_endpoints"].append(_item(
                    "endpoint", e["endpoint"], e["path"], "Not supported by this controller version – data not "
                    "available"))

    return {
        "site_id": site_id,
        "summary": {k: len(v) for k, v in sections.items()},
        "sections": sections,
    }
