"""Logging setup with automatic redaction of secrets."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from .config import Settings

_SECRET_KEYS = (
    "client_secret|clientSecret|secret|password|passwd|psk|wpaPsk|accessToken|access_token|"
    "refreshToken|refresh_token|token|authorization|cookie|AccessToken"
)
_PATTERNS = [
    re.compile(rf'(?i)("?(?:{_SECRET_KEYS})"?\s*[:=]\s*"?)([^"\s,&}}]+)'),
    re.compile(r"(?i)(AccessToken=)([^\s,;]+)"),
    re.compile(r"(?i)(Bearer\s+)([^\s,;]+)"),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(r"\1***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        record.msg = redact(message)
        record.args = ()
        return True


def setup_logging(settings: Settings) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(settings.logs_dir / "omada_docs.log", maxBytes=5_000_000, backupCount=5)
        )
    except OSError:
        pass
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    # httpx logs full URLs at INFO; keep it quieter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
