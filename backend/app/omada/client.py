"""Read-only HTTP client for the TP-Link Omada Open API (northbound API).

Verified behaviour (see docs/omada-api.md):

* ``GET {base}/api/info`` (no auth) returns ``result.omadacId`` / ``controllerVer`` / ``apiVer``.
* ``POST {base}/openapi/authorize/token?grant_type=client_credentials`` with JSON body
  ``{"omadacId", "client_id", "client_secret"}`` returns ``accessToken`` / ``expiresIn``.
* Requests carry ``Authorization: AccessToken=<token>``.
* Envelope ``{"errorCode": 0, "msg": "...", "result": ...}``; grid endpoints are paged with
  ``page`` (1-based) and ``pageSize`` and return ``{totalRows, currentPage, currentSize, data}``.

The only non-GET request this client ever sends is the token request. There is deliberately
no generic method for POST/PUT/PATCH/DELETE, which guarantees the controller is never modified.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

TOKEN_EXPIRED_CODES = {-44112, -44113}
UNSUPPORTED_CODES = {-1600}
PERMISSION_CODES = {-1005, -1505, -44118}
AUTH_FAILED_CODES = {-44106, -44116, -44111, -44114}


class OmadaError(Exception):
    def __init__(self, message: str, code: int | None = None, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class OmadaConnectionError(OmadaError):
    pass


class OmadaAuthError(OmadaError):
    pass


class OmadaUnsupportedError(OmadaError):
    """Endpoint not available on this controller version (-1600 / HTTP 404)."""


class OmadaPermissionError(OmadaError):
    pass


@dataclass
class ControllerInfo:
    omadac_id: str
    controller_version: str | None
    api_version: str | None
    raw: dict[str, Any]


class RateLimiter:
    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if not self.min_interval:
            return
        async with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class OmadaClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        omadac_id: str = "",
        api_version: str = "v1",
        verify_ssl: bool = True,
        timeout: float = 20.0,
        max_requests_per_second: float = 5.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
        page_size: int = 100,
    ):
        self.base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self.omadac_id = omadac_id
        self.api_version = api_version or "v1"
        self.max_retries = max_retries
        self.page_size = page_size
        self._token: str | None = None
        self._token_expiry = 0.0
        self._limiter = RateLimiter(max_requests_per_second)
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "omada-docs/0.1 (read-only)"},
            follow_redirects=False,
        )
        self.request_count = 0

    async def __aenter__(self) -> "OmadaClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ low level

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        attempt = 0
        while True:
            await self._limiter.wait()
            self.request_count += 1
            try:
                resp = await self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise OmadaConnectionError(f"Connection to controller failed: {exc.__class__.__name__}: {exc}")
                await self._backoff(attempt, f"transport error {exc.__class__.__name__}")
                attempt += 1
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self.max_retries:
                    return resp
                retry_after = resp.headers.get("Retry-After")
                await self._backoff(attempt, f"HTTP {resp.status_code}", retry_after)
                attempt += 1
                continue
            return resp

    async def _backoff(self, attempt: int, reason: str, retry_after: str | None = None) -> None:
        delay = min(30.0, 1.0 * (2**attempt))
        if retry_after and retry_after.isdigit():
            delay = min(60.0, float(retry_after))
        log.warning("Omada request retry %s in %.1fs (%s)", attempt + 1, delay, reason)
        await asyncio.sleep(delay)

    @staticmethod
    def _parse(resp: httpx.Response, path: str) -> Any:
        if resp.status_code == 404:
            raise OmadaUnsupportedError(f"{path}: not available (HTTP 404)", http_status=404)
        if resp.status_code in (401, 403):
            raise OmadaAuthError(f"{path}: HTTP {resp.status_code}", http_status=resp.status_code)
        if resp.status_code >= 400:
            raise OmadaError(f"{path}: HTTP {resp.status_code}", http_status=resp.status_code)
        try:
            body = resp.json()
        except ValueError as exc:
            raise OmadaError(f"{path}: response is not JSON") from exc
        if not isinstance(body, dict):
            raise OmadaError(f"{path}: unexpected response format")
        code = body.get("errorCode", 0)
        if code != 0:
            msg = str(body.get("msg") or "")[:200]
            if code in TOKEN_EXPIRED_CODES:
                raise OmadaAuthError(f"{path}: access token expired ({code})", code=code)
            if code in AUTH_FAILED_CODES:
                raise OmadaAuthError(f"{path}: authentication failed ({code}: {msg})", code=code)
            if code in UNSUPPORTED_CODES:
                raise OmadaUnsupportedError(f"{path}: not supported by this controller ({code})", code=code)
            if code in PERMISSION_CODES:
                raise OmadaPermissionError(f"{path}: permission denied ({code}: {msg})", code=code)
            raise OmadaError(f"{path}: error {code}: {msg}", code=code)
        return body.get("result")

    # ------------------------------------------------------------------ auth

    async def get_info(self) -> ControllerInfo:
        resp = await self._send("GET", "/api/info")
        result = self._parse(resp, "/api/info") or {}
        omadac_id = result.get("omadacId") or self.omadac_id
        if not omadac_id:
            raise OmadaError("Controller did not report an omadacId")
        if not self.omadac_id:
            self.omadac_id = omadac_id
        return ControllerInfo(omadac_id, result.get("controllerVer"), result.get("apiVer"), result)

    async def authenticate(self) -> None:
        if not self.omadac_id:
            await self.get_info()
        resp = await self._send(
            "POST",
            "/openapi/authorize/token",
            params={"grant_type": "client_credentials"},
            json={"omadacId": self.omadac_id, "client_id": self._client_id, "client_secret": self._client_secret},
        )
        try:
            result = self._parse(resp, "/openapi/authorize/token") or {}
        except OmadaAuthError:
            raise
        except OmadaError as exc:
            raise OmadaAuthError(f"Authentication failed: {exc}", code=exc.code) from exc
        token = result.get("accessToken")
        if not token:
            raise OmadaAuthError("Authentication failed: no access token returned")
        self._token = token
        expires_in = int(result.get("expiresIn") or 7200)
        self._token_expiry = time.monotonic() + max(60, expires_in - 120)
        log.info("Authenticated against Omada controller (token valid for %ss)", expires_in)

    @property
    def authenticated(self) -> bool:
        return bool(self._token) and time.monotonic() < self._token_expiry

    # ------------------------------------------------------------------ read API

    def _url(self, path: str, version: str | None = None) -> str:
        return f"/openapi/{version or self.api_version}/{self.omadac_id}{path}"

    async def get(self, path: str, params: dict[str, Any] | None = None, version: str | None = None) -> Any:
        if not self.authenticated:
            await self.authenticate()
        url = self._url(path, version)
        for attempt in range(2):
            resp = await self._send("GET", url, params=params, headers={"Authorization": f"AccessToken={self._token}"})
            try:
                return self._parse(resp, path)
            except OmadaAuthError as exc:
                if attempt == 0 and (exc.code in TOKEN_EXPIRED_CODES or exc.http_status == 401):
                    await self.authenticate()
                    continue
                raise
        return None  # pragma: no cover

    async def get_all(self, path: str, params: dict[str, Any] | None = None, max_pages: int = 200) -> list[Any]:
        """Fetch every page of a grid endpoint. Also accepts endpoints returning plain arrays."""
        items: list[Any] = []
        page = 1
        while page <= max_pages:
            result = await self.get(path, {**(params or {}), "page": page, "pageSize": self.page_size})
            if result is None:
                break
            if isinstance(result, list):
                return result
            data = result.get("data") or []
            items.extend(data)
            total = result.get("totalRows")
            if not data or (total is not None and len(items) >= int(total)) or len(data) < self.page_size:
                break
            page += 1
        return items
