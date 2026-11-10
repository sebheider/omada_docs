"""Application configuration loaded from environment variables (prefix ``OMADA_DOCS_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMADA_DOCS_", env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    database_url: str | None = None
    # Path prefix when served behind a reverse proxy sub-path, e.g. "/omada-docs".
    base_path: str = ""
    log_level: str = "INFO"
    # Demo mode serves generated mock data instead of contacting a controller.
    demo_mode: bool = False
    # Optional explicit encryption/session secret. Generated and stored in data_dir if empty.
    secret_key: str | None = None
    session_hours: int = 12
    cookie_secure: bool = False
    # Comma separated CIDRs allowed to access the UI. Default: private networks + loopback.
    allowed_networks: str = (
        "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1/128,fc00::/7,fe80::/10"
    )
    # Reverse-proxy integration
    trusted_proxies: str = ""
    proxy_auth_header: str = ""  # e.g. "Remote-User"; only honoured from trusted proxies
    proxy_auth_default_role: str = "viewer"
    # Initial administrator (optional; otherwise created through the first-run setup page)
    admin_username: str | None = None
    admin_password: str | None = None
    max_upload_mb: int = 20
    frontend_dir: Path = Field(default=Path(__file__).resolve().parents[2] / "static")

    @field_validator("base_path")
    @classmethod
    def _normalise_base_path(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and not v.startswith("/"):
            v = "/" + v
        return v

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'omada_docs.db'}"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.attachments_dir, self.logs_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
