"""Export renderers: HTML, PDF (WeasyPrint), DOCX (python-docx) and CSV."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import bleach
import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.export import svg

TEMPLATES = Path(__file__).parent / "templates"

ALLOWED_TAGS = sorted(set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td", "hr", "br",
    "ul", "ol", "li", "blockquote", "img", "del", "span"})
ALLOWED_ATTRS = {"a": ["href", "title"], "img": ["src", "alt", "title"], "th": ["align"], "td": ["align"]}


def render_markdown(text: str | None) -> str:
    html = md.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"])
    # Remote images would cause outbound requests during PDF rendering – only allow data: URIs.
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https", "mailto",
                                                                                          "data"], strip=True)
    return re.sub(r"<img[^>]+src=\"(?!data:)[^\"]*\"[^>]*>", "", cleaned)


def _fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    return str(value or "–")


def _side(side: dict | None) -> str:
    side = side or {}
    if side.get("type") == "any":
        return "Any"
    names = ", ".join(str(r.get("name") or r.get("id")) for r in side.get("refs") or []) or side.get("type") or "?"
    return ("NOT " if side.get("negate") else "") + names


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["dt"] = _fmt_dt
    env.filters["side"] = _side
    env.filters["markdown"] = render_markdown
    env.filters["chapter"] = lambda c, r: r["chapter_titles"].get(c, c)
    env.filters["rulename"] = lambda key, r: next(
        (x.get("name") for x in r["acl_rules"] if x["key"] == key), key)
    return env


def diagrams(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "topology": svg.topology_svg(report["topology"]),
        "segmentation": svg.segmentation_svg(report["topology"]["segmentation"]),
        "matrix": svg.matrix_svg(report["matrix"]),
        "ports": {s["mac"]: svg.port_matrix_svg(s, report["ports_by_switch"][s["mac"]]) for s in report["switches"]},
    }


def render_html(report: dict[str, Any], screen: bool = True) -> str:
    return _env().get_template("report.html").render(r=report, diagrams=diagrams(report), screen=screen)


def _no_fetch(url: str, *args, **kwargs):  # pragma: no cover - only hit if a remote resource sneaks in
    raise ValueError(f"External resources are not allowed in exports: {url[:60]}")


def render_pdf(report: dict[str, Any]) -> bytes:
    from weasyprint import HTML  # imported lazily: heavy native dependency

    return HTML(string=render_html(report, screen=False), url_fetcher=_no_fetch).write_pdf()


# ------------------------------------------------------------------------------------------------ DOCX


def _svg_png(svg_text: str, width: int = 1600) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=width, background_color="white")


def render_docx(report: dict[str, Any]) -> bytes:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    dg = diagrams(report)
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(1.5))
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(9.5)
    for name, size in (("Heading 1", 18), ("Heading 2", 13), ("Heading 3", 11)):
        styles[name].font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
        styles[name].font.size = Pt(size)
    footer = sec.footer.paragraphs[0]
    footer.text = f"{report['title']} · generated {_fmt_dt(report['generated_at'])}"
    footer.runs[0].font.size = Pt(8)

    def page_break() -> None:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None) -> None:
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(headers):
            cell = t.rows[0].cells[i]
            cell.text = h
            cell.paragraphs[0].runs[0].font.bold = True
        tr_pr = t.rows[0]._tr.get_or_add_trPr()
        hdr = OxmlElement("w:tblHeader")
        hdr.set(qn("w:val"), "true")
        tr_pr.append(hdr)
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = "" if v is None else str(v)
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(8)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        doc.add_paragraph()

    def image(svg_text: str, width_cm: float = 26.0) -> None:
        doc.add_picture(io.BytesIO(_svg_png(svg_text)), width=Cm(width_cm))

    def note(text: str) -> None:
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.italic = True
        r.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    # cover
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("Omada Network Documentation Platform").font.size = Pt(12)
    title = doc.add_paragraph()
    run = title.add_run(report["title"])
    run.font.size = Pt(28)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    snap = report["snapshot"]
    ctrl = report["controller"]
    meta = [
        ("Created", _fmt_dt(report["generated_at"])),
        ("Data snapshot", f"#{snap['id']} from {_fmt_dt(snap['created_at'])} (checksum {snap['checksum']})" if snap
         else "No snapshot available"),
        ("Last synchronisation", f"{_fmt_dt(report['last_sync']['finished_at'])} ({report['last_sync']['status']})"
         if report["last_sync"] else "never"),
        ("Controller", f"{ctrl.get('name') or '–'} · version {ctrl.get('version') or 'unknown'}"),
        ("Site", (report["site"] or {}).get("name") or "–"),
        ("Application version", report["app_version"]),
    ]
    for k, v in meta:
        p = doc.add_paragraph()
        p.add_run(f"{k}: ").bold = True
        p.add_run(v)
    note("Generated from read-only controller data and manual documentation. Contains no passwords, pre-shared keys "
         "or API credentials.")
    page_break()

    # table of contents (Word updates the field when the document is opened / F9)
    doc.add_heading("Table of contents", level=1)
    p = doc.add_paragraph()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), 'TOC \\o "1-2" \\h \\z \\u')
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "Right-click and choose “Update field” to build the table of contents."
    r.append(t)
    fld.append(r)
    p._p.append(fld)
    page_break()

    doc.add_heading("Version information", level=1)
    table(["Property", "Value"], [
        ["Document created", _fmt_dt(report["generated_at"])],
        ["Represented data snapshot", f"#{snap['id']} ({_fmt_dt(snap['created_at'])})" if snap else "–"],
        ["Controller", ctrl.get("name")], ["Controller version", ctrl.get("version") or "unknown"],
        ["Controller model", f"{ctrl.get('controller_type') or ''} {ctrl.get('model') or ''}".strip() or "–"],
        ["Open API version", ctrl.get("api_version") or "unknown"],
        ["Included chapters", ", ".join(report["chapter_titles"].values())],
    ])

    for num, c in enumerate(report["chapters"], start=1):
        page_break()
        doc.add_heading(f"{num}. {report['chapter_titles'][c]}", level=1)
        if c == "overview":
            image(dg["topology"])
            for n in report["topology"]["notes"]:
                note(n)
            if report["topology"]["unresolved"]:
                doc.add_heading("Devices with unknown connection", level=2)
                table(["Device", "Reason"], [[u["name"], u["reason"]] for u in report["topology"]["unresolved"]])
            doc.add_heading("Network segmentation", level=2)
            image(dg["segmentation"])
            doc.add_heading("Internet / WAN", level=2)
            table(["WAN", "Description", "Type", "VLAN", "Status", "IP", "Gateway", "ISP"],
                  [[w.get("name"), w.get("description"), w.get("type"), w.get("vlan_id"), w.get("status"),
                    (w.get("ipv4") or {}).get("address"), (w.get("ipv4") or {}).get("gateway"), w.get("isp")]
                   for w in report["wans"]])
            if report["routes"]:
                doc.add_heading("Static routes", level=2)
                table(["Name", "Enabled", "Destinations", "Next hop", "Metric"],
                      [[r.get("name"), "yes" if r.get("enabled") else "no", ", ".join(r.get("destinations") or []),
                        r.get("next_hop") or r.get("interface"), r.get("metric")] for r in report["routes"]])
            if report["vpns"]:
                doc.add_heading("VPN", level=2)
                table(["Name", "Type", "Enabled", "Remote", "Local networks", "Remote subnets"],
                      [[v.get("name"), v.get("type"), "yes" if v.get("enabled") else "no",
                        v.get("remote_ip") or v.get("remote_site"), ", ".join(v.get("local_networks") or []),
                        ", ".join(v.get("remote_subnets") or [])] for v in report["vpns"]])
        elif c == "vlans":
            seg = {s["id"]: s for s in report["topology"]["segmentation"]}
            table(["VLAN", "Name", "Network", "Gateway", "DHCP range", "DNS", "SSIDs", "Clients", "Description"],
                  [[n.get("vlan_id"), n["manual"].get("display_name") or n.get("name"), n.get("subnet"),
                    n.get("gateway"),
                    f"{n['dhcp'].get('range_start')} – {n['dhcp'].get('range_end')}" if (n.get("dhcp") or {}).get(
                        "enabled") else "disabled",
                    " ".join(filter(None, [(n.get("dhcp") or {}).get("dns_mode"),
                                           ", ".join((n.get("dhcp") or {}).get("dns_servers") or [])])),
                    ", ".join(seg.get(n["key"], {}).get("ssids") or []), seg.get(n["key"], {}).get("client_count"),
                    n["manual"].get("description")] for n in report["networks"]])
        elif c == "devices":
            table(["Name", "Type", "Model", "IP", "MAC", "Firmware", "Status", "Uplink", "Location"],
                  [[d["manual"].get("display_name") or d.get("name"), d.get("type"), d.get("model"), d.get("ip"),
                    d.get("mac"), d.get("firmware"), d.get("status"),
                    f"{d.get('uplink_device_name')} port {d.get('uplink_port')}" if d.get("uplink_device_name")
                    else ("–" if d.get("type") == "gateway" else "unknown"), d["manual"].get("location")]
                   for d in report["devices"]])
        elif c == "ports":
            for s in report["switches"]:
                doc.add_heading(f"{s['manual'].get('display_name') or s.get('name')} ({s.get('model')}, "
                                f"{s.get('ip')})", level=2)
                image(dg["ports"][s["mac"]], 18)
                table(["Port", "Link", "Speed", "PoE", "Profile", "Native VLAN", "Connected", "Description"],
                      [[f"{p.get('port')}{' (uplink)' if p.get('link_role') == 'uplink' else ''}", p.get("link_status"),
                        p.get("speed"),
                        f"{(p.get('poe') or {}).get('power_w')} W" if (p.get("poe") or {}).get("active") else "–",
                        p.get("profile_name"), p.get("native_network"),
                        ", ".join(cn.get("name") or cn.get("mac") or "" for cn in p.get("connected") or []),
                        " – ".join(filter(None, [p["manual"].get("display_name"), p["manual"].get("description")]))]
                       for p in report["ports_by_switch"][s["mac"]]])
        elif c == "wlans":
            note("Passwords and pre-shared keys are never collected or exported.")
            table(["SSID", "Enabled", "VLAN / network", "Bands", "Security", "Guest", "AP assignment", "Clients"],
                  [[w.get("ssid"), "yes" if w.get("enabled") else "no",
                    f"{w.get('vlan_id')} {w.get('network_name') or ''}" if w.get("vlan_enabled") else "default",
                    ", ".join(w.get("bands") or []), f"{w.get('security') or ''} {w.get('security_version') or ''}",
                    "yes" if w.get("guest") else "no", w.get("ap_assignment"), w.get("client_count")]
                   for w in report["wlans"]])
        elif c == "acl":
            for t_, label in (("gateway", "Gateway ACLs"), ("switch", "Switch ACLs"), ("eap", "EAP (wireless) ACLs")):
                rules = [r for r in report["acl_rules"] if r.get("acl_type") == t_]
                if not rules:
                    continue
                doc.add_heading(label, level=2)
                table(["#", "Name", "Enabled", "Source", "Destination", "Protocol", "Action", "Direction",
                       "Explanation", "Confidence"],
                      [[r.get("index"), r["manual"].get("display_name") or r.get("name"),
                        "yes" if r.get("enabled") else "no", _side(r.get("source")), _side(r.get("destination")),
                        ", ".join(r.get("protocols") or []).upper() or "ALL", r.get("action"),
                        ", ".join(r.get("directions") or []).replace("_", " "),
                        r["analysis"].get("explanation", "") + (
                            " ⚠ " + " ".join(r["analysis"]["confidence_reasons"])
                            if r["analysis"].get("confidence_reasons") else ""),
                        r["analysis"].get("confidence")] for r in rules],
                      [0.8, 3, 1.2, 3, 3, 1.6, 1.4, 2, 8.5, 1.7])
            if not report["acl_rules"]:
                note("No ACL rules configured.")
        elif c == "matrix":
            doc.add_paragraph("Calculated from the actual ACL configuration. “Restricted” means that only part of "
                              "the traffic is allowed or blocked; “unknown” means the effect cannot be determined "
                              "reliably.")
            image(dg["matrix"], 20)
            names = {s["id"]: s["name"] for s in report["matrix"]["segments"]}
            rule_names = {r["key"]: r.get("name") for r in report["acl_rules"]}
            table(["Source", "Destination", "Communication", "Basis", "Rules / notes"],
                  [[names.get(cell["source"]), names.get(cell["destination"]), cell["status"], cell["basis"],
                    ", ".join(rule_names.get(k, k) for k in cell["rules"]) + (
                        " – " + " ".join(cell["notes"]) if cell.get("notes") else "")]
                   for cell in report["matrix"]["cells"]
                   if cell["basis"] != "default" or cell["status"] != "allowed"])
        elif c == "nat":
            table(["Name", "Type", "Enabled", "Protocol", "External", "Internal IP", "Internal port", "Source"],
                  [[n["manual"].get("display_name") or n.get("name"), (n.get("nat_type") or "").replace("_", " "),
                    "yes" if n.get("enabled") else "no", n.get("protocol"),
                    f"{n.get('external_ip') or ''} {n.get('external_port') or ''}".strip(), n.get("internal_ip"),
                    n.get("internal_port"), f"{n.get('source') or ''} {', '.join(n.get('source_addresses') or [])}"]
                   for n in report["nat_rules"]])
        elif c == "clients":
            table(["Name", "IP", "MAC", "Network", "Connection", "Connected to", "Vendor"],
                  [[cl["manual"].get("display_name") or cl.get("name"), cl.get("ip"), cl.get("mac"),
                    cl.get("network_name"), f"{cl.get('connection_type') or ''} {cl.get('ssid') or ''}".strip(),
                    f"{cl.get('connected_device_name') or ''}{' port ' + str(cl['port']) if cl.get('port') else ''}",
                    cl.get("vendor")] for cl in report["clients"]])
        elif c == "manual":
            if not report["documents"]:
                note("No manual documentation entries.")
            for d in report["documents"]:
                doc.add_heading(d["title"], level=2)
                note(f"Category: {d['category'].replace('_', ' ')} · last modified {_fmt_dt(d['updated_at'])}"
                     + (f" · Tags: {', '.join(d['tags'])}" if d["tags"] else ""))
                _markdown_to_docx(doc, d["body"])
        elif c == "changes":
            note(f"Changes of the last {report['change_days']} days.")
            table(["Date", "Type", "Object", "Change", "Field", "Before", "After"],
                  [[_fmt_dt(ch["ts"]), ch["kind"], f"{ch['object_type']}: {ch['object_name']}", ch["change_type"],
                    ch["field"], (ch["before"] or "")[:120], (ch["after"] or "")[:120]] for ch in report["changes"]])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _markdown_to_docx(doc, text: str) -> None:
    """Simple Markdown → DOCX conversion (headings, lists, code, paragraphs)."""
    in_code = False
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            p = doc.add_paragraph(line)
            p.style = "No Spacing"
            for r in p.runs:
                r.font.name = "Consolas"
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            doc.add_heading(m.group(2), level=min(len(m.group(1)) + 1, 4))
        elif re.match(r"^\s*[-*+]\s+", line):
            doc.add_paragraph(re.sub(r"^\s*[-*+]\s+", "", _strip_inline(line)), style="List Bullet")
        elif re.match(r"^\s*\d+[.)]\s+", line):
            doc.add_paragraph(re.sub(r"^\s*\d+[.)]\s+", "", _strip_inline(line)), style="List Number")
        elif line.strip():
            doc.add_paragraph(_strip_inline(line))


def _strip_inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", s)
    return s


# ------------------------------------------------------------------------------------------------ CSV

CSV_TABLES = ("devices", "networks", "wlans", "switch_ports", "acl_rules", "nat_rules", "clients", "changes")


def _cell(v: Any) -> str:
    """Neutralise spreadsheet formula injection."""
    s = "" if v is None else (", ".join(map(str, v)) if isinstance(v, list) else str(v))
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def render_csv(report: dict[str, Any], table_name: str) -> str:
    rows: list[list[Any]]
    if table_name == "devices":
        header = ["name", "manual_name", "type", "model", "ip", "mac", "firmware", "serial", "status", "uplink",
                  "uplink_port", "location", "description"]
        rows = [[d.get("name"), d["manual"].get("display_name"), d.get("type"), d.get("model"), d.get("ip"),
                 d.get("mac"), d.get("firmware"), d.get("serial"), d.get("status"), d.get("uplink_device_name"),
                 d.get("uplink_port"), d["manual"].get("location"), d["manual"].get("description")]
                for d in report["devices"]]
    elif table_name == "networks":
        header = ["vlan_id", "name", "subnet", "gateway", "netmask", "dhcp_enabled", "dhcp_start", "dhcp_end",
                  "dns_mode", "dns_servers", "description"]
        rows = [[n.get("vlan_id"), n.get("name"), n.get("subnet"), n.get("gateway"), n.get("netmask"),
                 (n.get("dhcp") or {}).get("enabled"), (n.get("dhcp") or {}).get("range_start"),
                 (n.get("dhcp") or {}).get("range_end"), (n.get("dhcp") or {}).get("dns_mode"),
                 (n.get("dhcp") or {}).get("dns_servers"), n["manual"].get("description")] for n in report["networks"]]
    elif table_name == "wlans":
        header = ["ssid", "wlan_group", "enabled", "vlan_id", "network", "bands", "security", "security_version",
                  "guest", "broadcast", "clients"]
        rows = [[w.get("ssid"), w.get("wlan_group"), w.get("enabled"), w.get("vlan_id"), w.get("network_name"),
                 w.get("bands"), w.get("security"), w.get("security_version"), w.get("guest"), w.get("broadcast"),
                 w.get("client_count")] for w in report["wlans"]]
    elif table_name == "switch_ports":
        header = ["switch", "port", "link", "speed", "poe_active", "poe_w", "profile", "native_vlan", "tagged",
                  "connected", "link_role", "manual_name", "description"]
        rows = [[p.get("switch_name"), p.get("port"), p.get("link_status"), p.get("speed"),
                 (p.get("poe") or {}).get("active"), (p.get("poe") or {}).get("power_w"), p.get("profile_name"),
                 p.get("native_vlan_id"), p.get("tagged_networks"),
                 [c.get("name") or c.get("mac") for c in p.get("connected") or []], p.get("link_role"),
                 p["manual"].get("display_name"), p["manual"].get("description")]
                for ports in report["ports_by_switch"].values() for p in ports]
    elif table_name == "acl_rules":
        header = ["type", "index", "name", "enabled", "action", "source", "destination", "protocols", "ports",
                  "directions", "explanation", "confidence"]
        rows = [[r.get("acl_type"), r.get("index"), r.get("name"), r.get("enabled"), r.get("action"),
                 _side(r.get("source")), _side(r.get("destination")), r.get("protocols"),
                 (r.get("source", {}).get("ports") or []) + (r.get("destination", {}).get("ports") or []),
                 r.get("directions"), r["analysis"].get("explanation"), r["analysis"].get("confidence")]
                for r in report["acl_rules"]]
    elif table_name == "nat_rules":
        header = ["name", "type", "enabled", "protocol", "external_ip", "external_port", "internal_ip",
                  "internal_port", "source"]
        rows = [[n.get("name"), n.get("nat_type"), n.get("enabled"), n.get("protocol"), n.get("external_ip"),
                 n.get("external_port"), n.get("internal_ip"), n.get("internal_port"), n.get("source")]
                for n in report["nat_rules"]]
    elif table_name == "clients":
        header = ["name", "ip", "mac", "network", "vlan_id", "connection", "ssid", "connected_to", "port", "vendor"]
        rows = [[c.get("name"), c.get("ip"), c.get("mac"), c.get("network_name"), c.get("vlan_id"),
                 c.get("connection_type"), c.get("ssid"), c.get("connected_device_name"), c.get("port"),
                 c.get("vendor")] for c in report["clients"]]
    elif table_name == "changes":
        header = ["timestamp", "kind", "object_type", "object", "change", "field", "before", "after", "user"]
        rows = [[ch["ts"].isoformat(), ch["kind"], ch["object_type"], ch["object_name"], ch["change_type"],
                 ch["field"], ch["before"], ch["after"], ch["username"]] for ch in report["changes"]]
    else:
        raise ValueError(f"Unknown table '{table_name}'")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for row in rows:
        w.writerow([_cell(v) for v in row])
    return "\ufeff" + buf.getvalue()
