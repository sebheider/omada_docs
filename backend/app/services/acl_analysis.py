"""ACL interpretation, explanation and communication-matrix calculation.

All results are derived from the normalised ACL rules of the current dataset. Nothing is
hard-coded: when the effect of a rule cannot be determined reliably, the result is flagged
with a reduced confidence instead of guessing.

Normalised ACL rule format (produced by ``app.omada.parsers``)::

    {
      "key": "...", "acl_type": "gateway|switch|eap", "index": 1, "name": "...",
      "enabled": true, "action": "allow|deny|unknown", "protocols": ["all"] | ["tcp", ...],
      "direction": "lan_to_lan|lan_to_wan|wan_in|unknown",
      "source":      {"type": "any|network|ip_group|ip_port_group|ip|mac_group|ssid|unknown",
                      "refs": [{"id": "...", "name": "..."}]},
      "destination": {... same ...},
      "description": "..."
    }
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.i18n import t

Net = ipaddress.IPv4Network | ipaddress.IPv6Network

FULL, PARTIAL, NONE, UNKNOWN = "full", "partial", "none", "unknown"
INTERNET = "internet"


@dataclass
class Segment:
    id: str
    type: str  # network | group | internet
    name: str
    cidrs: list[Net] = field(default_factory=list)
    vlan_id: int | None = None
    guest: bool = False
    ref_id: str | None = None  # controller id of the referenced object


@dataclass
class Context:
    networks: dict[str, dict[str, Any]]  # by controller_id
    groups: dict[str, dict[str, Any]]  # by controller_id
    segments: list[Segment]
    guest_network_ids: set[str]
    nat_rules: list[dict[str, Any]]
    lang: str = "en"


def _net(value: Any) -> Net | None:
    if not value:
        return None
    try:
        return ipaddress.ip_network(str(value), strict=False)
    except ValueError:
        return None


def _group_cidrs(group: dict[str, Any]) -> list[Net]:
    out = []
    for entry in group.get("entries") or []:
        n = _net(entry.get("ip") if isinstance(entry, dict) else entry)
        if n:
            out.append(n)
    return out


def build_context(dataset: dict[str, list[dict[str, Any]]], site_id: str | None = None,
                  lang: str = "en") -> Context:
    def site_items(kind: str) -> list[dict[str, Any]]:
        return [o for o in dataset.get(kind, []) if site_id is None or o.get("site_id") == site_id]

    networks = {str(n.get("controller_id") or n["key"]): n for n in site_items("network")}
    groups = {str(g.get("controller_id") or g["key"]): g for g in site_items("ip_group")}
    guest_ids = {
        str(w.get("network_id")) for w in site_items("wlan") if w.get("guest") and w.get("network_id")
    }
    segments: list[Segment] = []
    for nid, n in sorted(networks.items(), key=lambda kv: (kv[1].get("vlan_id") or 0, kv[1].get("name") or "")):
        cidr = _net(n.get("subnet"))
        segments.append(Segment(
            id=f"network:{nid}", type="network", name=n.get("name") or nid,
            cidrs=[cidr] if cidr else [], vlan_id=n.get("vlan_id"),
            guest=bool(n.get("purpose") == "guest" or nid in guest_ids), ref_id=nid,
        ))
    used_groups: set[str] = set()
    for rule in site_items("acl_rule"):
        for side in (rule.get("source") or {}, rule.get("destination") or {}):
            if side.get("type") in ("ip_group", "ip_port_group"):
                used_groups.update(str(r.get("id")) for r in side.get("refs") or [])
    for gid in sorted(used_groups):
        g = groups.get(gid)
        segments.append(Segment(
            id=f"group:{gid}", type="group", name=(g or {}).get("name") or gid,
            cidrs=_group_cidrs(g) if g else [], ref_id=gid,
        ))
    segments.append(Segment(id=INTERNET, type="internet", name="Internet"))
    return Context(networks, groups, segments, guest_ids, site_items("nat_rule"), lang)


# --------------------------------------------------------------------------- coverage


def _cidr_relation(rule_cidrs: list[Net], seg_cidrs: list[Net]) -> str:
    """How much of the segment address space is matched by the rule address set."""
    if not rule_cidrs or not seg_cidrs:
        return UNKNOWN
    covered_all = all(any(s.version == r.version and s.subnet_of(r) for r in rule_cidrs) for s in seg_cidrs)
    if covered_all:
        return FULL
    overlaps = any(s.version == r.version and s.overlaps(r) for s in seg_cidrs for r in rule_cidrs)
    return PARTIAL if overlaps else NONE


def _side_cidrs(side: dict[str, Any], ctx: Context) -> tuple[list[Net], list[str]]:
    cidrs: list[Net] = []
    unresolved: list[str] = []
    for ref in side.get("refs") or []:
        rid = str(ref.get("id"))
        stype = side.get("type")
        if stype == "network":
            n = ctx.networks.get(rid)
            c = _net(n.get("subnet")) if n else None
        elif stype in ("ip_group", "ip_port_group"):
            g = ctx.groups.get(rid)
            gc = _group_cidrs(g) if g else []
            cidrs.extend(gc)
            c = gc[0] if gc else None
        elif stype == "ip":
            c = _net(ref.get("ip") or rid)
        else:
            c = None
        if c is None:
            unresolved.append(ref.get("name") or rid)
        elif stype not in ("ip_group", "ip_port_group"):
            cidrs.append(c)
    return cidrs, unresolved


def coverage(side: dict[str, Any], seg: Segment, ctx: Context) -> str:
    if side.get("negate"):
        inner = _coverage(side, seg, ctx)
        return {FULL: NONE, NONE: FULL}.get(inner, inner)
    return _coverage(side, seg, ctx)


def _coverage(side: dict[str, Any], seg: Segment, ctx: Context) -> str:
    stype = side.get("type") or "unknown"
    if stype == "any":
        return FULL
    if stype in ("country", "country_group", "domain_group"):
        return PARTIAL if seg.type == INTERNET else NONE
    if seg.type == INTERNET:
        if stype in ("network", "ssid", "mac_group"):
            return NONE
        if stype in ("ip_group", "ip_port_group", "ip"):
            cidrs, unresolved = _side_cidrs(side, ctx)
            if unresolved and not cidrs:
                return UNKNOWN
            public = [c for c in cidrs if not (c.is_private or c.is_loopback or c.is_link_local)]
            return PARTIAL if public else NONE
        return UNKNOWN
    refs = {str(r.get("id")) for r in side.get("refs") or []}
    if stype == "network":
        if seg.type == "network":
            if seg.ref_id in refs:
                return FULL
        cidrs, unresolved = _side_cidrs(side, ctx)
        rel = _cidr_relation(cidrs, seg.cidrs)
        if rel == UNKNOWN and seg.type == "network":
            return UNKNOWN if unresolved else NONE
        return rel if rel != UNKNOWN else (UNKNOWN if unresolved else NONE)
    if stype in ("ip_group", "ip_port_group", "ip"):
        if seg.type == "group" and seg.ref_id in refs:
            return FULL if stype != "ip_port_group" else PARTIAL
        cidrs, unresolved = _side_cidrs(side, ctx)
        rel = _cidr_relation(cidrs, seg.cidrs)
        if rel == UNKNOWN:
            return UNKNOWN if unresolved or not seg.cidrs else NONE
        if stype == "ip_port_group" and rel == FULL:
            return PARTIAL
        return rel
    if stype in ("ssid", "mac_group"):
        # Only a subset of devices of a network can match: never a full match.
        return UNKNOWN
    return UNKNOWN


def _min_cov(a: str, b: str) -> str:
    order = {NONE: 0, UNKNOWN: 1, PARTIAL: 2, FULL: 3}
    if NONE in (a, b):
        return NONE
    if UNKNOWN in (a, b):
        return UNKNOWN
    return a if order[a] <= order[b] else b


def _proto_full(rule: dict[str, Any]) -> bool:
    protos = [str(p).lower() for p in rule.get("protocols") or []]
    return not protos or "all" in protos


def _directions(rule: dict[str, Any]) -> set[str]:
    dirs = set(rule.get("directions") or [])
    if not dirs and rule.get("direction") and rule.get("direction") != "unknown":
        dirs.add(rule["direction"])
    return dirs


def _direction_applies(rule: dict[str, Any], src: Segment, dst: Segment) -> bool | None:
    if rule.get("acl_type") != "gateway":
        return src.type != INTERNET and dst.type != INTERNET
    dirs = _directions(rule)
    if not dirs:
        return None
    if src.type == INTERNET:
        return "wan_in" in dirs
    if dst.type == INTERNET:
        return "lan_to_wan" in dirs
    return "lan_to_lan" in dirs


def rule_coverage(rule: dict[str, Any], src: Segment, dst: Segment, ctx: Context) -> str:
    applies = _direction_applies(rule, src, dst)
    if applies is False:
        return NONE
    cov = _min_cov(coverage(rule.get("source") or {}, src, ctx), coverage(rule.get("destination") or {}, dst, ctx))
    if applies is None and cov != NONE:
        return UNKNOWN
    if cov == FULL and (not _proto_full(rule) or rule.get("acl_type") == "eap"):
        return PARTIAL
    return cov


# --------------------------------------------------------------------------- explanations


def _join(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else "?"
    return ", ".join(names[:-1]) + " and " + names[-1]


def _side_text(side: dict[str, Any], ctx: Context, is_source: bool, direction: str) -> str:
    stype = side.get("type") or "unknown"
    names = [str(r.get("name") or r.get("id")) for r in side.get("refs") or []]
    lang = ctx.lang
    if stype == "any":
        if not is_source and direction == "lan_to_wan":
            return t("acl.subject.internet", lang)
        if is_source and direction == "wan_in":
            return t("acl.subject.internet", lang)
        return t("acl.subject.any" if is_source else "acl.subject.any_dest", lang)
    if stype == "network":
        decorated = []
        for r in side.get("refs") or []:
            n = ctx.networks.get(str(r.get("id")))
            label = str(r.get("name") or (n or {}).get("name") or r.get("id"))
            if n and n.get("vlan_id") is not None:
                label += f" (VLAN {n['vlan_id']})"
            decorated.append(label)
        if is_source:
            return t("acl.subject.network" if len(decorated) == 1 else "acl.subject.networks", lang,
                     name=_join(decorated), names=_join(decorated))
        return t("acl.target.network" if len(decorated) == 1 else "acl.target.networks", lang,
                 name=_join(decorated), names=_join(decorated))
    if stype in ("ip_group", "ip_port_group", "ip", "mac_group", "ssid"):
        return t("acl.subject.group" if len(names) == 1 else "acl.subject.groups", lang,
                 name=_join(names), names=_join(names))
    return t("acl.subject.unknown", lang, name=_join(names) or "unknown")


def _proto_text(rule: dict[str, Any], lang: str) -> str:
    if _proto_full(rule):
        text = t("acl.proto.all", lang)
    else:
        text = t("acl.proto.list", lang, protocols=_join([str(p).upper() for p in rule.get("protocols")]))
    ports = []
    for side in (rule.get("source") or {}, rule.get("destination") or {}):
        ports.extend(str(p) for p in side.get("ports") or [])
    if ports:
        text += " " + t("acl.proto.ports", lang, ports=", ".join(ports))
    return text


def technical_text(rule: dict[str, Any]) -> str:
    def side(s: dict[str, Any]) -> str:
        if (s.get("type") or "") == "any":
            return "ANY"
        names = [str(r.get("name") or r.get("id")) for r in s.get("refs") or []]
        txt = ", ".join(names) or s.get("type", "?")
        if s.get("negate"):
            txt = "NOT " + txt
        if s.get("ports"):
            txt += ":" + ",".join(str(p) for p in s["ports"])
        return txt

    protos = "ALL" if _proto_full(rule) else ",".join(str(p).upper() for p in rule.get("protocols") or [])
    prefix = f"[{(rule.get('acl_type') or '?').upper()} #{rule.get('index', '?')}] "
    if rule.get("acl_type") == "gateway":
        prefix += (" + ".join(sorted(d.replace("_", " ").upper() for d in _directions(rule))) or "UNKNOWN") + ": "
    text = (f"{prefix}{side(rule.get('source') or {})} → {side(rule.get('destination') or {})} | {protos} | "
            f"{(rule.get('action') or 'unknown').upper()}")
    if rule.get("enabled") is False:
        text += " | DISABLED"
    return text


def _resolution_issues(rule: dict[str, Any], ctx: Context) -> list[str]:
    issues = []
    for side in (rule.get("source") or {}, rule.get("destination") or {}):
        stype = side.get("type") or "unknown"
        if stype == "unknown":
            issues.append("unknown object type")
            continue
        if stype in ("network", "ip_group", "ip_port_group", "ip"):
            _, unresolved = _side_cidrs(side, ctx)
            issues.extend(unresolved)
    return issues


def _overlaps(a: dict[str, Any], b: dict[str, Any], ctx: Context) -> str:
    """Coverage of rule b's traffic by rule a (FULL means a matches everything b matches)."""
    if a.get("acl_type") != b.get("acl_type"):
        return NONE
    if not (_directions(a) & _directions(b)) and (_directions(a) or _directions(b)):
        return NONE
    if a.get("source", {}).get("negate") or b.get("source", {}).get("negate") \
            or a.get("destination", {}).get("negate") or b.get("destination", {}).get("negate"):
        return UNKNOWN
    results = []
    for side_key in ("source", "destination"):
        sa, sb = a.get(side_key) or {}, b.get(side_key) or {}
        if sa.get("type") == "any":
            results.append(FULL)
            continue
        if sb.get("type") == "any":
            results.append(PARTIAL)
            continue
        if sa.get("type") == sb.get("type") and sa.get("type") != "ip_port_group":
            ra = {str(r.get("id")) for r in sa.get("refs") or []}
            rb = {str(r.get("id")) for r in sb.get("refs") or []}
            if rb and rb <= ra:
                results.append(FULL)
                continue
        ca, _ = _side_cidrs(sa, ctx)
        cb, _ = _side_cidrs(sb, ctx)
        rel = _cidr_relation(ca, cb)
        if rel == FULL and (sa.get("type") == "ip_port_group" or sb.get("type") == "ip_port_group"):
            rel = PARTIAL
        results.append(rel)
    cov = _min_cov(results[0], results[1])
    if cov == FULL and not _proto_full(a):
        pa = {str(p).lower() for p in a.get("protocols") or []}
        pb = {str(p).lower() for p in b.get("protocols") or []}
        cov = FULL if (not _proto_full(b) and pb <= pa) else PARTIAL
    return cov


def explain_rules(rules: list[dict[str, Any]], ctx: Context) -> list[dict[str, Any]]:
    """Return per-rule interpretation: technical text, explanation, confidence and related rules."""
    ordered = sorted(rules, key=lambda r: (r.get("acl_type") or "", r.get("index") or 0))
    out = []
    for i, rule in enumerate(ordered):
        lang = ctx.lang
        direction = rule.get("direction") or "unknown"
        src = _side_text(rule.get("source") or {}, ctx, True, direction)
        dst = _side_text(rule.get("destination") or {}, ctx, False, direction)
        action = rule.get("action") or "unknown"
        proto = _proto_text(rule, lang)
        if action == "deny":
            sentences = [t("acl.explain.deny", lang, src=src, dst=dst, proto=proto)]
        elif action == "allow":
            sentences = [t("acl.explain.allow", lang, src=src, dst=dst, proto=proto)]
        else:
            sentences = [t("acl.explain.unknown_action", lang, src=src, dst=dst)]
        sentences[0] = sentences[0][0].upper() + sentences[0][1:]
        if rule.get("acl_type") == "eap":
            sentences.append(t("acl.explain.wireless_only", lang))
        elif rule.get("acl_type") == "switch":
            sentences.append(t("acl.explain.switch", lang))
        if "wan_in" in _directions(rule):
            sentences.append(t("acl.explain.direction.wan_in", lang))
        for side in (rule.get("source") or {}, rule.get("destination") or {}):
            if side.get("type") == "network":
                for ref in side.get("refs") or []:
                    if str(ref.get("id")) in ctx.guest_network_ids:
                        sentences.append(t("acl.explain.guest", lang, name=ref.get("name") or ref.get("id")))

        reasons: list[str] = []
        confidence = "high"
        issues = _resolution_issues(rule, ctx)
        if issues:
            reasons.append(t("acl.confidence.unresolved", lang, names=", ".join(issues)))
            confidence = "low"
        if not _directions(rule) and rule.get("acl_type") == "gateway":
            reasons.append(t("acl.confidence.unknown_direction", lang))
            confidence = "low"
        if action == "unknown":
            confidence = "low"
        if not _proto_full(rule) or any((rule.get(s) or {}).get("ports") for s in ("source", "destination")):
            reasons.append(t("acl.confidence.ports", lang))

        related, shadowed_by, partial_conflicts = [], None, []
        if rule.get("enabled", True):
            for earlier in ordered[:i]:
                if not earlier.get("enabled", True):
                    continue
                ov = _overlaps(earlier, rule, ctx)
                if ov == FULL and shadowed_by is None:
                    shadowed_by = earlier
                if ov in (FULL, PARTIAL):
                    related.append(earlier["key"])
                    if ov == PARTIAL and earlier.get("action") != action:
                        partial_conflicts.append(earlier)
        for later in ordered[i + 1:]:
            if _overlaps(rule, later, ctx) in (FULL, PARTIAL) or _overlaps(later, rule, ctx) in (FULL, PARTIAL):
                related.append(later["key"])
        if shadowed_by is not None:
            sentences.append(t("acl.explain.shadowed", lang, rule=shadowed_by.get("name") or shadowed_by["key"]))
            if confidence == "high":
                confidence = "medium"
        if partial_conflicts:
            reasons.append(t("acl.confidence.partial_overlap", lang,
                             rules=", ".join(r.get("name") or r["key"] for r in partial_conflicts)))
            if confidence == "high":
                confidence = "medium"
        if not rule.get("enabled", True):
            sentences.append(t("acl.explain.disabled", lang))

        out.append({
            "key": rule["key"],
            "technical": technical_text(rule),
            "explanation": " ".join(sentences),
            "confidence": confidence,
            "confidence_reasons": reasons,
            "shadowed_by": shadowed_by["key"] if shadowed_by else None,
            "related_rules": list(dict.fromkeys(related)),
            "data_source": rule.get("_source") or rule.get("source_label") or "api",
        })
    return out


# --------------------------------------------------------------------------- matrix


def _evaluate_type(rules: list[dict[str, Any]], src: Segment, dst: Segment, ctx: Context):
    decided, exceptions, uncertain = None, [], []
    for rule in sorted(rules, key=lambda r: r.get("index") or 0):
        if not rule.get("enabled", True):
            continue
        cov = rule_coverage(rule, src, dst, ctx)
        if cov == NONE:
            continue
        if cov == UNKNOWN or rule.get("action") not in ("allow", "deny"):
            uncertain.append(rule)
            continue
        if cov == FULL:
            decided = rule
            break
        exceptions.append(rule)
    return decided, exceptions, uncertain


def evaluate_pair(rules: list[dict[str, Any]], src: Segment, dst: Segment, ctx: Context) -> dict[str, Any]:
    lang = ctx.lang
    notes: list[str] = []
    involved: list[str] = []
    statuses: list[str] = []
    confidence = "high"
    basis = "rule"
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in rules:
        by_type.setdefault(r.get("acl_type") or "gateway", []).append(r)

    any_decided = False
    for _acl_type, typed in sorted(by_type.items()):
        decided, exceptions, uncertain = _evaluate_type(typed, src, dst, ctx)
        involved += [r["key"] for r in exceptions + uncertain + ([decided] if decided else [])]
        if uncertain:
            confidence = "low"
            notes.append(t("matrix.uncertain", lang))
        if exceptions:
            notes.append(t("matrix.partial_rules", lang, rules=", ".join(r.get("name") or r["key"] for r in exceptions)))
        if decided is not None:
            any_decided = True
            notes.append(t("matrix.rule_decides", lang, rule=decided.get("name") or decided["key"]))
            other = "allow" if decided["action"] == "deny" else "deny"
            if any(e.get("action") == other for e in exceptions):
                statuses.append("restricted")
            else:
                statuses.append("blocked" if decided["action"] == "deny" else "allowed")
        elif any(e.get("action") == "deny" for e in exceptions):
            statuses.append("restricted")

    if not any_decided and not statuses:
        basis = "default"
        if src.type == INTERNET:
            fwd = [n for n in ctx.nat_rules if n.get("enabled", True) and n.get("nat_type") == "port_forwarding"
                   and _ip_in(n.get("internal_ip"), dst.cidrs)]
            if fwd:
                statuses.append("restricted")
                basis = "derived"
                involved += [n["key"] for n in fwd]
                notes.append(t("matrix.port_forwarding", lang, rules=", ".join(n.get("name") or n["key"] for n in fwd)))
            else:
                statuses.append("blocked")
                notes.append(t("matrix.default_wan_in", lang))
            confidence = "medium" if confidence == "high" else confidence
        elif dst.type == INTERNET:
            statuses.append("allowed")
            notes.append(t("matrix.default_wan_out", lang))
            confidence = "medium" if confidence == "high" else confidence
        else:
            statuses.append("allowed")
            notes.append(t("matrix.default_allow", lang))
            confidence = "medium" if confidence == "high" else confidence

    if src.guest and dst.type in ("network", "group") and dst.id != src.id:
        if "allowed" in statuses or "restricted" in statuses:
            statuses = ["blocked"]
            basis = "derived"
            notes.append(t("matrix.guest", lang))
            confidence = "medium" if confidence == "high" else confidence

    if "blocked" in statuses:
        status = "blocked"
    elif "restricted" in statuses:
        status = "restricted"
    else:
        status = "allowed"
    if confidence == "low":
        status_label = "unknown" if not any_decided else status
    else:
        status_label = status
    return {
        "source": src.id,
        "destination": dst.id,
        "status": status_label,
        "computed_status": status,
        "confidence": confidence,
        "basis": basis,
        "rules": list(dict.fromkeys(involved)),
        "notes": list(dict.fromkeys(notes)),
    }


def _ip_in(ip: Any, cidrs: Iterable[Net]) -> bool:
    try:
        addr = ipaddress.ip_address(str(ip))
    except ValueError:
        return False
    return any(addr.version == c.version and addr in c for c in cidrs)


def segment_dict(s: Segment) -> dict[str, Any]:
    return {"id": s.id, "type": s.type, "name": s.name, "vlan_id": s.vlan_id, "guest": s.guest,
            "cidrs": [str(c) for c in s.cidrs], "ref_id": s.ref_id}


def communication_matrix(rules: list[dict[str, Any]], ctx: Context) -> dict[str, Any]:
    cells = []
    for src in ctx.segments:
        for dst in ctx.segments:
            if src.id == dst.id or (src.type == "group" and dst.type == "group"):
                continue
            if src.type == INTERNET and dst.type == "group":
                continue
            cells.append(evaluate_pair(rules, src, dst, ctx))
    return {"segments": [segment_dict(s) for s in ctx.segments], "cells": cells}


def acl_graph(rules: list[dict[str, Any]], ctx: Context, matrix: dict[str, Any]) -> dict[str, Any]:
    """Graph for visualisation: nodes = segments, edges = rule-backed or relevant connections."""
    seg_by_id = {s.id: s for s in ctx.segments}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for rule in rules:
        for s in ctx.segments:
            for d in ctx.segments:
                if s.id == d.id:
                    continue
                if rule_coverage({**rule, "enabled": True}, s, d, ctx) == NONE:
                    continue
                # only draw edges for explicitly referenced endpoints (avoid "any" fan-out noise)
                if not (_references(rule.get("source") or {}, s) and _references(rule.get("destination") or {}, d, rule)):
                    continue
                e = edges.setdefault((s.id, d.id), {"source": s.id, "target": d.id, "rules": [], "disabled_rules": []})
                (e["rules"] if rule.get("enabled", True) else e["disabled_rules"]).append(rule["key"])
    cell_by_pair = {(c["source"], c["destination"]): c for c in matrix["cells"]}
    out_edges = []
    for (s, d), e in edges.items():
        cell = cell_by_pair.get((s, d))
        status = cell["status"] if cell else "unknown"
        out_edges.append({
            "id": f"{s}->{d}", **e,
            "status": status if e["rules"] else "disabled",
            "dashed": not e["rules"],
            "confidence": cell["confidence"] if cell else "low",
        })
    used = {e["source"] for e in out_edges} | {e["target"] for e in out_edges}
    nodes = [segment_dict(s) | {"has_rules": s.id in used} for s in seg_by_id.values()]
    return {"nodes": nodes, "edges": out_edges}


def _references(side: dict[str, Any], seg: Segment, rule: dict[str, Any] | None = None) -> bool:
    stype = side.get("type")
    if stype == "any":
        if seg.type == INTERNET:
            return True
        return False
    refs = {str(r.get("id")) for r in side.get("refs") or []}
    return seg.ref_id in refs if seg.ref_id else False


def analyze(dataset: dict[str, list[dict[str, Any]]], site_id: str | None = None, lang: str = "en") -> dict[str, Any]:
    ctx = build_context(dataset, site_id, lang)
    rules = [r for r in dataset.get("acl_rule", []) if site_id is None or r.get("site_id") == site_id]
    matrix = communication_matrix(rules, ctx)
    return {
        "rules": explain_rules(rules, ctx),
        "matrix": matrix,
        "graph": acl_graph(rules, ctx, matrix),
    }
