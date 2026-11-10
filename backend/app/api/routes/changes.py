"""Change history, configuration snapshots and document export."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.common import resolve_site
from app.api.deps import client_ip, get_current_user
from app.api.routes.data import _change_dict
from app.db.session import get_db
from app.models.system import ChangeLog, ConfigSnapshot, User
from app.services.changes import diff_datasets
from app.services.export import render
from app.services.export.data import CHAPTERS, DEFAULT_CHAPTERS, build_report
from app.services.manual import audit
from app.services.search import _escape_like

router = APIRouter(tags=["changes"])


@router.get("/changes")
def list_changes(kind: Literal["config", "manual"] | None = None, object_type: str | None = None,
                 change_type: str | None = None, site_id: str | None = None, sync_id: int | None = None,
                 days: int | None = Query(None, ge=1, le=3650), q: str | None = Query(None, max_length=200),
                 limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    conds = []
    if kind:
        conds.append(ChangeLog.kind == kind)
    if object_type:
        conds.append(ChangeLog.object_type == object_type)
    if change_type:
        conds.append(ChangeLog.change_type == change_type)
    if site_id:
        conds.append(or_(ChangeLog.site_id == site_id, ChangeLog.site_id.is_(None)))
    if sync_id:
        conds.append(ChangeLog.sync_id == sync_id)
    if days:
        conds.append(ChangeLog.ts >= datetime.now(timezone.utc) - timedelta(days=days))
    if q:
        like = f"%{_escape_like(q)}%"
        conds.append(or_(ChangeLog.object_name.ilike(like, escape="\\"), ChangeLog.object_key.ilike(like, escape="\\"),
                         ChangeLog.field.ilike(like, escape="\\"), ChangeLog.before.ilike(like, escape="\\"),
                         ChangeLog.after.ilike(like, escape="\\")))
    total = db.scalar(select(func.count(ChangeLog.id)).where(*conds))
    rows = db.scalars(select(ChangeLog).where(*conds).order_by(ChangeLog.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [_change_dict(c) for c in rows]}


def _snapshot_dict(s: ConfigSnapshot) -> dict:
    return {"id": s.id, "created_at": s.created_at, "source": s.source, "label": s.label,
            "controller_version": s.controller_version, "checksum": s.checksum, "object_count": s.object_count}


@router.get("/snapshots")
def list_snapshots(limit: int = Query(200, ge=1, le=2000), db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)) -> list[dict]:
    rows = db.scalars(select(ConfigSnapshot).order_by(ConfigSnapshot.id.desc()).limit(limit)).all()
    return [_snapshot_dict(s) for s in rows]


@router.get("/snapshots/compare")
def compare_snapshots(a: int, b: int, include_clients: bool = False, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)) -> dict:
    sa, sb = db.get(ConfigSnapshot, a), db.get(ConfigSnapshot, b)
    if sa is None or sb is None:
        raise HTTPException(404, "Snapshot not found")
    changes = diff_datasets(sa.data, sb.data, include_untracked=include_clients)
    return {"a": _snapshot_dict(sa), "b": _snapshot_dict(sb), "changes": changes,
            "summary": {t: sum(1 for c in changes if c["change_type"] == t) for t in ("added", "removed", "modified")}}


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    s = db.get(ConfigSnapshot, snapshot_id)
    if s is None:
        raise HTTPException(404, "Snapshot not found")
    return {**_snapshot_dict(s), "counts": {k: len(v) for k, v in (s.data or {}).items()}, "data": s.data}


# ------------------------------------------------------------------ export


@router.get("/export/options")
def export_options(_: User = Depends(get_current_user)) -> dict:
    return {"formats": ["pdf", "docx", "html", "csv"], "chapters": CHAPTERS, "default_chapters": DEFAULT_CHAPTERS,
            "csv_tables": list(render.CSV_TABLES)}


_export_lock = asyncio.Semaphore(2)


@router.get("/export")
async def export(request: Request, format: Literal["pdf", "docx", "html", "csv"] = "pdf",
                 site_id: str | None = None, chapters: str | None = None, anonymize: bool = True,
                 change_days: int = Query(90, ge=1, le=3650), table: str = "devices", download: bool = True,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    site_id = resolve_site(db, site_id)
    selected = [c for c in (chapters.split(",") if chapters else DEFAULT_CHAPTERS) if c in CHAPTERS]
    if not selected:
        raise HTTPException(422, "No valid chapter selected.")
    if format == "csv" and table not in render.CSV_TABLES:
        raise HTTPException(422, f"Unknown table. Allowed: {', '.join(render.CSV_TABLES)}")
    report = build_report(db, site_id, selected if format != "csv" else list(CHAPTERS), anonymize, change_days)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    base = f"network-documentation-{stamp}"
    async with _export_lock:
        if format == "pdf":
            data: bytes | str = await asyncio.to_thread(render.render_pdf, report)
            media, name = "application/pdf", f"{base}.pdf"
        elif format == "docx":
            data = await asyncio.to_thread(render.render_docx, report)
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            name = f"{base}.docx"
        elif format == "html":
            data = await asyncio.to_thread(render.render_html, report, True)
            media, name = "text/html; charset=utf-8", f"{base}.html"
        else:
            data = render.render_csv(report, table)
            media, name = "text/csv; charset=utf-8", f"{table}-{stamp}.csv"
    audit(db, user, "export", details={"format": format, "chapters": selected, "anonymize": anonymize,
                                       "site_id": site_id, "table": table if format == "csv" else None},
          ip=client_ip(request))
    db.commit()
    disposition = "attachment" if download or format != "html" else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{name}"'}
    if format == "html":
        # Exported HTML is self-contained (inline CSS/SVG) and never needs scripts.
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    return Response(data, media_type=media, headers=headers)
