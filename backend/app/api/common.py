"""Helpers shared by the API route modules."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.manual import ManualDescription, ManualRelationship
from app.models.omada import ENTITY_MODELS
from app.services.manual import description_dict, relationship_dict


def resolve_site(db: Session, site_id: str | None) -> str | None:
    """Return ``site_id`` if it exists, else the primary/first site (or None when nothing is synchronised)."""
    model = ENTITY_MODELS["site"]
    sites = db.scalars(select(model).order_by(model.id)).all()
    if site_id:
        if any(s.object_key == site_id for s in sites):
            return site_id
        raise HTTPException(404, "Site not found")
    primary = next((s for s in sites if (s.data or {}).get("primary")), None)
    return (primary or (sites[0] if sites else None)).object_key if sites else None


def manual_map(db: Session) -> dict[tuple[str, str], dict[str, Any]]:
    return {(m.object_type, m.object_key): description_dict(m) for m in db.scalars(select(ManualDescription)).all()}


def all_relationships(db: Session) -> list[dict[str, Any]]:
    return [relationship_dict(r) for r in db.scalars(select(ManualRelationship)).all()]


def check_kind(kind: str) -> None:
    if kind not in ENTITY_MODELS:
        raise HTTPException(404, f"Unknown object type '{kind}'")
