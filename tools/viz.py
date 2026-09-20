#!/usr/bin/env python3
"""Dependency-free SVG chart generators for the public site.

Every function returns an SVG string. Colours come from CSS classes (docs/stylesheets/viz.css) so the charts follow
the site's light/dark theme; status is also encoded with a letter or label, never colour alone.
"""
from html import escape

STATUS_LETTER = {"confirmed": "C", "single": "S", "inferred": "I", "override": "O", "missing": "-", "conflict": "!"}
STATUS_LABEL = {"confirmed": "Confirmed (2+ sources agree)", "single": "Single source", "inferred": "Inferred (labelled)",
                "override": "Override (reasoning recorded)", "missing": "Not stated", "conflict": "Sources disagree"}


def _svg(w, h, title, desc, body):
    return (f'<svg class="viz-svg" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>{body}</svg>')


def _t(x, y, s, cls="t", anchor="start", extra=""):
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}" {extra}>{escape(str(s))}</text>'


def power_chart(budget, supply_names):
    """budget: {rail: {draw_ma, capacity_ma, modules_without_figure, per_supply: {name: cap}}}"""
    left, right, top = 190, 130, 20
    plot_w, group_h = 720 - left - right, 128
    rows = ["Total draw"] + [f"{n} alone" for n in supply_names] + ["All supplies combined"]
    body, y = [], top
    for rail, v in budget.items():
        caps = [v["per_supply"][n] or 0 for n in supply_names]
        vals = [v["draw_ma"]] + caps + [v["capacity_ma"]]
        scale = plot_w / (max(vals) * 1.05)
        lower = " (lower bound)" if v["modules_without_figure"] else ""
        body.append(_t(8, y + 14, f"{rail} rail", "tb"))
        yy = y + 26
        for i, (label, val) in enumerate(zip(rows, vals)):
            bar_w = max(val * scale, 0.5)
            if i == 0:
                cls, txt = "bar-draw", f"{val} mA{lower}"
            else:
                pct = f"{100 * v['draw_ma'] / val:.0f}%" if val else "-"
                cls = "bar-over" if val and v["draw_ma"] > val else "bar-ok"
                txt = f"{val} mA  (draw = {pct})"
            body.append(_t(left - 8, yy + 13, label, "tm", "end"))
            body.append(f'<rect x="{left}" y="{yy}" width="{bar_w:.1f}" height="18" class="{cls}"/>')
            body.append(_t(left + bar_w + 6, yy + 13, txt, "t"))
            yy += 22
        y += group_h
    h = y + 36
    legend = (f'<rect x="8" y="{h - 26}" width="14" height="10" class="bar-draw"/>' + _t(28, h - 17, "draw (sum of published figures)", "tm")
              + f'<rect x="250" y="{h - 26}" width="14" height="10" class="bar-ok"/>' + _t(270, h - 17, "capacity covers the draw", "tm")
              + f'<rect x="450" y="{h - 26}" width="14" height="10" class="bar-over"/>' + _t(470, h - 17, "draw exceeds capacity", "tm"))
    desc = "; ".join(f"{r}: draw {v['draw_ma']} mA against capacities " + ", ".join(f"{n} {v['per_supply'][n]} mA" for n in supply_names) + f", combined {v['capacity_ma']} mA" for r, v in budget.items())
    return _svg(720, h, "Power draw against supply capacity, per rail", desc, "".join(body) + legend)


def trust_heatmap(matrix, fields):
    """matrix: [{name, statuses: {field: status}, values: {field: value}}]; fields: [(key, label)]"""
    label_w, cell_w, cell_h, top = 330, 96, 22, 70
    w, h = label_w + cell_w * len(fields) + 20, top + cell_h * len(matrix) + 96
    body = [_t(8, 22, "Each cell is one spec value. The letter shows how well it is supported.", "tm")]
    for j, (_, label) in enumerate(fields):
        body.append(_t(label_w + j * cell_w + cell_w / 2, top - 10, label, "tb", "middle"))
    for i, row in enumerate(matrix):
        y = top + i * cell_h
        body.append(_t(label_w - 8, y + 15, row["name"], "t", "end"))
        for j, (key, _) in enumerate(fields):
            st = row["statuses"][key]
            val = row["values"].get(key)
            x = label_w + j * cell_w
            body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell_w - 2}" height="{cell_h - 2}" class="st-{st}"><title>{escape(row["name"])}: {escape(str(val if val is not None else "not stated"))} ({escape(STATUS_LABEL[st])})</title></rect>')
            body.append(_t(x + cell_w / 2, y + 15, f"{STATUS_LETTER[st]}  {'' if val is None else val}", "cell", "middle"))
    ly = top + cell_h * len(matrix) + 22
    for k, st in enumerate(["confirmed", "single", "inferred", "override", "missing", "conflict"]):
        x, y = 8 + (k % 3) * 300, ly + (k // 3) * 22
        body.append(f'<rect x="{x}" y="{y}" width="34" height="16" class="st-{st}"/>' + _t(x + 17, y + 12, STATUS_LETTER[st], "cell", "middle") + _t(x + 42, y + 12, STATUS_LABEL[st], "tm"))
    counts = {}
    for r in matrix:
        for s in r["statuses"].values():
            counts[s] = counts.get(s, 0) + 1
    desc = f"{len(matrix)} modules by {len(fields)} spec fields. " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items(), key=lambda x: -x[1]))
    return _svg(w, h, "How well each Eurorack spec value is supported", desc, "".join(body))


def pipeline_diagram():
    boxes = {  # id: (x, y, w, h, label lines, class)
        "pdf": (10, 20, 150, 56, ["Manufacturer PDFs", "(local only)"], "b-local"),
        "conv": (200, 20, 150, 56, ["convert_manual.py", "split + tag + provenance"], "b-tool"),
        "sec": (390, 20, 170, 56, ["Sectioned markdown", "(local only)"], "b-local"),
        "src": (10, 116, 150, 56, ["Source pages and", "datasheets (listed)"], "b-data"),
        "fetch": (200, 116, 150, 56, ["fetch_specs.py", "numbers + raw lines"], "b-tool"),
        "evid": (390, 116, 170, 56, ["Evidence (JSON)", "value + exact line"], "b-data"),
        "over": (390, 196, 170, 56, ["overrides.yaml", "decisions + reasoning"], "b-data"),
        "inv": (390, 276, 170, 56, ["inventory.yaml", "gear, status, format"], "b-data"),
        "build": (640, 130, 150, 70, ["build_site.py", "build_eurorack.py", "generate everything"], "b-tool"),
        "pages": (640, 226, 150, 56, ["Generated pages", "budget, status, specs"], "b-out"),
        "site": (640, 312, 150, 44, ["Static site"], "b-out"),
    }
    straight = [("pdf", "conv"), ("conv", "sec"), ("src", "fetch"), ("fetch", "evid"), ("build", "pages"), ("pages", "site")]
    bus_sources, bus_x = ["sec", "evid", "over", "inv"], 600
    body = ['<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" class="arrowhead"/></marker></defs>']

    def cy(k):
        return boxes[k][1] + boxes[k][3] / 2
    for a_, b_ in straight:
        ax, ay, aw, ah = boxes[a_][:4]
        bx, by, bw, bh = boxes[b_][:4]
        if bx > ax + aw - 5:
            body.append(f'<path d="M{ax + aw} {cy(a_)} L{bx} {cy(b_)}" class="edge" marker-end="url(#ar)"/>')
        else:
            body.append(f'<path d="M{ax + aw / 2} {ay + ah} L{bx + bw / 2} {by}" class="edge" marker-end="url(#ar)"/>')
    for k in bus_sources:                                   # stubs from each input to a shared vertical bus
        body.append(f'<path d="M{boxes[k][0] + boxes[k][2]} {cy(k)} L{bus_x} {cy(k)}" class="edge"/>')
    body.append(f'<path d="M{bus_x} {cy("sec")} L{bus_x} {cy("inv")}" class="edge"/>')
    body.append(f'<path d="M{bus_x} {cy("build")} L{boxes["build"][0]} {cy("build")}" class="edge" marker-end="url(#ar)"/>')
    for k, (x, y, w, h, lines, cls) in boxes.items():
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}"/>')
        for i, ln in enumerate(lines):
            body.append(_t(x + w / 2, y + 22 + i * 15 if len(lines) > 2 else y + 24 + i * 16, ln, "bt" if i == 0 else "bm", "middle"))
    gates = [("validate.py", "structure, tags, links"), ("check_coverage.py", "did conversion lose text?"), ("regression diff", "did a change alter results?"),
             ("mkdocs --strict", "broken links fail build"), ("golden questions", "does retrieval find it?")]
    body.append(_t(10, 384, "Quality gates (run on every change)", "tb"))
    for i, (g, d) in enumerate(gates):
        x = 10 + i * 156
        body.append(f'<rect x="{x}" y="396" width="148" height="52" rx="6" class="b-gate"/>' + _t(x + 74, 417, g, "tb", "middle") + _t(x + 74, 435, d, "tiny", "middle"))
    body.append('<rect x="10" y="466" width="14" height="10" class="b-local"/>' + _t(30, 475, "local only, never published (copyright)", "tm")
                + '<rect x="290" y="466" width="14" height="10" class="b-tool"/>' + _t(310, 475, "code", "tm")
                + '<rect x="370" y="466" width="14" height="10" class="b-data"/>' + _t(390, 475, "committed data", "tm")
                + '<rect x="520" y="466" width="14" height="10" class="b-out"/>' + _t(540, 475, "generated output", "tm"))
    return _svg(800, 488, "Build pipeline", "Manual PDFs are converted to sectioned markdown (local only). Eurorack source pages are fetched into evidence, combined with human overrides and the inventory, and built into generated pages and a static site. Five quality gates run on every change.", "".join(body))


def failure_matrix(failures, detectors):
    """failures: [{id, title, caught_by}], detectors: [(key, label)]"""
    label_w, col_w, row_h, top = 360, 92, 26, 92
    w, h = label_w + col_w * len(detectors) + 10, top + row_h * len(failures) + 40
    body = []
    for j, (_, lab) in enumerate(detectors):
        words = lab.split(" ")
        mid = len(words) // 2 or 1
        for k, ln in enumerate([" ".join(words[:mid]), " ".join(words[mid:])]):
            body.append(_t(label_w + j * col_w + col_w / 2, top - 30 + k * 14, ln, "tb", "middle"))
    for i, f in enumerate(failures):
        y = top + i * row_h
        if i % 2 == 0:
            body.append(f'<rect x="0" y="{y}" width="{w}" height="{row_h}" class="zebra"/>')
        body.append(_t(8, y + 17, f"{f['id']}. {f['title']}", "t"))
        for j, (key, lab) in enumerate(detectors):
            if f["caught_by"] == key:
                cx = label_w + j * col_w + col_w / 2
                body.append(f'<circle cx="{cx}" cy="{y + row_h / 2}" r="8" class="dot"><title>{escape(f["title"])}: caught by {escape(lab)}</title></circle>')
    body.append(_t(8, h - 12, "Structural validator and strict build: 0 of the failures listed here (they check form, not fidelity).", "tm"))
    counts = {k: sum(1 for f in failures if f["caught_by"] == k) for k, _ in detectors}
    desc = "; ".join(f"{lab}: {counts[k]}" for k, lab in detectors if counts[k])
    return _svg(w, h, "Which check caught each defect", f"{len(failures)} defects found while building; caught by: {desc}. The structural validator and strict build caught none of them.", "".join(body))


def retrieval_chart(variants, metrics):
    """variants: [{label, hit1, hit3, hit5, mrr}]"""
    left, top, plot_w, plot_h = 60, 30, 600, 220
    n = len(variants)
    gw = plot_w / len(metrics)
    bw = min(34, (gw - 24) / n)
    body = []
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        y = top + plot_h - t * plot_h
        body.append(f'<line x1="{left}" y1="{y}" x2="{left + plot_w}" y2="{y}" class="grid"/>' + _t(left - 8, y + 4, f"{t:.2f}", "tm", "end"))
    for mi, (key, lab) in enumerate(metrics):
        gx = left + mi * gw + (gw - bw * n) / 2
        for vi, v in enumerate(variants):
            val = v[key]
            bh = val * plot_h
            x = gx + vi * bw
            body.append(f'<rect x="{x:.1f}" y="{top + plot_h - bh:.1f}" width="{bw - 3:.1f}" height="{bh:.1f}" class="v{vi}"><title>{escape(v["label"])}: {lab} = {val:.3f}</title></rect>')
            body.append(_t(x + (bw - 3) / 2, top + plot_h - bh - 5, f"{val:.2f}" if key != "mrr" else f"{val:.3f}", "tiny", "middle"))
        body.append(_t(left + mi * gw + gw / 2, top + plot_h + 20, lab, "tb", "middle"))
    for vi, v in enumerate(variants):
        x = left + vi * 210
        body.append(f'<rect x="{x}" y="{top + plot_h + 40}" width="14" height="10" class="v{vi}"/>' + _t(x + 20, top + plot_h + 49, v["label"], "tm"))
    desc = "; ".join(f"{v['label']}: hit@1 {v['hit1']}, hit@3 {v['hit3']}, hit@5 {v['hit5']}, MRR {v['mrr']}" for v in variants)
    return _svg(700, top + plot_h + 64, "Retrieval quality by indexing variant", desc, "".join(body))


def coverage_chart(groups):
    """groups: [{label, manual, spec, none}]"""
    left, row_h, top, plot_w = 300, 34, 30, 320
    mx = max(g["manual"] + g["spec"] + g["none"] for g in groups)
    scale = plot_w / mx
    body = []
    for i, g in enumerate(groups):
        y = top + i * row_h
        body.append(_t(left - 10, y + 17, g["label"], "t", "end"))
        x = left
        for key, cls in (("manual", "cv-manual"), ("spec", "cv-spec"), ("none", "cv-none")):
            wv = g[key] * scale
            if g[key]:
                body.append(f'<rect x="{x:.1f}" y="{y}" width="{wv:.1f}" height="22" class="{cls}"><title>{escape(g["label"])}: {g[key]} {key}</title></rect>')
                if wv > 16:
                    body.append(_t(x + wv / 2, y + 16, g[key], "cell", "middle"))
            x += wv
        body.append(_t(x + 8, y + 16, f'{g["manual"] + g["spec"] + g["none"]} items', "tm"))
    ly = top + len(groups) * row_h + 14
    for k, (cls, lab) in enumerate([("cv-manual", "Manual ingested"), ("cv-spec", "Sourced spec page"), ("cv-none", "Not covered yet")]):
        body.append(f'<rect x="{8 + k * 190}" y="{ly}" width="14" height="10" class="{cls}"/>' + _t(8 + k * 190 + 20, ly + 9, lab, "tm"))
    desc = "; ".join(f"{g['label']}: {g['manual']} manual, {g['spec']} spec page, {g['none']} not covered" for g in groups)
    return _svg(700, ly + 30, "Inventory coverage by kind of gear", desc, "".join(body))


CSS = """
.viz { margin: 1.2rem 0; overflow-x: auto; }
.viz-svg { width: 100%; height: auto; max-width: 900px; font-family: inherit; }
.viz-svg .t  { fill: var(--md-default-fg-color); font-size: 12.5px; }
.viz-svg .tb { fill: var(--md-default-fg-color); font-size: 12.5px; font-weight: 700; }
.viz-svg .tm { fill: var(--md-default-fg-color--light); font-size: 11.5px; }
.viz-svg .tiny { fill: var(--md-default-fg-color--light); font-size: 10.5px; }
.viz-svg .cell { fill: #111; font-size: 11px; font-weight: 700; }
.viz-svg .bt { fill: #111; font-size: 12.5px; font-weight: 700; }
.viz-svg .bm { fill: #222; font-size: 11.5px; }
.viz-svg .grid { stroke: var(--md-default-fg-color--lightest); stroke-width: 1; }
.viz-svg .zebra { fill: var(--md-default-fg-color--lightest); opacity: .35; }
.viz-svg .edge { stroke: var(--md-default-fg-color--light); stroke-width: 1.6; fill: none; }
.viz-svg .arrowhead { fill: var(--md-default-fg-color--light); }
.viz-svg .dot { fill: #0072B2; }
.viz-svg .bar-draw { fill: #56606b; }
.viz-svg .bar-ok { fill: #009E73; }
.viz-svg .bar-over { fill: #D55E00; }
.viz-svg .st-confirmed { fill: #66d1b0; }
.viz-svg .st-single { fill: #9ad3f3; }
.viz-svg .st-inferred { fill: #e7b6d2; }
.viz-svg .st-override { fill: #f3c76b; }
.viz-svg .st-missing { fill: #cfcfcf; }
.viz-svg .st-conflict { fill: #f0906b; }
.viz-svg .v0 { fill: #7a8794; }
.viz-svg .v1 { fill: #0072B2; }
.viz-svg .v2 { fill: #56B4E9; }
.viz-svg .cv-manual { fill: #66d1b0; }
.viz-svg .cv-spec { fill: #9ad3f3; }
.viz-svg .cv-none { fill: #cfcfcf; }
.viz-svg rect[class^="b-"] { stroke: var(--md-default-fg-color--light); stroke-width: 1.2; }
.viz-svg .b-local { fill: #f3c76b; stroke-dasharray: 5 3; }
.viz-svg .b-tool { fill: #9ad3f3; }
.viz-svg .b-data { fill: #66d1b0; }
.viz-svg .b-out { fill: #e7b6d2; }
.viz-svg .b-gate { fill: transparent; stroke-dasharray: 3 3; }
.viz-note { font-size: .9em; color: var(--md-default-fg-color--light); }
"""
