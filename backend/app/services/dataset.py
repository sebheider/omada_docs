"""Read/write helpers for the normalised technical dataset stored in the ``omada_*`` tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.omada import ENTITY_MODELS

KINDS = tuple(ENTITY_MODELS.keys())


def _with_meta(row: Any) -> dict[str, Any]:
    data = dict(row.data or {})
    data["_meta"] = {
        "source": row.source,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "site_id": row.site_id,
        "controller_id": row.controller_id,
        "validation_status": row.validation_status,
    }
    return data


def load_dataset(db: Session, site_id: str | None = None, kinds: tuple[str, ...] | None = None,
                 with_meta: bool = False) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in kinds or KINDS:
        model = ENTITY_MODELS[kind]
        stmt = select(model)
        if site_id and kind not in ("controller", "site"):
            stmt = stmt.where(model.site_id == site_id)
        rows = db.scalars(stmt.order_by(model.id)).all()
        out[kind] = [_with_meta(r) if with_meta else dict(r.data or {}) for r in rows]
    return out


def load_entities(db: Session, kind: str, site_id: str | None = None) -> list[dict[str, Any]]:
    return load_dataset(db, site_id, (kind,), with_meta=True)[kind]


def load_entity(db: Session, kind: str, key: str, site_id: str | None = None) -> dict[str, Any] | None:
    model = ENTITY_MODELS[kind]
    stmt = select(model).where(model.object_key == key)
    if site_id:
        stmt = stmt.where(model.site_id == site_id)
    row = db.scalars(stmt).first()
    return _with_meta(row) if row else None


def replace_dataset(db: Session, entities: dict[str, list[dict[str, Any]]], source: str,
                    collected_at: datetime | None = None) -> int:
    """Replace all technical tables with ``entities`` (the caller controls the transaction).

    Each entity may carry a ``_meta`` dict with ``source``, ``collected_at_dt``, ``updated_at_dt`` and
    ``validation_status`` overrides (used for carried-forward and unchanged objects).
    """
    collected_at = collected_at or utcnow()
    total = 0
    for kind, model in ENTITY_MODELS.items():
        db.execute(delete(model))
        seen: set[tuple[str | None, str]] = set()
        for ent in entities.get(kind, []):
            ident = (ent.get("site_id"), str(ent["key"]))
            if ident in seen:  # defensive: controller returned duplicates
                continue
            seen.add(ident)
            meta = ent.get("_meta") or {}
            row_collected = meta.get("collected_at_dt") or collected_at
            db.add(model(
                site_id=ident[0], object_key=ident[1],
                name=str(ent.get("name"))[:255] if ent.get("name") not in (None, "") else None,
                controller_id=ent.get("controller_id"), source=meta.get("source") or source,
                collected_at=row_collected, updated_at=meta.get("updated_at_dt") or row_collected,
                validation_status=meta.get("validation_status") or ent.get("validation_status") or "valid",
                data={k: v for k, v in ent.items() if k != "_meta"},
            ))
            total += 1
    return total


def row_index(db: Session) -> dict[tuple[str, str | None, str], Any]:
    """(kind, site_id, key) -> ORM row for the currently stored dataset."""
    out: dict[tuple[str, str | None, str], Any] = {}
    for kind, model in ENTITY_MODELS.items():
        for row in db.scalars(select(model)).all():
            out[(kind, row.site_id, row.object_key)] = row
    return out
