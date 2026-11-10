"""Backup import as an additional, untrusted data source.

Supported inputs (JSON only):
* ``omada-docs-raw``     – raw Open API responses in the collector structure (see docs/backup-import.md)
* ``omada-docs-dataset`` – normalised dataset export produced by this application (``GET /api/dataset/export``)
* ``api-responses``      – a JSON document with the same structure as the raw dump but without header
                           (e.g. responses collected manually with curl from the Open API)

* ``omada-native-backup`` – native Omada controller backup (``.cfg``). The file is decrypted in memory
                           (see :mod:`app.omada.cfg_crypto`) and mapped best effort
                           (see :mod:`app.omada.native_backup`). Already decrypted backups (JSON with
                           ``mainInfo``/``systemSetting``) are accepted as ``omada-native-backup-json``.
                           Neither the file nor the decrypted document is ever stored.

Imported data is validated, sanitised (secrets removed) and stored as a separate snapshot with
source ``backup``. It never overwrites API data – differences are reported as conflicts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.system import BackupImport, ConfigSnapshot, User
from app.omada import native_backup
from app.omada.cfg_crypto import CfgError, decrypt_cfg, looks_like_cfg
from app.omada.parsers import normalize, sanitize
from app.services.changes import UNTRACKED_KINDS, tracked_view
from app.services.dataset import KINDS, load_dataset, row_index
from app.services.manual import audit

MAX_DEPTH = 40
MAX_ITEMS = 200_000
MAX_STRING = 100_000
# Native backups are much larger (complete controller database incl. e.g. portal images).
NATIVE_LIMITS = {"max_depth": 64, "max_items": 5_000_000, "max_string": 16 * 1024 * 1024}

SITE_KEYS = {
    "site": dict, "devices": list, "clients": list, "lan_networks": list, "lan_profiles": list, "gateway_acls": list,
    "switch_acls": list, "eap_acls": list, "groups": list, "port_forwardings": list, "one_to_one_nat": list,
    "static_routes": list, "dhcp_reservations": list, "internet": dict, "vpns": list, "site_to_site_vpns": list,
    "switch_ports": list, "switch_poe": list, "wlan_groups": list, "wan_status": dict, "switch_detail": dict,
}
TOP_KEYS = {"format", "format_version", "collected_at", "controller_info", "controller_status", "sites",
            "endpoint_results", "request_count", "exported_at", "app_version"}


class BackupError(ValueError):
    pass


def _check_structure(value: Any, max_depth: int = MAX_DEPTH, max_items: int = MAX_ITEMS,
                     max_string: int = MAX_STRING) -> None:
    counter = [0]

    def walk(v: Any, depth: int) -> None:
        if depth > max_depth:
            raise BackupError("The JSON document is nested too deeply.")
        counter[0] += 1
        if counter[0] > max_items:
            raise BackupError("The JSON document contains too many elements.")
        if isinstance(v, dict):
            for k, x in v.items():
                if not isinstance(k, str) or len(k) > 200:
                    raise BackupError("Invalid key in JSON document.")
                walk(x, depth + 1)
        elif isinstance(v, list):
            for x in v:
                walk(x, depth + 1)
        elif isinstance(v, str) and len(v) > max_string:
            raise BackupError("A string value in the JSON document is too long.")

    walk(value, 0)


def parse_backup(filename: str, content: bytes) -> dict[str, Any]:
    """Validate and parse a backup file. Returns a result dict (never raises for invalid content)."""
    result: dict[str, Any] = {"filename": filename, "sha256": hashlib.sha256(content).hexdigest(), "status": "rejected",
                              "detected_format": None, "controller_version": None, "backup_version": None,
                              "errors": [], "warnings": [], "unsupported": [], "entities": None, "summary": {}}
    is_json = content[:16].lstrip().startswith((b"{", b"["))
    if not is_json:
        if filename.lower().endswith(".cfg") or looks_like_cfg(content):
            return _parse_native_cfg(content, result)
        result["detected_format"] = "unknown"
        result["errors"].append(
            "The file is neither a JSON document nor a native Omada controller backup (.cfg).")
        return result
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        result["errors"].append(f"Invalid JSON: {type(exc).__name__}: {exc}")
        return result
    if native_backup.is_native_document(data):
        result["detected_format"] = "omada-native-backup-json"
        return _parse_native(data, result)
    try:
        _check_structure(data)
    except BackupError as exc:
        result["errors"].append(str(exc))
        return result
    if not isinstance(data, dict):
        result["errors"].append("The top level of the JSON document must be an object.")
        return result

    fmt = data.get("format")
    if fmt == "omada-docs-dataset":
        return _parse_dataset(data, result)
    if fmt not in (None, "omada-docs-raw"):
        result["errors"].append(f"Unknown format '{fmt}'.")
        return result
    if not isinstance(data.get("sites"), list):
        result["errors"].append("No 'sites' list found – the file does not match a supported backup structure.")
        return result
    result["detected_format"] = fmt or "api-responses"
    result["backup_version"] = str(data.get("format_version")) if data.get("format_version") is not None else None
    info = data.get("controller_info") if isinstance(data.get("controller_info"), dict) else {}
    status = data.get("controller_status") if isinstance(data.get("controller_status"), dict) else {}
    result["controller_version"] = info.get("controllerVer") or status.get("controllerVersion")
    if not result["controller_version"]:
        result["warnings"].append("The controller version could not be detected.")

    for key in sorted(set(data) - TOP_KEYS):
        result["unsupported"].append({"area": key, "reason": "Unknown top-level section – ignored"})
    sites = []
    for i, s in enumerate(data["sites"]):
        if not isinstance(s, dict) or not isinstance(s.get("site"), dict) or not s["site"].get("siteId"):
            result["errors"].append(f"Site entry #{i + 1} is invalid (missing site.siteId).")
            continue
        clean: dict[str, Any] = {}
        for key, value in s.items():
            expected = SITE_KEYS.get(key)
            if expected is None:
                result["unsupported"].append({"area": f"sites[{s['site'].get('name') or i}].{key}",
                                              "reason": "Not interpreted by this application"})
                continue
            if value is not None and not isinstance(value, expected):
                result["errors"].append(f"Section '{key}' of site '{s['site'].get('name')}' has an invalid type.")
                continue
            if isinstance(value, list) and any(not isinstance(x, dict) for x in value):
                result["errors"].append(f"Section '{key}' of site '{s['site'].get('name')}' contains invalid items.")
                continue
            clean[key] = value
        sites.append(clean)
    if result["errors"]:
        return result
    raw = sanitize({"controller_info": info, "controller_status": status, "sites": sites,
                    "collected_at": data.get("collected_at")})
    try:
        entities = normalize(raw, None)
    except Exception as exc:  # noqa: BLE001 - parsers must never crash on untrusted input
        result["errors"].append(f"The data could not be interpreted: {type(exc).__name__}: {exc}")
        return result
    result["collected_at"] = data.get("collected_at")
    return _finish(result, entities)


def _parse_native_cfg(content: bytes, result: dict[str, Any]) -> dict[str, Any]:
    result["detected_format"] = "omada-native-backup"
    try:
        plain = decrypt_cfg(content)
    except CfgError as exc:
        result["errors"].append(str(exc))
        return result
    try:
        data = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        result["errors"].append(f"The backup was decrypted but does not contain valid JSON: {type(exc).__name__}")
        return result
    del plain  # drop the decrypted document as early as possible
    if not native_backup.is_native_document(data):
        result["errors"].append("The backup was decrypted but its structure is not recognised "
                                "(no 'mainInfo' / 'systemSetting' section).")
        return result
    return _parse_native(data, result)


def _parse_native(data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    try:
        _check_structure(data, **NATIVE_LIMITS)
    except BackupError as exc:
        result["errors"].append(str(exc))
        return result
    try:
        raw, meta = native_backup.convert(data)
        entities = normalize(raw, None)
    except Exception as exc:  # noqa: BLE001 - parsers must never crash on untrusted input
        result["errors"].append(f"The backup could not be interpreted: {type(exc).__name__}: {exc}")
        return result
    redacted = [0]
    entities = native_backup.redact(entities, meta["secrets"], redacted)
    if redacted[0]:
        meta["warnings"].append(f"{redacted[0]} value(s) matching secrets from the backup were redacted.")
    result.update(controller_version=meta["controller_version"], backup_version=meta["backup_version"],
                  collected_at=meta["collected_at"])
    result["warnings"] += meta["warnings"]
    result["unsupported"] += meta["unsupported"]
    return _finish(result, entities)


def _parse_dataset(data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    result["detected_format"] = "omada-docs-dataset"
    result["backup_version"] = str(data.get("format_version"))
    ents = data.get("entities")
    if not isinstance(ents, dict):
        result["errors"].append("'entities' must be an object.")
        return result
    entities: dict[str, list[dict]] = {}
    for kind, items in ents.items():
        if kind not in KINDS:
            result["unsupported"].append({"area": kind, "reason": "Unknown object type – ignored"})
            continue
        if not isinstance(items, list) or any(not isinstance(e, dict) or "key" not in e for e in items):
            result["errors"].append(f"Object list '{kind}' is invalid.")
            continue
        entities[kind] = [{**sanitize(e), "kind": kind, "key": str(e["key"])} for e in items]
    ctrl = (entities.get("controller") or [{}])[0]
    result["controller_version"] = ctrl.get("version")
    result["collected_at"] = data.get("exported_at")
    if result["errors"]:
        return result
    return _finish(result, entities)


def _finish(result: dict[str, Any], entities: dict[str, list[dict]]) -> dict[str, Any]:
    for kind in KINDS:
        entities.setdefault(kind, [])
    result["entities"] = entities
    result["summary"] = {"counts": {k: len(v) for k, v in entities.items()}}
    if not any(entities[k] for k in KINDS if k != "controller"):
        result["errors"].append("The file does not contain any usable configuration data.")
        return result
    result["status"] = "imported"
    return result


def compare_with_api(db: Session, entities: dict[str, list[dict]]) -> dict[str, Any]:
    """Compare backup entities with the currently stored API data; conflicts are reported per field."""
    api = load_dataset(db)
    rows = row_index(db)
    only_backup, only_api, conflicts = [], [], []
    for kind in KINDS:
        if kind in UNTRACKED_KINDS or kind == "controller":
            continue
        a = {(e.get("site_id"), str(e["key"])): e for e in api.get(kind, [])}
        b = {(e.get("site_id"), str(e["key"])): e for e in entities.get(kind, [])}
        for ident in b.keys() - a.keys():
            only_backup.append({"object_type": kind, "site_id": ident[0], "object_key": ident[1],
                                "object_name": b[ident].get("name")})
        for ident in a.keys() - b.keys():
            only_api.append({"object_type": kind, "site_id": ident[0], "object_key": ident[1],
                             "object_name": a[ident].get("name")})
        for ident in a.keys() & b.keys():
            av, bv = tracked_view(kind, a[ident]), tracked_view(kind, b[ident])
            row = rows.get((kind, ident[0], ident[1]))
            for fld in sorted(av.keys() & bv.keys()):
                if av[fld] != bv[fld] and av[fld] not in (None, "", []) and bv[fld] not in (None, "", []):
                    conflicts.append({
                        "object_type": kind, "site_id": ident[0], "object_key": ident[1],
                        "object_name": a[ident].get("name"), "field": fld, "api_value": av[fld],
                        "backup_value": bv[fld],
                        "api_source": row.source if row else "api",
                        "api_collected_at": row.collected_at.isoformat() if row and row.collected_at else None,
                    })
    return {"only_in_backup": only_backup[:2000], "only_in_api": only_api[:2000], "conflicts": conflicts[:5000],
            "counts": {"only_in_backup": len(only_backup), "only_in_api": len(only_api),
                       "conflicts": len(conflicts)}, "api_has_data": any(api.get(k) for k in KINDS
                                                                          if k != "controller")}


def import_backup(db: Session, user: User, filename: str, content: bytes, ip: str | None = None) -> BackupImport:
    parsed = parse_backup(filename, content)
    rec = BackupImport(filename=filename[:255], sha256=parsed["sha256"], detected_format=parsed["detected_format"],
                       controller_version=parsed["controller_version"], backup_version=parsed["backup_version"],
                       status=parsed["status"], unsupported=parsed["unsupported"],
                       errors=parsed["errors"] + [f"Warning: {w}" for w in parsed["warnings"]],
                       imported_by=user.username)
    summary = dict(parsed["summary"])
    if parsed["status"] == "imported":
        entities = parsed["entities"]
        summary["comparison"] = compare_with_api(db, entities)
        snap = ConfigSnapshot(source="backup", label=f"Backup import: {filename[:200]}",
                              controller_version=parsed["controller_version"],
                              checksum=hashlib.sha256(json.dumps(entities, sort_keys=True, default=str).encode())
                              .hexdigest(),
                              object_count=sum(len(v) for v in entities.values()), data=entities)
        db.add(snap)
        db.flush()
        rec.snapshot_id = snap.id
        summary["collected_at"] = parsed.get("collected_at")
    rec.summary = json.loads(json.dumps(summary, default=str))
    db.add(rec)
    db.flush()
    audit(db, user, "backup.import", "backup", str(rec.id),
          {"filename": rec.filename, "status": rec.status, "format": rec.detected_format}, ip)
    return rec


def import_dict(rec: BackupImport, full: bool = False) -> dict[str, Any]:
    out = {"id": rec.id, "imported_at": rec.imported_at, "filename": rec.filename, "sha256": rec.sha256,
           "detected_format": rec.detected_format, "controller_version": rec.controller_version,
           "backup_version": rec.backup_version, "status": rec.status, "unsupported": rec.unsupported or [],
           "errors": rec.errors or [], "snapshot_id": rec.snapshot_id, "imported_by": rec.imported_by,
           "counts": (rec.summary or {}).get("counts"),
           "comparison_counts": ((rec.summary or {}).get("comparison") or {}).get("counts")}
    if full:
        out["comparison"] = (rec.summary or {}).get("comparison")
    return out
