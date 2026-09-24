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
from midi_reference import markdown as midi_reference
import viz
import viz_graph
import viz_terms
import viz_code
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


def code_graph_page(inv):
    """The Patchbay's code <-> docs graph, tied to the knowledge graph, and the platform-scale reading of it."""
    pub = ROOT / "graph" / "public"
    code = viz_code.patchbay_subgraph(json.loads((pub / "code.json").read_text()))   # this page is about the Patchbay
    edges = json.loads((pub / "edges.json").read_text())
    ans = {a["id"]: a for a in json.loads((pub / "answers.json").read_text())["answers"]}
    snap = json.loads((ROOT / "data" / "snapshot.json").read_text())
    v = {x["id"]: x for x in code["vertices"]}
    ds_edges = [e for e in edges if e["src"].startswith("data:") and e["rel"] in ("DEFINES", "DESCRIBES")]
    kb = {"item": len(inv["items"]), "manual": len(snap["manuals"]), "section": sum(m["sections"] for m in snap["manuals"]),
          "defines_item": sum(1 for e in ds_edges if e["rel"] == "DEFINES" and e["dst"].startswith("item:")),
          "describes_item": sum(1 for e in ds_edges if e["rel"] == "DESCRIBES")}
    how = {"CONTAINS": "parsed (files in patchbay/)", "DEFINES": "parsed (Python ast; JavaScript top-level functions)",
           "CALLS": "parsed (a call to a known function in the body)", "HANDLED_BY": "parsed (the onAction switch)",
           "REQUESTS": "parsed (api() calls)", "SERVED_BY": "parsed (server routes; the website's stand-in)",
           "READS": "parsed (file names in the code)", "WRITES": "declared, then verified in the code",
           "DOCUMENTS": "declared in the guide (covers notes); README paths parsed", "PART_OF": "declared",
           "USES": "declared"}
    rels = code["counts"]["edges"]
    rel_rows = "\n".join(f"| {r} | {n} | {how.get(r, '')} |" for r, n in sorted(rels.items(), key=lambda kv: -kv[1]))
    acts = {x["name"]: x.get("label", "") for x in code["vertices"] if x["type"] == "ui_action"}
    cov_rows = []
    for sec in [x for x in code["vertices"] if x["type"] == "doc_section" and x.get("audience") == "user"]:
        outs = [e["dst"] for e in code["edges"] if e["src"] == sec["id"] and e["rel"] == "DOCUMENTS"]
        buttons = [v[o]["name"] for o in outs if v[o]["type"] == "ui_action"]
        fns = [v[o]["name"] for o in outs if v[o]["type"] == "function"]
        cov_rows.append(f"| {sec['name']} | {', '.join(buttons) or '—'} | {', '.join(f'`{f}`' for f in fns) or '—'} |")
    reads = {}
    for e in code["edges"]:
        if e["rel"] in ("READS", "WRITES") and v[e["dst"]]["type"] == "dataset":
            reads.setdefault(e["dst"], {"READS": [], "WRITES": []})[e["rel"]].append(v[e["src"]]["name"].split("/")[-1])
    ds_rows = []
    for d, rw in sorted(reads.items(), key=lambda kv: (v[kv[0]].get("system") != "gear-kb", kv[0])):
        n_kb = sum(1 for e in ds_edges if e["src"] == d)
        if d == "data:docs/manuals":
            n_kb = f"{kb['section']:,} manual sections (private, so not in the public graph)"
        ds_rows.append(f"| `{v[d]['name']}` | {v[d].get('system')} | {', '.join(sorted(rw['READS'])) or '—'} | "
                       f"{', '.join(sorted(rw['WRITES'])) or '—'} | {n_kb or '—'} |")
    secs, fns, acts_hit = viz_code.impact(code, "/api/sessions")
    qa = "\n".join(f"- **{ans[q]['question']}** " + "; ".join(ans[q]["answer"]) + ".  " +
                   " ".join(f"`{k}: {s_}`" for k, s_ in ans[q]["checks"].items()) for q in ("q10", "q11", "q12") if q in ans)
    n = code["counts"]["vertices"]
    return f"""# Patchbay: code, docs and the knowledge graph

The [Patchbay](patchbay-app.md) is small enough to read in an afternoon, which makes it a good place to show an idea
that matters much more at scale: **documentation, code and data can be one graph**, built from the source on every
change, so that questions like *"which pages go stale if this API changes?"* are answered by a query instead of by
memory.

`tools/build_code_graph.py` reads the app (its Python with the `ast` module, its JavaScript, its HTML buttons, its
[user guide](patchbay-guide.md) and README) and writes `graph/public/code.json`: **{sum(n.values())} vertices** and
**{sum(rels.values())} typed edges**. `tools/build_graph.py` merges that into the main knowledge graph, and the graph's
question runner checks three questions about it against answers worked out without the graph.

## One graph, from a guide page down to the gear

{fig(viz_code.layer_diagram(code, kb), "Counts are computed from graph/public/code.json and the knowledge graph on every build. Manual sections stay private (copyright), so their edges never reach the public snapshot.")}

| Relationship | Edges | How it is derived |
|---|---|---|
{rel_rows}

Most edges are **parsed** from the code. The links from the user guide to the code are **declared**: each guide section
ends with a hidden note such as `covers: save saveas fn:openDialog`. Declared links are then **checked**, so they cannot
quietly rot. The build fails if a button has no guide section, if a note names a button or function that no longer
exists, or if a section covers a button but never shows its on-screen label. It also fails if the README names a code
file that is gone, if the client calls an API route that no server serves, or if a module claims to write a file it
never writes. The first run of these checks caught two real drift bugs: the guide said "jack labels" where the button
says "jack names", and the README pointed at a path that only exists one folder up.

## Which guide section covers which button

| Guide section | Buttons it documents | Functions it documents |
|---|---|---|
{chr(10).join(cov_rows)}

## Worked example: what a change to the session API touches

Only three functions call `/api/sessions`: {", ".join(f"`{f}`" for f in fns)}. The buttons they handle are
{", ".join(f"**{a}**" for a in acts_hit)}. The guide sections that document either are
{" and ".join(f"*{s_}*" for s_ in secs)}. The same routes are served twice: by the local server (`do_GET`,
`do_PUT`, `do_DELETE`) and by the website's stand-in (`staticApi`), so a change has two implementations to keep in step.

{fig(viz_code.impact_diagram(code, "/api/sessions", secs, fns, acts_hit), "Drawn from code.json with the same rule the graph question uses: direct links only, so the dispatcher that reaches every function does not flag every page.")}

## Tied to the knowledge graph

The app's datasets are the join. A knowledge-base file **defines** the vertices it is the source of record for
(`inventory.yaml` → every item) and **describes** the ones it adds facts to (`connections.yaml` → the items it
wires or mounts). The Patchbay's own files (sessions, jack edits) belong to the app, not the knowledge base.

| Dataset | Belongs to | Read by | Written by | Knowledge-graph vertices it defines or describes (public) |
|---|---|---|---|---|
{chr(10).join(ds_rows)}

Checked against the graph (each answer is also worked out without the graph):

{qa}

## Scaled out: the Patchbay as one app on a larger platform

Picture the Patchbay as one of many applications and services on a shared platform, each with its own user docs and
its own code, all built on shared data and shared APIs. The same relationships carry over unchanged, and they get
more useful as the platform grows.

{fig(viz_code.platform_diagram(), "Each app publishes the same small schema at build time. The graph is the union, joined on ids that several apps share.")}

**The schema is small and stays the same.** Four families of relationship cover it: **documentation**
(`DOCUMENTS`), **behaviour** (`HANDLED_BY`, `CALLS`, `REQUESTS`, `SERVED_BY`), **data lineage** (`READS`, `WRITES`,
`DEFINES`, `DESCRIBES`) and **ownership** (`CONTAINS`, `PART_OF`, `USES`, and in a larger setting an `OWNED_BY` edge
to a team). Every app's build emits its own slice in that schema, exactly as `build_code_graph.py` does here, and a
central job merges the slices.

**Apps join through what they share, not through each other.** Two apps never need to know about each other: they
meet at a dataset both read, an API route one serves and another calls, or a domain entity (here, a piece of gear)
their data defines. Those shared ids are what turn many small graphs into one.

**The questions cross app boundaries.** With the slices merged, the same queries this page runs for one app run for
all of them:

- *Change impact:* "If this dataset's schema changes, which apps read it, which of their features use it, and which
  user-guide pages must be reviewed?" (the worked example above, across every app at once)
- *Documentation debt:* "Which user-facing features, in any app, have no documentation?" (question q10, platform-wide)
- *Stale docs:* "Which pages document a button, route or function that no longer exists?" (caught at build time)
- *Answer grounding:* a support or search question lands on a guide section; the graph walks from that section to the
  feature, the code that implements it, the data it reads, and the domain entities involved, so an answer can cite
  all of them. Graph neighbours also help rank search results.
- *Ownership:* with `OWNED_BY` edges, "who owns every page affected by this change?"

**What keeps it trustworthy at scale** is what keeps it trustworthy here: every edge says how it was derived (parsed,
declared, or verified), declared links are checked on every build so drift fails the build rather than accumulating,
inputs are hashed so a stale graph is refused, visibility rules keep private material out of what gets published (as
the manual sections are kept out here), and each graph question is checked against an answer worked out without the
graph.

**Honest limits of this small version.** The JavaScript is read with patterns, not a full parser, so dynamic calls are
missed; the guide-to-code links are hand-declared (checked, but written by a person); and the impact rule follows
direct links only. A platform version would use proper parsers per language and would add service-level edges (queues,
events, schemas) alongside the function-level ones shown here.
"""


def context_graph_page(inv):
    """Three apps' docs and code plus the manuals of 25 makers, joined by one vocabulary: the whole idea on one page."""
    pub = ROOT / "graph" / "public"
    code = json.loads((pub / "code.json").read_text())
    terms = json.loads((pub / "terms.json").read_text())
    edges = json.loads((pub / "edges.json").read_text())
    ans = {a["id"]: a for a in json.loads((pub / "answers.json").read_text())["answers"]}
    man = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    items = {i["id"]: i for i in inv["items"]}
    vt = Counter(v["type"] for v in code["vertices"])
    apps = sorted(v["name"] for v in code["vertices"] if v["type"] == "app")
    in_man = {c["id"] for c in terms["concepts"] if any(c["labels"].values())}
    app_of = {e["dst"] for e in code["edges"] if e["rel"] == "CONTAINS"}
    in_app = {e["dst"].split(":", 1)[1] for e in code["edges"] if e["rel"] == "USES_TERM" and e["src"] in app_of}
    c = {"manuals": len(man), "makers": len({items[m["device"]].get("manufacturer") for m in man if m["device"] in items}),
         "formats": len({m["doc_type"] for m in man}), "app_docs": vt["doc_section"], "apps": len(apps),
         "code_files": vt["code_file"], "buttons": vt["ui_action"],
         "concepts": sum(1 for x in terms["concepts"] if not x.get("grouping")),
         "labels": sum(1 + len(x.get("alt", [])) for x in terms["concepts"]),
         "shared": len(in_man & in_app), "uses_term": sum(1 for e in edges if e["rel"] == "USES_TERM")}
    ocr = sum(1 for m in man if str(m.get("pdf", "")).endswith(".ocr.pdf"))
    n_secs = sum(m["sections"] for m in json.loads((ROOT / "data" / "snapshot.json").read_text())["manuals"])
    fmt = Counter(m["doc_type"] for m in man)
    fmt_line = ", ".join(f"{n} {k.replace('-', ' ')}{'s' if n != 1 else ''}" for k, n in fmt.most_common())
    skipped = code.get("terminology", {}).get("skipped_matches", {})
    joins = {}
    for e in code["edges"]:
        if e["rel"] == "READS":
            joins.setdefault(e["dst"], set()).add(next(a for a in code["edges"] if a["rel"] == "CONTAINS" and a["dst"] == e["src"])["src"])
    shared_ds = sorted(d.split(":", 1)[1] for d, a in joins.items() if len(a) >= 2)
    qa = "\n".join(f"- **{ans[q]['question']}**  \n  " + "; ".join(ans[q]["answer"]) + ".  " +
                   " ".join(f"`{k}: {s_}`" for k, s_ in ans[q]["checks"].items()) for q in ("q13", "q14", "q15") if q in ans)
    return f"""# Many sources, one context graph

This knowledge base started as a way to keep studio gear straight. Its real subject turned out to be a common problem:
**content from many authors, in many formats, that uses different words for the same things**, and that has to be
usable as one body of knowledge.

The sources here are {c['manuals']} documents from {c['makers']} manufacturers ({fmt_line}; {ocr} of them scanned and
OCR'd), plus three apps that each have code and documentation of their own: {", ".join(apps)}. The documentation site is
treated as an app like the others. It has content, build code and data dependencies, and it publishes another app's
user guide. Nothing here is rewritten to force the sources to agree. Each source keeps its own words, and a shared
vocabulary maps those words onto one set of concepts.

{fig(viz_code.context_diagram(c), "Every number is counted from the committed graph files on each build.")}

## The layers, and how they join

| Layer | What it links | Built by | Checked by |
|---|---|---|---|
| Inventory and wiring | gear, makers, cables, case positions, power | hand-kept YAML | validators; graph questions q1-q6 |
| Manuals | {c['manuals']} documents, {n_secs:,} sections, provenance per section | `convert_manual.py` | coverage checks, strict build |
| Terminology | {c['concepts']} concepts, {c['labels']} labels, typed relations | `TERMS.yaml`, `build_terms.py` | taxonomy rules; q7-q9 |
| Code and docs | {c['apps']} apps, {vt['code_file']} code files, {vt['function']} functions, {vt['doc_section']} doc sections | `build_code_graph.py` | drift checks; q10-q12 |
| One context graph | all of the above, joined | `build_graph.py` | q13-q15 below |

The joins are ids that more than one source shares:

- **Terminology.** A manual, a doc section, a code comment and a button label that name the same concept all get a
  `USES_TERM` edge to it ({c['uses_term']:,} such edges). That's how a Roland manual's "sync" and the Patchbay's
  "Clock/Sync" legend end up next to each other.
- **Datasets.** Apps that read the same file are joined through it. The three apps here share
  {len(shared_ds)} datasets (for example {", ".join(f"`{d}`" for d in shared_ds[:4])}).
- **Domain entities.** A dataset *defines* or *describes* items and manuals, so code and docs reach the gear itself.

## Asking across every source at once

{qa}

The second answer is the whole problem in one line: five different words for one idea, spread across the
manufacturers, and the apps pick up three of them. Without the shared concept those would be five unrelated strings.

## Same word, different meaning

The matcher that reads the manuals reads the apps too, but some gear terms are also everyday English. In a sequencer
manual *fill*, *pattern*, *chain* and *step* are features. In a developer's notes they are ordinary words ("fill the
field", "a regex pattern"). So outside the manuals, {len(skipped)} such concepts are not matched
({", ".join(f"{k} {n}" for k, n in skipped.items())} matches set aside). Content from different authors needs
**source-aware** rules, not one global list, and the graph records which rule applied.

## How this maps onto a larger content estate

| Here | In a larger organization |
|---|---|
| {c['makers']} manufacturers, each with its own conventions | many teams and vendors, each with its own conventions |
| full manuals, quick starts, datasheets, web pages, OCR'd scans | wikis, doc sites, tickets, specs, slide decks, scanned records |
| "clock", "sync", "MIDI clock", "clock pulse" for one idea | different team names for one product, process or field |
| `TERMS.yaml`: preferred and alternative labels, broader/narrower | a shared vocabulary or taxonomy, owned and reviewed |
| three apps' code and docs graphs in one schema | an application catalogue, each system publishing its slice |
| datasets several apps read | shared data products and API contracts |
| gear items, manuals, placements | the business entities everyone talks about |
| private manual sections kept out of the public graph | access rules carried on every vertex and edge |

## What made it work

- **Map, don't rewrite.** Sources keep their own words, and the vocabulary maps them to concepts. Nothing is lost,
  and a disagreement shows up as a fact instead of being flattened.
- **Provenance on everything.** Every section, spec value and edge says where it came from and how it was derived:
  parsed, declared, or verified.
- **Unknown stays unknown.** A missing fact is recorded as missing, never guessed. The graph questions tell "not
  recorded" apart from "none".
- **Documentation is an app.** It has content, build code, data inputs and outputs, and it is checked like any other
  app.
- **Checks on every build.** Drift, staleness and coverage are checked every time, so errors fail the build instead of
  accumulating. Every graph answer is checked against a result worked out without the graph.
- **Privacy as structure, not care.** Private material has its own visibility, git-ignored files never enter the
  graph, and the published output is scanned before every commit.

## What a consumer gets

One graph that answers "what is this, where is it described, who uses it, and what breaks if it changes?" whatever
the source. The Patchbay is itself a consumer: it reads the inventory, the wiring, the MIDI plan and the drawings from
this graph to pre-patch a session. Search, question-answering that cites its sources, change-impact reviews and
content-gap reports are all queries over the same edges.
"""


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
    (DOCS / "stylesheets" / "viz.css").write_text(viz.CSS + viz_graph.CSS + viz_terms.CSS + viz_code.CSS, encoding="utf-8")
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
- [Terminology](visuals/terms.md): a taxonomy and ontology of the words the manuals use, and who says what
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

    # ---------- terminology ----------
    tm = viz_terms.Terms(ROOT)
    if tm.d["terms_sha256"] != hashlib.sha256((ROOT / "TERMS.yaml").read_bytes()).hexdigest():
        raise SystemExit("graph/public/terms.json is STALE for TERMS.yaml. Run: .venv/bin/python tools/build_terms.py")
    heat, naming = viz_terms.naming_heatmap(tm, gr)
    q = {a["id"]: a for a in ans["answers"]}
    if not q["q8"]["answer"][0].startswith(f"{len(naming)} concepts"):
        raise SystemExit(f"terminology page and graph q8 disagree: page has {len(naming)} concepts, graph says {q['q8']['answer'][0]!r}")
    cs = tm.d["concepts"]
    n_group = sum(1 for c in cs if c["grouping"])
    n_labels = sum(len(c["labels"]) for c in cs)
    n_poly = sum(1 for c in cs if len(c["broader"]) > 1)
    corpus = tm.d["corpus"]
    naming_table = "\n".join(f"| {c['pref']} | " + "<br>".join(f"**{w}**: {', '.join(sorted(m for m in dom if dom[m] == w))}" for w in sorted({w for w in dom.values() if w}))
                              + ("<br>*tied*: " + ", ".join(sorted(m for m in dom if dom[m] is None)) if None in dom.values() else "") + " |" for c, _, dom in naming)
    rel_table = "\n".join(f"| **{p['label']}**<br>{' / '.join(tm.facet[x]['pref'] for x in p['domain'])} → {' / '.join(tm.facet[x]['pref'] for x in p['range'])} | "
                          + "; ".join(f"{tm.name(r['s'])} → {tm.name(r['o'])}" for r in tm.d["relations"] if r["p"] == p["id"]) + " |" for p in tm.d["predicates"])
    homo_table = "\n".join(f"| {h['label']} | " + "<br>".join(h["senses"]) + f" | {sum(h['counts'].values())} in {len(h['counts'])} |" for h in tm.d["homographs"])
    concept_table = "\n".join(
        f"| {tm.facet[c['facet']]['pref']} | {c['pref']}{' *(grouping)*' if c['grouping'] else ''} | {', '.join(c['alt']) or '-'} | "
        f"{', '.join(tm.name(b) for b in c['broader'])} | {', '.join(tm.name(x) for x in c['close']) or '-'} | {c['tag']} | "
        f"{'-' if c['grouping'] and not tm.manuals_using(c['id']) else len(tm.manuals_using(c['id']))} |" for c in cs)
    page("visuals/terms.md", "Terminology", f"""
# Terminology: a taxonomy and an ontology of the gear's vocabulary

The manufacturers describe the same ideas in different words: Dreadbox's manual says **EG** where
Elektron's says **envelope**, Behringer writes **HPF** where Elektron writes **highpass**, and Elektron places **trigs**
where everyone else talks about **steps**. This page organises that vocabulary
two ways:

- a **taxonomy** says what kind of thing each concept is (a VCF *is a kind of* filter), arranged as a hierarchy;
- an **ontology** adds typed relationships between concepts (a filter *has parameter* cutoff, an LFO *modulates* it)
  with rules about which kinds of concept each relationship may connect.

The concept scheme is written by hand in `TERMS.yaml`; `tools/build_terms.py` checks it and counts where every label
occurs in the {corpus['manuals']} converted manuals ({corpus['sections']} sections, {corpus['manufacturers']} makers). Only the counts are published, never
the manual text. The terms are also nodes in the [knowledge graph](graph.md), linked to the manuals that use them.

| Measure | Value |
|---|---|
| Facets (top classes) | {len(tm.facet)} |
| Concepts | {len(cs)} ({n_group} grouping nodes, {n_poly} with two parents) |
| Labels (preferred + synonyms) | {n_labels} |
| Typed relations | {len(tm.d['relations'])}, using {len(tm.d['predicates'])} predicates |
| Concepts named differently by different makers | {len(naming)} |
| Homographs (one word, two meanings) | {len(tm.d['homographs'])} |

## Taxonomy

Each panel is a facet; indentation means *is a kind of*. The bar shows how many of the {corpus['manuals']} manuals use the concept
under any of its names. A concept with two parents is listed in full under the first and marked *(also)* under the second:
MIDI clock is a MIDI message by format and a sync signal by purpose.

{fig(viz_terms.taxonomy_tree(tm), "Hover a concept for its synonyms and notes. Grouping nodes (italic) organise the tree but are not manual terms themselves, so they are not required to occur in the text.")}

Three modelling choices that a flat tag list cannot express:

- **Synonym vs kind vs neighbour.** *Emphasis* is a synonym of resonance (same control, different word), so it is a label
  on the same concept. *VCF* is a kind of filter, so it is a narrower concept. *Trig* is close to *step* but not the
  same (an Elektron trig is an event placed on a step), so the two stay separate and are linked as close matches.
- **Polyhierarchy.** A concept may have two parents when it genuinely belongs in two places (LFO: an oscillator by
  construction, a modulation source by use).
- **Facets as classes.** Every concept belongs to exactly one facet, and the facet is its class in the ontology below.

## Ontology

The ontology is small on purpose: {len(tm.d['predicates'])} relation types, each with a *domain* and *range* (which classes it may
connect). The checker rejects a statement like "filter carries MIDI message", because *carries* only runs from a port to
a signal. That rule turns a modelling slip into a build failure.

{fig(viz_terms.ontology_diagram(tm), "Boxes are facets; arrows are kinds of relation between them, with how many statements of each kind. Loops are relations inside one class (a song contains chains, a chain contains patterns).")}

One worked example: the filter, the kinds of filter, its parameters, and what modulates them. It reads both ways: the
taxonomy says ADSR is a kind of envelope, the ontology says an envelope modulates cutoff, so the graph can conclude that
an ADSR modulates cutoff without anyone writing that down.

{fig(viz_terms.neighbourhood(tm, "filter"), "Each box shows the preferred label and its synonyms. Hollow arrowheads are is-a links (taxonomy); filled arrowheads are typed relations (ontology).")}

| Relation, and the classes it may connect | Statements |
|---|---|
{rel_table}

## Same concept, different words

For each concept, which word each manufacturer's manuals use most. Only concepts where makers with a clear favourite
disagree are shown; a maker whose manuals use two words equally often is marked *tied* and decides nothing.

{fig(heat, "Each row is one label of a concept; each column a manufacturer. Shading is that label's share of the maker's mentions of the concept; the outlined cell is the word that maker uses most.")}

| Concept | Word used most, by maker |
|---|---|
{naming_table}

## Questions the terminology answers

Both are graph queries (see the [knowledge graph](graph.md)), each checked against separate code that reads the raw files.

| Question | Answer |
|---|---|
""" + "\n".join(f"| {q[k]['question']} | " + "<br>".join(q[k]["answer"]) + " |" for k in ("q8", "q9")) + f"""

## Homographs: one word, two meanings

Some words mean two different things across these manuals. They are counted but assigned to no concept, because a
count cannot tell the senses apart. Longer labels are matched first, so *gate length* and *gate output* are counted as
their own concepts and only a bare *gate* lands here.

| Word | Senses | Mentions (in manuals) |
|---|---|---|
{homo_table}

## How it is checked

`tools/build_terms.py` fails the build if:

- a `broader` link points nowhere, loops, or a concept reaches zero or two facets;
- one label belongs to two concepts (after folding case, hyphens and plurals), or a homograph is also a concept label;
- a close match duplicates a hierarchy link (SKOS keeps the two apart);
- a relation uses an undeclared predicate, or its subject or object falls outside the predicate's domain or range;
- **a concept occurs in no manual** (grouping nodes excepted): a term nobody uses is invented.

Each check was tested by breaking `TERMS.yaml` on purpose and confirming the build fails with the expected message.

## Limits

- **Counts are string matches, not meanings.** Whole words, case-insensitive, plurals folded, longest label first. Common
  words (*release*, *trigger*, *step*) are also used in their everyday sense, so their counts are upper bounds.
- **The scheme is one person's model.** The concepts were chosen from the manuals by the author with an AI assistant;
  the checks prove it is consistent and grounded in the text, not that it is the only reasonable model.
- **Coverage follows the manuals.** Gear without an ingested manual (most Eurorack modules) contributes no vocabulary.

## Every concept

| Facet | Concept | Also called | Kind of | Close to | Tag | Manuals |
|---|---|---|---|---|---|---|
{concept_table}
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
    page("midi-channels.md", "MIDI channels", midi_reference())

    # ---------- the patchbay app, published as a static read-only page (GitHub Pages has no server) ----------
    pb = ROOT / "patchbay"
    if (pb / "data" / "gear.json").is_file():
        dst = DOCS / "patchbay"
        shutil.copytree(pb / "web", dst, dirs_exist_ok=True)
        shutil.copytree(pb / "icons", dst / "icons", dirs_exist_ok=True, ignore=shutil.ignore_patterns("_sheet.html"))
        shutil.copy(pb / "data" / "gear.json", dst / "gear.json")
        page("patchbay-app.md", "Patchbay",
             "# Patchbay\n\nA drag-and-drop patch planner built on this knowledge base: drop gear on a canvas, patch "
             "audio/MIDI/clock/CV cables jack to jack (the recorded studio wiring is pre-patched), and open the "
             "Eurorack as its own rack view with faceplates at true HP width in your case rows.\n\n"
             "**[Open the patchbay](patchbay/index.html)**\n\n"
             "On this website it runs without a server: sessions are saved in your browser only, and jack edits are "
             "off. The full app (saving session files, editing jacks) runs locally from the repository's `patchbay/` "
             "folder with `make serve`. All faceplates and icons are drawn from data; no product photos are used.\n\n"
             "- [User guide](patchbay-guide.md): every button and gesture, section by section.\n"
             "- [Code, docs and the knowledge graph](patchbay-code-graph.md): how the guide is linked to the code, "
             "and the code to the knowledge graph, as one graph, and how that scales to a platform of many apps.")
        guide = (pb / "docs" / "user-guide.md").read_text(encoding="utf-8")
        page("patchbay-guide.md", "Patchbay user guide", guide)
        page("patchbay-code-graph.md", "Patchbay: code, docs and the knowledge graph", code_graph_page(inv))
        page("context-graph.md", "Many sources, one context graph", context_graph_page(inv))

    # ---------- config ----------
    nav = [{"Home": "index.md"},
           {"Visual explanations": [{"How the pipeline works": "visuals/pipeline.md"}, {"Inventory coverage": "visuals/coverage.md"},
                                    {"How well each spec is supported": "visuals/trust.md"}, {"Power budget": "visuals/power.md"}, {"Knowledge graph": "visuals/graph.md"}, {"Terminology": "visuals/terms.md"},
                                    {"What the checks caught": "visuals/checks.md"}, {"Retrieval results": "visuals/retrieval.md"}]},
           {"Inventory": "inventory.md"}, {"MIDI channels": "midi-channels.md"},
           {"Patchbay": [{"Overview": "patchbay-app.md"}, {"User guide": "patchbay-guide.md"},
                         {"Code, docs and the knowledge graph": "patchbay-code-graph.md"}]},
           {"One context graph": "context-graph.md"}, {"Eurorack": eu["nav"]},
           {"About the project": [{t: f"about/{f}"} for f, t in [("index.md", "Overview"), ("architecture.md", "Architecture"),
                                                                 ("verification.md", "How correctness is checked"), ("evaluation.md", "Retrieval evaluation"),
                                                                 ("decisions.md", "Decision log"), ("runbook.md", "Runbook"),
                                                                 ("terminology.md", "How the terminology was built"), ("limitations.md", "Limitations and open questions"), ("status.md", "Current status")]]}]
    cfg = {"site_name": "Gear Knowledge Base", "site_description": "A machine-readable studio gear knowledge base, explained with charts",
           "site_url": SITE, "repo_url": REPO, "repo_name": "differentJason/gear-graph", "docs_dir": "docs",
           "theme": THEME,
           "extra_css": versioned(EXTRA_CSS + ["stylesheets/viz.css"], DOCS / "stylesheets"), "plugins": ["search"], "nav": nav}
    (OUT / "mkdocs.yml").write_text("# GENERATED by tools/build_public.py. Do not edit.\n" + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    print(f"public site written to {OUT}: {sum(1 for _ in DOCS.rglob('*.md'))} pages")


if __name__ == "__main__":
    main()
