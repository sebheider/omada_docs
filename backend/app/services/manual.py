"""Manual documentation: descriptions, free documents, relationships and attachments.

All modifications are written to the audit log and to the change log (``kind='manual'``).
Manual data is keyed by (object_type, object_key) and is never modified by synchronisation.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.manual import ManualAttachment, ManualDescription, ManualDocument, ManualRelationship
from app.models.system import AuditLog, ChangeLog, User

OBJECT_TYPES = {
    "site", "network", "device", "switch_port", "wlan", "acl_rule", "nat_rule", "client", "route", "vpn",
    "ip_group", "port_profile", "wan", "connection", "location", "document",
}
DESCRIPTION_FIELDS = ("display_name", "description", "location", "responsible", "notes", "tags")
DOCUMENT_CATEGORIES = ("network_architecture", "security", "cabling", "operations", "maintenance", "emergency",
                       "access", "other")
RELATIONS = ("related", "connected_to", "located_in", "depends_on")

# Allowed attachment types: extension -> (content type, required magic prefix or None)
ATTACHMENT_TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
    ".txt": ("text/plain", None),
    ".md": ("text/markdown", None),
    ".csv": ("text/csv", None),
    ".log": ("text/plain", None),
    ".json": ("application/json", None),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", (b"PK\x03\x04",)),
}
TEXT_TYPES = {".txt", ".md", ".csv", ".log", ".json"}

# Detects "password: value" style credentials. Mentioning the word "password" alone is fine.
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(pass(?:word|wort|phrase)?|pwd|psk|pre-?shared[ _-]?key|wpa[ _-]?key|secret|api[ _-]?key|token|"
    r"kennwort)\b\s*[:=]\s*\S{3,}")


class ManualError(ValueError):
    """Validation error raised for invalid manual input (mapped to HTTP 422)."""


def check_no_credentials(*texts: str | None) -> None:
    for text in texts:
        if text and _CREDENTIAL_RE.search(text):
            raise ManualError(
                "The text appears to contain a password, key or token. Credentials must not be stored in "
                "documentation entries – please use a password manager and reference it instead.")


def audit(db: Session, user: User | None, action: str, object_type: str | None = None, object_key: str | None = None,
          details: dict | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(username=user.username if user else None, action=action, object_type=object_type,
                    object_key=object_key, details=details, ip=ip))


def _log_change(db: Session, user: User | None, object_type: str, object_key: str, name: str | None,
                change_type: str, field: str | None, before: Any, after: Any, site_id: str | None = None) -> None:
    def fmt(v: Any) -> str | None:
        if v is None or v == "" or v == []:
            return None
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        s = str(v)
        return s if len(s) <= 2000 else s[:2000] + "…"

    db.add(ChangeLog(kind="manual", site_id=site_id, object_type=object_type, object_key=object_key,
                     object_name=(name or "")[:255] or None, change_type=change_type, field=field,
                     before=fmt(before), after=fmt(after), username=user.username if user else None))


def _clean_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = tags.split(",")
    out = []
    for t in tags:
        t = str(t).strip()[:50]
        if t and t not in out:
            out.append(t)
    return out[:30]


# ---------------------------------------------------------------- descriptions


def description_dict(m: ManualDescription | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {"id": m.id, "object_type": m.object_type, "object_key": m.object_key, "site_id": m.site_id,
            "display_name": m.display_name, "description": m.description, "location": m.location,
            "responsible": m.responsible, "notes": m.notes, "tags": m.tags or [], "created_at": m.created_at,
            "updated_at": m.updated_at, "updated_by": m.updated_by, "source": "manual"}


def get_description(db: Session, object_type: str, object_key: str) -> ManualDescription | None:
    return db.scalars(select(ManualDescription).where(ManualDescription.object_type == object_type,
                                                      ManualDescription.object_key == object_key)).first()


def descriptions_for(db: Session, object_type: str) -> dict[str, dict[str, Any]]:
    rows = db.scalars(select(ManualDescription).where(ManualDescription.object_type == object_type)).all()
    return {r.object_key: description_dict(r) for r in rows}


def upsert_description(db: Session, user: User, object_type: str, object_key: str, data: dict[str, Any],
                       site_id: str | None = None, ip: str | None = None) -> ManualDescription:
    if object_type not in OBJECT_TYPES:
        raise ManualError(f"Unsupported object type '{object_type}'.")
    if not object_key or len(object_key) > 255:
        raise ManualError("Invalid object key.")
    values = {f: data.get(f) for f in DESCRIPTION_FIELDS if f in data}
    if "tags" in values:
        values["tags"] = _clean_tags(values["tags"])
    for f in ("display_name", "location", "responsible"):
        if values.get(f) is not None:
            values[f] = str(values[f]).strip()[:255] or None
    for f in ("description", "notes"):
        if values.get(f) is not None:
            values[f] = str(values[f])[:50_000] or None
    check_no_credentials(*(v for v in values.values() if isinstance(v, str)))

    m = get_description(db, object_type, object_key)
    created = m is None
    if created:
        m = ManualDescription(object_type=object_type, object_key=object_key, site_id=site_id)
        db.add(m)
    changed = {}
    for f, v in values.items():
        before = getattr(m, f)
        if (before or None) != (v or None):
            changed[f] = (before, v)
            setattr(m, f, v)
    if site_id and not m.site_id:
        m.site_id = site_id
    m.updated_by = user.username
    name = values.get("display_name") or m.display_name or object_key
    for f, (before, after) in changed.items():
        _log_change(db, user, object_type, object_key, name, "added" if created else "modified", f, before, after,
                    m.site_id)
    if changed or created:
        audit(db, user, "description.create" if created else "description.update", object_type, object_key,
              {"fields": sorted(changed)}, ip)
    db.flush()
    return m


def delete_description(db: Session, user: User, object_type: str, object_key: str, ip: str | None = None) -> bool:
    m = get_description(db, object_type, object_key)
    if not m:
        return False
    _log_change(db, user, object_type, object_key, m.display_name or object_key, "removed", "description",
                m.description, None, m.site_id)
    audit(db, user, "description.delete", object_type, object_key, None, ip)
    db.delete(m)
    db.flush()
    return True


# ---------------------------------------------------------------- relationships


def relationship_dict(r: ManualRelationship) -> dict[str, Any]:
    return {"id": r.id, "source_type": r.source_type, "source_key": r.source_key, "target_type": r.target_type,
            "target_key": r.target_key, "relation": r.relation, "description": r.description,
            "created_at": r.created_at, "created_by": r.created_by, "source": "manual"}


def relationships_for(db: Session, object_type: str, object_key: str) -> list[dict[str, Any]]:
    rows = db.scalars(select(ManualRelationship).where(or_(
        (ManualRelationship.source_type == object_type) & (ManualRelationship.source_key == object_key),
        (ManualRelationship.target_type == object_type) & (ManualRelationship.target_key == object_key),
    ))).all()
    return [relationship_dict(r) for r in rows]


def add_relationship(db: Session, user: User, data: dict[str, Any], ip: str | None = None) -> ManualRelationship:
    for f in ("source_type", "target_type"):
        if data.get(f) not in OBJECT_TYPES:
            raise ManualError(f"Unsupported {f.replace('_', ' ')} '{data.get(f)}'.")
    for f in ("source_key", "target_key"):
        if not data.get(f) or len(str(data[f])) > 255:
            raise ManualError(f"Invalid {f.replace('_', ' ')}.")
    relation = data.get("relation") or "related"
    if relation not in RELATIONS:
        raise ManualError(f"Unsupported relation '{relation}'.")
    if (data["source_type"], str(data["source_key"])) == (data["target_type"], str(data["target_key"])):
        raise ManualError("An object cannot be related to itself.")
    check_no_credentials(data.get("description"))
    r = ManualRelationship(source_type=data["source_type"], source_key=str(data["source_key"]),
                           target_type=data["target_type"], target_key=str(data["target_key"]), relation=relation,
                           description=(data.get("description") or None), created_by=user.username)
    db.add(r)
    db.flush()
    label = f"{r.source_type}:{r.source_key} → {r.target_type}:{r.target_key}"
    _log_change(db, user, "relationship", str(r.id), label, "added", relation, None, label)
    audit(db, user, "relationship.create", "relationship", str(r.id), relationship_dict(r) | {"created_at": None}, ip)
    return r


def delete_relationship(db: Session, user: User, rel_id: int, ip: str | None = None) -> bool:
    r = db.get(ManualRelationship, rel_id)
    if not r:
        return False
    label = f"{r.source_type}:{r.source_key} → {r.target_type}:{r.target_key}"
    _log_change(db, user, "relationship", str(r.id), label, "removed", r.relation, label, None)
    audit(db, user, "relationship.delete", "relationship", str(r.id), None, ip)
    db.delete(r)
    db.flush()
    return True


# ---------------------------------------------------------------- documents


def document_dict(d: ManualDocument, db: Session | None = None, full: bool = True) -> dict[str, Any]:
    out = {"id": d.id, "title": d.title, "category": d.category, "tags": d.tags or [], "created_at": d.created_at,
           "updated_at": d.updated_at, "created_by": d.created_by, "updated_by": d.updated_by}
    if full:
        out["body"] = d.body
    if db is not None:
        out["relationships"] = relationships_for(db, "document", str(d.id))
        out["attachments"] = [attachment_dict(a) for a in db.scalars(
            select(ManualAttachment).where(ManualAttachment.document_id == d.id)).all()]
    return out


def _validate_document(data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "title" in data or not partial:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ManualError("A title is required.")
        out["title"] = title[:255]
    if "body" in data or not partial:
        out["body"] = str(data.get("body") or "")[:200_000]
    if "category" in data or not partial:
        category = data.get("category") or "other"
        if category not in DOCUMENT_CATEGORIES:
            raise ManualError(f"Unsupported category '{category}'.")
        out["category"] = category
    if "tags" in data or not partial:
        out["tags"] = _clean_tags(data.get("tags"))
    check_no_credentials(out.get("title"), out.get("body"))
    return out


def create_document(db: Session, user: User, data: dict[str, Any], ip: str | None = None) -> ManualDocument:
    values = _validate_document(data)
    d = ManualDocument(**values, created_by=user.username, updated_by=user.username)
    db.add(d)
    db.flush()
    _log_change(db, user, "document", str(d.id), d.title, "added", None, None, d.title)
    audit(db, user, "document.create", "document", str(d.id), {"title": d.title}, ip)
    for rel in data.get("relationships") or []:
        add_relationship(db, user, {"source_type": "document", "source_key": str(d.id), **rel}, ip)
    return d


def update_document(db: Session, user: User, doc_id: int, data: dict[str, Any], ip: str | None = None) -> ManualDocument:
    d = db.get(ManualDocument, doc_id)
    if d is None:
        raise LookupError("Document not found")
    values = _validate_document(data, partial=True)
    changed = []
    for f, v in values.items():
        before = getattr(d, f)
        if before != v:
            changed.append(f)
            _log_change(db, user, "document", str(d.id), values.get("title") or d.title, "modified", f,
                        before if f != "body" else f"{len(before or '')} characters",
                        v if f != "body" else f"{len(v or '')} characters")
            setattr(d, f, v)
    d.updated_by = user.username
    if changed:
        audit(db, user, "document.update", "document", str(d.id), {"fields": changed}, ip)
    db.flush()
    return d


def delete_document(db: Session, user: User, doc_id: int, ip: str | None = None) -> bool:
    d = db.get(ManualDocument, doc_id)
    if d is None:
        return False
    for a in db.scalars(select(ManualAttachment).where(ManualAttachment.document_id == d.id)).all():
        _remove_attachment_file(a)
    db.execute(delete(ManualRelationship).where(
        or_((ManualRelationship.source_type == "document") & (ManualRelationship.source_key == str(d.id)),
            (ManualRelationship.target_type == "document") & (ManualRelationship.target_key == str(d.id)))))
    _log_change(db, user, "document", str(d.id), d.title, "removed", None, d.title, None)
    audit(db, user, "document.delete", "document", str(d.id), {"title": d.title}, ip)
    db.delete(d)
    db.flush()
    return True


# ---------------------------------------------------------------- attachments


def attachment_dict(a: ManualAttachment) -> dict[str, Any]:
    return {"id": a.id, "document_id": a.document_id, "filename": a.filename, "content_type": a.content_type,
            "size": a.size, "sha256": a.sha256, "uploaded_at": a.uploaded_at, "uploaded_by": a.uploaded_by}


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .") or "file"
    return name[:200]


def validate_upload(filename: str, content: bytes, max_bytes: int) -> tuple[str, str]:
    """Return (safe filename, content type) or raise ManualError."""
    if not content:
        raise ManualError("The uploaded file is empty.")
    if len(content) > max_bytes:
        raise ManualError(f"The file exceeds the maximum size of {max_bytes // (1024 * 1024)} MB.")
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in ATTACHMENT_TYPES:
        raise ManualError(f"File type '{ext or 'unknown'}' is not allowed. Allowed: "
                          + ", ".join(sorted(ATTACHMENT_TYPES)))
    ctype, magic = ATTACHMENT_TYPES[ext]
    if magic and not any(content.startswith(m) for m in magic):
        raise ManualError("The file content does not match its extension.")
    if ext == ".webp" and content[8:12] != b"WEBP":
        raise ManualError("The file content does not match its extension.")
    if ext in TEXT_TYPES:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManualError("Text files must be UTF-8 encoded.") from exc
        if b"\x00" in content:
            raise ManualError("Text files must not contain binary data.")
    return name, ctype


def add_attachment(db: Session, user: User, doc_id: int, filename: str, content: bytes,
                   ip: str | None = None) -> ManualAttachment:
    d = db.get(ManualDocument, doc_id)
    if d is None:
        raise LookupError("Document not found")
    settings = get_settings()
    name, ctype = validate_upload(filename, content, settings.max_upload_mb * 1024 * 1024)
    stored = secrets.token_hex(24)
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    (settings.attachments_dir / stored).write_bytes(content)
    a = ManualAttachment(document_id=d.id, filename=name, stored_name=stored, content_type=ctype, size=len(content),
                         sha256=hashlib.sha256(content).hexdigest(), uploaded_by=user.username)
    db.add(a)
    db.flush()
    _log_change(db, user, "document", str(d.id), d.title, "modified", "attachments", None, name)
    audit(db, user, "attachment.upload", "document", str(d.id), {"filename": name, "size": len(content)}, ip)
    return a


def attachment_path(a: ManualAttachment) -> Path:
    path = (get_settings().attachments_dir / a.stored_name).resolve()
    if path.parent != get_settings().attachments_dir.resolve():
        raise ManualError("Invalid attachment path")
    return path


def _remove_attachment_file(a: ManualAttachment) -> None:
    try:
        attachment_path(a).unlink(missing_ok=True)
    except (OSError, ManualError):
        pass


def delete_attachment(db: Session, user: User, att_id: int, ip: str | None = None) -> bool:
    a = db.get(ManualAttachment, att_id)
    if a is None:
        return False
    d = db.get(ManualDocument, a.document_id)
    _remove_attachment_file(a)
    _log_change(db, user, "document", str(a.document_id), d.title if d else None, "modified", "attachments",
                a.filename, None)
    audit(db, user, "attachment.delete", "document", str(a.document_id), {"filename": a.filename}, ip)
    db.delete(a)
    db.flush()
    return True
