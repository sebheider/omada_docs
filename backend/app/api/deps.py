"""FastAPI dependencies: current user, roles, CSRF protection, client IP resolution."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ip_in_networks, token_hash
from app.db.session import get_db
from app.models.system import User, UserSession

SESSION_COOKIE = "omada_docs_session"
CSRF_COOKIE = "omada_docs_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def client_ip(request: Request) -> str | None:
    """Return the real client IP, honouring X-Forwarded-For only from trusted proxies."""
    settings = get_settings()
    peer = request.client.host if request.client else None
    if peer and settings.trusted_proxies and ip_in_networks(peer, settings.trusted_proxies):
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            # right-most address not belonging to a trusted proxy
            for hop in reversed([h.strip() for h in fwd.split(",") if h.strip()]):
                if not ip_in_networks(hop, settings.trusted_proxies):
                    return hop
    return peer


def _proxy_user(request: Request, db: Session) -> User | None:
    settings = get_settings()
    if not settings.proxy_auth_header or not settings.trusted_proxies:
        return None
    peer = request.client.host if request.client else None
    if not ip_in_networks(peer, settings.trusted_proxies):
        return None
    username = request.headers.get(settings.proxy_auth_header, "").strip()
    if not username:
        return None
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        role = "admin" if settings.proxy_auth_default_role == "admin" else "viewer"
        user = User(username=username[:64], role=role, auth_source="proxy", password_hash=None)
        db.add(user)
        db.commit()
    return user if user.is_active else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _proxy_user(request, db)
    if user is not None:
        request.state.auth = "proxy"
        request.state.user = user
        return user
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    sess = db.get(UserSession, token_hash(token))
    now = datetime.now(timezone.utc)
    if sess is None or _aware(sess.expires_at) < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER)
        if not header or header != sess.csrf_token:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    request.state.auth = "session"
    request.state.user = user
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return user


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
