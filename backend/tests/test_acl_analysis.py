"""ACL interpretation and communication matrix on small synthetic datasets."""

from __future__ import annotations

from app.services.acl_analysis import analyze

SITE = "s1"


def net(key: str, name: str, vlan: int, subnet: str, **kw) -> dict:
    return {"kind": "network", "key": key, "controller_id": key, "site_id": SITE, "name": name, "vlan_id": vlan,
            "subnet": subnet, "purpose": "interface", **kw}


NAMES = {"a": "Home", "b": "IoT", "c": "Servers"}


def rule(idx: int, action: str, src: str | None, dst: str | None, negate_dst: bool = False, **kw) -> dict:
    def side(ref, negate=False):
        if ref is None:
            return {"type": "any", "negate": False, "refs": []}
        return {"type": "network", "negate": negate,
                "refs": [{"id": ref, "name": NAMES.get(ref, ref), "resolved": True}]}

    return {"kind": "acl_rule", "key": f"gateway:r{idx}", "controller_id": f"r{idx}", "site_id": SITE,
            "name": f"Rule {idx}", "acl_type": "gateway", "index": idx, "enabled": kw.pop("enabled", True),
            "action": action, "protocols": kw.pop("protocols", ["all"]), "directions": ["lan_to_lan"],
            "direction": "lan_to_lan", "source": side(src), "destination": side(dst, negate_dst), **kw}


NETS = [net("a", "Home", 10, "192.168.10.0/24"), net("b", "IoT", 30, "192.168.30.0/24"),
        net("c", "Servers", 20, "192.168.20.0/24")]


def cell(result, src, dst):
    return next(c for c in result["matrix"]["cells"]
                if c["source"] == f"network:{src}" and c["destination"] == f"network:{dst}")


def test_default_allows_lan_to_lan():
    result = analyze({"network": NETS, "acl_rule": []}, SITE)
    c = cell(result, "a", "b")
    assert c["status"] == "allowed" and c["basis"] == "default"


def test_deny_rule_blocks_and_is_explained():
    result = analyze({"network": NETS, "acl_rule": [rule(1, "deny", "b", "a")]}, SITE)
    assert cell(result, "b", "a")["status"] == "blocked"
    assert cell(result, "a", "b")["status"] == "allowed"
    info = result["rules"][0]
    assert info["confidence"] == "high"
    assert "IoT" in info["explanation"] and "Home" in info["explanation"]


def test_earlier_allow_restricts_later_deny():
    rules = [rule(1, "allow", "b", "c", protocols=["tcp"], destination_ports=["53"]), rule(2, "deny", "b", None)]
    rules[0]["destination"]["ports"] = ["53"]
    result = analyze({"network": NETS, "acl_rule": rules}, SITE)
    assert cell(result, "b", "c")["status"] == "restricted"
    assert cell(result, "b", "a")["status"] == "blocked"


def test_shadowed_rule_is_detected():
    rules = [rule(1, "deny", "b", None), rule(2, "allow", "b", "a")]
    result = analyze({"network": NETS, "acl_rule": rules}, SITE)
    second = next(r for r in result["rules"] if r["key"] == "gateway:r2")
    assert second["shadowed_by"] and "gateway:r1" in second["shadowed_by"]


def test_negated_destination():
    result = analyze({"network": NETS, "acl_rule": [rule(1, "deny", "b", "c", negate_dst=True)]}, SITE)
    assert cell(result, "b", "a")["status"] == "blocked"
    assert cell(result, "b", "c")["status"] == "allowed"
    assert "NOT" in result["rules"][0]["technical"]


def test_disabled_rule_has_no_effect():
    result = analyze({"network": NETS, "acl_rule": [rule(1, "deny", "b", "a", enabled=False)]}, SITE)
    assert cell(result, "b", "a")["status"] == "allowed"
    assert "DISABLED" in result["rules"][0]["technical"]


def test_unknown_reference_reduces_confidence():
    r = rule(1, "deny", "b", "zzz")
    r["destination"]["refs"][0]["resolved"] = False
    result = analyze({"network": NETS, "acl_rule": [r]}, SITE)
    assert result["rules"][0]["confidence"] != "high"
    assert result["rules"][0]["confidence_reasons"]
