#!/usr/bin/env python3
"""Build the PUBLIC site into public/ from committed data only (no manuals, no PDFs, no local-only files).

    python tools/build_public.py            # writes public/docs/** and public/mkdocs.yml
    mkdocs build --strict -f public/mkdocs.yml

Inputs (all committed): inventory.yaml, tools/manifest.yaml, eurorack/*, docs/about/*, data/*.json, evals/results.json.
"""
import hashlib
import json
import shutil
from collections import Counter, OrderedDict
from pathlib import Path

import yaml

import build_eurorack
import viz
import viz_graph
from site_theme import EXTRA_CSS, THEME, versioned

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public"
DOCS = OUT / "docs"
REPO = "https://github.com/differentJason/gear-graph"
SITE = "https://differentjason.github.io/gear-graph/"

GROUPS = OrderedDict([
    ("Interfaces, monitors, computers, software", {"audio-interface", "monitors", "headphones", "computer", "software"}),
    ("Controllers", {"controller"}),
    ("Synths, drum machines, MIDI", {"synth", "sampler-drum-machine", "groovebox", "drum-machine", "midi-utility"}),
    ("Guitars, amps, pedals", {"guitar", "bass", "amp", "di-preamp", "pedal-wah", "pedal-modulation", "pedal-distortion", "pedal-eq",
                               "pedal-time", "pedal-utility", "pedal-synth"}),
    ("Eurorack (modules, supplies, case)", {"eurorack-module", "eurorack-power", "eurorack-case"}),
])


def group_of(cat):
    return next((g for g, cats in GROUPS.items() if cat in cats), "Other")


def page(rel, title, body):
    p = DOCS / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: {title}\n---\n\n{body.strip()}\n", encoding="utf-8")


def fig(svg, note=""):
    return f'<div class="viz">{svg}</div>\n' + (f'\n<p class="viz-note">{note}</p>\n' if note else "")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    DOCS.mkdir(parents=True)
    inv = yaml.safe_load((ROOT / "inventory.yaml").read_text())
    items = inv["items"]
    man = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    snap = json.loads((ROOT / "data" / "snapshot.json").read_text())
    cov = {c["id"]: c for c in json.loads((ROOT / "data" / "coverage.json").read_text())}
    res = json.loads((ROOT / "evals" / "results.json").read_text())
    fail = json.loads((ROOT / "data" / "failures.json").read_text())

    shutil.copytree(ROOT / "docs" / "about", DOCS / "about")
    eu = build_eurorack.build(items, DOCS)
    (DOCS / "stylesheets").mkdir()
    (DOCS / "stylesheets" / "viz.css").write_text(viz.CSS + viz_graph.CSS, encoding="utf-8")
    shutil.copy(ROOT / "docs" / "stylesheets" / "tni.css", DOCS / "stylesheets" / "tni.css")

    manual_devices = {m["device"] for m in man}
    n_sections = sum(m["sections"] for m in snap["manuals"])
    n_full = sum(1 for m in snap["manuals"] if m["doc_type"] == "user-manual")
    n_quick = len(snap["manuals"]) - n_full
    eu_ids = {m["id"] for m in eu["matrix"]}

    # ---------- home ----------
    page("index.md", "Gear Knowledge Base", f"""
# Gear Knowledge Base

A personal, machine-readable knowledge base for a home music studio, built as a learning project about **structuring,
verifying and measuring content for retrieval**. This site explains how it works with charts and diagrams, and
publishes the parts that can be public: the gear inventory, sourced Eurorack specifications, and the project's
documentation. Source code: [{REPO.split('github.com/')[1]}]({REPO}).

## Explore

- [How the pipeline works](visuals/pipeline.md): from source documents to a checked, generated site
- [Inventory coverage](visuals/coverage.md): what is documented, and how well
- [How well each spec is supported](visuals/trust.md): every Eurorack number, with the evidence behind it
- [Power budget](visuals/power.md): will the supplies cover the modules?
- [Knowledge graph](visuals/graph.md): what it holds, how the studio is wired, where each module is mounted
- [What the checks caught](visuals/checks.md): 11 real defects and which check found each
- [Retrieval results](visuals/retrieval.md): what indexing choices helped a keyword search
- [Inventory](inventory.md) and [Eurorack modules](eurorack/index.md)
- [About the project](about/index.md): architecture, decisions, runbook, limitations

## At a glance

| Measure | Value |
|---|---|
| Manuals converted | {len(snap['manuals'])} ({n_full} full manuals, {n_quick} quick starts), {n_sections} sections |
| Inventory items | {snap['inventory_items']} ({sum(1 for i in items if i['category'].startswith('eurorack'))} Eurorack) |
| Eurorack spec pages | {eu['count']} |
| Eurorack spec values by support | {', '.join(f'{n} {s}' for s, n in sorted(eu['tally'].items(), key=lambda x: -x[1]))} |
| Retrieval questions | {res['golden_questions']} ({res['answerable_questions']} answerable) |

## About the manuals

The manufacturers' manuals are copyright their owners. They were converted on the author's machine for personal
reference, and **the manual text is deliberately not published here**. What is published is the method, the measured
results, and everything that can be shared.
""")

    # ---------- pipeline ----------
    page("visuals/pipeline.md", "How the pipeline works", f"""
# How the pipeline works

Two pipelines feed one site. Manuals are converted to sectioned markdown with provenance; Eurorack specifications are
fetched into evidence files that keep the exact line each number came from. Human decisions sit on top in a separate
file, so a judgment call is visible instead of buried in code.

{fig(viz.pipeline_diagram(), "Yellow, dashed boxes stay on the author's machine (copyright). Nothing in this pipeline calls a language model.")}

## How to read it

- **Left to right** is the flow of data. **Blue** boxes are code, **green** boxes are committed data, **pink** boxes are generated.
- **The five gates at the bottom** run on every change. They check different things, so no single one is trusted alone.
  The next pages show why: [what the checks caught](checks.md).

More detail: [architecture](../about/architecture.md), [runbook](../about/runbook.md).
""")

    # ---------- coverage ----------
    groups = []
    for g in GROUPS:
        its = [i for i in items if group_of(i["category"]) == g]
        manual = sum(1 for i in its if i["id"] in manual_devices)
        spec = sum(1 for i in its if i["id"] in eu_ids)
        groups.append({"label": g, "manual": manual, "spec": spec, "none": len(its) - manual - spec})
    rows = "\n".join(f"| {g['label']} | {g['manual']} | {g['spec']} | {g['none']} |" for g in groups)
    manual_rows = "\n".join(f"| {m['title']} | {m['doc_type'].replace('-', ' ')} | {m['sections']} | "
                            + (f"{cov[m['id']]['unique_word_recall']:.1%} / {cov[m['id']]['occurrence_recall']:.1%}" if m["id"] in cov else "not measured")
                            + " |" for m in snap["manuals"])
    page("visuals/coverage.md", "Inventory coverage", f"""
# Inventory coverage

Not every piece of gear is documented to the same depth. A first slice (the studio signal chain) got manuals; the
Eurorack modules got sourced specification pages; the rest is not covered yet.

{fig(viz.coverage_chart(groups), "Counts include items marked unused in the inventory; unused modules are not covered.")}

| Kind of gear | Manual ingested | Spec page | Not covered yet |
|---|---|---|---|
{rows}

## The manuals

| Manual | Kind | Sections | Word recall (unique / occurrence) |
|---|---|---|---|
{manual_rows}

*Word recall* is the share of the PDF's words that survived conversion, measured against the PDF's own text. Below
95% is flagged. The quick start with no figure is a multilingual sheet with no clean English-only reference to measure
against, and the check says so instead of reporting a misleading number.

Three of the six are **quick starts, not full manuals**. The site says so wherever they appear.
""")

    # ---------- trust heatmap ----------
    page("visuals/trust.md", "How well each spec is supported", f"""
# How well each spec is supported

Every Eurorack number on this site keeps the source it came from and the exact line of text it was read from. A value
counts as **confirmed** only when two independent sources agree. The chart shows all {len(eu['matrix'])} pages by five fields.

{fig(viz.trust_heatmap(eu['matrix'], eu['fields']), "The number in each cell is the value. Letters carry the meaning so colour is never the only signal.")}

## What it shows

- Most values are **single-source** (S): usually a community database (ModularGrid), not the maker. That is honest about
  how thin the evidence is, and it is the reason the power budget is called a *paper* budget.
- **Confirmed** (C) means two sources agree: a maker's page or datasheet plus ModularGrid (After Later, Antumbra, Jake's), or
  ModularGrid plus a retailer listing (the Behringer modules). Agreement between two non-maker sources is a weaker guarantee
  than agreement with the maker.
- **Inferred** (I) values are zero-draw assumptions for passive modules, each with its reasoning on the module page.
- **Not stated** (-) usually means the source does not list a +5V figure or a depth.

Click into any module from the [Eurorack overview](../eurorack/index.md) to see its evidence table.
""")

    # ---------- power ----------
    page("visuals/power.md", "Power budget", f"""
# Power budget

The question: *will each power supply cover the modules it feeds?* The sums are computed over the
[knowledge graph](graph.md), using where each module is mounted and which supply feeds it.

{fig(viz.power_chart(eu['budget']), "Bars are milliamps. The +5V total is a lower bound because some modules do not state a +5V figure.")}

## How to read it

- **Draw** is the sum of published figures for the modules that supply feeds, not for the whole rack.
- Placement (which case, which supply) is recorded by the owner and validated: modules must fit their case's rows.
- Case figures are labelled **peak** by the maker; continuous capacity may be lower.

## Caveats

- A paper budget from published figures, not a measurement.
- Most figures are single-source (see [how well each spec is supported](trust.md)).
- It assumes every in-use module is running at once.
- The owner sourced the module draw values from the manufacturers and attests them; that is recorded separately and does
  not change how many sources agreed. Zero-draw figures for passive modules are inferred, not sourced.

The full per-module table is on the [power budget page](../eurorack/power-budget.md).
""")

    # ---------- knowledge graph ----------
    gr = viz_graph.Graph(ROOT)
    pub = ROOT / "graph" / "public"
    ans = json.loads((pub / "answers.json").read_text())
    if ans["graph_sha256"] != hashlib.sha256((pub / "vertices.json").read_bytes() + (pub / "edges.json").read_bytes()).hexdigest():
        raise SystemExit("graph/public/answers.json is STALE (the graph snapshot changed). Run: .venv-graph/bin/python tools/query_graph.py")
    ask_rows = "\n".join(f"| {a['question']} | " + "<br>".join(a["answer"]) + f" | {' and '.join(sorted(a['checks'])) or '-'} |" for a in ans["answers"])
    vt, et = gr.counts()
    cell = lambda x: "-" if x in (None, "") else str(x).replace("|", "/")
    short = viz_graph.short
    conn = sorted(gr.edges("CONNECTS", setup="main-studio"), key=lambda e: (e["medium"], gr.v[e["src"]]["name"], gr.v[e["dst"]]["name"]))
    conn_rows = "\n".join(f"| {short(gr.v[e['src']])} | {cell(e.get('from_port'))} | {short(gr.v[e['dst']])} | {cell(e.get('to_port'))} | "
                          f"{viz_graph.MEDIUM[e['medium']]} | {e['status']}{', swappable' if e.get('swappable') else ''} |" for e in conn)
    rack_rows = []
    for case in sorted((v for v in gr.v.values() if v["type"] == "item" and v.get("rows")), key=lambda v: v["name"]):
        mods = viz_graph.rack_modules(gr, case["id"])
        for m in sorted(mods, key=lambda m: (m["position"] or 99, m["short"].lower())):
            sup = "" if m["role"] == "supply" else f"{m['p12']} mA ({m['p12_status']}{', owner-attested' if m['attested'] else ''})" if m["p12"] is not None else "not stated"
            rack_rows.append(f"| {m['short']} | {case['name']} | {m['row'] or m['fmt']} | {m['hp']} | {sup or 'power supply'} |")
    page("visuals/graph.md", "Knowledge graph", f"""
# Knowledge graph

The graph is **derived** from the files in this repository (the inventory, the recorded wiring, the Eurorack evidence,
the test questions) and can be rebuilt at any time; nothing is edited in it. The [power budget](power.md) is computed
over it. Below: what it holds, how the studio is wired, and where each Eurorack module is mounted.

## What is in it

{fig(viz_graph.schema_diagram(gr), "Boxes are kinds of node with their counts; arrows are kinds of relationship. Dashed arrows and the yellow box are local-only: they come from the manufacturers' copyrighted manuals, so they are not in the public graph.")}

| Node type | Count |
|---|---|
""" + "\n".join(f"| {k} | {n} |" for k, n in sorted(vt.items())) + """

| Relationship | Count |
|---|---|
""" + "\n".join(f"| {k} | {n} |" for k, n in sorted(et.items())) + f"""

{fig(viz_graph.category_chart(gr), "Item counts per category, computed from the graph's IN_CATEGORY edges.")}

## How the studio is wired

Only what the owner has stated is recorded. A solid line is confirmed; a dashed line is proposed and waiting for an
answer. Port names are printed inside the boxes, level with their cable. This is the main-studio setup; the alternate
jam-location setup is not recorded yet.

{fig(viz_graph.routing_diagram(gr, {"audio", "usb"}, "Audio and computer", "ra", layering="alap"), "Default inputs on the audio interface: 1 drum machine, 2 open, 3/4 Analog Four, 5/6 Eurorack, 7/8 Digitakt. Other gear is swapped in as needed.")}

{fig(viz_graph.routing_diagram(gr, {"midi", "clock"}, "MIDI and clock", "rb"), "The drum machine is the master clock. Any device on the MIDI Thru box can be swapped; the Behringer K2 and the Donner B1 share one output.")}

| From | Port | To | Port | Medium | Status |
|---|---|---|---|---|---|
{conn_rows}

## How far the clock and MIDI reach

The same wiring, viewed from one device: every box is captioned with its hop distance from the RD-9 over *confirmed*
links only, the same rule the graph's `reach` query uses (see "Questions the graph answers" below). This is q2 as a
picture instead of a table.

{fig(viz_graph.routing_diagram(gr, {"midi", "clock"}, "MIDI and clock, distance from the RD-9", "rc", root="behringer-rd-9"), "The RD-9 is outlined as the root. One hop: MIDI Thru5, Arturia KeyStep, Jake's Clock and Musical Divider, Korg SQ-64. Two hops, through the Thru5: Analog Four, Korg M1, Digitakt, Dreadbox Typhon, Behringer K2, Donner B1.")}

## Where each module is mounted

{fig(viz_graph.rack_diagram(gr), "Block width is proportional to HP; shading is the +12V draw. The custom case's 3U rows are drawn in name order because the row and position of each module are not recorded.")}

| Module | Case | Row | HP | +12V draw |
|---|---|---|---|---|
""" + "\n".join(rack_rows) + """

## Questions the graph answers

Each answer is computed from the graph above and checked: **hand** means the expected answer was worked out by hand from the
recorded wiring; **cross** means separate code that reads the raw files (no graph) reached the same answer. An empty answer
means *not recorded*, which is not the same as *not connected*.

| Question | Answer | Checked by |
|---|---|---|
""" + ask_rows + """

## How to read it, and what it leaves out

- **Eurorack patch cables are not recorded.** They change every session, so the graph holds only what stays put:
  which case, which supply, the clock input and the output stage.
- **Ports are the owner's words.** Where a device's manual is available to the author, each port name is looked up in its text; devices with no ingested manual (the audio interface, the Digitakt, the Eurorack output module) are unchecked.
- **The graph inherits the trust levels of its sources.** A single-source spec stays single-source here; see
  [how well each spec is supported](trust.md).
- **Relationships exist only where they were stated.** A device with no line drawn has no recorded connection; that
  means "not recorded", not "not connected".
""")

    # ---------- checks ----------
    det = fail["detectors"]
    fr = "\n".join(f"| {f['id']} | {f['title']} | {dict(det)[f['caught_by']]} | {f['how']} | {f['fix']} |" for f in fail["failures"])
    page("visuals/checks.md", "What the checks caught", f"""
# What the checks caught

Building this surfaced {len(fail['failures'])} real defects. The interesting part is *which check found each one*.

{fig(viz.failure_matrix(fail['failures'], [tuple(d) for d in det]), "Dots show the check that caught each defect. No single check caught them all.")}

## What it shows

- The **structural checks** (schema validation and the strict build) caught **none** of these, because they test form, not fidelity.
  A clean build does not mean correct content.
- The most valuable check was **measuring completeness** against the source (the coverage check), which exposed
  a factory-reset procedure that a well-meant cleanup step had silently deleted.
- Several defects were found only by **reading the output** against the source. Automated checks narrow the search;
  they do not replace looking.

## The defects

| # | Defect | Caught by | How it showed | Fix |
|---|---|---|---|---|
{fr}

More: [how correctness is checked](../about/verification.md).
""")

    # ---------- retrieval ----------
    changed = [(q, r) for q, r in res["first_hit_rank"].items() if r[0] != r[1]]
    fmt = lambda v: "not in top 5" if v is None else str(v)
    crow = "\n".join(f"| `{q}` | {fmt(r[0])} | {fmt(r[1])} |" for q, r in changed)
    miss = [q for q, r in res["first_hit_rank"].items() if r[1] is None]
    page("visuals/retrieval.md", "Retrieval results", f"""
# Retrieval results

If software searches this knowledge base, does it find the right page, and which structuring choices help? Retrieval is
scored on its own, with no language model, using a keyword search ({res['retriever']}) and {res['golden_questions']} test
questions ({res['answerable_questions']} answerable; the rest test whether a system can say "I don't know").

{fig(viz.retrieval_chart(res['variants'], [('hit1', 'hit@1'), ('hit3', 'hit@3'), ('hit5', 'hit@5'), ('mrr', 'MRR')]), "hit@k: an expected page is in the top k results. MRR: how high the first correct page ranks (1.0 is best).")}

## What changed when device metadata was indexed

Indexing manufacturer, model and device alongside the page text moved these questions (first correct rank):

| Question | Baseline | With metadata |
|---|---|---|
{crow}

## What it does and does not say

- Metadata helped, but with {res['answerable_questions']} answerable questions this is a lead to re-test, not a settled result.
- Indexing the tags too added nothing.
- **Vocabulary mismatch is a content problem.** One question asked for the *back* of a device; the manual only says
  *rear panel*, so a keyword search cannot connect them. Adding plain-language aliases to pages is the obvious next experiment.
- One miss (`a02`) is the test's fault: several pages legitimately answer it, but only one was accepted.
- Keyword search **cannot abstain**: it returns confident-looking results even when the answer is not in the knowledge base.
- No language-model-judged evaluation has been run, so nothing here says anything about answer quality.

More: [evaluation](../about/evaluation.md). Questions that never found a page: {', '.join(f'`{q}`' for q in miss)}.
""")

    # ---------- public inventory ----------
    parts = ["# Inventory", "", "Gear in the studio and how well each item is documented. *Manual text is not published on this site.*", ""]
    for g in GROUPS:
        its = [i for i in items if group_of(i["category"]) == g]
        parts += [f"## {g}", "", "| Item | Status | Documentation | Notes |", "|---|---|---|---|"]
        for i in its:
            if i["id"] in eu_ids:
                link = f"[{i['name']}](eurorack/{i['id']}.md)"
                doc = "spec page"
            else:
                link = i["name"] + (f" {i['version']}" if i.get("version") else "")
                doc = "manual converted (text not published)" if i["id"] in manual_devices else "not started"
            status = i["status"] + (" (unused)" if i.get("in_use") is False else "")
            note = " ".join(x for x in [i.get("role", ""), i.get("note", "")] if x).replace("|", "/")
            parts.append(f"| {link} | {status} | {doc} | {note} |")
        parts.append("")
    if inv.get("removed"):
        parts += ["## Removed", ""] + [f"- {r['name']}: {r['reason']}" for r in inv["removed"]]
    page("inventory.md", "Inventory", "\n".join(parts))

    # ---------- config ----------
    nav = [{"Home": "index.md"},
           {"Visual explanations": [{"How the pipeline works": "visuals/pipeline.md"}, {"Inventory coverage": "visuals/coverage.md"},
                                    {"How well each spec is supported": "visuals/trust.md"}, {"Power budget": "visuals/power.md"}, {"Knowledge graph": "visuals/graph.md"},
                                    {"What the checks caught": "visuals/checks.md"}, {"Retrieval results": "visuals/retrieval.md"}]},
           {"Inventory": "inventory.md"}, {"Eurorack": eu["nav"]},
           {"About the project": [{t: f"about/{f}"} for f, t in [("index.md", "Overview"), ("architecture.md", "Architecture"),
                                                                 ("verification.md", "How correctness is checked"), ("evaluation.md", "Retrieval evaluation"),
                                                                 ("decisions.md", "Decision log"), ("runbook.md", "Runbook"),
                                                                 ("limitations.md", "Limitations and open questions"), ("status.md", "Current status")]]}]
    cfg = {"site_name": "Gear Knowledge Base", "site_description": "A machine-readable studio gear knowledge base, explained with charts",
           "site_url": SITE, "repo_url": REPO, "repo_name": "differentJason/gear-graph", "docs_dir": "docs",
           "theme": THEME,
           "extra_css": versioned(EXTRA_CSS + ["stylesheets/viz.css"], DOCS / "stylesheets"), "plugins": ["search"], "nav": nav}
    (OUT / "mkdocs.yml").write_text("# GENERATED by tools/build_public.py. Do not edit.\n" + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    print(f"public site written to {OUT}: {sum(1 for _ in DOCS.rglob('*.md'))} pages")


if __name__ == "__main__":
    main()
