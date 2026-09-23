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
