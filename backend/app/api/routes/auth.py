"""Authentication: first-run setup, login/logout, session info, password change and user management."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, client_ip, get_current_user, require_admin
from app.core.config import get_settings
from app.core.security import (
    hash_password,
    new_token,
    token_hash,
    validate_password_strength,
    verify_password,
)
from app.db.session import get_db
from app.models.system import User, UserSession
from app.services.manual import audit

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

# Simple in-memory brute-force protection: max failures per (ip) and per (username) in a sliding window.
_FAIL_WINDOW = 15 * 60
_FAIL_LIMIT = 8
_failures: dict[str, deque[float]] = defaultdict(deque)


def _too_many(*keys: str) -> bool:
    now = time.monotonic()
    for k in keys:
        q = _failures[k]
        while q and now - q[0] > _FAIL_WINDOW:
            q.popleft()
        if len(q) >= _FAIL_LIMIT:
            return True
    return False


def _record_failure(*keys: str) -> None:
    now = time.monotonic()
    for k in keys:
        _failures[k].append(now)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "auth_source": u.auth_source,
            "is_active": u.is_active, "created_at": u.created_at, "last_login": u.last_login}


def _cookie_path() -> str:
    return get_settings().base_path or "/"


def _start_session(db: Session, user: User, request: Request, response: Response) -> str:
    settings = get_settings()
    token, csrf = new_token(), new_token()
    now = datetime.now(timezone.utc)
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.add(UserSession(id=token_hash(token), user_id=user.id, csrf_token=csrf,
                       expires_at=now + timedelta(hours=settings.session_hours), ip=client_ip(request)))
    user.last_login = now
    max_age = settings.session_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="strict",
                        secure=settings.cookie_secure, path=_cookie_path())
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="strict",
                        secure=settings.cookie_secure, path=_cookie_path())
    return csrf


@router.get("/state")
def auth_state(request: Request, db: Session = Depends(get_db)) -> dict:
    """Public endpoint used by the UI to decide between setup, login and the application."""
    settings = get_settings()
    setup_required = not db.scalar(select(func.count(User.id)))
    user = None
    csrf = None
    try:
        u = get_current_user(request, db)
        user = _user_dict(u)
        token = request.cookies.get(SESSION_COOKIE)
        sess = db.get(UserSession, token_hash(token)) if token else None
        csrf = sess.csrf_token if sess else None
    except HTTPException:
        pass
    return {"setup_required": setup_required and not settings.proxy_auth_header, "user": user, "csrf_token": csrf,
            "demo_mode": settings.demo_mode, "version": __version__, "auth_mode": getattr(request.state, "auth", None)}


@router.post("/setup")
def setup(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """Create the first administrator. Only possible while no user exists."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "Setup has already been completed.")
    if err := validate_password_strength(body.password):
        raise HTTPException(422, err)
    user = User(username=body.username.strip(), password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.flush()
    csrf = _start_session(db, user, request, response)
    audit(db, user, "auth.setup", ip=client_ip(request))
    db.commit()
    return {"user": _user_dict(user), "csrf_token": csrf}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request) or "unknown"
    keys = (f"ip:{ip}", f"user:{body.username.lower()}")
    if _too_many(*keys):
        raise HTTPException(429, "Too many failed login attempts. Please wait a few minutes.")
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        if user is None:
            verify_password(body.password, hash_password("timing-equaliser"))
        _record_failure(*keys)
        audit(db, None, "auth.login_failed", "user", body.username[:64], ip=ip)
        db.commit()
        raise HTTPException(401, "Invalid username or password.")
    for k in keys:
        _failures.pop(k, None)
    csrf = _start_session(db, user, request, response)
    audit(db, user, "auth.login", ip=ip)
    db.commit()
    return {"user": _user_dict(user), "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.id == token_hash(token)))
    audit(db, user, "auth.logout", ip=client_ip(request))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path=_cookie_path())
    response.delete_cookie(CSRF_COOKIE, path=_cookie_path())
    return {"ok": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(max_length=256)


@router.post("/password")
def change_password(body: PasswordChange, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    if user.auth_source != "local":
        raise HTTPException(400, "Users authenticated by the reverse proxy have no local password.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "The current password is incorrect.")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(422, err)
    user.password_hash = hash_password(body.new_password)
    token = request.cookies.get(SESSION_COOKIE)
    # invalidate all other sessions of this user
    db.execute(delete(UserSession).where(UserSession.user_id == user.id,
                                         UserSession.id != (token_hash(token) if token else "")))
    audit(db, user, "auth.password_changed", "user", user.username, ip=client_ip(request))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ user management (admin)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(max_length=256)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    role: Literal["admin", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


@users_router.get("")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    return [_user_dict(u) for u in db.scalars(select(User).order_by(User.username)).all()]


@users_router.post("")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> dict:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "A user with this name already exists.")
    if err := validate_password_strength(body.password):
        raise HTTPException(422, err)
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    audit(db, admin, "user.create", "user", body.username, {"role": body.role}, client_ip(request))
    db.commit()
    return _user_dict(u)


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))) or 0


@users_router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    demoting = (body.role == "viewer" and u.role == "admin") or (body.is_active is False and u.role == "admin")
    if demoting and u.is_active and _active_admins(db) <= 1:
        raise HTTPException(400, "At least one active administrator is required.")
    changes = {}
    if body.role is not None:
        u.role, changes["role"] = body.role, body.role
    if body.is_active is not None:
        u.is_active, changes["is_active"] = body.is_active, body.is_active
        if not body.is_active:
            db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    if body.password:
        if u.auth_source != "local":
            raise HTTPException(400, "Proxy users have no local password.")
        if err := validate_password_strength(body.password):
            raise HTTPException(422, err)
        u.password_hash = hash_password(body.password)
        db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        changes["password"] = "reset"
    audit(db, admin, "user.update", "user", u.username, changes, client_ip(request))
    db.commit()
    return _user_dict(u)


@users_router.delete("/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account.")
    if u.role == "admin" and u.is_active and _active_admins(db) <= 1:
        raise HTTPException(400, "At least one active administrator is required.")
    db.delete(u)
    audit(db, admin, "user.delete", "user", u.username, ip=client_ip(request))
    db.commit()
    return {"ok": True}
