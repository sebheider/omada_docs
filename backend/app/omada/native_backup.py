"""Best-effort mapping of decrypted native Omada controller backups to the collector structure.

A decrypted ``.cfg`` contains the controller's internal "SDN backup" JSON (``mainInfo``,
``systemSetting``, ``sites``, ``deviceBriefInfo``, ...). This format is undocumented and may change
between controller versions, so the mapping is heuristic and defensive:

* Lists of objects are classified by the name of the section they are stored under.
* Objects are read with the Open API field names (the controller uses largely the same names
  internally) and handed to the regular :func:`app.omada.parsers.normalize`.
* Objects that do not carry the minimum fields for their type are skipped and counted.
* Everything that is not recognised is reported as an unsupported area.

The input is untrusted. Secrets are removed by name (:func:`sanitize`), individually encrypted
``v2#`` values are discarded, and as a final safeguard every secret value found in the backup is
redacted from the mapped result should it appear anywhere (e.g. under an unexpected field name).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.omada.parsers import DEVICE_TYPES, is_secret_key, norm_mac, sanitize

ENCRYPTED_PREFIX = "v2#"
REDACTED = "[redacted]"
KNOWN_TOP = {"mainInfo", "systemSetting", "sites", "deviceBriefInfo"}
IGNORED_TOP = {"__omada_encrypted_fields__"}
MAX_WALK_DEPTH = 4
MIN_SECRET_LEN = 6

# (target section, name fragments, excluded fragments) – first match wins on the normalised key name.
SECTION_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("dhcp_reservations", ("dhcpreservation", "staticlease", "dhcpstatic", "ipreservation", "fixedip"), ()),
    ("one_to_one_nat", ("onetoone",), ()),
    ("port_forwardings", ("portforward", "virtualserver"), ()),
    ("gateway_acls", ("gatewayacl", "osgacl", "firewallacl"), ()),
    ("switch_acls", ("switchacl",), ()),
    ("eap_acls", ("eapacl",), ()),
    ("site_to_site_vpns", ("sitetositevpn", "sitevpn"), ()),
    ("vpns", ("vpn",), ("user", "account")),
    ("static_routes", ("staticrout", "route"), ("policy",)),
    ("lan_profiles", ("lanprofile", "portprofile", "switchprofile"), ()),
    ("groups", ("ipgroup", "profilegroup", "profilesgroup", "groupprofile"), ()),
    ("ssids", ("ssid",), ()),
    ("wlans", ("wlangroup", "wlan"), ()),
    ("lan_networks", ("lannetwork", "network"), ("wan", "vpn")),
    ("devices", ("device",), ("account", "group", "tag")),
]

_SITE_INFO_KEYS = ("site", "siteInfo", "basicInfo", "siteBasicInfo", "siteEntity")
_ID_KEYS = ("id", "_id", "siteId", "key")
# Object ids / UUIDs stored under fields such as "key" are identifiers, not secrets.
_IDENTIFIER_RE = re.compile(r"[0-9a-fA-F]{24}|[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def classify(name: str) -> str | None:
    low = _norm_name(name)
    for target, fragments, excluded in SECTION_RULES:
        if any(f in low for f in fragments) and not any(x in low for x in excluded):
            return target
    return None


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _unwrap(value: Any) -> Any:
    """Convert MongoDB extended JSON (``{"$oid": ..}``, ``{"$numberLong": ..}``) to plain values."""
    if isinstance(value, dict):
        if len(value) == 1:
            (k, v), = value.items()
            if k in ("$oid", "$date", "$numberDecimal"):
                return v
            if k in ("$numberLong", "$numberInt"):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return v
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _strip_encrypted(value: Any, counter: list[int]) -> Any:
    if isinstance(value, dict):
        return {k: _strip_encrypted(v, counter) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_encrypted(v, counter) for v in value]
    if isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
        counter[0] += 1
        return None
    return value


def collect_secrets(value: Any, out: set[str] | None = None, under_secret: bool = False) -> set[str]:
    """All string values stored under secret-like keys (used to verify nothing leaks into the result)."""
    out = out if out is not None else set()
    if isinstance(value, dict):
        for k, v in value.items():
            collect_secrets(v, out, under_secret or is_secret_key(str(k)))
    elif isinstance(value, list):
        for v in value:
            collect_secrets(v, out, under_secret)
    elif (under_secret and isinstance(value, str) and len(value) >= MIN_SECRET_LEN
          and not _IDENTIFIER_RE.fullmatch(value)):
        out.add(value)
    return out


def redact(value: Any, secrets: set[str], counter: list[int]) -> Any:
    if isinstance(value, dict):
        return {k: redact(v, secrets, counter) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets, counter) for v in value]
    if isinstance(value, str) and value in secrets:
        counter[0] += 1
        return REDACTED
    return value


def is_native_document(data: Any) -> bool:
    return isinstance(data, dict) and "format" not in data and bool({"mainInfo", "systemSetting"} & data.keys())


# ----------------------------------------------------------------------------- per-object normalisation

def _with_id(item: dict) -> dict:
    out = dict(item)
    if out.get("id") in (None, ""):
        out["id"] = _first(item, "_id", "key", "uuid")
    if out.get("id") is not None:
        out["id"] = str(out["id"])
    return out


def _infer_device_type(dev: dict) -> str | None:
    t = dev.get("type")
    if isinstance(t, str) and t.lower() in DEVICE_TYPES:
        return t.lower()
    model = str(_first(dev, "model", "modelName", "showModel") or "").upper()
    model = model.removeprefix("TL-")
    if model.startswith("EAP"):
        return "ap"
    if model.startswith(("SG", "SX", "SL", "ES")):
        return "switch"
    if model.startswith(("ER", "FR", "DR", "G")):
        return "gateway"
    return None


def _prepare(section: str, item: dict) -> dict | None:
    """Return the object in Open API shape, or ``None`` if it lacks the minimum fields for its type."""
    d = _with_id(item)
    if section == "devices":
        if d.get("mac") is None:
            d["mac"] = _first(item, "macAddress", "deviceMac")
        mac = norm_mac(d.get("mac"))
        if not mac or not re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", mac):
            return None
        d["type"] = _infer_device_type(d)
        if d.get("name") in (None, ""):
            d["name"] = _first(item, "deviceName", "alias")
        if d.get("firmwareVersion") is None:
            d["firmwareVersion"] = _first(item, "firmware", "fwVersion", "version")
        d["status"] = d["status"] if isinstance(d.get("status"), int) else None
        return d
    if section == "lan_networks":
        if d.get("name") in (None, "") or d.get("id") is None:
            return None
        if not d.get("gatewaySubnet") and d.get("ip") and (d.get("mask") or d.get("netmask")):
            d["gatewaySubnet"] = f"{d['ip']}/{d.get('mask') or d.get('netmask')}"
        if d.get("dhcpSettingsVO") is None and isinstance(d.get("dhcpSettings"), dict):
            d["dhcpSettingsVO"] = d["dhcpSettings"]
        if d.get("vlan") is None and d.get("gatewaySubnet") is None:
            return None
        return d
    if section in ("ssids", "wlans"):
        if d.get("name") in (None, ""):
            d["name"] = _first(item, "ssid", "ssidName", "wlanName")
        return d if d.get("name") and d.get("id") is not None else None
    if section == "groups":
        d["groupId"] = d.get("groupId") or d.get("id")
        return d if d.get("name") and d["groupId"] and (d.get("ipList") or d.get("ipv6List") or
                                                        d.get("portList") is not None) else None
    if section in ("gateway_acls", "switch_acls", "eap_acls"):
        return d if d.get("id") is not None and d.get("policy") in (0, 1) else None
    if section == "port_forwardings":
        return d if d.get("id") is not None and (d.get("externalPort") or d.get("forwardIp")) else None
    if section == "one_to_one_nat":
        return d if d.get("id") is not None and (d.get("externalIp") or d.get("internalIp")) else None
    if section == "static_routes":
        return d if d.get("id") is not None and d.get("destinations") else None
    if section in ("vpns", "site_to_site_vpns", "lan_profiles"):
        return d if d.get("id") is not None and d.get("name") else None
    if section == "dhcp_reservations":
        return d if d.get("mac") and d.get("ip") and d.get("netId") else None
    return None


# ----------------------------------------------------------------------------- document walk

def _site_entries(sites: Any) -> list[tuple[str | None, dict]]:
    if isinstance(sites, list):
        return [(None, s) for s in sites if isinstance(s, dict)]
    if isinstance(sites, dict):
        if any(k in sites for k in ("name", "siteName", *_SITE_INFO_KEYS)):
            return [(None, sites)]
        return [(str(k), v) for k, v in sites.items() if isinstance(v, dict)]
    return []


def _site_info(entry: dict) -> dict:
    for k in _SITE_INFO_KEYS:
        v = entry.get(k)
        if isinstance(v, dict) and _first(v, "name", "siteName"):
            return v
    return entry


def _walk(value: Any, path: list[str], depth: int, found: list[tuple[str, list[str], list]]) -> None:
    """Collect ``(section, path, items)`` for every list of objects below ``value``."""
    if depth > MAX_WALK_DEPTH or not isinstance(value, dict):
        return
    for k, v in value.items():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            found.append((classify(k) or "", [*path, k], v))
        elif isinstance(v, dict):
            section = classify(k)
            # Objects keyed by id (``{"<id>": {...}, ...}``) are treated like a list.
            if section and v and all(isinstance(x, dict) for x in v.values()) and not _first(v, "name", "id"):
                found.append((section, [*path, k], [{"id": key, **x} for key, x in v.items()]))
            else:
                _walk(v, [*path, k], depth + 1, found)


def _site_ref_matches(dev: dict, site_id: str, site_name: str | None) -> bool:
    ref = _first(dev, "siteId", "site", "siteKey", "siteName")
    return ref is not None and str(ref) in (site_id, site_name)


def _version_from(*dicts: dict, keys: tuple[str, ...]) -> str | None:
    for d in dicts:
        v = _first(d, *keys)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return None


def _timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value) if isinstance(value, str) and value else None


def convert(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a decrypted native backup to the collector structure.

    Returns ``(raw, meta)``; ``raw`` is sanitised and can be passed to ``normalize``. ``meta`` contains
    ``controller_version``, ``backup_version``, ``collected_at``, ``warnings``, ``unsupported``,
    ``secrets`` (values to redact) and ``stats``.
    """
    secrets = collect_secrets(doc)
    encrypted = [0]
    data = _strip_encrypted(_unwrap(sanitize(doc)), encrypted)
    warnings: list[str] = [
        "Native Omada backups use an undocumented internal format. The mapping is best effort – verify the "
        "imported data against the Open API data."]
    unsupported: list[dict[str, str]] = []
    main = data.get("mainInfo") if isinstance(data.get("mainInfo"), dict) else {}
    system = data.get("systemSetting") if isinstance(data.get("systemSetting"), dict) else {}

    controller_version = _version_from(main, system, keys=(
        "controllerVersion", "controllerVer", "omadacVersion", "softwareVersion", "version"))
    backup_version = _version_from(main, keys=("backupVersion", "backupFileVersion", "fileVersion", "dbVersion"))
    collected_at = _timestamp(_first(main, "backupTime", "createTime", "time", "timestamp"))
    controller_info = {"controllerVer": controller_version, "omadacId": _first(main, "omadacId", "controllerId")}
    controller_status = {"name": _first(main, "controllerName", "name") or _first(system, "controllerName")}

    for key in sorted(set(data) - KNOWN_TOP - IGNORED_TOP):
        unsupported.append({"area": key, "reason": "Not interpreted by this application (native backup section)"})

    stats: dict[str, int] = {}
    skipped: dict[str, int] = {}
    sites: list[dict[str, Any]] = []
    for i, (dict_key, entry) in enumerate(_site_entries(data.get("sites"))):
        info = _site_info(entry)
        site_id = str(_first(info, *_ID_KEYS) or dict_key or f"backup-site-{i + 1}")
        name = str(_first(info, "name", "siteName") or site_id)
        site: dict[str, Any] = {
            "site": {"siteId": site_id, "name": name, "region": _first(info, "region", "country"),
                     "timeZone": _first(info, "timeZone", "timezone"), "scenario": info.get("scenario"),
                     "address": info.get("address"), "type": info.get("type") if info.get("type") in (0, 1) else None}}
        found: list[tuple[str, list[str], list]] = []
        _walk(entry, [], 0, found)
        used_top: set[str] = set()
        ssid_items: list[dict] = []
        wlan_items: list[dict] = []
        for section, path, items in found:
            if not section:
                continue
            for item in items:
                prepared = _prepare(section, item)
                if prepared is None:
                    skipped[section] = skipped.get(section, 0) + 1
                    continue
                used_top.add(path[0])
                if section == "wlans":
                    nested = _first(item, "ssids", "ssidList")
                    if isinstance(nested, list):
                        for s in nested:
                            if isinstance(s, dict) and (p := _prepare("ssids", s)):
                                ssid_items.append({**p, "_wlan": prepared["id"]})
                    wlan_items.append(prepared)
                elif section == "ssids":
                    ssid_items.append(prepared)
                else:
                    site.setdefault(section, []).append(prepared)
        site_level = {k for k in entry if k not in _SITE_INFO_KEYS}
        for key in sorted(site_level - used_top):
            if isinstance(entry.get(key), (dict, list)):
                unsupported.append({"area": f"sites[{name}].{key}", "reason": "Not interpreted by this application"})
        site["wlan_groups"] = _wlan_groups(wlan_items, ssid_items)
        sites.append(site)

    if not sites:
        warnings.append("No sites were found in the backup.")

    unassigned = _assign_brief_devices(data.get("deviceBriefInfo"), sites, skipped)
    if unassigned:
        warnings.append(f"{unassigned} device(s) from 'deviceBriefInfo' could not be assigned to a site and were "
                        "skipped.")
    for site in sites:
        for section, items in site.items():
            if isinstance(items, list):
                stats[section] = stats.get(section, 0) + len(items)
        stats["ssids"] = stats.get("ssids", 0) + sum(len(g["ssids"]) for g in site["wlan_groups"])
        stats.pop("wlan_groups", None)
    if skipped:
        warnings.append("Objects without the required fields were skipped: "
                        + ", ".join(f"{k}: {v}" for k, v in sorted(skipped.items())))
    if encrypted[0]:
        warnings.append(f"{encrypted[0]} individually encrypted value(s) ('v2#') were discarded.")
    if not controller_version:
        warnings.append("The controller version could not be detected.")
    raw = {"controller_info": controller_info, "controller_status": controller_status, "sites": sites,
           "collected_at": collected_at}
    return raw, {"controller_version": controller_version, "backup_version": backup_version,
                 "collected_at": collected_at, "warnings": warnings, "unsupported": unsupported,
                 "secrets": secrets, "stats": stats}


def _wlan_groups(wlans: list[dict], ssids: list[dict]) -> list[dict]:
    groups = {w["id"]: {"group": {"id": w["id"], "name": w.get("name")}, "ssids": []} for w in wlans}
    loose: list[dict] = []
    seen: set[str] = set()
    for s in ssids:
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        ref = s.pop("_wlan", None) or _first(s, "wlanId", "wlanGroupId", "wlan")
        entry = {"summary": s, "detail": s}
        if ref is not None and str(ref) in groups:
            groups[str(ref)]["ssids"].append(entry)
        else:
            loose.append(entry)
    out = [g for g in groups.values() if g["ssids"]]
    if loose:
        out.append({"group": {}, "ssids": loose})
    return out


def _assign_brief_devices(brief: Any, sites: list[dict], skipped: dict[str, int]) -> int:
    if isinstance(brief, dict):
        brief = next((v for v in brief.values() if isinstance(v, list)), list(brief.values()))
    if not isinstance(brief, list):
        return 0
    unassigned = 0
    for item in brief:
        if not isinstance(item, dict):
            continue
        dev = _prepare("devices", item)
        if dev is None:
            skipped["devices"] = skipped.get("devices", 0) + 1
            continue
        target = next((s for s in sites if _site_ref_matches(item, s["site"]["siteId"], s["site"]["name"])), None)
        if target is None and len(sites) == 1:
            target = sites[0]
        if target is None:
            unassigned += 1
            continue
        devices = target.setdefault("devices", [])
        mac = norm_mac(dev["mac"])
        existing = next((d for d in devices if norm_mac(d.get("mac")) == mac), None)
        if existing is None:
            devices.append(dev)
        else:
            for k, v in dev.items():
                if existing.get(k) in (None, ""):
                    existing[k] = v
    return unassigned
