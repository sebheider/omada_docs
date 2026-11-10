"""Administration: controller settings, synchronisation, backup import, application backup and audit log."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.system import AuditLog, BackupImport, SyncHistory, User
from app.services import app_backup, backup_import, scheduler, sync
from app.services.manual import audit
from app.services.settings_store import SYNC_INTERVALS, load_controller_settings, save_controller_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])
_background: set[asyncio.Task] = set()


# ------------------------------------------------------------------ controller settings


class ControllerSettingsIn(BaseModel):
    host: str = Field(default="", max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    scheme: Literal["https", "http"] = "https"
    client_id: str = Field(default="", max_length=255)
    client_secret: str | None = Field(default=None, max_length=512)  # empty/None = keep existing
    omadac_id: str = Field(default="", max_length=128)
    api_version: Literal["v1"] = "v1"
    verify_ssl: bool = True
    site_ids: list[str] = Field(default_factory=list)
    sync_interval: str = "manual"
    request_timeout: float = Field(default=20.0, ge=2, le=300)
    max_requests_per_second: float = Field(default=5.0, ge=0.2, le=50)
    snapshot_retention: int = Field(default=200, ge=5, le=5000)

    @model_validator(mode="before")
    @classmethod
    def _split_url(cls, data: Any) -> Any:
        """Accept a pasted URL like ``https://omada.local:8043/path`` and split scheme, host and port."""
        if not isinstance(data, dict) or not isinstance(data.get("host"), str):
            return data
        data = dict(data)
        v = data["host"].strip()
        for scheme in ("https", "http"):
            if v.lower().startswith(scheme + "://"):
                v = v[len(scheme) + 3:]
                data["scheme"] = scheme
        v = v.split("/")[0]
        m = re.fullmatch(r"(\[[0-9a-fA-F:.]+\]|[^:]+):(\d{1,5})", v)
        if m:
            v, data["port"] = m.group(1), int(m.group(2))
        data["host"] = v
        return data

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        if any(c in v for c in " @?#/"):
            raise ValueError("Invalid host name")
        return v

    @field_validator("sync_interval")
    @classmethod
    def _interval(cls, v: str) -> str:
        if v not in SYNC_INTERVALS:
            raise ValueError(f"Allowed values: {', '.join(SYNC_INTERVALS)}")
        return v


@router.get("/settings/controller")
def get_controller_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return {**load_controller_settings(db).public_dict(), "sync_intervals": list(SYNC_INTERVALS),
            "demo_mode": get_settings().demo_mode, "next_run": scheduler.next_run()}


@router.put("/settings/controller")
def put_controller_settings(body: ControllerSettingsIn, request: Request, db: Session = Depends(get_db),
                            admin: User = Depends(require_admin)) -> dict:
    data = body.model_dump()
    if not data.get("client_secret"):
        data.pop("client_secret")
    cs = save_controller_settings(db, data)
    audit(db, admin, "settings.controller", details={k: v for k, v in data.items() if k != "client_secret"}
          | {"client_secret_changed": bool(body.client_secret)}, ip=client_ip(request))
    db.commit()
    scheduler.reschedule()
    return {**cs.public_dict(), "next_run": scheduler.next_run()}


@router.post("/settings/controller/test")
async def test_controller(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    cs = load_controller_settings(db)
    if not cs.configured and not get_settings().demo_mode:
        raise HTTPException(400, "Controller address, client ID and client secret must be configured first.")
    result = await sync.test_connection(cs)
    audit(db, admin, "settings.test_connection", details={"ok": result.get("ok")}, ip=client_ip(request))
    db.commit()
    return result


# ------------------------------------------------------------------ synchronisation


@router.post("/sync")
async def start_sync(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    cs = load_controller_settings(db)
    if not cs.configured and not get_settings().demo_mode:
        raise HTTPException(400, "The controller connection is not configured.")
    if sync.is_running():
        raise HTTPException(409, "A synchronisation is already running.")
    audit(db, admin, "sync.start", ip=client_ip(request))
    db.commit()

    async def runner() -> None:
        try:
            await sync.run_sync("manual")
        except sync.SyncError as exc:
            log.info("Manual synchronisation not started: %s", exc)
        except Exception:  # noqa: BLE001
            log.exception("Manual synchronisation crashed")

    task = asyncio.create_task(runner())
    _background.add(task)
    task.add_done_callback(_background.discard)
    await asyncio.sleep(0)  # let the task acquire the lock
    return {"started": True}


@router.get("/sync/status")
def get_sync_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    return {**sync.sync_status(db), "next_run": scheduler.next_run(),
            "interval": load_controller_settings(db).sync_interval}


@router.get("/sync/history")
def get_sync_history(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                     db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(select(SyncHistory).order_by(SyncHistory.id.desc()).limit(limit).offset(offset)).all()
    return {"total": db.scalar(select(func.count(SyncHistory.id))),
            "items": [sync.history_dict(h) for h in rows]}


@router.get("/sync/history/{sync_id}")
def get_sync_detail(sync_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    h = db.get(SyncHistory, sync_id)
    if h is None:
        raise HTTPException(404, "Synchronisation not found")
    return sync.history_dict(h, with_details=True)


# ------------------------------------------------------------------ backup import


@router.post("/backup/import")
async def import_backup_file(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)) -> dict:
    content = await _read_limited(file)
    rec = await asyncio.to_thread(backup_import.import_backup, db, admin, file.filename or "upload", content,
                                  client_ip(request))
    db.commit()
    return backup_import.import_dict(rec, full=True)


@router.get("/backup/imports")
def list_imports(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[dict]:
    return [backup_import.import_dict(r) for r in
            db.scalars(select(BackupImport).order_by(BackupImport.id.desc()).limit(200)).all()]


@router.get("/backup/imports/{import_id}")
def get_import(import_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    rec = db.get(BackupImport, import_id)
    if rec is None:
        raise HTTPException(404, "Import not found")
    return backup_import.import_dict(rec, full=True)


@router.get("/backup/app")
def download_app_backup(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    name, data = app_backup.create_backup()
    audit(db, admin, "backup.app_download", details={"size": len(data)}, ip=client_ip(request))
    db.commit()
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/backup/restore")
async def restore_app_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    content = await _read_limited(file, 1024)
    if sync.is_running():
        raise HTTPException(409, "Please wait until the running synchronisation has finished.")
    username = admin.username
    # Release this request's connection (same cached session as used for authentication) before the
    # database file is replaced.
    db.close()
    try:
        info = app_backup.restore_backup(content)
    except app_backup.RestoreError as exc:
        raise HTTPException(422, str(exc)) from exc
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        db.add(AuditLog(username=username, action="backup.restore", details=info, ip=client_ip(request)))
        db.commit()
    scheduler.reschedule()
    return {"ok": True, **info}


async def _read_limited(file: UploadFile, max_mb: int | None = None) -> bytes:
    limit = (max_mb or get_settings().max_upload_mb) * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"The file exceeds the maximum size of {limit // (1024 * 1024)} MB.")
    return content


# ------------------------------------------------------------------ audit log


@router.get("/audit")
def get_audit(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              action: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    stmt = select(AuditLog)
    count = select(func.count(AuditLog.id))
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
        count = count.where(AuditLog.action.startswith(action))
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return {"total": db.scalar(count), "items": [
        {"id": a.id, "ts": a.ts, "username": a.username, "action": a.action, "object_type": a.object_type,
         "object_key": a.object_key, "details": a.details, "ip": a.ip} for a in rows]}
