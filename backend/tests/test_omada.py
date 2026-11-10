"""Omada client, collector and parser behaviour against the simulated controller."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.omada.client import OmadaAuthError, OmadaClient
from app.omada.collector import Collector
from app.omada.mock import SITE_ID, DemoController
from app.omada.parsers import normalize, sanitize


def collect(demo: DemoController, **kw) -> dict:
    async def go():
        async with OmadaClient("https://demo.local", demo.client_id, demo.client_secret,
                               transport=demo.transport(), max_requests_per_second=1000, **kw) as c:
            return await Collector(c).collect()

    return asyncio.run(go())


def test_sanitize_removes_secrets_recursively():
    data = {"name": "x", "psk": "p", "securityKey": "secret1", "radiusPwd": "r", "nested": {"password": "pw", "ok": 1,
                                                                    "list": [{"preSharedKey": "k", "v": 2}]}}
    assert sanitize(data) == {"name": "x", "nested": {"ok": 1, "list": [{"v": 2}]}}


def test_collect_and_normalize_demo_controller():
    demo = DemoController()
    raw = collect(demo)
    assert all(m == "GET" for m, p in demo.requests if p.startswith("/openapi/v1")), "API access must be read-only"
    entities = normalize(raw, "demo.local")
    for kind in ("device", "network", "wlan", "switch_port", "client", "acl_rule", "nat_rule", "ip_group"):
        assert entities[kind], kind
    dumped = json.dumps(entities)
    for secret in ("AT-demo-token", "RT-demo", "\"psk\"", "\"password\""):
        assert secret not in dumped
    nets = {n["key"]: n for n in entities["network"] if n["site_id"] == SITE_ID}
    assert nets["net-server"]["vlan_id"] == 20 and nets["net-server"]["subnet"] == "192.168.20.0/24"
    # ACL sides with empty references become "any"; NAT entries keep their own type field
    assert all(r["source"]["type"] for r in entities["acl_rule"])
    assert {n["nat_type"] for n in entities["nat_rule"]} <= {"port_forwarding", "one_to_one"}


def test_endpoint_failure_is_isolated():
    raw = collect(DemoController(fail_paths=("/lan-networks",)), max_retries=0)
    results = raw["endpoint_results"]
    assert any(r["endpoint"].startswith("lan") and r["status"] == "error" for r in results)
    assert any(r["status"] == "ok" for r in results)
    assert normalize(raw)["device"], "other endpoints must still be collected"


def test_unsupported_endpoints_on_old_controller():
    raw = collect(DemoController(pre_60=True))
    assert any(r["status"] == "unsupported" for r in raw["endpoint_results"])


def test_invalid_credentials_raise_auth_error():
    demo = DemoController()

    async def go():
        async with OmadaClient("https://demo.local", "wrong", "wrong", transport=demo.transport(),
                               max_requests_per_second=1000) as c:
            await c.authenticate()

    with pytest.raises(OmadaAuthError):
        asyncio.run(go())
