"""REST API: authentication, CSRF, roles, network restrictions, manual documentation, search, export, import."""

from __future__ import annotations

import io
import zipfile

from .conftest import ADMIN

DEVICE = "40-ED-00-00-01-01"


def login(client, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_setup_login_and_csrf(client):
    assert client.get("/api/auth/state").json()["setup_required"] is True
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/auth/setup", json={"username": "admin", "password": "short"}).status_code in (400, 422)
    h = {"X-CSRF-Token": client.post("/api/auth/setup", json=ADMIN).json()["csrf_token"]}
    assert client.post("/api/auth/setup", json=ADMIN).status_code in (400, 403, 409)
    assert client.post("/api/sync").status_code == 403, "unsafe requests need the CSRF header"
    assert client.post("/api/sync", headers={**h, "Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/dashboard").status_code == 200
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/auth/login", json={**ADMIN, "password": "wrong-password"}).status_code == 401


def test_disallowed_network_is_rejected():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), client=("203.0.113.9", 4000)) as c:
        assert c.get("/api/auth/state").status_code == 403


def test_viewer_is_read_only(client, admin):
    r = client.post("/api/users", json={"username": "viewer", "password": "viewer-pass-1", "role": "viewer"},
                    headers=admin)
    assert r.status_code == 200, r.text
    client.post("/api/auth/logout", headers=admin)
    h = login(client, "viewer", "viewer-pass-1")
    assert client.get(f"/api/entities/device/{DEVICE}").status_code == 200
    assert client.put("/api/manual/descriptions/device/" + DEVICE, json={"description": "x"},
                      headers=h).status_code == 403
    assert client.post("/api/manual/documents", json={"title": "x", "body": "y"}, headers=h).status_code == 403
    assert client.get("/api/backup/app").status_code == 403
    assert client.get("/api/settings/controller").status_code == 403


def test_entities_detail_and_related(client, admin):
    for kind in ("device", "network", "wlan", "switch_port", "client", "acl_rule", "nat_rule", "wan", "ip_group"):
        r = client.get(f"/api/entities/{kind}")
        assert r.status_code == 200 and r.json()["items"], kind
    detail = client.get("/api/entities/network/net-server").json()
    assert detail["entity"]["vlan_id"] == 20
    assert detail["related"]["acl_rules"], "networks link to the ACL rules referencing them"
    assert client.get("/api/entities/network/does-not-exist").status_code == 404
    assert client.get("/api/entities/bogus").status_code in (400, 404)


def test_acl_topology_and_ip_search(client, admin):
    acl = client.get("/api/acl").json()
    assert acl["rules"] and acl["matrix"]["cells"]
    assert all(r["analysis"]["explanation"] for r in acl["rules"])
    topo = client.get("/api/topology").json()
    assert topo["nodes"] and topo["edges"]
    groups = {g["category"] for g in client.get("/api/search?q=192.168.20.5").json()["groups"]}
    assert "networks" in groups, "an IP must be matched to the subnet that contains it"


def test_manual_documentation_and_credential_guard(client, admin):
    url = "/api/manual/descriptions/network/net-server"
    r = client.put(url, json={"display_name": "Server LAN", "description": "NAS", "tags": ["core"]}, headers=admin)
    assert r.status_code == 200
    assert client.put(url, json={"notes": "password: hunter22"}, headers=admin).status_code in (400, 422)
    assert client.get("/api/entities/network/net-server").json()["manual"]["display_name"] == "Server LAN"
    assert client.get("/api/search?q=server lan").json()["total"] > 0
    assert client.get("/api/changes?kind=manual").json()["total"] >= 1

    doc = client.post("/api/manual/documents", headers=admin, json={
        "title": "Cabling", "body": "# Rack", "category": "cabling",
        "relationships": [{"target_type": "device", "target_key": DEVICE}]})
    assert doc.status_code == 200, doc.text
    did = doc.json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    att = client.post(f"/api/manual/documents/{did}/attachments", headers=admin,
                      files={"file": ("plan.png", png, "image/png")})
    assert att.status_code == 200, att.text
    dl = client.get(f"/api/manual/attachments/{att.json()['id']}")
    assert dl.content == png and "attachment" in dl.headers["content-disposition"]
    bad = client.post(f"/api/manual/documents/{did}/attachments", headers=admin,
                      files={"file": ("evil.html", b"<script>alert(1)</script>", "text/html")})
    assert bad.status_code in (400, 415, 422)


def test_exports(client, admin):
    expected = {"pdf": b"%PDF", "docx": b"PK", "html": b"<!DOCTYPE html", "csv": b""}
    for fmt, magic in expected.items():
        r = client.get(f"/api/export?format={fmt}")
        assert r.status_code == 200, (fmt, r.text[:200])
        assert r.content.startswith(magic), fmt
    client.put("/api/manual/descriptions/network/net-server", json={"notes": "=cmd|' /C calc'!A0"},
               headers=admin)
    csv = client.get("/api/export?format=csv&table=networks")
    if csv.content.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(csv.content)) as z:
            text = "".join(z.read(n).decode() for n in z.namelist())
    else:
        text = csv.text
    assert "=cmd" not in text.replace("'=cmd", ""), "CSV formula injection must be neutralised"


def test_backup_import(client, admin):
    cfg = client.post("/api/backup/import", headers=admin,
                      files={"file": ("backup.cfg", b"\x00\x01binary", "application/octet-stream")})
    assert cfg.json()["status"] == "rejected"
    dataset = client.get("/api/dataset/export")
    assert dataset.status_code == 200
    r = client.post("/api/backup/import", headers=admin,
                    files={"file": ("dataset.json", dataset.content, "application/json")})
    assert r.status_code == 200 and r.json()["status"] == "imported", r.text
    assert r.json()["comparison_counts"]["conflicts"] == 0, "re-importing our own export matches the API data"


def test_controller_settings_never_return_secret(client, admin):
    r = client.put("/api/settings/controller", headers=admin, json={
        "host": "https://omada.local:8043/path", "client_id": "abc", "client_secret": "s3cret-value"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["host"], body["port"], body["scheme"]) == ("omada.local", 8043, "https")
    assert body["client_secret_set"] is True
    assert "s3cret-value" not in client.get("/api/settings/controller").text
    assert "s3cret-value" not in client.get("/api/audit").text


def test_app_backup_and_restore(client, admin):
    client.put("/api/manual/descriptions/network/net-server", json={"description": "before backup"}, headers=admin)
    backup = client.get("/api/backup/app")
    assert backup.status_code == 200 and backup.content.startswith(b"PK")
    client.put("/api/manual/descriptions/network/net-server", json={"description": "after backup"}, headers=admin)
    r = client.post("/api/backup/restore", headers=admin, files={"file": ("b.zip", backup.content)})
    assert r.status_code == 200, r.text
    h = login(client, ADMIN["username"], ADMIN["password"])
    assert h
    assert client.get("/api/entities/network/net-server").json()["manual"]["description"] == "before backup"


def test_dashboard_changes_are_filtered_by_site(client, admin):
    from app.services.sync import run_sync

    from .conftest import run

    run(run_sync("manual"))
    for site in ("demo-site-home", "demo-site-office"):
        dash = client.get(f"/api/dashboard?site_id={site}").json()
        assert all(c["site_id"] in (site, None) for c in dash["recent_changes"]), site
