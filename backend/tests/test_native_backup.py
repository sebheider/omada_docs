"""Native Omada controller backups (.cfg): decryption, best-effort mapping and secret handling."""

from __future__ import annotations

import gzip
import json

import pytest

from app.omada.cfg_crypto import CfgError, decrypt_cfg, looks_like_cfg, rc4
from app.services.backup_import import parse_backup

SITE_ID = "64a1b2c3d4e5f60718293a4b"
SECRETS = ["SuperSecretPSK1", "R4diusS3cret!", "DevAdminPw1", "MailSecret99"]

NATIVE = {
    "mainInfo": {"controllerVersion": "5.15.24.21", "backupVersion": "3", "backupTime": 1_700_000_000_000,
                 "omadacId": "omadac-1"},
    "systemSetting": {"pbkdf2KeySaltIv": "0" * 96, "smtpPassword": "MailSecret99"},
    "sites": [{
        "site": {"_id": {"$oid": SITE_ID}, "name": "Office", "timeZone": "UTC"},
        "lanNetworks": [
            {"_id": {"$oid": "net-lan"}, "name": "LAN", "vlan": 1, "gatewaySubnet": "192.168.0.1/24", "purpose": 0},
            {"id": "net-iot", "name": "IoT", "vlan": 20, "gatewaySubnet": "10.20.0.1/24", "purpose": 0,
             "radiusSecret": "R4diusS3cret!"},
            {"id": "broken", "description": "no name -> skipped"},
        ],
        "wlans": [{"id": "w1", "name": "Default"}],
        "ssids": [{"id": "s1", "name": "CorpWiFi", "wlanId": "w1", "security": 3, "band": 3, "ssidEnable": True,
                   "vlanEnable": True, "vlanId": 20, "pskSetting": {"securityKey": "SuperSecretPSK1", "versionPsk": 2}}],
        "portForwardings": [{"id": "pf1", "name": "Web", "status": 1, "protocol": 1, "externalPort": "443",
                             "forwardIp": "192.168.0.10", "forwardPort": "443"}],
        "gatewayAcls": [{"id": "a1", "name": "Block IoT", "policy": 0, "status": 1, "sourceType": 0,
                         "sourceIds": ["net-iot"], "destinationType": 0, "destinationIds": ["net-lan"],
                         "direction": {"lanToLan": True}}],
        "dashboardLayout": {"widgets": [{"x": 1}]},
        "deviceAccount": {"username": "admin", "password": "DevAdminPw1"},
    }],
    "deviceBriefInfo": [
        {"mac": "AA:BB:CC:00:11:22", "model": "EAP650", "name": "AP-1", "siteId": SITE_ID, "sn": "v2#AAAA"},
        {"mac": "aa-bb-cc-00-11-33", "model": "TL-SG2008P", "name": "DevAdminPw1", "site": "Office"},
        {"mac": "not-a-mac", "name": "garbage"},
    ],
    "role": [{"name": "admin"}],
    "tenant": {"name": "t"},
}


def make_cfg(doc: dict) -> bytes:
    """Build a .cfg like the controller does: RC4(GZIP(JSON)) – RC4 is symmetric."""
    return rc4(gzip.compress(json.dumps(doc).encode(), mtime=0))


def test_rc4_key_matches_known_backup_prefix():
    # Every controller backup starts with these bytes (Java gzip header encrypted with the static key).
    assert rc4(bytes.fromhex("1f8b08000000000000ff")) == bytes.fromhex("a55e94e75ee5c8e7b536")


def test_decrypt_roundtrip_and_invalid_input():
    cfg = make_cfg(NATIVE)
    assert looks_like_cfg(cfg) and not looks_like_cfg(b'{"a": 1}')
    assert json.loads(decrypt_cfg(cfg)) == NATIVE
    with pytest.raises(CfgError, match="could not be decrypted"):
        decrypt_cfg(b"\x00\x01 this is not a backup at all")
    with pytest.raises(CfgError, match="truncated"):
        decrypt_cfg(cfg[: len(cfg) // 2])
    bomb = rc4(gzip.compress(b"0" * 300_000))
    with pytest.raises(CfgError, match="maximum size"):
        decrypt_cfg(bomb, max_size=100_000)


def test_native_backup_mapping():
    r = parse_backup("controller.cfg", make_cfg(NATIVE))
    assert r["status"] == "imported", r["errors"]
    assert r["detected_format"] == "omada-native-backup"
    assert (r["controller_version"], r["backup_version"]) == ("5.15.24.21", "3")
    ents = r["entities"]
    counts = r["summary"]["counts"]
    assert {k: counts[k] for k in ("site", "network", "wlan", "device", "nat_rule", "acl_rule")} == {
        "site": 1, "network": 2, "wlan": 1, "device": 2, "nat_rule": 1, "acl_rule": 1}
    assert ents["site"][0]["key"] == SITE_ID
    wlan = ents["wlan"][0]
    assert (wlan["ssid"], wlan["wlan_group"], wlan["security"], wlan["network_name"]) == (
        "CorpWiFi", "Default", "WPA-Personal", "IoT")
    devices = {d["mac"]: d for d in ents["device"]}
    assert devices["AA-BB-CC-00-11-22"]["type"] == "ap"
    assert devices["AA-BB-CC-00-11-33"]["type"] == "switch"
    acl = ents["acl_rule"][0]
    assert [x["name"] for x in acl["source"]["refs"]] == ["IoT"]
    areas = {u["area"] for u in r["unsupported"]}
    assert {"role", "tenant", "sites[Office].dashboardLayout"} <= areas
    assert "sites[Office].lanNetworks" not in areas
    text = " ".join(r["warnings"])
    assert "best effort" in text and "'v2#'" in text and "redacted" in text and "lan_networks: 1" in text


def test_native_backup_never_leaks_secrets(client, admin, db):
    from app.models.system import ConfigSnapshot

    r = client.post("/api/backup/import", headers=admin,
                    files={"file": ("controller.cfg", make_cfg(NATIVE), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["status"] == "imported", r.text
    snap = db.get(ConfigSnapshot, r.json()["snapshot_id"])
    stored = json.dumps(snap.data) + r.text + client.get(f"/api/backup/imports/{r.json()['id']}").text
    for secret in SECRETS:
        assert secret not in stored
    assert "v2#AAAA" not in stored


def test_decrypted_native_json_and_unknown_binary():
    r = parse_backup("backup.json", json.dumps(NATIVE).encode())
    assert (r["status"], r["detected_format"]) == ("imported", "omada-native-backup-json"), r["errors"]
    r = parse_backup("random.bin", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert (r["status"], r["detected_format"]) == ("rejected", "unknown")
    r = parse_backup("other.cfg", make_cfg({"something": "else"}))
    assert r["status"] == "rejected" and "not recognised" in r["errors"][0]
