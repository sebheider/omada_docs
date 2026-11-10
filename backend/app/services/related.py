"""Cross-references between technical objects for detail pages ("what belongs to this object?")."""

from __future__ import annotations

import ipaddress
from typing import Any

from app.services.acl_analysis import analyze


def _ref(kind: str, e: dict[str, Any], detail: str | None = None) -> dict[str, Any]:
    return {"object_type": kind, "object_key": str(e.get("key")), "name": e.get("name") or e.get("key"),
            "detail": detail}


def _acl_refs(rule: dict[str, Any]) -> set[str]:
    return {str(x.get("id")) for side in ("source", "destination") for x in (rule.get(side) or {}).get("refs") or []}


def _in_subnet(ip: str | None, cidr: str | None) -> bool:
    try:
        return bool(ip and cidr) and ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def _groups_containing(ds: dict[str, list[dict]], ip: str | None) -> list[dict]:
    return [g for g in ds.get("ip_group", [])
            if any(_in_subnet(ip, x.get("ip")) for x in g.get("entries") or [])]


def related(ds: dict[str, list[dict[str, Any]]], kind: str, entity: dict[str, Any]) -> dict[str, list[dict]]:
    """Return related objects grouped by label. ``ds`` must be the dataset of the entity's site."""
    out: dict[str, list[dict]] = {}
    key = str(entity.get("key"))

    def add(label: str, items: list[dict]) -> None:
        if items:
            out[label] = items

    acls = ds.get("acl_rule", [])
    if kind == "network":
        name, vlan = entity.get("name"), entity.get("vlan_id")
        add("gateways", [_ref("device", d, d.get("model")) for d in ds.get("device", []) if d.get("type") == "gateway"])
        add("wlans", [_ref("wlan", w, f"VLAN {w.get('vlan_id')}") for w in ds.get("wlan", [])
                      if w.get("network_id") == key or (w.get("vlan_enabled") and vlan and w.get("vlan_id") == vlan)])
        ports = []
        for p in ds.get("switch_port", []):
            if p.get("native_network_id") == key:
                ports.append(_ref("switch_port", p, f"{p.get('switch_name')} port {p.get('port')} · untagged"))
            elif name and name in (p.get("tagged_networks") or []):
                ports.append(_ref("switch_port", p, f"{p.get('switch_name')} port {p.get('port')} · tagged"))
        add("switch_ports", ports)
        add("acl_rules", [_ref("acl_rule", r, f"{r.get('acl_type')} #{r.get('index')} · {r.get('action')}")
                          for r in acls if key in _acl_refs(r)])
        add("nat_rules", [_ref("nat_rule", n, f"→ {n.get('internal_ip')}:{n.get('internal_port')}")
                          for n in ds.get("nat_rule", []) if _in_subnet(n.get("internal_ip"), entity.get("subnet"))])
        add("clients", [_ref("client", c, c.get("ip")) for c in ds.get("client", []) if c.get("network_id") == key])
        add("routes", [_ref("route", r, ", ".join(r.get("destinations") or [])) for r in ds.get("route", [])
                       if _in_subnet(r.get("next_hop"), entity.get("subnet"))])
        add("vpns", [_ref("vpn", v, v.get("type")) for v in ds.get("vpn", []) if name in (v.get("local_networks") or [])])
    elif kind == "device":
        mac = entity.get("mac")
        devices = {d.get("mac"): d for d in ds.get("device", [])}
        if entity.get("uplink_device_mac") in devices:
            add("uplink", [_ref("device", devices[entity["uplink_device_mac"]], f"port {entity.get('uplink_port')}")])
        add("downstream_devices", [_ref("device", d, f"port {d.get('uplink_port')}") for d in devices.values()
                                   if d.get("uplink_device_mac") == mac])
        add("switch_ports", [_ref("switch_port", p, f"{p.get('link_status')} · {p.get('profile_name') or ''}")
                             for p in ds.get("switch_port", []) if p.get("switch_mac") == mac])
        add("clients", [_ref("client", c, c.get("ip")) for c in ds.get("client", [])
                        if c.get("connected_device_mac") == mac])
        if entity.get("type") == "ap":
            add("wlans", [_ref("wlan", w, w.get("ap_assignment")) for w in ds.get("wlan", []) if w.get("enabled")])
        if entity.get("type") == "gateway":
            add("wans", [_ref("wan", w, w.get("status")) for w in ds.get("wan", [])])
    elif kind == "switch_port":
        devices = {d.get("mac"): d for d in ds.get("device", [])}
        if entity.get("switch_mac") in devices:
            add("switch", [_ref("device", devices[entity["switch_mac"]])])
        nets = {n.get("name"): n for n in ds.get("network", [])}
        native = [n for n in ds.get("network", []) if n.get("key") == entity.get("native_network_id")]
        add("networks", [_ref("network", n, "untagged") for n in native]
            + [_ref("network", nets[t], "tagged") for t in entity.get("tagged_networks") or [] if t in nets])
        add("connected", [_ref("client" if c.get("type") == "client" else "device",
                               {"key": c.get("mac"), "name": c.get("name")}, c.get("source"))
                          for c in entity.get("connected") or [] if c.get("mac")])
        add("port_profile", [_ref("port_profile", p) for p in ds.get("port_profile", [])
                             if p.get("key") == entity.get("profile_id")])
    elif kind == "wlan":
        add("networks", [_ref("network", n, f"VLAN {n.get('vlan_id')}") for n in ds.get("network", [])
                         if n.get("key") == entity.get("network_id")])
        add("clients", [_ref("client", c, c.get("ip")) for c in ds.get("client", [])
                        if c.get("ssid") and c.get("ssid") == entity.get("ssid")])
        add("acl_rules", [_ref("acl_rule", r, f"#{r.get('index')} · {r.get('action')}") for r in acls
                          if r.get("acl_type") == "eap" and key in _acl_refs(r)])
    elif kind == "client":
        ip = entity.get("ip")
        nets = [n for n in ds.get("network", []) if n.get("key") == entity.get("network_id")
                or _in_subnet(ip, n.get("subnet"))]
        add("networks", [_ref("network", n, n.get("subnet")) for n in nets])
        add("connected_to", [_ref("device", d, f"port {entity.get('port')}" if entity.get("port") else entity.get("ssid"))
                             for d in ds.get("device", []) if d.get("mac") == entity.get("connected_device_mac")])
        groups = _groups_containing(ds, ip)
        add("ip_groups", [_ref("ip_group", g) for g in groups])
        ids = {n["key"] for n in nets} | {g["key"] for g in groups}
        add("acl_rules", [_ref("acl_rule", r, f"{r.get('acl_type')} #{r.get('index')} · {r.get('action')}")
                          for r in acls if ids & _acl_refs(r)])
        add("nat_rules", [_ref("nat_rule", n, f"{n.get('protocol')} {n.get('external_port')}")
                          for n in ds.get("nat_rule", []) if ip and n.get("internal_ip") == ip])
    elif kind == "acl_rule":
        by_key = {(k, str(e.get("key"))): (k, e) for k in ("network", "ip_group", "wlan") for e in ds.get(k, [])}
        refs = []
        for side in ("source", "destination"):
            for x in (entity.get(side) or {}).get("refs") or []:
                for k in ("network", "ip_group", "wlan"):
                    if (k, str(x.get("id"))) in by_key:
                        refs.append(_ref(k, by_key[(k, str(x.get("id")))][1], side))
                        break
        add("referenced_objects", refs)
    elif kind == "ip_group":
        add("acl_rules", [_ref("acl_rule", r, f"{r.get('acl_type')} #{r.get('index')} · {r.get('action')}")
                          for r in acls if key in _acl_refs(r)])
    elif kind == "nat_rule":
        ip = entity.get("internal_ip")
        add("target_clients", [_ref("client", c, c.get("ip")) for c in ds.get("client", []) if ip and c.get("ip") == ip])
        add("networks", [_ref("network", n, n.get("subnet")) for n in ds.get("network", [])
                         if _in_subnet(ip, n.get("subnet"))])
    elif kind == "port_profile":
        add("switch_ports", [_ref("switch_port", p, f"{p.get('switch_name')} port {p.get('port')}")
                             for p in ds.get("switch_port", []) if p.get("profile_id") == key])
    return out


def acl_rule_analysis(ds: dict[str, list[dict[str, Any]]], site_id: str, key: str) -> dict[str, Any] | None:
    return next((r for r in analyze(ds, site_id)["rules"] if r["key"] == key), None)
