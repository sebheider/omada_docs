"""Backup and restore of the application's own data (database + attachments).

The archive contains a consistent SQLite copy (online backup API), all attachments and a manifest.
The encryption key (``secret.key``) is intentionally NOT included: after restoring on another
installation with a different key, the controller client secret has to be entered again.
"""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app import __version__
from app.core.config import get_settings
from app.db import session as db_session
from app.db.migrate import upgrade_to_head

MAX_RESTORE_BYTES = 2 * 1024 ** 3
SQLITE_HEADER = b"SQLite format 3\x00"


class RestoreError(ValueError):
    pass


def _db_path() -> Path:
    url = make_url(get_settings().db_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise RestoreError("Backup/restore is only supported for the built-in SQLite database.")
    return Path(url.database)


def _sqlite_copy(src_path: Path, dst_path: Path) -> None:
    """Consistent copy via the SQLite online backup API (includes data still in the WAL)."""
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def create_backup() -> tuple[str, bytes]:
    settings = get_settings()
    src_path = _db_path()
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "omada_docs.db"
        _sqlite_copy(src_path, copy)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(copy, "omada_docs.db")
            files = 0
            if settings.attachments_dir.exists():
                for f in sorted(settings.attachments_dir.iterdir()):
                    if f.is_file():
                        zf.write(f, f"attachments/{f.name}")
                        files += 1
            zf.writestr("manifest.json", json.dumps({
                "format": "omada-docs-app-backup", "format_version": 1, "app_version": __version__,
                "created_at": datetime.now(timezone.utc).isoformat(), "attachments": files,
                "note": "secret.key is not included; re-enter the controller client secret after restoring "
                        "on a different installation.",
            }, indent=2))
    name = f"omada-docs-backup-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
    return name, buf.getvalue()


def _validate_db(path: Path) -> None:
    with path.open("rb") as fh:
        if fh.read(16) != SQLITE_HEADER:
            raise RestoreError("The archive does not contain a valid SQLite database.")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RestoreError("The database in the archive is corrupt.")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"users", "alembic_version", "manual_descriptions"} <= tables:
            raise RestoreError("The database in the archive is not an Omada Docs database.")
    except sqlite3.DatabaseError as exc:
        raise RestoreError(f"The database in the archive cannot be read: {exc}") from exc
    finally:
        con.close()


def restore_backup(content: bytes) -> dict:
    settings = get_settings()
    if len(content) > MAX_RESTORE_BYTES:
        raise RestoreError("The archive is too large.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise RestoreError("The file is not a valid ZIP archive.") from exc
    with zf, tempfile.TemporaryDirectory() as tmp:
        names = zf.namelist()
        if "manifest.json" not in names or "omada_docs.db" not in names:
            raise RestoreError("The archive is not an Omada Docs backup (manifest or database missing).")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except ValueError as exc:
            raise RestoreError("Invalid manifest.") from exc
        if manifest.get("format") != "omada-docs-app-backup":
            raise RestoreError("Unsupported backup format.")
        total = sum(i.file_size for i in zf.infolist())
        if total > MAX_RESTORE_BYTES * 4:
            raise RestoreError("The archive expands to an unreasonable size.")
        attachments = []
        for n in names:
            if n in ("manifest.json", "omada_docs.db"):
                continue
            parts = n.split("/")
            if len(parts) != 2 or parts[0] != "attachments" or not parts[1] or not parts[1].isalnum():
                raise RestoreError(f"Unexpected file in archive: {n}")
            attachments.append(n)
        tmp_db = Path(tmp) / "omada_docs.db"
        tmp_db.write_bytes(zf.read("omada_docs.db"))
        _validate_db(tmp_db)

        db_path = _db_path()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        if db_path.exists():
            _sqlite_copy(db_path, db_path.with_name(f"{db_path.name}.pre-restore-{stamp}"))
        db_session.get_engine().dispose()
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        shutil.copy2(tmp_db, db_path)

        att_dir = settings.attachments_dir
        if att_dir.exists():
            att_dir.rename(att_dir.with_name(f"attachments.pre-restore-{stamp}"))
        att_dir.mkdir(parents=True, exist_ok=True)
        for n in attachments:
            (att_dir / n.split("/")[1]).write_bytes(zf.read(n))

    db_session.init_engine()
    upgrade_to_head()
    return {"restored": True, "app_version": manifest.get("app_version"), "created_at": manifest.get("created_at"),
            "attachments": len(attachments)}
