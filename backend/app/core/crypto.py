"""Encryption of secrets at rest (Fernet / AES-128-CBC + HMAC)."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _load_master_secret() -> bytes:
    settings = get_settings()
    if settings.secret_key:
        return settings.secret_key.encode()
    key_file = settings.data_dir / "secret.key"
    if key_file.exists():
        return key_file.read_bytes().strip()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48).encode()
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(value)
    return value


@lru_cache
def master_secret() -> bytes:
    return _load_master_secret()


@lru_cache
def _fernet() -> Fernet:
    digest = hashlib.sha256(b"omada-docs-credential-encryption:" + master_secret()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
