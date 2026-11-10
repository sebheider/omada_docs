"""Persistent application settings. Secrets are encrypted at rest and never returned to clients."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.models.system import AppSetting

SYNC_INTERVALS: dict[str, int | None] = {
    "manual": None,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "1d": 24 * 60 * 60,
}

SECRET_KEYS = {"client_secret"}


@dataclass
class ControllerSettings:
    host: str = ""
    port: int = 443
    scheme: str = "https"
    client_id: str = ""
    client_secret: str = ""
    omadac_id: str = ""  # auto-detected via /api/info when empty
    api_version: str = "v1"
    verify_ssl: bool = True
    site_ids: list[str] = field(default_factory=list)  # empty = all sites
    sync_interval: str = "manual"
    request_timeout: float = 20.0
    max_requests_per_second: float = 5.0
    snapshot_retention: int = 200

    @property
    def configured(self) -> bool:
        return bool(self.host and self.client_id and self.client_secret)

    @property
    def base_url(self) -> str:
        default = (self.scheme == "https" and self.port == 443) or (self.scheme == "http" and self.port == 80)
        return f"{self.scheme}://{self.host}" + ("" if default else f":{self.port}")

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("client_secret")
        data["client_secret_set"] = bool(self.client_secret)
        data["configured"] = self.configured
        return data


def _get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    if row is None or row.value is None:
        return None
    if row.encrypted:
        return decrypt(row.value)
    return json.loads(row.value)


def _set(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key) or AppSetting(key=key)
    if key in SECRET_KEYS:
        row.value = encrypt(value) if value else None
        row.encrypted = True
    else:
        row.value = json.dumps(value)
        row.encrypted = False
    db.add(row)


def load_controller_settings(db: Session) -> ControllerSettings:
    cs = ControllerSettings()
    for name in cs.__dataclass_fields__:
        value = _get(db, f"controller.{name}" if name not in SECRET_KEYS else name)
        if value is not None:
            setattr(cs, name, value)
    return cs


def save_controller_settings(db: Session, updates: dict[str, Any]) -> ControllerSettings:
    current = load_controller_settings(db)
    for name, value in updates.items():
        if name not in current.__dataclass_fields__:
            continue
        if name in SECRET_KEYS:
            if value:  # empty value = keep existing secret
                _set(db, name, value)
            continue
        _set(db, f"controller.{name}", value)
    db.commit()
    return load_controller_settings(db)


def get_value(db: Session, key: str, default: Any = None) -> Any:
    value = _get(db, key)
    return default if value is None else value


def set_value(db: Session, key: str, value: Any) -> None:
    _set(db, key, value)
    db.commit()
