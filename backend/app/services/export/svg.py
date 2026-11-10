"""Server-side SVG diagrams for exports (embedded in HTML/PDF, rasterised for DOCX)."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
from xml.sax.saxutils import escape

FONT = "font-family='DejaVu Sans, Arial, sans-serif'"
STATUS_COLORS = {"allowed": "#16a34a", "blocked": "#dc2626", "restricted": "#f59e0b", "unknown": "#9ca3af"}
NODE_COLORS = {"internet": "#0ea5e9", "gateway": "#4f46e5", "switch": "#0891b2", "ap": "#7c3aed",
               "client": "#64748b", "location": "#a16207", "device": "#475569"}


def _t(text: Any, max_len: int = 28) -> str:
    s = "" if text is None else str(text)
    return escape(s if len(s) <= max_len else s[: max_len - 1] + "…")


def _svg(width: int, height: int, body: list[str]) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}' {FONT}>" + "".join(body) + "</svg>")


def topology_svg(topo: dict[str, Any]) -> str:
    nodes = {n["id"]: n for n in topo["nodes"]}
    children: dict[str, list[str]] = defaultdict(list)
    for e in topo["edges"]:
        children[e["source"]].append(e["target"])
    roots = [n for n in nodes if n == "internet"] or [n["id"] for n in topo["nodes"] if n["type"] == "gateway"]
    level: dict[str, int] = {}
    queue = deque((r, 0) for r in roots)
    while queue:
        nid, lv = queue.popleft()
        if nid in level:
            continue
        level[nid] = lv
        for c in sorted(children.get(nid, []), key=lambda x: nodes[x]["label"]):
            queue.append((c, lv + 1))
    rows: dict[int, list[str]] = defaultdict(list)
    for nid, lv in level.items():
        rows[lv].append(nid)
    unresolved = [nid for nid in nodes if nid not in level]
    bw, bh, gapx, gapy = 180, 54, 24, 70
    max_cols = max([len(v) for v in rows.values()] + [len(unresolved), 1])
    width = max(max_cols * (bw + gapx) + gapx, 600)
    pos: dict[str, tuple[int, int]] = {}
    for lv in sorted(rows):
        ids = rows[lv]
        total = len(ids) * bw + (len(ids) - 1) * gapx
        x0 = (width - total) // 2
        for i, nid in enumerate(ids):
            pos[nid] = (x0 + i * (bw + gapx), 20 + lv * (bh + gapy))
    y_unres = 20 + (max(rows) + 1 if rows else 0) * (bh + gapy) + 20
    if unresolved:
        total = len(unresolved) * bw + (len(unresolved) - 1) * gapx
        x0 = (width - total) // 2
        for i, nid in enumerate(unresolved):
            pos[nid] = (x0 + i * (bw + gapx), y_unres + 24)
    height = (y_unres + 24 + bh + 20) if unresolved else y_unres
    body = []
    for e in topo["edges"]:
        if e["source"] not in pos or e["target"] not in pos:
            continue
        (x1, y1), (x2, y2) = pos[e["source"]], pos[e["target"]]
        dash = " stroke-dasharray='6 4'" if e["evidence"] in ("manual", "derived") else ""
        color = {"api": "#475569", "lldp": "#2563eb", "manual": "#a16207", "derived": "#0ea5e9"}.get(e["evidence"],
                                                                                                    "#475569")
        sx, sy, tx, ty = x1 + bw // 2, y1 + bh, x2 + bw // 2, y2
        body.append(f"<line x1='{sx}' y1='{sy}' x2='{tx}' y2='{ty}' stroke='{color}' stroke-width='2'{dash}/>")
        if e.get("label"):
            body.append(f"<text x='{(sx + tx) // 2 + 4}' y='{(sy + ty) // 2}' font-size='10' fill='#334155'>"
                        f"{_t(e['label'], 22)}</text>")
    if unresolved:
        body.append(f"<text x='20' y='{y_unres + 10}' font-size='12' fill='#b91c1c'>Connection unknown "
                    "(no uplink reported by the controller):</text>")
    for nid, (x, y) in pos.items():
        n = nodes[nid]
        color = NODE_COLORS.get(n["type"], "#475569")
        offline = n["data"].get("status") not in (None, "online", "connected")
        dash = " stroke-dasharray='5 3'" if nid in unresolved else ""
        body.append(f"<rect x='{x}' y='{y}' width='{bw}' height='{bh}' rx='8' fill='white' stroke='{color}' "
                    f"stroke-width='2'{dash}/>")
        body.append(f"<rect x='{x}' y='{y}' width='6' height='{bh}' rx='3' fill='{color}'/>")
        body.append(f"<text x='{x + 14}' y='{y + 20}' font-size='12' font-weight='bold' fill='#0f172a'>"
                    f"{_t(n['label'], 24)}</text>")
        sub = " · ".join(str(v) for v in (n["data"].get("model"), n["data"].get("ip")) if v) or n["type"]
        body.append(f"<text x='{x + 14}' y='{y + 38}' font-size='10' fill='#475569'>{_t(sub, 30)}</text>")
        if offline:
            body.append(f"<circle cx='{x + bw - 12}' cy='{y + 12}' r='5' fill='#dc2626'/>")
    legend_y = height + 4
    items = [("Reported by controller", "#475569", ""), ("LLDP", "#2563eb", ""),
             ("Manual / derived", "#a16207", " stroke-dasharray='6 4'")]
    for i, (label, color, dash) in enumerate(items):
        x = 20 + i * 200
        body.append(f"<line x1='{x}' y1='{legend_y + 8}' x2='{x + 30}' y2='{legend_y + 8}' stroke='{color}' "
                    f"stroke-width='2'{dash}/><text x='{x + 36}' y='{legend_y + 12}' font-size='11'>{label}</text>")
    return _svg(width, legend_y + 24, body)


def matrix_svg(matrix: dict[str, Any]) -> str:
    segs = matrix.get("segments") or []
    cells = {(c["source"], c["destination"]): c for c in matrix.get("cells") or []}
    n = len(segs)
    label_w, cell, top = 170, 34, 150
    width, height = label_w + n * cell + 20, top + n * cell + 60
    body = ["<text x='10' y='20' font-size='12' fill='#334155'>Rows: source · Columns: destination</text>"]
    for j, s in enumerate(segs):
        x = label_w + j * cell + cell // 2
        body.append(f"<text transform='translate({x + 4},{top - 6}) rotate(-60)' font-size='11'>"
                    f"{_t(s['name'], 22)}</text>")
    for i, src in enumerate(segs):
        y = top + i * cell
        body.append(f"<text x='{label_w - 8}' y='{y + cell // 2 + 4}' font-size='11' text-anchor='end'>"
                    f"{_t(src['name'], 24)}</text>")
        for j, dst in enumerate(segs):
            x = label_w + j * cell
            if src["id"] == dst["id"]:
                body.append(f"<rect x='{x}' y='{y}' width='{cell}' height='{cell}' fill='#f1f5f9' stroke='white'/>")
                continue
            c = cells.get((src["id"], dst["id"]))
            status = c["status"] if c else "unknown"
            body.append(f"<rect x='{x}' y='{y}' width='{cell}' height='{cell}' fill='{STATUS_COLORS[status]}' "
                        f"stroke='white' stroke-width='2' opacity='{0.55 if c and c.get('basis') == 'default' else 1}'/>")
            symbol = {"allowed": "✓", "blocked": "✕", "restricted": "!", "unknown": "?"}[status]
            body.append(f"<text x='{x + cell // 2}' y='{y + cell // 2 + 5}' font-size='14' text-anchor='middle' "
                        f"fill='white'>{symbol}</text>")
    ly = top + n * cell + 20
    for k, (status, color) in enumerate(STATUS_COLORS.items()):
        x = 10 + k * 140
        body.append(f"<rect x='{x}' y='{ly}' width='16' height='16' fill='{color}'/>"
                    f"<text x='{x + 22}' y='{ly + 13}' font-size='11'>{status.title()}</text>")
    body.append(f"<text x='{10 + 4 * 140}' y='{ly + 13}' font-size='11' fill='#475569'>Faded = default behaviour "
                "(no explicit rule)</text>")
    return _svg(max(width, 900), height, body)


def port_matrix_svg(switch: dict[str, Any], ports: list[dict[str, Any]]) -> str:
    pw, ph, gap = 40, 34, 6
    cols = (len(ports) + 1) // 2 or 1
    width, height = 20 + cols * (pw + gap) + 20, 2 * (ph + gap) + 70
    body = []
    for idx, p in enumerate(ports):
        col, row = idx // 2, idx % 2
        x, y = 20 + col * (pw + gap), 10 + row * (ph + gap)
        if p.get("warning"):
            color = "#dc2626"
        elif p.get("link_role") == "uplink":
            color = "#2563eb"
        elif (p.get("poe") or {}).get("active"):
            color = "#f59e0b"
        elif p.get("link_status") == "up":
            color = "#16a34a"
        else:
            color = "#9ca3af"
        body.append(f"<rect x='{x}' y='{y}' width='{pw}' height='{ph}' rx='4' fill='{color}'/>")
        body.append(f"<text x='{x + pw // 2}' y='{y + ph // 2 + 5}' font-size='12' fill='white' text-anchor='middle' "
                    f"font-weight='bold'>{p.get('port')}</text>")
    ly = 2 * (ph + gap) + 30
    legend = [("Link", "#16a34a"), ("No link", "#9ca3af"), ("PoE active", "#f59e0b"), ("Warning", "#dc2626"),
              ("Uplink", "#2563eb")]
    for k, (label, color) in enumerate(legend):
        x = 20 + k * 110
        body.append(f"<rect x='{x}' y='{ly}' width='14' height='14' fill='{color}'/>"
                    f"<text x='{x + 20}' y='{ly + 12}' font-size='11'>{label}</text>")
    return _svg(max(width, 580), height, body)


def segmentation_svg(segmentation: list[dict[str, Any]]) -> str:
    bw, bh, gap = 200, 92, 16
    per_row = 5
    rows = (len(segmentation) + per_row - 1) // per_row or 1
    width = per_row * (bw + gap) + gap
    height = rows * (bh + gap) + gap
    body = []
    palette = ["#4f46e5", "#0891b2", "#16a34a", "#ca8a04", "#db2777", "#7c3aed", "#ea580c", "#0d9488"]
    for i, s in enumerate(sorted(segmentation, key=lambda s: s.get("vlan_id") or 0)):
        x, y = gap + (i % per_row) * (bw + gap), gap + (i // per_row) * (bh + gap)
        color = "#f59e0b" if s.get("guest") else palette[i % len(palette)]
        body.append(f"<rect x='{x}' y='{y}' width='{bw}' height='{bh}' rx='10' fill='{color}' fill-opacity='0.08' "
                    f"stroke='{color}' stroke-width='2'/>")
        body.append(f"<text x='{x + 12}' y='{y + 22}' font-size='13' font-weight='bold' fill='{color}'>"
                    f"VLAN {s.get('vlan_id') if s.get('vlan_id') is not None else '?'} · {_t(s.get('name'), 16)}</text>")
        body.append(f"<text x='{x + 12}' y='{y + 42}' font-size='11'>{_t(s.get('subnet') or 'No subnet', 30)}</text>")
        body.append(f"<text x='{x + 12}' y='{y + 60}' font-size='11' fill='#475569'>"
                    f"{_t('SSIDs: ' + (', '.join(s.get('ssids') or []) or '–'), 30)}</text>")
        body.append(f"<text x='{x + 12}' y='{y + 78}' font-size='11' fill='#475569'>Clients: {s.get('client_count', 0)}"
                    f"{' · Guest' if s.get('guest') else ''}</text>")
    return _svg(width, height, body)
