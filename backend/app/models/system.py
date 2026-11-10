"""Application/system tables: users, sessions, settings, sync history, snapshots, change log, audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin | viewer
    auth_source: Mapped[str] = mapped_column(String(16), default="local")  # local | proxy
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the session token
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_key: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))


class SyncHistory(Base):
    __tablename__ = "sync_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|partial|failed
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual|scheduled|startup
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    new_objects: Mapped[int] = mapped_column(Integer, default=0)
    changed_objects: Mapped[int] = mapped_column(Integer, default=0)
    removed_objects: Mapped[int] = mapped_column(Integer, default=0)
    total_objects: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)  # per-endpoint results
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("config_snapshots.id", ondelete="SET NULL"))


class ConfigSnapshot(Base):
    __tablename__ = "config_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(16))  # api | backup | demo
    label: Mapped[str | None] = mapped_column(String(255))
    controller_version: Mapped[str | None] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON)


class ChangeLog(Base):
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # config | manual
    sync_id: Mapped[int | None] = mapped_column(ForeignKey("sync_history.id", ondelete="SET NULL"))
    site_id: Mapped[str | None] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    object_key: Mapped[str] = mapped_column(String(255))
    object_name: Mapped[str | None] = mapped_column(String(255))
    change_type: Mapped[str] = mapped_column(String(16))  # added | removed | modified
    field: Mapped[str | None] = mapped_column(String(128))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(64))


class BackupImport(Base):
    __tablename__ = "backup_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    detected_format: Mapped[str | None] = mapped_column(String(64))
    controller_version: Mapped[str | None] = mapped_column(String(64))
    backup_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # imported | rejected
    summary: Mapped[dict | None] = mapped_column(JSON)
    unsupported: Mapped[list | None] = mapped_column(JSON)
    errors: Mapped[list | None] = mapped_column(JSON)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("config_snapshots.id", ondelete="SET NULL"))
    imported_by: Mapped[str | None] = mapped_column(String(64))


class SearchEntry(Base):
    """Denormalised search index, rebuilt after synchronisations and manual edits."""

    __tablename__ = "search_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(255))
    site_id: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text)
