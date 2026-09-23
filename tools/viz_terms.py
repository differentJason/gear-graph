#!/usr/bin/env python3
"""Terminology views for the public site, as dependency-free inline SVG. Input is graph/public/terms.json (TERMS.yaml
plus per-manual label COUNTS, no manual text) and the public graph snapshot for which maker wrote which manual.

    taxonomy_tree(t)          the concept hierarchy, one panel per facet, with how many manuals use each concept
    ontology_diagram(t)       the ontology at class level: which kinds of concept each typed relation connects
    neighbourhood(t, focus)   one real example: kinds of filter, its parameters, what modulates them
    naming_heatmap(t, g)      the same concept in different words: which label each maker's manuals use

Design notes (same method as viz_graph): usage is a MAGNITUDE, so it is a bar or the one-hue ramp; relationship KINDS
are told apart by line style and a printed label, never by colour alone (is-a = hollow arrowhead, as in UML; a typed
relation = filled arrowhead with its name; a close match = dashed, no arrowhead). Every figure has a table on the page.
"""
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

from viz import _svg, _t
from viz_graph import _fit, _ramp

FACET_GRID = [["signal", "port", "block"], ["parameter", "sequencing", "effect"], ["memory", "controller"]]


class Terms:
    """terms.json with a few lookups."""

    def __init__(self, root):
        self.d = json.loads((Path(root) / "graph" / "public" / "terms.json").read_text())
        self.c = {c["id"]: c for c in self.d["concepts"]}
        self.facet = {f["id"]: f for f in self.d["facets"]}
        self.n_manuals = self.d["corpus"]["manuals"]

    def name(self, x):
        return self.c[x]["pref"] if x in self.c else self.facet[x]["pref"]

    def manuals_using(self, cid):
        return sorted({m for per in self.c[cid]["labels"].values() for m in per})

    def children(self):
        """Primary parent -> children, in file order; plus (secondary parent -> children) for polyhierarchy."""
        prim, sec = defaultdict(list), defaultdict(list)
        for c in self.d["concepts"]:
            prim[c["broader"][0]].append(c["id"])
            for b in c["broader"][1:]:
                sec[b].append(c["id"])
        return prim, sec

    def facet_of(self, x):
        return self.c[x]["facet"] if x in self.c else x


def _arrowdefs(pfx):
    return (f'<defs><marker id="{pfx}-rel" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            '<path d="M0 1 L9 5 L0 9 z" class="arrowhead"/></marker>'
            f'<marker id="{pfx}-isa" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse">'
            '<path d="M1 1 L11 6 L1 11 z" class="isa-head"/></marker></defs>')


# ------------------------------------------------------------------------------------------ taxonomy
def taxonomy_tree(t):
    prim, sec = t.children()
    colw, lh, head = 300, 17, 36
    body, heights, panels = [], [], []
    for r, row in enumerate(FACET_GRID):
        rows_h = []
        for col, f in enumerate(row):
            lines = []

            def walk(node, depth):
                for k in prim.get(node, []):
                    lines.append((depth, k, False))
                    walk(k, depth + 1)
                for k in sec.get(node, []):
                    lines.append((depth, k, True))
            walk(f, 0)
            panels.append((r, col, f, lines))
            rows_h.append(head + len(lines) * lh + 10)
        heights.append(max(rows_h))
    ys = [6]
    for hh in heights[:-1]:
        ys.append(ys[-1] + hh + 12)
    for r, col, f, lines in panels:
        x0, y0 = 4 + col * colw, ys[r]
        n = sum(1 for _, k, s in lines if not s)
        body.append(f'<g><title>{escape(t.facet[f]["pref"])}: {escape(t.facet[f]["note"])} {n} concepts.</title>'
                    f'<rect x="{x0}" y="{y0}" width="{colw - 10}" height="24" rx="5" class="b-tool"/>'
                    + _t(x0 + 8, y0 + 16, t.facet[f]["pref"], "bt") + _t(x0 + colw - 18, y0 + 16, f"{n} concepts", "bm", "end") + "</g>")
        # connectors: a vertical from each parent down to its last child, and a tick into each child
        stack = []
        for i, (depth, k, secondary) in enumerate(lines):
            y = y0 + head + i * lh + 10
            px = x0 + 6 + depth * 12
            del stack[depth:]
            py = stack[depth - 1] if depth else y0 + 24
            body.append(f'<path d="M{px} {py + (4 if depth else 0)} V{y - 4} H{px + 7}" class="tree"/>')
            stack.append(y)
            c = t.c[k]
            label = _fit(c["pref"], 26 - depth * 2 - (6 if secondary else 0))
            used = len(t.manuals_using(k))
            if secondary:
                tip = f'{c["pref"]}: also a kind of {t.name(c["broader"][1])} (second parent; listed in full under {t.name(c["broader"][0])})'
                body.append(f'<g><title>{escape(tip)}</title>' + _t(px + 10, y, label + " (also)", "tm-i") + "</g>")
                continue
            alt = f'; also called {", ".join(c["alt"])}' if c["alt"] else ""
            tip = (f'{c["pref"]}{alt}. ' + ("A grouping node: it organises the tree and is not required to occur in the manuals."
                                              if c["grouping"] else f"Used in {used} of {t.n_manuals} manuals.") + (f' {c["note"]}' if c.get("note") else ""))
            cls = "tm-i" if c["grouping"] else "t"
            parts = [f'<g><title>{escape(tip)}</title>', _t(px + 10, y, label, cls)]
            if not c["grouping"]:
                bx = x0 + colw - 86
                parts.append(f'<rect x="{bx}" y="{y - 9}" width="{max(1.5, 48 * used / t.n_manuals):.1f}" height="9" class="cat-bar"/>')
                parts.append(_t(bx + 52, y, str(used), "tiny"))
            parts.append("</g>")
            body.append("".join(parts))
    h = ys[-1] + heights[-1] + 30
    legend = (f'<rect x="8" y="{h - 21}" width="48" height="9" class="cat-bar"/>' + _t(62, h - 12, f"manuals that use the concept (bar full = {t.n_manuals})", "tm")
              + _t(420, h - 12, "italic = grouping node, or a second parent (also)", "tm-i"))
    desc = (f"{len(t.d['concepts'])} concepts in {len(t.facet)} facets, drawn as indented trees. "
            + "; ".join(f"{t.facet[f]['pref']}: {sum(1 for c in t.d['concepts'] if c['facet'] == f)}" for f in t.facet) + ".")
    return _svg(900, h, "Taxonomy: the concept hierarchy by facet", desc, "".join(body) + legend)


# ------------------------------------------------------------------------------------------ ontology (class level)
# Facet boxes are placed by hand so the graph is planar (no crossing arrows): signal and parameter are the two hubs on
# the centre line; what feeds both sits either side. Each relation's label position is placed by hand too; a facet
# pair missing from LABEL falls back to the segment midpoint, which will look wrong and so gets noticed.
POS = {"port": (120, 40), "signal": (450, 40), "controller": (95, 200), "block": (285, 200), "sequencing": (620, 200),
       "memory": (820, 200), "parameter": (450, 350), "effect": (450, 460)}
LABEL = {  # (subject facet, object facet): (x, y, anchor)
    ("port", "signal"): (285, 30, "middle"), ("controller", "signal"): (196, 118, "end"), ("block", "signal"): (384, 166, "start"),
    ("sequencing", "signal"): (576, 142, "start"), ("signal", "sequencing"): (530, 142, "end"), ("signal", "memory"): (700, 116, "start"),
    ("signal", "parameter"): (458, 248, "start"), ("controller", "parameter"): (236, 296, "end"), ("block", "parameter"): (340, 238, "start"),
    ("sequencing", "parameter"): (560, 292, "start"), ("effect", "parameter"): (458, 410, "start"), ("memory", "sequencing"): (720, 190, "middle"),
    ("sequencing", "sequencing"): (655, 276, "middle"), ("memory", "memory"): (820, 276, "middle")}


def ontology_diagram(t):
    w, h = 130, 46
    agg = defaultdict(Counter)
    for r in t.d["relations"]:
        agg[(t.facet_of(r["s"]), t.facet_of(r["o"]))][r["p"]] += 1
    plabel = {p["id"]: p["label"] for p in t.d["predicates"]}
    per_facet = Counter(c["facet"] for c in t.d["concepts"])
    body = [_arrowdefs("on")]

    def clip(a, b):
        """Point where the segment a->b leaves box a (so arrows start and end on the box edge)."""
        (x1, y1), (x2, y2) = a, b
        dx, dy = x2 - x1, y2 - y1
        s = min(abs((w / 2) / dx) if dx else 9e9, abs((h / 2) / dy) if dy else 9e9)
        return x1 + dx * s, y1 + dy * s

    for (fs, fo), preds in sorted(agg.items()):
        lines = [f"{plabel[p]} {n}" for p, n in sorted(preds.items())]
        tip = f'{t.facet[fs]["pref"]} → {t.facet[fo]["pref"]}: {", ".join(lines)}'
        if fs == fo:                                                   # a loop under the box: relations inside one class
            x, y = POS[fs]
            x += 35 if fs == "sequencing" else 0                       # clear of the arrow down to parameter
            d = f"M{x - 18} {y + h / 2} C{x - 30} {y + h / 2 + 38} {x + 30} {y + h / 2 + 38} {x + 18} {y + h / 2}"
        else:
            a, b = POS[fs], POS[fo]
            off = 6 if (fo, fs) in agg else 0                          # two directions: two parallel lines
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = (dx * dx + dy * dy) ** 0.5
            ox, oy = -dy / ln * off, dx / ln * off
            (x1, y1), (x2, y2) = clip(a, b), clip(b, a)
            d = f"M{x1 + ox:.1f} {y1 + oy:.1f} L{x2 + ox:.1f} {y2 + oy:.1f}"
        body.append(f'<g><title>{escape(tip)}</title><path d="{d}" class="edge" marker-end="url(#on-rel)"/></g>')
        lx, ly, anchor = LABEL.get((fs, fo), ((POS[fs][0] + POS[fo][0]) / 2, (POS[fs][1] + POS[fo][1]) / 2, "middle"))
        body += [_t(lx, ly + i * 13, ln_, "elabel", anchor) for i, ln_ in enumerate(lines)]
    for f, (x, y) in POS.items():
        body.append(f'<g><title>{escape(t.facet[f]["pref"])}: {escape(t.facet[f]["note"])} {per_facet[f]} concepts.</title>'
                    f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" rx="6" class="b-tool"/>'
                    + _t(x, y - 3, _fit(t.facet[f]["pref"], 19), "bt", "middle") + _t(x, y + 13, f"{per_facet[f]} concepts", "bm", "middle") + "</g>")
    desc = ("Each box is a facet (a class of concept); each arrow is a kind of typed relation, labelled with how many relation "
            "statements of that kind connect the two classes. " + "; ".join(f"{t.facet[a]['pref']} to {t.facet[b]['pref']}: "
            + ", ".join(f"{plabel[p]} {n}" for p, n in preds.items()) for (a, b), preds in sorted(agg.items())) + ".")
    return _svg(900, 500, "Ontology: which kinds of concept each relation connects", desc, "".join(body))


# ------------------------------------------------------------------------------------------ one worked neighbourhood
def neighbourhood(t, focus="filter"):
    """Kinds of <focus> -> <focus> -> its parameters <- what modulates them <- kinds of modulator."""
    prim, sec = t.children()
    kids = lambda x: prim.get(x, []) + sec.get(x, [])
    rel = t.d["relations"]
    params = [r["o"] for r in rel if r["s"] == focus and r["p"] == "has_parameter"]
    mods = defaultdict(list)
    for r in rel:
        if r["p"] == "modulates" and r["o"] in params:
            mods[r["s"]].append(r["o"])
    mod_kinds = {m: [k for k in kids(m) if not t.c[k]["grouping"]] for m in mods}
    cols = [kids(focus), [focus], params, list(mods), [k for m in mods for k in mod_kinds[m]]]
    xs, bw, bh = [80, 255, 450, 645, 820], 150, 40
    pos = {}
    H = 60 + max(len(c) for c in cols) * 62
    for x, col in zip(xs, cols):
        top = (H - 30 - len(col) * 62) / 2 + 20
        for i, k in enumerate(col):
            pos[k] = (x, top + i * 62 + bh / 2)
    body = [_arrowdefs("nb")]

    def edge(a, b, kind, label=""):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        sx = 1 if x2 > x1 else -1
        x1, x2 = x1 + sx * bw / 2, x2 - sx * bw / 2
        cls, mk = ("edge isa", "nb-isa") if kind == "isa" else ("edge", "nb-rel")
        tip = f'{t.name(a)} {"is a kind of" if kind == "isa" else label} {t.name(b)}'
        s = f'<g><title>{escape(tip)}</title><path d="M{x1:.1f} {y1:.1f} C{(x1 + x2) / 2:.1f} {y1:.1f} {(x1 + x2) / 2:.1f} {y2:.1f} {x2:.1f} {y2:.1f}" class="{cls}" marker-end="url(#{mk})"/></g>'
        return s

    for k in cols[0]:
        body.append(edge(k, focus, "isa"))
    for p in params:
        body.append(edge(focus, p, "rel", "has parameter"))
    for m, targets in mods.items():
        for p in targets:
            body.append(edge(m, p, "rel", "modulates"))
        for k in mod_kinds[m]:
            body.append(edge(k, m, "isa"))
    heads = ["kinds of " + t.name(focus), t.name(focus), "its parameters", "what modulates them", "kinds of modulator"]
    for x, hd in zip(xs, heads):
        body.append(_t(x, 14, hd, "tb", "middle"))
    for k, (x, y) in pos.items():
        c = t.c[k]
        used = len(t.manuals_using(k))
        alt = f'also: {", ".join(c["alt"])}' if c["alt"] else ""
        tip = f'{c["pref"]}' + (f' (also called {", ".join(c["alt"])})' if c["alt"] else "") + f'. Used in {used} of {t.n_manuals} manuals.'
        body.append(f'<g><title>{escape(tip)}</title><rect x="{x - bw / 2}" y="{y - bh / 2}" width="{bw}" height="{bh}" rx="6" class="b-data"/>'
                    + _t(x, y - (2 if alt else -4), c["pref"], "bt", "middle") + (_t(x, y + 13, _fit(alt, 24), "bm", "middle") if alt else "") + "</g>")
    y = H - 12
    legend = (f'<path d="M8 {y - 4} H44" class="edge isa" marker-end="url(#nb-isa)"/>' + _t(52, y, "is a kind of (taxonomy)", "tm")
              + f'<path d="M230 {y - 4} H266" class="edge" marker-end="url(#nb-rel)"/>' + _t(274, y, "typed relation (ontology): has parameter, modulates", "tm"))
    desc = (f"Worked example around '{t.name(focus)}'. Kinds: {', '.join(t.name(k) for k in cols[0])}. Parameters: {', '.join(t.name(p) for p in params)}. "
            + " ".join(f"{t.name(m)} modulates {', '.join(t.name(p) for p in ps)}." for m, ps in mods.items())
            + " " + " ".join(f"{t.name(k)} is a kind of {t.name(m)}." for m in mods for k in mod_kinds[m]))
    return _svg(900, H, f"Taxonomy and ontology together: the {t.name(focus)}", desc, "".join(body) + legend)


# ------------------------------------------------------------------------------------------ same concept, different words
def maker_of_manual(g):
    """manual id -> manufacturer, from the public graph (item -HAS_MANUAL-> manual; the item carries its maker)."""
    return {e["dst"].split(":", 1)[1]: (g.v[e["src"]].get("manufacturer") or "maker not recorded") for e in g.edges("HAS_MANUAL")}


def naming_rows(t, g):
    """[(concept, {maker: Counter(label -> n)}, {maker: most-used label, or None on a tie})] for every concept where makers
    with one clear most-used label disagree (the q8 rule in query_graph.py)."""
    mk = maker_of_manual(g)
    out = []
    for c in t.d["concepts"]:
        if c["grouping"]:
            continue
        per = defaultdict(Counter)
        for label, counts in c["labels"].items():
            for mid, n in counts.items():
                per[mk[mid]][label] += n
        dom = {}
        for m, cnt in per.items():
            tied = sorted(l for l, n in cnt.items() if n == max(cnt.values()))
            dom[m] = tied[0] if len(tied) == 1 else None                   # a tie: no single word for that maker
        if len({w for w in dom.values() if w}) > 1:
            out.append((c, per, dom))
    return out


def naming_heatmap(t, g):
    rows = naming_rows(t, g)
    makers = Counter(m for _, per, _ in rows for m in per)
    cols = sorted(makers, key=lambda m: (-makers[m], m))
    left, top, cw, rh = 250, 118, 40, 17
    body, y = [], top
    for j, m in enumerate(cols):
        x = left + j * cw + cw / 2
        body.append(f'<text x="{x + 4}" y="{top - 8}" class="tm" text-anchor="start" transform="rotate(-50 {x + 4} {top - 8})">{escape(_fit(m, 20))}</text>')
    for ci, (c, per, dom) in enumerate(rows):
        labels = [l for l in c["labels"] if any(per[m][l] for m in per)]
        if ci:
            body.append(f'<path d="M4 {y + 2} H{left + len(cols) * cw}" class="grid"/>')
            y += 5
        for li, lab in enumerate(labels):
            yy = y + li * rh
            if li == 0:
                body.append(_t(8, yy + 12, _fit(c["pref"], 18), "tb"))
            body.append(_t(left - 8, yy + 12, _fit(lab, 16), "t-s", "end"))
            for j, m in enumerate(cols):
                n = per[m][lab] if m in per else 0
                if not n:
                    continue
                share = n / sum(per[m].values())
                x = left + j * cw
                tip = f"{m}: '{lab}' {n} of {sum(per[m].values())} mentions of {c['pref']} ({round(100 * share)}%)" + (" - its most-used word" if dom[m] == lab else " - tied with another word" if dom[m] is None and n == max(per[m].values()) else "")
                cls = "hm dom" if dom[m] == lab else "hm"
                body.append(f'<g><title>{escape(tip)}</title><rect x="{x + 1}" y="{yy + 1}" width="{cw - 2}" height="{rh - 2}" rx="2" class="{cls}" style="fill:{_ramp(share)}"/>'
                            + _t(x + cw / 2, yy + 12, str(n), "cell", "middle") + "</g>")
        y += len(labels) * rh + 4
    h = y + 36
    gid = "nm-ramp"
    legend = (f'<defs><linearGradient id="{gid}" x1="0" x2="1"><stop offset="0" stop-color="{_ramp(0)}"/><stop offset="1" stop-color="{_ramp(1)}"/></linearGradient></defs>'
              f'<rect x="8" y="{h - 24}" width="90" height="10" style="fill:url(#{gid})"/>' + _t(104, h - 15, "share of that maker's mentions of the concept (0 → 100%)", "tm")
              + f'<rect x="470" y="{h - 25}" width="22" height="12" rx="2" class="hm dom" style="fill:{_ramp(1)}"/>' + _t(498, h - 15, "outlined = that maker's most-used word; number = mentions", "tm"))
    desc = (f"{len(rows)} concepts whose manufacturers' manuals most often use different words for them. "
            + " ".join(f"{c['pref']}: " + "; ".join(f"{m} says {dom[m] or 'two words equally'}" for m in sorted(dom)) + "." for c, _, dom in rows))
    return _svg(900, h, "Same concept, different words", desc, "".join(body) + legend), rows


CSS = """
.viz-svg .t-s { fill: var(--md-default-fg-color); font-size: 11.5px; }
.viz-svg .tm-i { fill: var(--md-default-fg-color--light); font-size: 11.5px; font-style: italic; }
.viz-svg .tree { stroke: var(--md-default-fg-color--lighter); stroke-width: 1; fill: none; }
.viz-svg .edge.isa { stroke-width: 1.3; }
.viz-svg .isa-head { fill: var(--md-default-bg-color); stroke: var(--md-default-fg-color--light); stroke-width: 1.2; }
.viz-svg .hm { stroke: none; }
.viz-svg .hm.dom { stroke: var(--md-default-fg-color); stroke-width: 1.6; }
"""
