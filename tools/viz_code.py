"""Inline-SVG diagrams for the Patchbay code <-> docs <-> knowledge graph page (graph/public/code.json).

Same visual language as viz.py (box classes b-tool / b-data / b-out / b-gate, .edge, .arrowhead) so the page reads
as part of the site. Every number drawn is counted from code.json or passed in; nothing is typed in by hand.
"""
from collections import Counter

from viz import _svg, _t

ARROW = ('<defs><marker id="arc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L10 5L0 10z" class="arrowhead"/></marker></defs>')


def _box(x, y, w, h, lines, cls):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}"/>']
    for i, ln in enumerate(lines):
        out.append(_t(x + w / 2, y + 22 + i * 16, ln, "bt" if i == 0 else "bm", "middle"))
    return "".join(out)


def _arrow(x1, y1, x2, y2, label="", lx=None, ly=None):
    out = f'<path d="M{x1} {y1} L{x2} {y2}" class="edge" marker-end="url(#arc)"/>'
    if label:
        lx = (x1 + x2) / 2 if lx is None else lx
        ly = (y1 + y2) / 2 - 5 if ly is None else ly
        out += _t(lx, ly, label, "tiny", "middle")
    return out


CSS = """
.viz-svg .b-act { fill: #c9b6f0; }
"""


def impact(code, route_prefix):
    """Same rule as query_graph.doc_impact, over code.json (for drawing; the graph question is the check)."""
    v = {x["id"]: x for x in code["vertices"]}
    routes = {i for i, x in v.items() if x["type"] == "api_route" and x["name"].split(" ", 1)[1].startswith(route_prefix)}
    es = code["edges"]
    fns = {e["src"] for e in es if e["rel"] == "REQUESTS" and e["dst"] in routes}
    acts = {e["src"] for e in es if e["rel"] == "HANDLED_BY" and e["dst"] in fns}
    secs = {e["src"] for e in es if e["rel"] == "DOCUMENTS" and (e["dst"] in fns or e["dst"] in acts) and v[e["src"]].get("audience") == "user"}
    return sorted(v[x]["name"] for x in secs), sorted(v[x]["name"] for x in fns), sorted(v[x]["name"] for x in acts)


def rel_counts(code):
    """(rel, src type, dst type) -> count, from code.json."""
    t = {v["id"]: v["type"] for v in code["vertices"]}
    return Counter((e["rel"], t.get(e["src"]), t.get(e["dst"])) for e in code["edges"])


def layer_diagram(code, kb):
    """kb: {"item": n, "manual": n, "section": n, "defines_item": n, "describes_item": n}."""
    c, n = rel_counts(code), Counter(v["type"] for v in code["vertices"])
    docs = Counter(v.get("audience") for v in code["vertices"] if v["type"] == "doc_section")
    lang = Counter(v.get("language") for v in code["vertices"] if v["type"] == "function")
    ds = Counter(v.get("system") for v in code["vertices"] if v["type"] == "dataset")
    L = lambda x, y, s_, a="middle": _t(x, y, s_, "tiny", a)
    b = [ARROW]
    b.append(_box(10, 130, 160, 56, ["User guide", f"{docs['user']} sections"], "b-out"))
    b.append(_box(250, 10, 170, 56, ["UI actions", f"{n['ui_action']} buttons"], "b-act"))
    b.append(_box(250, 130, 170, 72, ["Functions", f"{lang['javascript']} JS, {lang['python']} Python",
                                      f"CALLS {c[('CALLS', 'function', 'function')]} among them"], "b-tool"))
    b.append(_box(250, 280, 170, 56, ["API routes", f"{n['api_route']}, two servers"], "b-tool"))
    b.append(_box(500, 10, 170, 56, ["Developer README", f"{docs['developer']} sections"], "b-out"))
    b.append(_box(500, 138, 170, 56, ["Code files", f"{n['code_file']}"], "b-tool"))
    b.append(_box(500, 280, 170, 56, ["Datasets", f"{ds['gear-kb']} KB, {ds['patchbay']} app state"], "b-data"))
    b.append(_t(760, 130, "Knowledge graph", "tb"))
    b.append(_box(760, 142, 150, 48, [f"Items ({kb['item']})"], "b-data"))
    b.append(_box(760, 222, 150, 48, [f"Manuals ({kb['manual']})"], "b-data"))
    b.append(_box(760, 302, 150, 48, [f"Sections ({kb['section']:,})", "private"], "b-local"))
    # documentation
    b.append(_arrow(170, 145, 250, 45) + L(150, 88, f"DOCUMENTS {c[('DOCUMENTS', 'doc_section', 'ui_action')]}"))
    b.append(_arrow(170, 165, 250, 165) + L(210, 158, f"DOCUMENTS {c[('DOCUMENTS', 'doc_section', 'function')]}"))
    b.append(_arrow(585, 66, 585, 138) + L(592, 106, f"DOCUMENTS {c[('DOCUMENTS', 'doc_section', 'code_file')]}", "start"))
    # behaviour
    b.append(_arrow(335, 66, 335, 130) + L(342, 102, f"HANDLED_BY {c[('HANDLED_BY', 'ui_action', 'function')]}", "start"))
    b.append(_arrow(305, 202, 305, 280) + L(298, 246, f"REQUESTS {c[('REQUESTS', 'function', 'api_route')]}", "end"))
    b.append(_arrow(365, 280, 365, 202) + L(372, 246, f"SERVED_BY {c[('SERVED_BY', 'api_route', 'function')]}", "start"))
    b.append(_arrow(500, 166, 420, 166) + L(460, 159, f"DEFINES {c[('DEFINES', 'code_file', 'function')]}"))
    # data lineage and the tie to the knowledge graph
    b.append(_arrow(585, 194, 585, 280) + L(592, 240, f"READS {c[('READS', 'code_file', 'dataset')]}", "start")
             + L(592, 254, f"WRITES {c[('WRITES', 'code_file', 'dataset')]}", "start"))
    b.append(_arrow(670, 296, 760, 170) + L(752, 196, f"DEFINES {kb['defines_item']}, DESCRIBES {kb['describes_item']}", "end"))
    b.append(_arrow(670, 306, 760, 246) + L(752, 262, f"DEFINES {kb['manual']}", "end"))
    b.append(_arrow(670, 318, 760, 326) + L(716, 334, "DEFINES"))
    b.append('<rect x="10" y="366" width="14" height="10" class="b-out"/>' + _t(30, 375, "documentation", "tm")
             + '<rect x="140" y="366" width="14" height="10" class="b-act"/>' + _t(160, 375, "what a user clicks", "tm")
             + '<rect x="300" y="366" width="14" height="10" class="b-tool"/>' + _t(320, 375, "code", "tm")
             + '<rect x="380" y="366" width="14" height="10" class="b-data"/>' + _t(400, 375, "data and knowledge", "tm")
             + '<rect x="540" y="366" width="14" height="10" class="b-local"/>' + _t(560, 375, "private (not in the public graph)", "tm"))
    return _svg(920, 386, "The Patchbay's code, docs and data as one graph",
                "User-guide sections document UI actions and functions; actions are handled by functions; functions request "
                "API routes that server functions serve; code files read and write datasets; knowledge-base datasets "
                "define and describe the items, manuals and manual sections of the knowledge graph.", "".join(b))


def impact_diagram(code, route_prefix, sections, fns, acts):
    """The q11 path: user-guide sections <- buttons <- functions -> routes -> the functions that serve them."""
    name = {v["id"]: v["name"] for v in code["vertices"]}
    routes = sorted(v["id"] for v in code["vertices"] if v["type"] == "api_route"
                    and v["name"].split(" ", 1)[1].startswith(route_prefix))
    served = sorted({(e["src"], e["dst"], e.get("mode", "")) for e in code["edges"] if e["rel"] == "SERVED_BY" and e["src"] in routes})
    servers = sorted({s[1] for s in served})
    cols = [("Review these guide sections", sections, "b-out"), ("Buttons", acts, "b-act"), ("Functions that call it", fns, "b-tool"),
            ("API routes", [name[r] for r in routes], "b-tool"), ("Served by", [name[s].replace("Handler.", "") + (" (website)" if "app.js" in s else " (local)") for s in servers], "b-data")]
    xs, w, h, gap = [10, 200, 350, 510, 700], [175, 130, 140, 170, 170], 30, 12
    pos, b = {}, [ARROW]
    tallest = max(len(c[1]) for c in cols)
    for (title, items, cls), x, bw in zip(cols, xs, w):
        b.append(_t(x, 18, title, "tb"))
        top = 34 + (tallest - len(items)) * (h + gap) / 2
        for i, it in enumerate(items):
            y = top + i * (h + gap)
            b.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{h}" rx="6" class="{cls}"/>' + _t(x + bw / 2, y + 20, it, "bm", "middle"))
            pos[(title, it)] = (x, y, bw)
    def link(a, b_, rev=False):
        (x1, y1, w1), (x2, y2, _) = pos[a], pos[b_]
        return (f'<path d="M{x2} {y2 + h / 2} L{x1 + w1} {y1 + h / 2}" class="edge" marker-end="url(#arc)"/>' if rev
                else f'<path d="M{x1 + w1} {y1 + h / 2} L{x2} {y2 + h / 2}" class="edge" marker-end="url(#arc)"/>')
    es = code["edges"]
    fid = {name[v]: v for v in name}
    cov = {(e["src"], e["dst"]) for e in es if e["rel"] == "DOCUMENTS"}
    for s in sections:
        sid = next(v["id"] for v in code["vertices"] if v["type"] == "doc_section" and v["name"] == s and v.get("audience") == "user")
        for a in acts:
            if (sid, f"action:{a}") in cov:
                b.append(link(("Review these guide sections", s), ("Buttons", a)))
        for f in fns:
            if any(e["src"] == sid and e["dst"].endswith(f":{f}") and e["rel"] == "DOCUMENTS" for e in es):
                b.append(f'<path d="M{pos[("Review these guide sections", s)][0] + 175} {pos[("Review these guide sections", s)][1] + h / 2} '
                         f'C 330 {pos[("Review these guide sections", s)][1] + h / 2} 330 {pos[("Functions that call it", f)][1] + h / 2} '
                         f'{pos[("Functions that call it", f)][0]} {pos[("Functions that call it", f)][1] + h / 2}" class="edge" marker-end="url(#arc)"/>')
    for e in es:
        if e["rel"] == "HANDLED_BY" and e["src"].startswith("action:") and e["src"][7:] in acts and name.get(e["dst"]) in fns:
            b.append(link(("Buttons", e["src"][7:]), ("Functions that call it", name[e["dst"]])))
        if e["rel"] == "REQUESTS" and name.get(e["src"]) in fns and e["dst"] in routes:
            b.append(link(("Functions that call it", name[e["src"]]), ("API routes", name[e["dst"]])))
    for r, s, mode in served:
        lab = name[s].replace("Handler.", "") + (" (website)" if "app.js" in s else " (local)")
        b.append(link(("API routes", name[r]), ("Served by", lab)))
    H = 34 + tallest * (h + gap) + 10
    return _svg(880, H, f"What a change to {route_prefix} touches",
                "Read right to left from the API: the functions that call it, the buttons they handle, and the user-guide "
                "sections that document either; and left to right to the two implementations that serve it.", "".join(b))


def platform_diagram():
    """Generic picture: several apps, each with its own code<->docs graph, joined through shared data and APIs."""
    b = [ARROW]
    apps = [("Patchbay", "this repository"), ("Another app", "same schema"), ("A service", "same schema")]
    for i, (a, sub) in enumerate(apps):
        x = 10 + i * 200
        b.append(f'<rect x="{x}" y="10" width="180" height="120" rx="10" class="b-gate"/>')
        b.append(_t(x + 90, 30, a, "tb", "middle") + _t(x + 90, 46, sub, "tm", "middle"))
        b.append(_box(x + 10, 56, 75, 60, ["Docs", ""], "b-out") + _box(x + 95, 56, 75, 60, ["Code", ""], "b-tool"))
        b.append(_arrow(x + 85, 86, x + 95, 86))
        b.append(_arrow(x + 90, 130, 300, 178))
    b.append(_box(170, 180, 260, 50, ["Shared datasets and API contracts", ""], "b-data"))
    b.append(_arrow(300, 230, 300, 258))
    b.append(_box(120, 260, 360, 56, ["One knowledge graph", "domain entities + docs + code + owners"], "b-data"))
    b.append(_t(620, 60, "Each app publishes its own", "tm") + _t(620, 76, "code<->docs graph in the same", "tm")
             + _t(620, 92, "schema at build time.", "tm") + _t(620, 190, "They join on shared ids:", "tm")
             + _t(620, 206, "datasets, API routes, entities.", "tm") + _t(620, 280, "Questions then cross app", "tm")
             + _t(620, 296, "boundaries.", "tm"))
    return _svg(880, 326, "One app among many on a platform",
                "Several apps each publish a docs-to-code graph in the same schema; they join through shared datasets "
                "and API contracts into one knowledge graph of domain entities, documentation, code and owners.", "".join(b))


def patchbay_subgraph(code):
    """The Patchbay's slice of code.json (the other apps share the file): its files, functions, docs, buttons, routes,
    plus the datasets and systems they touch."""
    keep = {v["id"] for v in code["vertices"] if "patchbay/" in v["id"] or v["type"] in ("ui_action", "api_route")
            or v["id"] == "app:patchbay"}
    keep |= {e["dst"] for e in code["edges"] if e["src"] in keep and e["rel"] in ("READS", "WRITES", "USES")}
    keep |= {e["dst"] for e in code["edges"] if e["src"] in keep and e["rel"] == "PART_OF"}
    vs = [v for v in code["vertices"] if v["id"] in keep]
    es = [e for e in code["edges"] if e["src"] in keep and e["dst"] in keep]
    counts = {"vertices": dict(Counter(v["type"] for v in vs)), "edges": dict(Counter(e["rel"] for e in es))}
    return {**code, "vertices": vs, "edges": es, "counts": counts}


def context_diagram(c):
    """Many sources -> one shared vocabulary -> many uses. c: counts computed by the caller."""
    b = [ARROW]
    src = [(f"{c['manuals']} manuals", f"{c['makers']} manufacturers, {c['formats']} formats"),
           (f"{c['app_docs']} app doc sections", f"{c['apps']} apps, incl. the docs site"),
           (f"{c['code_files']} code files", "docstrings and comments"),
           (f"{c['buttons']} UI labels", "what users click")]
    for i, (a, s_) in enumerate(src):
        y = 20 + i * 74
        b.append(_box(10, y, 220, 56, [a, s_], "b-local" if i == 0 else "b-out" if i == 1 else "b-tool" if i == 2 else "b-act"))
        b.append(_arrow(230, y + 28, 330, 150 + (i - 1.5) * 18))
    b.append(_box(330, 110, 220, 90, ["Shared vocabulary", f"{c['concepts']} concepts, {c['labels']} labels",
                                      f"{c['shared']} used by manuals and apps"], "b-data"))
    b.append(_t(440, 222, f"USES_TERM {c['uses_term']:,} edges", "tiny", "middle"))
    uses = ["Search and navigation", "Grounded answers (cite the sources)", "Change impact across apps", "Content gaps both ways"]
    for i, u in enumerate(uses):
        y = 30 + i * 66
        b.append(_arrow(550, 155, 640, y + 22))
        b.append(f'<rect x="640" y="{y}" width="230" height="44" rx="8" class="b-data"/>' + _t(755, y + 27, u, "bt", "middle"))
    b.append(_t(10, 318, "Sources keep their own words; the vocabulary maps every word to one concept, so every use sees one graph.", "tm"))
    return _svg(880, 330, "Many sources, one context graph",
                "Manuals from many manufacturers, app documentation, code comments and UI labels are all read with one "
                "label matcher into a shared vocabulary of concepts, which serves search, grounded answers, change impact "
                "and gap analysis.", "".join(b))
