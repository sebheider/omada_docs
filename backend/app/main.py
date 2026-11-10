"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import func, select, text

from app import __version__
from app.api.deps import SAFE_METHODS, client_ip
from app.api.routes import admin, auth, changes, data, manual
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import hash_password, ip_in_networks, validate_password_strength
from app.db import session as db_session
from app.db.migrate import upgrade_to_head
from app.models.system import SyncHistory, User
from app.services import scheduler, sync

log = logging.getLogger("omada_docs")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
       "object-src 'none'")


def _bootstrap_admin() -> None:
    settings = get_settings()
    if not (settings.admin_username and settings.admin_password):
        return
    with db_session.SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            return
        if err := validate_password_strength(settings.admin_password):
            log.error("OMADA_DOCS_ADMIN_PASSWORD rejected: %s", err)
            return
        db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password),
                    role="admin"))
        db.commit()
        log.info("Initial administrator '%s' created from environment", settings.admin_username)


async def _initial_demo_sync() -> None:
    with db_session.SessionLocal() as db:
        if db.scalar(select(func.count(SyncHistory.id))):
            return
    try:
        await sync.run_sync("startup")
    except Exception:  # noqa: BLE001
        log.exception("Initial demo synchronisation failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()
    db_session.init_engine()
    upgrade_to_head()
    _bootstrap_admin()
    with db_session.SessionLocal() as db:
        # A sync that was interrupted by a restart can never finish – mark it as failed.
        for h in db.scalars(select(SyncHistory).where(SyncHistory.status == "running")).all():
            h.status, h.error = "failed", "Interrupted by application restart"
        db.commit()
    scheduler.start()
    tasks = []
    if settings.demo_mode:
        log.warning("DEMO MODE: serving generated example data – no controller is contacted")
        tasks.append(asyncio.create_task(_initial_demo_sync()))
    log.info("Omada Docs %s started (data dir %s)", __version__, settings.data_dir)
    yield
    scheduler.shutdown()
    for t in tasks:
        t.cancel()
    db_session.get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Omada Network Documentation Platform", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
                  root_path=settings.base_path)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        ip = client_ip(request)
        if not ip_in_networks(ip, settings.allowed_networks):
            log.warning("Rejected request from %s (not in allowed networks)", ip)
            return JSONResponse({"detail": "Access from this network is not allowed."}, status_code=403)
        if request.method not in SAFE_METHODS:
            # Defence in depth against cross-site requests (in addition to SameSite cookies and CSRF tokens).
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request rejected."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != "null":
                host = request.headers.get("x-forwarded-host") if ip_in_networks(
                    request.client.host if request.client else None, settings.trusted_proxies or "") else None
                host = host or request.headers.get("host")
                if origin.split("://", 1)[-1] != host:
                    return JSONResponse({"detail": "Cross-origin request rejected."}, status_code=403)
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    for r in (auth.router, auth.users_router, admin.router, data.router, manual.router, changes.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict:
        try:
            with db_session.get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": db_ok, "version": __version__,
                "sync_running": sync.is_running(), "demo_mode": settings.demo_mode}

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(path: str) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    _mount_frontend(app, settings.frontend_dir)
    return app


def _mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built single-page application with index.html fallback for client-side routes."""
    root = root.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") \
                    else {}
                return FileResponse(candidate, headers=headers)
        if index.is_file():
            html = index.read_text(encoding="utf-8")
            base = get_settings().base_path
            # The UI reads the base path from <base href>; inject the configured prefix.
            html = html.replace('<base href="/" />', f'<base href="{base}/" />')
            return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Frontend not built. API available under /api."}, status_code=404)


app = create_app()
