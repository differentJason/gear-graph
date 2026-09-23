#!/usr/bin/env python3
"""Knowledge-graph views for the public site, as dependency-free inline SVG. Input is the PUBLIC snapshot only
(graph/public/vertices.json, edges.json), so nothing derived from manual text can appear here.

    schema_diagram(g)              what kinds of things and relationships the graph holds, with counts
    routing_diagram(g, media, ...) how the gear is wired, one panel per group of media
    rack_diagram(g)                which module sits in which case, sized by HP, shaded by +12V draw

Design notes (dataviz method): cable medium is IDENTITY, so it takes the categorical palette in fixed slot order
(validated for both site surfaces); an unconfirmed link is DASHED, never a colour; draw is a MAGNITUDE, so it is a
one-hue ramp; every diagram has a legend, a title element per mark, and a table beside it on the page.
"""
import json
import re
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

from viz import _svg, _t

MEDIUM = {"audio": "Audio", "usb": "USB (two-way)", "midi": "MIDI", "clock": "Clock / sync"}   # fixed slot order 1-4


class Graph:
    """The public snapshot with a few lookups."""

    def __init__(self, root):
        d = Path(root) / "graph" / "public"
        self.v = {x["id"]: x for x in json.loads((d / "vertices.json").read_text())}
        self.e = json.loads((d / "edges.json").read_text())

    def edges(self, rel, **where):
        return [e for e in self.e if e["rel"] == rel and all(e.get(k) == v for k, v in where.items())]

    def counts(self):
        vt, et = defaultdict(int), defaultdict(int)
        for x in self.v.values():
            vt[x["type"]] += 1
        for e in self.e:
            et[e["rel"]] += 1
        return vt, et

    def specs(self, item_id):
        return {self.v[e["dst"]]["field"]: self.v[e["dst"]] for e in self.edges("HAS_SPEC", src=item_id)}


def short(v):
    """Display name: drop the maker prefix and a trailing 1U tag ('Elektron Analog Four MKII' -> 'Analog Four MKII')."""
    n, m = v["name"], v.get("manufacturer") or ""
    if m and n.startswith(m + " ") and len(n) > len(m) + 1:
        n = n[len(m) + 1:]
    return n[:-3] if n.endswith(" 1U") else n


def _fit(text, chars):
    return text if len(text) <= chars else text[: max(chars - 1, 1)] + "…"


def _fit_words(text, chars):
    """Shorten at a word boundary ('qTone Eurorack Dual Channel...' -> 'qTone Eurorack…') instead of mid-word."""
    if len(text) <= chars:
        return text
    out = ""
    for w in text.split():
        if len(out) + len(w) + (1 if out else 0) > chars - 1:
            break
        out = f"{out} {w}".strip()
    return (out or text[: chars - 1]) + "…"


def _wrap(text, chars, max_lines):
    """Greedy word wrap. Returns the lines, or None if it does not fit."""
    lines, cur = [], ""
    for w in text.split():
        if len(w) > chars:
            return None
        if len(cur) + len(w) + (1 if cur else 0) <= chars:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines if len(lines) <= max_lines else None


# ------------------------------------------------------------------------------------------ schema
def schema_diagram(g):
    vt, et = g.counts()
    boxes = {  # key: (x, y, label, local_only)
        "manufacturer": (110, 20), "item": (110, 170), "category": (110, 320),
        "manual": (350, 20), "spec": (350, 170), "source": (350, 320),
        "section": (590, 20), "question": (590, 170), "tag": (760, 170)}
    w, h = 130, 46
    local = {"section"}

    def box(k):
        x, y = boxes[k]
        if k in local:
            return (f'<g><title>{k}: local only. Derived from the manufacturers\' copyrighted manuals, so it is not in the public graph.</title>'
                    f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="b-local"/>' + _t(x + w / 2, y + 20, k, "bt", "middle")
                    + _t(x + w / 2, y + 36, "local only", "bm", "middle") + "</g>")
        return (f'<g><title>{k}: {vt[k]} nodes in the public graph</title><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="b-tool"/>'
                + _t(x + w / 2, y + 20, k, "bt", "middle") + _t(x + w / 2, y + 36, f"{vt[k]} nodes", "bm", "middle") + "</g>")

    def anchor(k, side):
        x, y = boxes[k]
        return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h)}[side]

    def arrow(a, sa, b_, sb, label, dx=0, dy=0, dashed=False, anchor_="middle"):
        (x1, y1), (x2, y2) = anchor(a, sa), anchor(b_, sb)
        cls = "edge dashed" if dashed else "edge"
        mx, my = (x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy
        return (f'<path d="M{x1} {y1} L{x2} {y2}" class="{cls}" marker-end="url(#sc-ar)"/>' + _t(mx, my, label, "elabel", anchor_))

    n = lambda rel: et.get(rel, 0)
    body = ['<defs><marker id="sc-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            '<path d="M0 1 L9 5 L0 9 z" class="arrowhead"/></marker></defs>']
    body += [arrow("item", "t", "manufacturer", "b", f"MADE_BY {n('MADE_BY')}", 8, 0, anchor_="start"),
             arrow("item", "b", "category", "t", f"IN_CATEGORY {n('IN_CATEGORY')}", 8, 0, anchor_="start"),
             arrow("item", "r", "spec", "l", f"HAS_SPEC {n('HAS_SPEC')}", 0, -8),
             arrow("spec", "b", "source", "t", f"SOURCED_FROM {n('SOURCED_FROM')}", 8, 0, anchor_="start"),
             arrow("item", "r", "manual", "l", f"HAS_MANUAL {n('HAS_MANUAL')}", 16, -4, anchor_="start"),
             arrow("manual", "r", "section", "l", "HAS_SECTION (local)", 0, -8, dashed=True),
             arrow("section", "r", "tag", "t", "TAGGED (local)", 6, 0, dashed=True, anchor_="start"),
             arrow("question", "t", "section", "b", "EXPECTS (local)", 8, 0, dashed=True, anchor_="start")]
    # consulted: item -> source, a straight diagonal that stays clear of the other boxes
    body.append('<path d="M240 208 L350 338" class="edge" marker-end="url(#sc-ar)"/>')
    body.append(_t(326, 288, f"CONSULTED {n('CONSULTED')}", "elabel", "start"))
    # self links on item
    body.append('<path d="M110 185 C52 168 52 226 110 209" class="edge" marker-end="url(#sc-ar)"/>')
    body.append(_t(8, 100, "item → item", "tb"))
    for i, rel in enumerate(("CONNECTS", "INSTALLED_IN", "POWERED_BY")):
        body.append(_t(8, 118 + i * 15, f"{rel} {n(rel)}", "elabel", "start"))
    body += [box(k) for k in boxes]
    h_total = 410
    legend = (f'<rect x="8" y="{h_total - 26}" width="14" height="10" class="b-tool"/>' + _t(28, h_total - 17, "in the public graph (count of nodes)", "tm")
              + f'<rect x="280" y="{h_total - 26}" width="14" height="10" class="b-local"/>' + _t(300, h_total - 17, "local only (derived from copyrighted manuals); dashed arrows touch it", "tm"))
    desc = ("Node types and relationships. " + "; ".join(f"{k} {vt[k]}" for k in sorted(vt)) + ". Relationships: "
            + "; ".join(f"{r} {c}" for r, c in sorted(et.items())) + ". Section nodes exist only on the author's machine.")
    return _svg(900, h_total, "Structure of the knowledge graph", desc, "".join(body) + legend)


# ------------------------------------------------------------------------------------------ composition
def category_chart(g):
    """Horizontal bar chart of item counts per category, computed from the graph's IN_CATEGORY edges
    (item -> category), not from re-reading inventory.yaml -- this is a view of the graph, not the source file."""
    counts = Counter(g.v[e["dst"]]["name"] for e in g.edges("IN_CATEGORY"))
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    left, row_h, top, plot_w = 220, 22, 16, 460
    mx = max(counts.values())
    scale = plot_w / mx
    body = []
    for i, (label, n) in enumerate(rows):
        y = top + i * row_h
        body.append(_t(left - 10, y + 15, label, "t", "end"))
        wv = max(n * scale, 2)
        body.append(f'<rect x="{left}" y="{y}" width="{wv:.1f}" height="16" class="cat-bar">'
                    f'<title>{escape(label)}: {n} item{"s" if n != 1 else ""}</title></rect>')
        body.append(_t(left + wv + 6, y + 14, str(n), "tm"))
    h = top + len(rows) * row_h + 10
    desc = ("How many items the graph has in each category, from its IN_CATEGORY edges: "
            + "; ".join(f"{l} {n}" for l, n in rows))
    return _svg(left + plot_w + 60, h, "Items by category", desc, "".join(body))


# ------------------------------------------------------------------------------------------ routing
def _natural(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s or "")]


def _reach_dist(edges, root_vid):
    """Hop count from root_vid to every vertex reachable over these (already-filtered) edges, confirmed only --
    same rule as query_graph.py's reach(): only confirmed connections count. BFS, not a graph library, since this
    module has no Spark dependency."""
    conf = [e for e in edges if e["status"] == "confirmed"]
    dist, frontier = {root_vid: 0}, [root_vid]
    while frontier:
        nxt = []
        for n in frontier:
            for e in conf:
                if e["src"] == n and e["dst"] not in dist:
                    dist[e["dst"]] = dist[n] + 1
                    nxt.append(e["dst"])
        frontier = nxt
    return dist


def routing_diagram(g, media, panel_title, uid, setup="main-studio", layering="asap", root=None):
    """Layered left-to-right wiring diagram. Port names sit INSIDE the device boxes, level with their cable, so labels
    never collide. layering='alap' pushes sources right, next to what they feed (good when many sources feed one sink).
    root: an inventory id (bare, no 'item:' prefix). When given, each box is captioned with its hop distance from
    root over confirmed edges only -- turns a `reach` query's answer into a picture instead of just a table."""
    edges = [e for e in g.edges("CONNECTS", setup=setup) if e["medium"] in media]
    root_vid = f"item:{root}" if root else None
    dist = _reach_dist(edges, root_vid) if root_vid else {}
    order = []
    for e in sorted(edges, key=lambda e: (e["src"], e["dst"])):
        for k in (e["src"], e["dst"]):
            if k not in order:
                order.append(k)
    succ, pred = defaultdict(list), defaultdict(list)
    for e in edges:
        succ[e["src"]].append(e)
        pred[e["dst"]].append(e)
    depth_m, height_m = {}, {}

    def depth(n):
        if n not in depth_m:
            depth_m[n] = 1 + max((depth(e["src"]) for e in pred[n]), default=-1)
        return depth_m[n]

    def height(n):
        if n not in height_m:
            height_m[n] = 1 + max((height(e["dst"]) for e in succ[n]), default=-1)
        return height_m[n]

    top_layer = max(depth(n) for n in order)
    layer_of = {n: (top_layer - height(n) if layering == "alap" else depth(n)) for n in order}
    layers = defaultdict(list)
    for n in order:
        layers[layer_of[n]].append(n)
    n_layers = max(layers) + 1

    # node geometry: name lines on top, then one 16px row per cable that needs a port label
    def swappable(n):
        return bool(pred[n]) and all(e.get("swappable") for e in pred[n])

    def midi_caption(n):
        if "midi" not in media:
            return ""
        v = g.v[n]
        parts = []
        if v.get("midi_in_ch"):
            parts.append(f"IN {v['midi_in_ch']}")
        if v.get("midi_out_ch"):
            parts.append(f"OUT {v['midi_out_ch']}")
        return " · ".join(parts)

    def hop_caption(n):
        if not root_vid or n not in dist:
            return ""
        return "root" if dist[n] == 0 else f"{dist[n]} hop" + ("s" if dist[n] != 1 else "")

    bw, gap, top = 176, 16, 34
    geo = {}
    for n in order:
        v = g.v[n]
        name = short(v)
        lines = _wrap(name, 22, 2) or [_fit(name, 22)]
        head = (6 + 14 * len(lines) + (12 if swappable(n) else 0) + (12 if midi_caption(n) else 0)
                + (12 if hop_caption(n) else 0) + 4)
        in_lab, out_lab = any(e.get("to_port") for e in pred[n]), any(e.get("from_port") for e in succ[n])
        rows = max(len(pred[n]) if in_lab or len(pred[n]) > 1 else 0, len(succ[n]) if out_lab or len(succ[n]) > 1 else 0)
        geo[n] = {"lines": lines, "head": head, "h": max(40, head + 16 * rows + 4) if rows else max(40, head + 8), "in_lab": in_lab, "out_lab": out_lab}

    for k in range(n_layers):        # order each layer: by port number where cables land on numbered ports, else by neighbours
        prev = {n: i for i, n in enumerate(layers[k - 1])} if k else {}
        layers[k].sort(key=lambda n: (_natural(min((e.get("to_port") or "~" for e in succ[n]), default="~")),
                                      sum(prev.get(e["src"], 0) for e in pred[n]) / max(len(pred[n]), 1)))
    total = {k: sum(geo[n]["h"] for n in layers[k]) + gap * (len(layers[k]) - 1) for k in layers}
    plot_h = max(total.values())
    pos = {}
    for k in range(n_layers):
        x = 20 + (k * (900 - 40 - bw) / (n_layers - 1) if n_layers > 1 else (900 - bw) / 2 - 20)
        y = top + (plot_h - total[k]) / 2
        for n in layers[k]:
            pos[n] = (x, y)
            y += geo[n]["h"] + gap

    def cy(n):
        return pos[n][1] + geo[n]["h"] / 2

    for n in order:                  # cables leave/arrive top to bottom in the order of what they connect to
        succ[n].sort(key=lambda e: (cy(e["dst"]), _natural(e.get("to_port"))))
        pred[n].sort(key=lambda e: (_natural(e.get("to_port")), cy(e["src"])))

    def attach(n, lst, e, labelled):
        gm, (x, y) = geo[n], pos[n]
        if len(lst) == 1 and not labelled:
            return y + gm["h"] / 2
        return y + gm["head"] + 8 + 16 * lst.index(e)

    body = ['<defs>' + "".join(f'<marker id="{uid}-{m}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                               f'<path d="M0 1 L9 5 L0 9 z" class="mk-{m}"/></marker>' for m in MEDIUM) + '</defs>', _t(8, 18, panel_title, "tb")]
    ports = []                        # port labels are drawn after the boxes, inside them
    out_done = set()
    for e in edges:
        (sx, _), (dx, _) = pos[e["src"]], pos[e["dst"]]
        y1 = attach(e["src"], succ[e["src"]], e, geo[e["src"]]["out_lab"])
        y2 = attach(e["dst"], pred[e["dst"]], e, geo[e["dst"]]["in_lab"])
        x1, x2 = sx + bw, dx
        c = (x2 - x1) / 2
        dash = "" if e["status"] == "confirmed" else ' stroke-dasharray="7 4"'
        ports_txt = f', {e["from_port"]} → {e["to_port"]}' if e.get("from_port") and e.get("to_port") else (f', {e.get("from_port") or e.get("to_port")}' if (e.get("from_port") or e.get("to_port")) else "")
        tip = f'{g.v[e["src"]]["name"]} → {g.v[e["dst"]]["name"]}: {MEDIUM[e["medium"]]}{ports_txt} ({e["status"]}{", swappable" if e.get("swappable") else ""})'
        start = f' marker-start="url(#{uid}-{e["medium"]})"' if e.get("bidirectional") else ""
        body.append(f'<path d="M{x1} {y1} C{x1 + c} {y1} {x2 - c} {y2} {x2} {y2}" class="ln ln-{e["medium"]}" marker-end="url(#{uid}-{e["medium"]})"{start}{dash}><title>{escape(tip)}</title></path>')
        if e.get("to_port"):
            ports.append(_t(x2 + 7, y2 + 4, e["to_port"], "port", "start"))
        if e.get("from_port"):
            key = (e["src"], e["from_port"])
            if key not in out_done:   # one label per port even when a port feeds several cables
                out_done.add(key)
                ys = [attach(e["src"], succ[e["src"]], f, True) for f in succ[e["src"]] if f.get("from_port") == e["from_port"]]
                ports.append(_t(x1 - 7, sum(ys) / len(ys) + 4, e["from_port"], "port", "end"))
    for n, (x, y) in pos.items():
        v, gm = g.v[n], geo[n]
        capy = y + 6 + 14 * len(gm["lines"]) + 9
        captions = ""
        if swappable(n):
            captions += _t(x + bw / 2, capy, "swappable", "bm", "middle")
            capy += 12
        mc = midi_caption(n)
        if mc:
            captions += _t(x + bw / 2, capy, mc, "bm", "middle")
            capy += 12
        hc = hop_caption(n)
        if hc:
            captions += _t(x + bw / 2, capy, hc, "bm", "middle")
        box_cls = "b-tool b-root" if n == root_vid else "b-tool"
        body.append(f'<g><title>{escape(v["name"])}</title><rect x="{x}" y="{y}" width="{bw}" height="{gm["h"]}" rx="6" class="{box_cls}"/>'
                    + "".join(_t(x + bw / 2, y + 6 + 14 * i + 10, ln, "bt", "middle") for i, ln in enumerate(gm["lines"]))
                    + captions + "</g>")
    body += ports
    h = top + plot_h + 44
    used = [m for m in MEDIUM if any(e["medium"] == m for e in edges)]
    lx, ly = 8, h - 16
    legend = []
    for m in used:
        legend.append(f'<line x1="{lx}" y1="{ly}" x2="{lx + 26}" y2="{ly}" class="ln ln-{m}"/>' + _t(lx + 32, ly + 4, MEDIUM[m], "tm"))
        lx += 52 + 6.6 * len(MEDIUM[m])
    if any(e["status"] != "confirmed" for e in edges):
        legend.append(f'<line x1="{lx}" y1="{ly}" x2="{lx + 26}" y2="{ly}" class="ln ln-none" stroke-dasharray="7 4"/>' + _t(lx + 32, ly + 4, "dashed = not yet confirmed by the owner", "tm"))
    desc = f"{panel_title}. " + "; ".join(f'{short(g.v[e["src"]])} to {short(g.v[e["dst"]])} by {MEDIUM[e["medium"]]} ({e["status"]})' for e in edges)
    return _svg(900, h, panel_title, desc, "".join(body) + "".join(legend))


# ------------------------------------------------------------------------------------------ rack
RAMP = ((0xBC, 0xD6, 0xF5), (0x6E, 0xA6, 0xEC))    # one hue, light -> darker; #111 text clears 8:1 on both ends


def _ramp(t):
    return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(*RAMP))


def rack_modules(g, case_id, setup="main-studio"):
    """[{id, name, hp, fmt, row, position, p12, status, attested}] for confirmed placements in a case."""
    out = []
    for e in g.edges("INSTALLED_IN", dst=case_id, setup=setup):
        if e["status"] != "confirmed":
            continue
        it, sp = g.v[e["src"]], g.specs(e["src"])
        p12 = sp.get("ma_p12", {})
        out.append({"id": e["src"], "name": it["name"], "short": short(it), "hp": int((sp.get("hp") or {}).get("value") or 0),
                    "fmt": it.get("format") or "3U", "row": e.get("row"), "position": e.get("position"), "role": it.get("role"),
                    "p12": p12.get("value"), "p12_status": p12.get("status"), "attested": bool(p12.get("attested"))})
    return out


def rack_diagram(g, setup="main-studio"):
    cases = [v for v in g.v.values() if v["type"] == "item" and v.get("rows")]
    S, left, right = 9.3, 46, 900 - 46 - 84 * 9.3
    every = [m for c in cases for m in rack_modules(g, c["id"], setup)]
    vmax = max([m["p12"] for m in every if m["p12"] is not None and m["role"] != "supply"] + [1])
    body, y = [], 6

    def block(m, x, yy, w, hh):
        supply = m["role"] == "supply"
        fill = "b-out" if supply else "st-missing" if m["p12"] is None else ""
        style = "" if supply or m["p12"] is None else f' style="fill:{_ramp(m["p12"] / vmax)}"'
        tip = (f'{m["name"]}: {m["hp"]} HP; ' + (f'+12V {m["p12"]} mA ({m["p12_status"]}{", owner-attested" if m["attested"] else ""})'
               if m["p12"] is not None else "+12V draw not stated") + ("; power supply" if m["role"] == "supply" else ""))
        parts = [f'<g><title>{escape(tip)}</title><rect x="{x:.1f}" y="{yy}" width="{w - 2:.1f}" height="{hh}" rx="3" class="blk {fill}"{style}/>']
        label = "PSU" if m["role"] == "supply" else m["short"]
        chars, lines = int((w - 8) / 6.0), int((hh - 6) / 13)
        wrapped = _wrap(label, chars, lines) if chars >= 3 else None
        if wrapped:
            y0 = yy + hh / 2 - (len(wrapped) - 1) * 6.5 + 4
            parts += [_t(x + (w - 2) / 2, y0 + i * 13, ln, "bm", "middle") for i, ln in enumerate(wrapped)]
        elif hh >= 60 and w >= 14:
            vt = _fit_words(label, int((hh - 10) / 6.0))
            parts.append(f'<text x="{x + (w - 2) / 2 + 4:.1f}" y="{yy + hh / 2}" class="bm" text-anchor="middle" transform="rotate(-90 {x + (w - 2) / 2 + 4:.1f} {yy + hh / 2})">{escape(vt)}</text>')
        parts.append("</g>")
        return "".join(parts)

    for c in sorted(cases, key=lambda c: c["name"]):
        mods = rack_modules(g, c["id"], setup)
        rows = [(r.split(":")[0], int(r.split(":")[1])) for r in c["rows"].split(",")]
        used = sum(m["hp"] for m in mods)
        cap_by_fmt = defaultdict(int)
        for f_, hp_ in rows:
            cap_by_fmt[f_] += hp_
        first = next((m for m in mods if m["role"] != "supply"), None)
        supply = next((g.v[e["dst"]] for e in g.edges("POWERED_BY", setup=setup) if first and e["src"] == first["id"]), None)
        fed = "built-in supply" if supply and supply["id"] == c["id"] else f'fed by {supply["name"]}' if supply else "supply not recorded"
        body.append(_t(left, y + 14, f'{c["name"]}', "tb"))
        body.append(_t(left + 12 + 7 * len(c["name"]), y + 14, f'· {fed} · {used} HP placed in {sum(h for _, h in rows)} HP of rows', "tm"))
        y += 24
        placed_1u = sorted([m for m in mods if (m["row"] or m["fmt"]) == "1U"], key=lambda m: m["short"])
        placed_3u = [m for m in mods if (m["row"] or m["fmt"]) != "1U"]
        ordered = any(m["position"] for m in placed_3u)
        placed_3u.sort(key=lambda m: (m["position"] or 0) if ordered else m["short"].lower())
        unordered_3u = bool(placed_3u) and not ordered
        queue = {"1U": placed_1u, "3U": placed_3u}       # blocks fill each row in order, wrapping at the row's width
        for f_, hp_ in rows:
            hh = 46 if f_ == "1U" else 118
            body.append(f'<rect x="{left}" y="{y}" width="{hp_ * S:.1f}" height="{hh}" rx="4" class="rackbg"/>')
            body.append(_t(left - 6, y + hh / 2 + 4, f_, "tm", "end"))
            x_hp, q = 0, queue[f_]
            while q and x_hp + q[0]["hp"] <= hp_:
                m = q.pop(0)
                body.append(block(m, left + x_hp * S, y, m["hp"] * S, hh))
                x_hp += m["hp"]
            y += hh + 6
        if any(queue.values()):
            body.append(_t(left, y + 12, "note: some modules did not fit their row in this drawing", "tm"))
            y += 16
        if unordered_3u:
            body.append(_t(left, y + 8, "Row and position within the 3U rows are not recorded: modules are drawn in name order, wrapped at each row's width.", "tiny"))
            y += 18
        y += 16
    # legend
    gid = "rack-ramp"
    body.append(f'<defs><linearGradient id="{gid}" x1="0" x2="1"><stop offset="0" stop-color="{_ramp(0)}"/><stop offset="1" stop-color="{_ramp(1)}"/></linearGradient></defs>')
    lx, ly = left, y + 6
    body += [_t(lx, ly + 10, "+12V draw", "tm"), f'<rect x="{lx + 66}" y="{ly}" width="130" height="12" rx="2" fill="url(#{gid})"/>',
             _t(lx + 66, ly + 26, "0 mA", "tiny"), _t(lx + 196, ly + 26, f"{int(vmax)} mA", "tiny", "end"),
             f'<rect x="{lx + 236}" y="{ly}" width="26" height="12" rx="2" class="st-missing"/>', _t(lx + 268, ly + 10, "no figure stated", "tm"),
             f'<rect x="{lx + 386}" y="{ly}" width="26" height="12" rx="2" class="b-out"/>', _t(lx + 418, ly + 10, "power supply mounted in the case", "tm"),
             _t(lx + 66, ly + 42, "Block width is proportional to HP. 1U-format modules sit in their own row. The NiftyCASE row is its usable area per the maker.", "tiny")]
    h = ly + 54
    desc = "; ".join(f'{c["name"]}: ' + ", ".join(f'{m["short"]} {m["hp"]} HP' for m in rack_modules(g, c["id"], setup)) for c in cases)
    return _svg(900, h, "Where each Eurorack module is mounted", desc, "".join(body))


CSS = """
.viz-svg { --m-audio: #2a78d6; --m-usb: #eda100; --m-midi: #eb6834; --m-clock: #1baf7a; }
[data-md-color-scheme="slate"] .viz-svg { --m-audio: #3987e5; --m-usb: #c98500; --m-midi: #d95926; --m-clock: #199e70; }
.viz-svg .ln { fill: none; stroke-width: 2.2; stroke-linecap: round; }
.viz-svg .ln-audio { stroke: var(--m-audio); } .viz-svg .ln-usb { stroke: var(--m-usb); stroke-width: 3; }
.viz-svg .ln-midi { stroke: var(--m-midi); }   .viz-svg .ln-clock { stroke: var(--m-clock); }
.viz-svg .ln-none { stroke: var(--md-default-fg-color--light); }
.viz-svg .mk-audio { fill: var(--m-audio); } .viz-svg .mk-usb { fill: var(--m-usb); }
.viz-svg .mk-midi { fill: var(--m-midi); }   .viz-svg .mk-clock { fill: var(--m-clock); }
.viz-svg .elabel { fill: var(--md-default-fg-color--light); font-size: 10.5px; paint-order: stroke; stroke: var(--md-default-bg-color); stroke-width: 3px; }
.viz-svg .edge.dashed { stroke-dasharray: 6 4; }
.viz-svg .port { fill: #222; font-size: 10.5px; font-weight: 600; }
.viz-svg .rackbg { fill: var(--md-default-fg-color--lightest); }
.viz-svg .b-root { stroke: #0072B2; stroke-width: 3; }
.viz-svg .cat-bar { fill: #9ad3f3; }
"""
