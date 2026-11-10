"""Change detection between two normalised configuration datasets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Kinds that represent runtime state rather than configuration are not tracked.
UNTRACKED_KINDS = {"client"}

# Fields that change constantly (runtime state) and are ignored for change tracking.
VOLATILE_FIELDS: dict[str, set[str]] = {
    "*": {"collected_at", "source", "validation_status"},
    "controller": {"uptime_seconds", "status"},
    "site": {"device_count", "client_count"},
    "device": {"uptime_seconds", "status", "client_count", "cpu_percent", "memory_percent", "last_seen"},
    "switch_port": {"link_status", "speed", "duplex", "poe.active", "poe.power_w", "connected",
                    "learned_macs", "lldp", "rx_bytes", "tx_bytes", "errors", "link_role", "poe.pd_class",
                    "warning"},
    "wlan": {"client_count"},
    "wan": {"status", "ipv4.address", "ipv4.gateway", "ipv6.address", "uptime_seconds"},
    "vpn": {"status"},
}


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("_"):
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = value
    return out


def _is_volatile(kind: str, field: str) -> bool:
    fields = VOLATILE_FIELDS.get(kind, set()) | VOLATILE_FIELDS["*"]
    return any(field == f or field.startswith(f + ".") for f in fields)


def tracked_view(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in flatten(obj).items() if not _is_volatile(kind, k)}


def config_checksum(entities: dict[str, list[dict[str, Any]]]) -> str:
    view = {
        kind: sorted(json.dumps(tracked_view(kind, o), sort_keys=True, default=str) for o in items)
        for kind, items in sorted(entities.items())
        if kind not in UNTRACKED_KINDS
    }
    return hashlib.sha256(json.dumps(view, sort_keys=True).encode()).hexdigest()


def _fmt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, sort_keys=True, default=str)
    return str(v)


def _index(items: list[dict[str, Any]]) -> dict[tuple[str | None, str], dict[str, Any]]:
    return {(o.get("site_id"), str(o["key"])): o for o in items}


def diff_datasets(
    before: dict[str, list[dict[str, Any]]] | None,
    after: dict[str, list[dict[str, Any]]],
    include_untracked: bool = False,
) -> list[dict[str, Any]]:
    """Return a list of change dicts (object_type, object_key, change_type, field, before, after)."""
    changes: list[dict[str, Any]] = []
    if before is None:
        return changes
    kinds = sorted(set(before) | set(after))
    for kind in kinds:
        if kind in UNTRACKED_KINDS and not include_untracked:
            continue
        old = _index(before.get(kind, []))
        new = _index(after.get(kind, []))
        for ident in sorted(new.keys() - old.keys(), key=str):
            obj = new[ident]
            changes.append(_change(kind, ident, obj, "added", None, None, _summary(obj)))
        for ident in sorted(old.keys() - new.keys(), key=str):
            obj = old[ident]
            changes.append(_change(kind, ident, obj, "removed", None, _summary(obj), None))
        for ident in sorted(old.keys() & new.keys(), key=str):
            a, b = tracked_view(kind, old[ident]), tracked_view(kind, new[ident])
            for fld in sorted(a.keys() | b.keys()):
                if a.get(fld) != b.get(fld):
                    changes.append(
                        _change(kind, ident, new[ident], "modified", fld, _fmt(a.get(fld)), _fmt(b.get(fld)))
                    )
    return changes


def _summary(obj: dict[str, Any]) -> str:
    parts = [str(obj.get(k)) for k in ("name", "ip", "mac", "vlan_id", "subnet") if obj.get(k) not in (None, "")]
    return ", ".join(dict.fromkeys(parts))


def _change(kind, ident, obj, change_type, fld, before, after) -> dict[str, Any]:
    return {
        "object_type": kind,
        "site_id": ident[0],
        "object_key": ident[1],
        "object_name": obj.get("name"),
        "change_type": change_type,
        "field": fld,
        "before": before,
        "after": after,
    }
