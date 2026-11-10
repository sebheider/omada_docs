"""Network overview graph.

Edges are only created from positive evidence:
* ``api``    – uplink reported by the controller (device uplinkDeviceMac / client switch port / AP)
* ``lldp``   – LLDP neighbour information on a switch port
* ``manual`` – a manual "connected_to" relationship
* ``derived``– logical relations computed from configuration (e.g. VLAN ↔ SSID, gateway ↔ WAN)

Devices without such evidence are listed as unresolved – connections are never guessed.
"""

from __future__ import annotations

from typing import Any

ROLE_CATEGORIES = {
    "server": ("server", "nas", "synology", "qnap", "proxmox", "esxi", "unraid", "truenas", "iobroker",
               "home assistant", "pi-hole", "pihole", "web server"),
    "camera": ("camera", "cam ", "reolink", "hikvision", "dahua", "axis", "doorbell"),
    "iot": ("shelly", "tasmota", "sonoff", "thermostat", "tado", "hue", "plug", "sensor", "vacuum", "roborock",
            "esp", "iot"),
}


def client_role(c: dict[str, Any], manual: dict[str, Any] | None = None) -> str | None:
    """Rough role classification used only for icons/grouping (marked as derived)."""
    text = " ".join(str(x or "") for x in (c.get("name"), c.get("vendor"), c.get("hostname"), c.get("network_name"),
                                           (manual or {}).get("display_name"),
                                           " ".join((manual or {}).get("tags") or []))).lower()
    for role, needles in ROLE_CATEGORIES.items():
        if any(n in text for n in needles):
            return role
    return None


def build_topology(dataset: dict[str, list[dict[str, Any]]], site_id: str | None,
                   manual: dict[tuple[str, str], dict[str, Any]], relationships: list[dict[str, Any]],
                   include_clients: str = "important") -> dict[str, Any]:
    """Return {nodes, edges, unresolved, notes}.

    include_clients: ``none`` | ``important`` (wired clients and documented/classified clients) | ``all``.
    """

    def items(kind: str) -> list[dict[str, Any]]:
        return [e for e in dataset.get(kind, []) if site_id is None or e.get("site_id") == site_id]

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    notes: list[str] = []

    def add_node(nid: str, ntype: str, label: str, **data: Any) -> None:
        nodes.setdefault(nid, {"id": nid, "type": ntype, "label": label, "data": data})

    def add_edge(src: str, dst: str, source: str, label: str | None = None, **data: Any) -> None:
        if src in nodes and dst in nodes:
            eid = f"{src}->{dst}:{source}"
            if not any(e["id"] == eid for e in edges):
                edges.append({"id": eid, "source": src, "target": dst, "evidence": source, "label": label,
                              "data": data})

    devices = items("device")
    by_mac = {d["mac"]: d for d in devices if d.get("mac")}
    wans = items("wan")
    gateways = [d for d in devices if d.get("type") == "gateway"]

    if wans or gateways:
        add_node("internet", "internet", "Internet", wans=[{"name": w.get("name"), "status": w.get("status"),
                                                            "type": w.get("type"), "isp": w.get("isp")} for w in wans])
    for d in devices:
        m = manual.get(("device", d["mac"])) or {}
        add_node(f"device:{d['mac']}", d.get("type") or "device", m.get("display_name") or d.get("name") or d["mac"],
                 mac=d["mac"], model=d.get("model"), ip=d.get("ip"), status=d.get("status"),
                 location=m.get("location"), key=d["mac"])

    for g in gateways:
        if wans:
            up = [w for w in wans if w.get("status") == "connected"]
            add_edge("internet", f"device:{g['mac']}", "derived",
                     ", ".join(w.get("name") or "WAN" for w in (up or wans)),
                     note="WAN ports configured on the gateway")

    for d in devices:
        if d.get("type") == "gateway":
            continue
        up = d.get("uplink_device_mac")
        if up and up in by_mac:
            add_edge(f"device:{up}", f"device:{d['mac']}", "api",
                     f"Port {d['uplink_port']}" if d.get("uplink_port") else None,
                     speed=d.get("uplink_speed"), port=d.get("uplink_port"))
        elif up:
            unresolved.append({"object_type": "device", "object_key": d["mac"], "name": d.get("name"),
                               "reason": f"Uplink device {up} is not part of the collected data"})
        else:
            unresolved.append({"object_type": "device", "object_key": d["mac"], "name": d.get("name"),
                               "reason": "The controller does not report an uplink for this device"})

    # LLDP neighbours on switch ports that point to known devices (adds evidence, avoids duplicates)
    for p in items("switch_port"):
        lldp = p.get("lldp") or {}
        chassis = (lldp.get("chassis_id") or "").upper().replace(":", "-")
        if chassis in by_mac and chassis != p.get("switch_mac"):
            a, b = f"device:{chassis}", f"device:{p['switch_mac']}"
            if not any({e["source"], e["target"]} == {a, b} for e in edges):
                add_edge(a, b, "lldp", f"Port {p.get('port')}", port=p.get("port"))

    clients = items("client")
    if include_clients != "none":
        for c in clients:
            m = manual.get(("client", c["mac"])) or {}
            role = client_role(c, m)
            wired = c.get("connection_type") == "wired"
            if include_clients == "important" and not (wired or role or m):
                continue
            add_node(f"client:{c['mac']}", "client", m.get("display_name") or c.get("name") or c["mac"],
                     mac=c["mac"], ip=c.get("ip"), role=role, role_source="derived" if role else None,
                     network=c.get("network_name"), vlan_id=c.get("vlan_id"), wireless=not wired,
                     ssid=c.get("ssid"), key=c["mac"])
            parent = c.get("connected_device_mac")
            if parent and parent in by_mac:
                label = f"Port {c['port']}" if wired and c.get("port") is not None else (c.get("ssid") or None)
                add_edge(f"device:{parent}", f"client:{c['mac']}", "api", label, wireless=not wired)

    # manual connections
    for r in relationships:
        if r.get("relation") != "connected_to":
            continue
        def nid(t: str, k: str) -> str | None:
            if t in ("device", "client"):
                return f"{t}:{k}"
            if t == "location":
                add_node(f"location:{k}", "location", k)
                return f"location:{k}"
            return None
        a, b = nid(r["source_type"], r["source_key"]), nid(r["target_type"], r["target_key"])
        if a and b and a in nodes and b in nodes:
            add_edge(a, b, "manual", r.get("description"), relationship_id=r["id"])

    # logical VLAN segmentation
    networks = items("network")
    segmentation = []
    for n in networks:
        m = manual.get(("network", n["key"])) or {}
        segmentation.append({
            "id": n["key"], "name": m.get("display_name") or n.get("name"), "vlan_id": n.get("vlan_id"),
            "subnet": n.get("subnet"), "gateway": n.get("gateway"),
            "guest": any(w.get("guest") and w.get("network_id") == n["key"] for w in items("wlan")),
            "ssids": [w.get("ssid") for w in items("wlan") if w.get("network_id") == n["key"]],
            "client_count": sum(1 for c in clients if c.get("network_id") == n["key"]),
            "description": m.get("description"),
        })

    if unresolved:
        notes.append("Some devices have no reported uplink. Their physical connection is unknown and is therefore "
                     "not drawn.")
    notes.append("Lines show logical connections reported by the controller (uplinks, client attachment points). "
                 "The physical cabling may differ, e.g. when unmanaged switches are in between.")
    return {"nodes": list(nodes.values()), "edges": edges, "unresolved": unresolved, "notes": notes,
            "segmentation": segmentation}
