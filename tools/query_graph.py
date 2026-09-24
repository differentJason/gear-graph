#!/usr/bin/env python3
"""Ask the knowledge graph its acceptance questions, and check every answer.

    .venv-graph/bin/python tools/query_graph.py

Loads the PUBLIC snapshot (graph/public/*.json), so it runs from a fresh clone. Each answer is checked two ways:
  hand    = evals/graph_golden.yaml states the expected answer, worked out by hand from connections.yaml;
  cross   = an independent implementation reads the raw source files (evidence, connections.yaml) with no graph in it.
A graph query that only agreed with itself would prove nothing. Exit code 1 if any check fails.
Writes graph/public/answers.json (read by build_public.py for the site; carries a digest of the snapshot it answered from).
"""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "graph")]

from build_graph import ESCHEMA, VSCHEMA             # noqa: E402  (the same schemas that wrote the snapshot)
from check_env import spark_session                  # noqa: E402
from graphframes import GraphFrame                   # noqa: E402
from pyspark.sql import functions as F               # noqa: E402

PUB = ROOT / "graph" / "public"
ROUTING = ["CONNECTS", "INSTALLED_IN", "POWERED_BY"]


def snapshot_digest():
    return hashlib.sha256((PUB / "vertices.json").read_bytes() + (PUB / "edges.json").read_bytes()).hexdigest()


def load(spark):
    v = spark.read.schema(VSCHEMA).option("multiLine", True).json(str(PUB / "vertices.json"))
    e = spark.read.schema(ESCHEMA).option("multiLine", True).json(str(PUB / "edges.json"))
    return GraphFrame(v, e)


def bare(x):
    return x.split(":", 1)[1]


# ------------------------------------------------------------------------------------------ the queries
def feeds(g, item):
    """One hop: what does this item feed, by which medium? (confirmed links only)"""
    rows = (g.find("(a)-[e]->(b)").filter(f"a.id = 'item:{item}' AND e.rel = 'CONNECTS' AND e.status = 'confirmed'")
            .select("e.medium", "b.id", "e.from_port", "e.to_port").collect())
    out = defaultdict(list)
    for r in rows:
        out[r["medium"]].append(bare(r["id"]))
    return {m: sorted(v) for m, v in sorted(out.items())}


def reach(g, root, media):
    """Everything that receives from `root` over these media, directly or through other devices.
    Runs GraphFrames shortestPaths on the REVERSED confirmed-edge graph, so each vertex learns its distance back to the root."""
    edges = (g.edges.filter(F.col("rel") == "CONNECTS").filter(F.col("status") == "confirmed").filter(F.col("medium").isin(media))
             .select(F.col("dst").alias("src"), F.col("src").alias("dst"), "rel"))
    dist = GraphFrame(g.vertices, edges).shortestPaths(landmarks=[f"item:{root}"]).select("id", "distances").collect()
    return {bare(r["id"]): r["distances"][f"item:{root}"] for r in dist if r["distances"] and r["id"] != f"item:{root}"}


def source_support(g):
    """How many sources stand behind each spec value, and of what tier? Returns Counter of labels."""
    v, e = g.vertices, g.edges
    tier = v.filter("type = 'source'").select(F.col("id").alias("sid"), F.col("tier"))
    per = (e.filter("rel = 'SOURCED_FROM'").join(tier, e.dst == tier.sid).groupBy(F.col("src").alias("spec"))
           .agg(F.count("*").alias("n"), F.first("tier").alias("tier")))
    specs = v.filter("type = 'spec'").select(F.col("id").alias("spec"), "status", "attested")
    rows = specs.join(per, "spec", "left").collect()
    out = Counter()
    for r in rows:
        n = r["n"] or 0
        out["no source (override, inferred or missing)" if n == 0 else f"one {r['tier']} source" if n == 1 else "two or more sources"] += 1
    attested_single = sum(1 for r in rows if (r["n"] or 0) == 1 and r["attested"])
    return out, attested_single, len(rows)


def midi_conflicts(g):
    """Fan-out points on the confirmed MIDI graph: items with 2+ outgoing confirmed CONNECTS edges, medium=midi.
    For each, group the downstream devices by their recorded midi_in_ch. 2+ devices sharing a non-null channel is a
    conflict (they would all respond to the same messages from that fan-out). A downstream device with no recorded
    midi_in_ch is reported separately: not recorded is not the same as no conflict."""
    midi_edges = (g.find("(a)-[e]->(b)").filter("e.rel = 'CONNECTS' AND e.status = 'confirmed' AND e.medium = 'midi'")
                  .select(F.col("a.id").alias("src"), F.col("b.id").alias("dst"), F.col("b.midi_in_ch").alias("ch")).collect())
    by_src = defaultdict(list)
    for r in midi_edges:
        by_src[r["src"]].append((r["dst"], r["ch"]))
    conflicts, unrecorded_ch = {}, {}
    for src, downstream in by_src.items():
        if len(downstream) < 2:
            continue
        groups = defaultdict(list)
        for dst, ch in downstream:
            groups[ch].append(bare(dst))
        fan = bare(src)
        dup = {ch: sorted(v) for ch, v in groups.items() if ch is not None and len(v) > 1}
        if dup:
            conflicts[fan] = dup
        if groups.get(None):
            unrecorded_ch[fan] = sorted(groups[None])
    return conflicts, unrecorded_ch


def unrecorded(g):
    """Items with no confirmed connection, placement or supply link, grouped by category. 'Not recorded' is not 'not connected'."""
    touched = (g.edges.filter(F.col("rel").isin(ROUTING)).filter(F.col("status") == "confirmed")
               .select(F.col("src").alias("id")).union(g.edges.filter(F.col("rel").isin(ROUTING)).filter(F.col("status") == "confirmed")
                                                       .select(F.col("dst").alias("id"))).distinct())
    items = g.vertices.filter("type = 'item'").select("id", "name", "category", "in_use")
    rows = items.join(touched, "id", "left_anti").collect()
    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(bare(r["id"]))
    return {k: sorted(v) for k, v in sorted(by.items())}


def naming(g):
    """Concepts that different manufacturers' documentation names differently. For each (concept, manufacturer), the label
    used most often is that manufacturer's word for it (a tie is reported as a tie and does not count); a concept whose makers
    have 2+ different clear words is reported.
    Motif: (item)-[HAS_MANUAL]->(manual)-[USES_TERM]->(term)."""
    rows = (g.find("(i)-[h]->(m); (m)-[u]->(t)").filter("h.rel = 'HAS_MANUAL' AND u.rel = 'USES_TERM' AND t.role = 'concept'")
            .groupBy(F.col("t.id").alias("term"), F.col("i.manufacturer").alias("mfr"), F.col("u.label").alias("label"))
            .agg(F.sum("u.value").alias("n")).collect())
    return _dominant((bare(r["term"]), r["mfr"], r["label"], r["n"]) for r in rows)


def _dominant(rows):
    per = defaultdict(Counter)
    for term, mfr, label, n in rows:
        per[(term, mfr or "maker not recorded")][label] += int(n)
    words = defaultdict(lambda: defaultdict(list))
    for (term, mfr), c in per.items():
        top = max(c.values())
        tied = sorted(l for l, n in c.items() if n == top)
        words[term][tied[0] if len(tied) == 1 else " = ".join(tied) + " (tie)"].append(mfr)
    # only makers with ONE clear most-used word decide whether a concept is named differently; a tie is shown, not counted
    return {t: {w: sorted(m) for w, m in sorted(ws.items())} for t, ws in sorted(words.items())
            if len([w for w in ws if not w.endswith("(tie)")]) > 1}


def inherits(g, param, predicate="MODULATES"):
    """Which devices document something that <predicate> <param>, counting narrower kinds of it (inheritance down BROADER)?
    Direct subjects come from the typed relation; their descendants from GraphFrames shortestPaths over BROADER edges
    (child -> parent), with the subjects as landmarks. A device qualifies if its manual uses the parameter AND a subject."""
    subj = [r["src"] for r in g.edges.filter(f"rel = '{predicate}' AND dst = 'term:{param}'").select("src").collect()]
    tv = g.vertices.filter("type = 'term'")
    broader = g.edges.filter("rel = 'BROADER'").select("src", "dst", "rel")
    dist = GraphFrame(tv, broader).shortestPaths(landmarks=subj).select("id", "distances").collect()
    kinds = {r["id"]: min(r["distances"].values()) for r in dist if r["distances"]}          # subject itself has distance 0
    uses = (g.find("(i)-[h]->(m); (m)-[u]->(t)").filter("h.rel = 'HAS_MANUAL' AND u.rel = 'USES_TERM'")
            .select(F.col("i.id").alias("item"), F.col("t.id").alias("term")).distinct().collect())
    by_item = defaultdict(set)
    for r in uses:
        by_item[bare(r["item"])].add(r["term"])
    out = {it: sorted(bare(t) for t in terms if t in kinds) for it, terms in by_item.items() if f"term:{param}" in terms}
    inherited = sorted(bare(k) for k, d in kinds.items() if d > 0)
    return {k: v for k, v in sorted(out.items()) if v}, inherited


# ------------------------------------------------------------------------------------------ independent cross-checks
def cross_naming():
    """From graph/public/terms.json + inventory.yaml + tools/manifest.yaml only: no graph."""
    t = json.loads((PUB / "terms.json").read_text())
    inv = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    mfr = {m["id"]: inv[m["device"]].get("manufacturer") for m in yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]}
    return _dominant((c["id"], mfr[mid], label, n) for c in t["concepts"] if not c["grouping"]
                     for label, per in c["labels"].items() for mid, n in per.items())


def cross_inherits(param, predicate="modulates"):
    """From TERMS.yaml (hierarchy, relations) + terms.json (usage) + tools/manifest.yaml only: no graph."""
    t = yaml.safe_load((ROOT / "TERMS.yaml").read_text())
    usage = json.loads((PUB / "terms.json").read_text())
    kids = defaultdict(set)
    for c in t["concepts"]:
        for b in c["broader"]:
            kids[b].add(c["id"])
    todo = [s for s, p, o in t["relations"] if p == predicate and o == param]
    kinds = set()
    while todo:
        x = todo.pop()
        if x not in kinds:
            kinds.add(x)
            todo += kids[x]
    used = defaultdict(set)
    for c in usage["concepts"]:
        for per in c["labels"].values():
            for mid in per:
                used[mid].add(c["id"])
    device = {m["id"]: m["device"] for m in yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]}
    by_item = defaultdict(set)
    for mid, cs in used.items():
        by_item[device[mid]] |= cs
    return {it: sorted(cs & kinds) for it, cs in sorted(by_item.items()) if param in cs and cs & kinds}
def cross_source_support():
    """From the raw evidence files and overrides only: no graph."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build_eurorack as be
    ov = yaml.safe_load((ROOT / "eurorack" / "overrides.yaml").read_text()) or {}
    inv = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    out, n_specs = Counter(), 0
    for f in sorted((ROOT / "eurorack" / "evidence").glob("*.json")):
        rec = json.loads(f.read_text())
        if f.stem not in inv:
            continue
        for field, _ in be.FIELDS:
            n_specs += 1
            seen = [s["tier"] for s in rec["sources"] if field in s["values"]] if field not in ov.get(f.stem, {}) else []
            out["no source (override, inferred or missing)" if not seen else f"one {seen[0]} source" if len(seen) == 1 else "two or more sources"] += 1
    return out, n_specs


def cross_midi_conflicts():
    """From connections.yaml + midi_channels.yaml only: no graph."""
    c = yaml.safe_load((ROOT / "connections.yaml").read_text())
    m = yaml.safe_load((ROOT / "midi_channels.yaml").read_text()) or {}
    ch_by_device = {}
    for rec in m.get("channels", []):
        if rec["device"] not in ch_by_device:
            ch_by_device[rec["device"]] = rec.get("in")
    by_src = defaultdict(list)
    for l in c["links"]:
        if l["status"] == "confirmed" and l["medium"] == "midi":
            by_src[l["from"]].append((l["to"], ch_by_device.get(l["to"])))
    conflicts, unrecorded_ch = {}, {}
    for src, downstream in by_src.items():
        if len(downstream) < 2:
            continue
        groups = defaultdict(list)
        for dst, ch in downstream:
            groups[ch].append(dst)
        dup = {ch: sorted(v) for ch, v in groups.items() if ch is not None and len(v) > 1}
        if dup:
            conflicts[src] = dup
        if groups.get(None):
            unrecorded_ch[src] = sorted(groups[None])
    return conflicts, unrecorded_ch


def cross_unrecorded():
    """From connections.yaml only."""
    c = yaml.safe_load((ROOT / "connections.yaml").read_text())
    inv = yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]
    touched = set()
    for l in c["links"]:
        if l["status"] == "confirmed":
            touched |= {l["from"], l["to"]}
    for p in c["placements"]:
        if p["status"] == "confirmed":
            touched |= {p["module"], p["case"], p["powered_by"]}
    by = defaultdict(list)
    for i in inv:
        if i["id"] not in touched:
            by[i["category"]].append(i["id"])
    return {k: sorted(v) for k, v in sorted(by.items())}


# ---------- the Patchbay app: code <-> user docs <-> knowledge graph ----------
def _code_edges(g, rels):
    return [r.asDict() for r in g.edges.filter(F.col("rel").isin(rels)).select("src", "dst", "rel").collect()]


def undocumented(g):
    """UI actions that no USER-guide section documents (doc drift, seen from the graph)."""
    v = {r["id"]: r.asDict() for r in g.vertices.filter("type IN ('ui_action', 'doc_section')").collect()}
    documented = {e["dst"] for e in _code_edges(g, ["DOCUMENTS"]) if v.get(e["src"], {}).get("role") == "user"}
    return sorted(v[a]["name"] for a in v if v[a]["type"] == "ui_action" and a not in documented)


def doc_impact(g, route_prefix):
    """User-guide sections to review if the API routes under `route_prefix` change: sections that document a function
    requesting such a route, or a UI action handled by such a function. Direct links only (no transitive CALLS), so a
    dispatcher that reaches everything does not flag every page."""
    v = {r["id"]: r.asDict() for r in g.vertices.filter("type IN ('api_route', 'doc_section', 'function', 'ui_action')").collect()}
    es = _code_edges(g, ["REQUESTS", "HANDLED_BY", "DOCUMENTS"])
    routes = {i for i, x in v.items() if x["type"] == "api_route" and x["name"].split(" ", 1)[1].startswith(route_prefix)}
    fns = {e["src"] for e in es if e["rel"] == "REQUESTS" and e["dst"] in routes}
    acts = {e["src"] for e in es if e["rel"] == "HANDLED_BY" and e["dst"] in fns}
    secs = {e["src"] for e in es if e["rel"] == "DOCUMENTS" and (e["dst"] in fns or e["dst"] in acts)
            and v.get(e["src"], {}).get("role") == "user"}
    return sorted(v[x]["name"] for x in secs), sorted(v[x]["name"] for x in fns), sorted(v[x]["name"] for x in acts)


def kb_reach(g):
    """For each knowledge-base dataset the Patchbay's code reads: how many knowledge-graph vertices it defines or
    describes (public snapshot, so the private manual sections are not counted)."""
    es = _code_edges(g, ["READS", "DEFINES", "DESCRIBES", "PART_OF"])
    kb = {e["src"] for e in es if e["rel"] == "PART_OF" and e["dst"] == "system:gear-kb"}
    read = {e["dst"] for e in es if e["rel"] == "READS" and e["src"].startswith("file:patchbay/")} & kb
    out = {}
    for d in sorted(read):
        n = sum(1 for e in es if e["src"] == d and e["rel"] in ("DEFINES", "DESCRIBES"))
        if n:
            out[d.split(":", 1)[1]] = n
    return out


def cross_undocumented():
    """From the raw files, not the graph: onAction's cases vs the user guide's covers notes."""
    app = (ROOT / "patchbay" / "web" / "app.js").read_text(encoding="utf-8")
    body = app[app.index("function onAction"):]
    nxt = body.find("\nfunction ", 1)
    body = body[:nxt] if nxt > 0 else body
    acts = set(re.findall(r"case '([a-z-]+)':", body))
    guide = (ROOT / "patchbay" / "docs" / "user-guide.md").read_text(encoding="utf-8")
    covered = {t for c in re.findall(r"<!--\s*covers:(.*?)-->", guide, re.S) for t in c.split() if not t.startswith("fn:")}
    return sorted(acts - covered)


def cross_kb_reach():
    """Counted from the YAML files directly."""
    ids = {i["id"] for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    c = yaml.safe_load((ROOT / "connections.yaml").read_text())
    conn = {x for l in c["links"] for x in (l["from"], l["to"])} | {x for p in c["placements"] for x in (p["module"], p["case"], p["powered_by"])}
    midi = {m["device"] for m in (yaml.safe_load((ROOT / "midi_channels.yaml").read_text()) or {}).get("channels", [])}
    img = {e["device"] for e in yaml.safe_load((ROOT / "tools" / "image_manifest.yaml").read_text())["images"]}
    man = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    counts = {"connections.yaml": len(conn & ids), "inventory.yaml": len(ids), "midi_channels.yaml": len(midi & ids),
              "tools/image_manifest.yaml": len(img & ids), "tools/manifest.yaml": len(man)}
    # which of them the app reads, decided from its source text (not from the graph)
    src = "".join(f.read_text(encoding="utf-8") for d in ("tools", "web") for f in (ROOT / "patchbay" / d).glob("*.[pj][ys]"))
    named = {"connections.yaml": r"connections\.yaml", "inventory.yaml": r"inventory\.yaml", "midi_channels.yaml": r"midi_channels\.yaml",
             "tools/image_manifest.yaml": r"image_manifest\.yaml", "tools/manifest.yaml": r"(?<!image_)manifest\.yaml"}
    return {k: n for k, n in counts.items() if re.search(named[k], src)}


# ---------- one context graph: manuals, app docs and code joined by the shared terminology ----------
def _family(g, root):
    """root concept plus every narrower concept (BROADER edges point child -> parent)."""
    br = [(r["src"], r["dst"]) for r in g.edges.filter("rel = 'BROADER'").select("src", "dst").collect()]
    fam, grew = {f"term:{root}"}, True
    while grew:
        new = {c for c, p_ in br if p_ in fam} - fam
        fam |= new
        grew = bool(new)
    return fam


def _app_of(g):
    """doc/code vertex -> app name (CONTAINS)."""
    names = {r["id"]: r["name"] for r in g.vertices.filter("type = 'app'").collect()}
    return {r["dst"]: names[r["src"]] for r in g.edges.filter("rel = 'CONTAINS'").select("src", "dst").collect() if r["src"] in names}


def concept_where(g, root):
    fam = _family(g, root)
    vt = {r["id"]: (r["type"], r["name"]) for r in g.vertices.filter("type IN ('manual', 'doc_section', 'code_file')").collect()}
    ut = [r for r in g.edges.filter("rel = 'USES_TERM'").select("src", "dst").collect() if r["dst"] in fam and r["src"] in vt]
    app = _app_of(g)
    docs, code = {}, set()
    for r in ut:
        t, nm_ = vt[r["src"]]
        if t == "doc_section":
            docs.setdefault(app.get(r["src"], "?"), set()).add(nm_)
        elif t == "code_file":
            code.add(nm_)
    return {"manuals": len({r["src"] for r in ut if vt[r["src"]][0] == "manual"}),
            "doc_sections": {a: sorted(v) for a, v in sorted(docs.items())}, "code_files": sorted(code)}


def vocabulary(g, root):
    """Which words each manufacturer's manuals use for this concept family, and which words the apps use."""
    fam = _family(g, root)
    mfr = {r["src"]: r["dst"] for r in g.edges.filter("rel = 'MADE_BY'").select("src", "dst").collect()}
    man_item = {r["dst"]: r["src"] for r in g.edges.filter("rel = 'HAS_MANUAL'").select("src", "dst").collect()}
    mname = {r["id"]: r["name"] for r in g.vertices.filter("type = 'manufacturer'").collect()}
    app = _app_of(g)
    words_m, words_a = defaultdict(set), defaultdict(set)
    for r in g.edges.filter("rel = 'USES_TERM'").select("src", "dst", "label").collect():
        if r["dst"] not in fam or not r["label"]:
            continue
        for lab in r["label"].split("; "):
            if r["src"].startswith("manual:") and man_item.get(r["src"]) in mfr:
                words_m[lab.lower()].add(mname[mfr[man_item[r["src"]]]])
            elif r["src"] in app:
                words_a[lab.lower()].add(app[r["src"]])
    return {"manufacturers": {w: sorted(v) for w, v in sorted(words_m.items())}, "apps": {w: sorted(v) for w, v in sorted(words_a.items())}}


def term_gaps(g):
    """Concepts the apps' docs and code use that no manual uses; and how many manual concepts no app mentions."""
    ut = g.edges.filter("rel = 'USES_TERM'").select("src", "dst").collect()
    app = _app_of(g)
    in_man = {r["dst"] for r in ut if r["src"].startswith("manual:")}
    in_app = {r["dst"] for r in ut if r["src"] in app}
    return {"apps_only": sorted(t.split(":", 1)[1] for t in in_app - in_man), "manuals_only": len(in_man - in_app),
            "shared": len(in_man & in_app)}


def _raw_context():
    """Raw inputs for the cross-checks: terms.json (manual label counts), TERMS.yaml (hierarchy), code.json (apps)."""
    terms = json.loads((PUB / "terms.json").read_text())
    code = json.loads((PUB / "code.json").read_text())
    return terms, code


def _raw_family(terms, root):
    br = [(c["id"], p_) for c in terms["concepts"] for p_ in c.get("broader", [])]
    fam, grew = {root}, True
    while grew:
        new = {c for c, p_ in br if p_ in fam} - fam
        fam |= new
        grew = bool(new)
    return fam


def _raw_app_of(code):
    names = {v["id"]: v["name"] for v in code["vertices"] if v["type"] == "app"}
    return {e["dst"]: names[e["src"]] for e in code["edges"] if e["rel"] == "CONTAINS" and e["src"] in names}


def cross_concept_where(root):
    terms, code = _raw_context()
    fam = _raw_family(terms, root)
    manuals = {mid for c in terms["concepts"] if c["id"] in fam for per in c["labels"].values() for mid in per}
    v = {x["id"]: x for x in code["vertices"]}
    app = _raw_app_of(code)
    docs, files = defaultdict(set), set()
    for e in code["edges"]:
        if e["rel"] == "USES_TERM" and e["dst"].split(":", 1)[1] in fam:
            if v[e["src"]]["type"] == "doc_section":
                docs[app.get(e["src"], "?")].add(v[e["src"]]["name"])
            elif v[e["src"]]["type"] == "code_file":
                files.add(v[e["src"]]["name"])
    return {"manuals": len(manuals), "doc_sections": {a: sorted(x) for a, x in sorted(docs.items())}, "code_files": sorted(files)}


def cross_vocabulary(root):
    terms, code = _raw_context()
    fam = _raw_family(terms, root)
    inv = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    dev = {m["id"]: m["device"] for m in yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]}
    words_m, words_a = defaultdict(set), defaultdict(set)
    for c in terms["concepts"]:
        if c["id"] in fam:
            for lab, per in c["labels"].items():
                for mid in per:
                    mk = inv.get(dev.get(mid), {}).get("manufacturer")
                    if mk:
                        words_m[lab.lower()].add(mk)
    app = _raw_app_of(code)
    for e in code["edges"]:
        if e["rel"] == "USES_TERM" and e["dst"].split(":", 1)[1] in fam and e["src"] in app:
            for lab in e["label"].split("; "):
                words_a[lab.lower()].add(app[e["src"]])
    return {"manufacturers": {w: sorted(v) for w, v in sorted(words_m.items())}, "apps": {w: sorted(v) for w, v in sorted(words_a.items())}}


def cross_term_gaps():
    terms, code = _raw_context()
    in_man = {c["id"] for c in terms["concepts"] if any(c["labels"].get(l) for l in c["labels"])}
    app = _raw_app_of(code)
    in_app = {e["dst"].split(":", 1)[1] for e in code["edges"] if e["rel"] == "USES_TERM" and e["src"] in app}
    return {"apps_only": sorted(in_app - in_man), "manuals_only": len(in_man - in_app), "shared": len(in_man & in_app)}


# ------------------------------------------------------------------------------------------ run
def main():
    golden = yaml.safe_load((ROOT / "evals" / "graph_golden.yaml").read_text())
    spark = spark_session("gear-graph-query")
    g = load(spark)
    names = {bare(r["id"]): r["name"] for r in g.vertices.filter("type = 'item'").select("id", "name").collect()}
    nm = lambda x: names.get(x, x)
    answers, failures = [], []

    def record(qid, question, result, lines, expected=None, cross=None, note=None):
        checks = []
        if expected is not None:
            checks.append(("hand", result == expected))
        if cross is not None:
            checks.append(("cross", result == cross))
        for kind, ok in checks:
            if not ok:
                failures.append(f"{qid} ({kind}): graph said {result!r}")
        answers.append({"id": qid, "question": question, "answer": lines, "checks": {k: ("pass" if ok else "FAIL") for k, ok in checks}, **({"note": note} if note else {})})
        print(f"{qid}  " + "  ".join(f"[{k}:{'ok' if ok else 'FAIL'}]" for k, ok in checks) + f"  {question}")
        for ln in lines:
            print("       " + ln)

    for q in golden["questions"]:
        kind, qid = q["query"], q["id"]
        if kind == "feeds":
            res = feeds(g, q["item"])
            lines = [f"{m}: {', '.join(nm(x) for x in v)}" for m, v in res.items()] or ["nothing recorded (not the same as nothing connected)"]
            record(qid, q["question"], res, lines, expected=q["expected"], note=q.get("note"))
        elif kind == "reach":
            res = reach(g, q["item"], q["media"])
            lines = [f"{len(res)} devices",
                     "directly: " + ", ".join(sorted(nm(k) for k, d in res.items() if d == 1)),
                     "through one other device: " + ", ".join(sorted(nm(k) for k, d in res.items() if d == 2))]
            record(qid, q["question"], {k: v for k, v in sorted(res.items())}, lines, expected={k: v for k, v in sorted(q["expected"].items())}, note=q.get("note"))
        elif kind == "support":
            res, attested, total = source_support(g)
            cross, cross_total = cross_source_support()
            lines = [f"{n} of {total} spec values: {label}" for label, n in sorted(res.items(), key=lambda kv: -kv[1])]
            lines.append(f"{attested} of the single-source values are attested correct by the owner")
            record(qid, q["question"], dict(res), lines, cross=dict(cross), note=q.get("note"))
            if total != cross_total:
                failures.append(f"{qid}: graph has {total} specs, raw files have {cross_total}")
        elif kind == "midi_conflicts":
            conflicts, unrec = midi_conflicts(g)
            cross_conflicts, cross_unrec = cross_midi_conflicts()
            res = {"conflicts": conflicts, "unrecorded": unrec}
            cross = {"conflicts": cross_conflicts, "unrecorded": cross_unrec}
            lines = ([f"conflict at {nm(src)}: channel {ch} shared by {', '.join(nm(x) for x in v)}"
                      for src, dup in conflicts.items() for ch, v in dup.items()]
                     + [f"{nm(src)}: no midi_in_ch recorded for {', '.join(nm(x) for x in v)} (not recorded is not the same as no conflict)"
                        for src, v in unrec.items()]) or ["no fan-out point has 2+ downstream devices with a recorded channel yet"]
            record(qid, q["question"], res, lines, cross=cross, note=q.get("note"))
        elif kind == "unrecorded":
            res = unrecorded(g)
            cross = cross_unrecorded()
            lines = [f"{k}: {len(v)}" for k, v in res.items()]
            record(qid, q["question"], res, [f"{sum(len(v) for v in res.values())} items have no confirmed connection, placement or supply link"] + lines, cross=cross, note=q.get("note"))
        elif kind == "naming":
            res = naming(g)
            lines = [f"{len(res)} concepts are named differently by different manufacturers"]
            for term in q.get("show", []):
                if term in res:
                    lines.append(f"{term}: " + "; ".join(f"'{w}' ({', '.join(m)})" for w, m in res[term].items()))
            record(qid, q["question"], res, lines, cross=cross_naming(), note=q.get("note"))
        elif kind == "inherits":
            res, inherited = inherits(g, q["param"])
            lines = [f"{nm(it)}: {', '.join(v)}" for it, v in res.items()] + [f"counted through the hierarchy (narrower kinds): {', '.join(inherited)}"]
            record(qid, q["question"], res, lines, cross=cross_inherits(q["param"]), note=q.get("note"))
        elif kind == "undocumented":
            res = undocumented(g)
            lines = [f"{len(res)} UI actions have no user-guide section" + (": " + ", ".join(res) if res else "")]
            record(qid, q["question"], res, lines, expected=q.get("expected"), cross=cross_undocumented(), note=q.get("note"))
        elif kind == "doc_impact":
            secs, fns, acts = doc_impact(g, q["route_prefix"])
            lines = [f"review: {', '.join(secs)}", f"because these functions call {q['route_prefix']}: {', '.join(fns)}",
                     f"and these buttons are handled by them: {', '.join(acts) or 'none'}"]
            record(qid, q["question"], secs, lines, expected=q["expected"], note=q.get("note"))
        elif kind == "kb_reach":
            res = kb_reach(g)
            lines = [f"{d}: {n} knowledge-graph vertices" for d, n in res.items()]
            record(qid, q["question"], res, lines, cross=cross_kb_reach(), note=q.get("note"))
        elif kind == "concept_where":
            res = concept_where(g, q["concept"])
            lines = [f"{res['manuals']} manuals"] + [f"{a} docs: {', '.join(v)}" for a, v in res["doc_sections"].items()] + \
                    [f"code: {', '.join(res['code_files']) or 'none'}"]
            record(qid, q["question"], res, lines, cross=cross_concept_where(q["concept"]), note=q.get("note"))
        elif kind == "vocabulary":
            res = vocabulary(g, q["concept"])
            lines = [f"'{w}': {', '.join(m)}" for w, m in res["manufacturers"].items()] + \
                    [f"the apps say '{w}' ({', '.join(a)})" for w, a in res["apps"].items()]
            record(qid, q["question"], res, lines, cross=cross_vocabulary(q["concept"]), note=q.get("note"))
        elif kind == "term_gaps":
            res = term_gaps(g)
            lines = [f"{res['shared']} concepts are used by both the manuals and the apps",
                     f"used only by the apps: {', '.join(res['apps_only']) or 'none'}",
                     f"{res['manuals_only']} manual concepts are not mentioned by any app"]
            record(qid, q["question"], res, lines, cross=cross_term_gaps(), note=q.get("note"))
        else:
            failures.append(f"{qid}: unknown query kind {kind!r}")

    (PUB / "answers.json").write_text(json.dumps({"generated_by": "tools/query_graph.py", "graph_sha256": snapshot_digest(), "answers": answers},
                                                  indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    spark.stop()
    print(f"\n{len(answers)} questions, {len(failures)} failure(s)")
    for f in failures:
        print("FAIL  " + f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
