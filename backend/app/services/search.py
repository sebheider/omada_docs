"""Global search over technical and manual data.

A denormalised ``search_entries`` table is rebuilt after every synchronisation and manual edit.
Matching uses case-insensitive substring search, which works well for IP/MAC prefixes and
comfortably handles several thousand objects in SQLite. IP address queries additionally return
the containing networks and ACL rules / NAT rules that affect the address.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.manual import ManualDescription, ManualDocument
from app.models.system import SearchEntry
from app.services.dataset import load_dataset

CATEGORY = {
    "device": "devices", "client": "clients", "network": "networks", "wlan": "wlans",
    "switch_port": "switch_ports", "acl_rule": "acl_rules", "nat_rule": "nat_rules", "route": "routes",
    "vpn": "vpns", "ip_group": "ip_groups", "port_profile": "port_profiles", "wan": "wans", "site": "sites",
    "document": "documentation",
}

CATEGORY_ORDER = ["devices", "clients", "networks", "wlans", "switch_ports", "acl_rules", "nat_rules",
                  "ip_groups", "port_profiles", "routes", "vpns", "wans", "sites", "documentation"]


def _vals(*values: Any) -> list[str]:
    out: list[str] = []
    for v in values:
        if v is None or v == "":
            continue
        if isinstance(v, (list, tuple, set)):
            out.extend(_vals(*v))
        elif isinstance(v, dict):
            out.extend(_vals(*v.values()))
        else:
            out.append(str(v))
    return out


def _side_names(side: dict | None) -> list[str]:
    side = side or {}
    return [r.get("name") or r.get("id") for r in side.get("refs") or []] + list(side.get("ports") or [])


def _entry_for(kind: str, e: dict[str, Any]) -> tuple[str, str | None, list[str]]:
    """Return (title, subtitle, searchable values) for an entity."""
    name = e.get("name") or e.get("key")
    if kind == "device":
        return name, f"{e.get('type')} · {e.get('model')} · {e.get('ip')}", _vals(
            e.get("name"), e.get("mac"), e.get("ip"), e.get("ipv6"), e.get("model"), e.get("model_name"),
            e.get("serial"), e.get("firmware"), e.get("type"))
    if kind == "client":
        return name, f"{e.get('ip') or '-'} · {e.get('network_name') or '-'} · {e.get('connected_device_name') or ''}", \
            _vals(e.get("name"), e.get("hostname"), e.get("mac"), e.get("ip"), e.get("ipv6"), e.get("vendor"),
                  e.get("network_name"), e.get("ssid"), f"vlan {e.get('vlan_id')}" if e.get("vlan_id") else None)
    if kind == "network":
        return name, f"VLAN {e.get('vlan_id')} · {e.get('subnet') or '-'}", _vals(
            e.get("name"), f"vlan {e.get('vlan_id')}", e.get("vlan_id"), e.get("subnet"), e.get("gateway"),
            e.get("domain"), (e.get("dhcp") or {}).get("dns_servers"),
            [(r.get("ip"), r.get("mac"), r.get("name")) for r in (e.get("dhcp") or {}).get("reservations") or []])
    if kind == "wlan":
        return e.get("ssid") or name, f"VLAN {e.get('vlan_id') or '-'} · {e.get('security')}", _vals(
            e.get("ssid"), e.get("wlan_group"), e.get("network_name"), f"vlan {e.get('vlan_id')}",
            e.get("bands"), e.get("security"))
    if kind == "switch_port":
        connected = e.get("connected") or []
        return f"{e.get('switch_name')} · Port {e.get('port')}", \
            f"{e.get('profile_name') or '-'} · {', '.join(c.get('name') or c.get('mac') or '' for c in connected)}", \
            _vals(e.get("switch_name"), f"port {e.get('port')}", e.get("name"), e.get("profile_name"),
                  e.get("native_network"), e.get("tagged_networks"),
                  [(c.get("name"), c.get("mac"), c.get("ip")) for c in connected], e.get("lldp"))
    if kind == "acl_rule":
        src, dst = _side_names(e.get("source")), _side_names(e.get("destination"))
        return name, f"{e.get('acl_type')} #{e.get('index')} · {e.get('action')} · {', '.join(src)} → {', '.join(dst)}", \
            _vals(e.get("name"), e.get("description"), e.get("action"), e.get("protocols"), src, dst, e.get("acl_type"))
    if kind == "nat_rule":
        return name, f"{e.get('external_port') or e.get('external_ip') or ''} → {e.get('internal_ip')}:{e.get('internal_port') or ''}", \
            _vals(e.get("name"), e.get("internal_ip"), e.get("internal_port"), e.get("external_port"),
                  e.get("external_ip"), e.get("protocol"))
    if kind == "ip_group":
        return name, ", ".join(x.get("ip") for x in e.get("entries") or [] if x.get("ip"))[:200], _vals(
            e.get("name"), [x.get("ip") for x in e.get("entries") or []], e.get("ports"), e.get("macs"),
            e.get("domains"), e.get("description"))
    if kind == "route":
        return name, f"{', '.join(e.get('destinations') or [])} via {e.get('next_hop') or e.get('interface') or '-'}", \
            _vals(e.get("name"), e.get("destinations"), e.get("next_hop"), e.get("interface"))
    if kind == "vpn":
        return name, e.get("type"), _vals(e.get("name"), e.get("type"), e.get("remote_ip"), e.get("remote_subnets"),
                                          e.get("local_networks"))
    if kind == "wan":
        return name, f"{e.get('type') or '-'} · {(e.get('ipv4') or {}).get('address') or '-'}", _vals(
            e.get("name"), e.get("description"), e.get("isp"), (e.get("ipv4") or {}).get("address"))
    if kind == "port_profile":
        return name, f"Native: {e.get('native_network') or '-'}", _vals(
            e.get("name"), e.get("native_network"), e.get("tagged_networks"), e.get("untagged_networks"))
    if kind == "site":
        return name, e.get("region"), _vals(e.get("name"), e.get("region"), e.get("scenario"))
    return name, None, _vals(e.get("name"))


def rebuild(db: Session) -> int:
    db.execute(delete(SearchEntry))
    manual = {(m.object_type, m.object_key): m for m in db.scalars(select(ManualDescription)).all()}
    dataset = load_dataset(db)
    count = 0
    for kind, items in dataset.items():
        if kind == "controller":
            continue
        for e in items:
            title, subtitle, values = _entry_for(kind, e)
            m = manual.get((kind, str(e.get("key"))))
            if m:
                values += _vals(m.display_name, m.description, m.location, m.responsible, m.notes, m.tags)
                if m.display_name:
                    title = f"{m.display_name} ({title})"
            db.add(SearchEntry(category=CATEGORY.get(kind, kind), object_type=kind, object_key=str(e.get("key")),
                               site_id=e.get("site_id"), title=str(title or "")[:255],
                               subtitle=(str(subtitle)[:512] if subtitle else None),
                               text="\n".join(values).lower()))
            count += 1
    for doc in db.scalars(select(ManualDocument)).all():
        db.add(SearchEntry(category="documentation", object_type="document", object_key=str(doc.id), site_id=None,
                           title=doc.title[:255], subtitle=doc.category,
                           text="\n".join(_vals(doc.title, doc.body, doc.category, doc.tags)).lower()))
        count += 1
    # Manual descriptions for objects that currently do not exist in the controller data remain searchable.
    existing = {(k, str(e.get("key"))) for k, items in dataset.items() for e in items}
    for (otype, okey), m in manual.items():
        if (otype, okey) not in existing:
            db.add(SearchEntry(category=CATEGORY.get(otype, "documentation"), object_type=otype, object_key=okey,
                               site_id=m.site_id, title=(m.display_name or okey)[:255],
                               subtitle="Manual description (object not present in current data)",
                               text="\n".join(_vals(m.display_name, okey, m.description, m.location, m.responsible,
                                                    m.notes, m.tags)).lower()))
            count += 1
    db.flush()
    return count


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ip_related(db: Session, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, site_id: str | None) -> list[dict]:
    """Networks containing the IP, IP groups containing it, and ACL / NAT rules that reference them."""
    ds = load_dataset(db, site_id, ("network", "ip_group", "acl_rule", "nat_rule"))
    results: list[dict] = []
    net_ids, group_ids = set(), set()

    def contains(cidr: str | None) -> bool:
        try:
            return bool(cidr) and ip in ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return False

    for n in ds["network"]:
        if contains(n.get("subnet")):
            net_ids.add(n["key"])
            results.append(_hit("network", n, f"VLAN {n.get('vlan_id')} · {n.get('subnet')}",
                                f"{ip} is inside this network"))
    for g in ds["ip_group"]:
        if any(contains(x.get("ip")) for x in g.get("entries") or []):
            group_ids.add(g["key"])
            results.append(_hit("ip_group", g, None, f"{ip} is a member of this group"))
    for r in ds["acl_rule"]:
        refs = {x.get("id") for side in ("source", "destination") for x in (r.get(side) or {}).get("refs") or []}
        if refs & (net_ids | group_ids):
            results.append(_hit("acl_rule", r, f"{r.get('acl_type')} #{r.get('index')} · {r.get('action')}",
                                "Rule references a network or group containing this address"))
    for n in ds["nat_rule"]:
        if n.get("internal_ip") == str(ip):
            results.append(_hit("nat_rule", n, None, "Forwards traffic to this address"))
    return results


def _hit(kind: str, e: dict, subtitle: str | None, reason: str | None = None) -> dict:
    return {"category": CATEGORY.get(kind, kind), "object_type": kind, "object_key": str(e.get("key")),
            "site_id": e.get("site_id"), "title": e.get("name") or e.get("key"), "subtitle": subtitle,
            "reason": reason}


def search(db: Session, query: str, site_id: str | None = None, limit: int = 300) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if len(q) < 1:
        return {"query": query, "total": 0, "groups": []}
    terms = [t for t in q.split() if t][:8]
    stmt = select(SearchEntry)
    for term in terms:
        stmt = stmt.where(SearchEntry.text.like(f"%{_escape_like(term)}%", escape="\\"))
    if site_id:
        stmt = stmt.where(or_(SearchEntry.site_id == site_id, SearchEntry.site_id.is_(None)))
    rows = db.scalars(stmt.limit(limit)).all()
    hits = [{"category": r.category, "object_type": r.object_type, "object_key": r.object_key, "site_id": r.site_id,
             "title": r.title, "subtitle": r.subtitle, "reason": None} for r in rows]

    try:
        ip = ipaddress.ip_address(q)
    except ValueError:
        ip = None
    if ip is not None:
        seen = {(h["object_type"], h["object_key"]) for h in hits}
        for h in _ip_related(db, ip, site_id):
            if (h["object_type"], h["object_key"]) not in seen:
                hits.append(h)
                seen.add((h["object_type"], h["object_key"]))

    def rank(h: dict) -> tuple:
        title = (h["title"] or "").lower()
        return (0 if title == q else 1 if title.startswith(q) else 2, title)

    groups: dict[str, list[dict]] = {}
    for h in sorted(hits, key=rank):
        groups.setdefault(h["category"], []).append(h)
    ordered = [{"category": c, "items": groups[c]} for c in CATEGORY_ORDER if c in groups]
    ordered += [{"category": c, "items": items} for c, items in groups.items() if c not in CATEGORY_ORDER]
    return {"query": query, "total": len(hits), "groups": ordered}
