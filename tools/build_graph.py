#!/usr/bin/env python3
"""Build the knowledge graph (PySpark + GraphFrames) from the repository's source files.

    .venv-graph/bin/python tools/build_graph.py

Inputs : inventory.yaml, connections.yaml, eurorack/{evidence,overrides.yaml}, tools/manifest.yaml, VOCAB.yaml,
         evals/golden.jsonl, and (local only) the converted manual sections in docs/manuals/.
Outputs: graph/out/{vertices,edges}.parquet   full graph, includes manual-derived nodes  (git-ignored)
         graph/public/{vertices,edges}.json   public subgraph, a committed snapshot       (no manual-derived nodes)
         graph/public/budget.json             per-supply power load, computed FROM the graph; read by build_eurorack.py

The graph is derived and rebuildable; nothing here is a source of truth. Schema and rules: graph/README.md.
Exit code 1 if any integrity or privacy check fails.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "graph")]

import build_eurorack as be                          # noqa: E402  (resolve() and the digest live with the Eurorack code)
from check_env import spark_session                  # noqa: E402
from graphframes import GraphFrame                   # noqa: E402
from pyspark.sql import functions as F               # noqa: E402
from pyspark.sql.types import (BooleanType, DoubleType, IntegerType, StringType, StructField, StructType)  # noqa: E402

OUT, PUB = ROOT / "graph" / "out", ROOT / "graph" / "public"
RAIL = {"ma_p12": "+12V", "ma_m12": "-12V", "ma_p5": "+5V"}
# The full word list is deliberately NOT in this file: in a public repository it would itself be a hint. It lives in the
# git-ignored private/leak-patterns.txt (one regex per line). Only generic patterns are built in.
GENERIC_LEAK = r"/hom[e]/|~[/]|@gmail\.com"      # bracketed so this line does not match the scan it configures


def leak_pattern():
    parts, f = [GENERIC_LEAK], ROOT / "private" / "leak-patterns.txt"
    if f.exists():
        parts += [l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]
    else:
        print("note: private/leak-patterns.txt not found; only the generic leak checks ran")
    return re.compile("|".join(parts), re.I)


VSCHEMA = StructType([StructField(n, t, True) for n, t in [
    ("id", StringType()), ("type", StringType()), ("name", StringType()), ("visibility", StringType()),
    ("category", StringType()), ("manufacturer", StringType()), ("status", StringType()), ("in_use", BooleanType()),
    ("format", StringType()), ("role", StringType()), ("field", StringType()), ("value", DoubleType()),
    ("tier", StringType()), ("url", StringType()), ("http", StringType()), ("doc_type", StringType()), ("version", StringType()),
    ("attested", StringType())]])
ESCHEMA = StructType([StructField(n, t, True) for n, t in [
    ("src", StringType()), ("dst", StringType()), ("rel", StringType()), ("visibility", StringType()),
    ("setup", StringType()), ("medium", StringType()), ("from_port", StringType()), ("to_port", StringType()),
    ("status", StringType()), ("confirmed", StringType()), ("value", DoubleType()), ("line", StringType()),
    ("swappable", BooleanType()), ("bidirectional", BooleanType()), ("position", IntegerType()), ("row", StringType()),
    ("http", StringType()), ("note", StringType())]])


class Builder:
    """Collects vertices and edges as dicts; visibility of an edge is derived from its endpoints, never set by hand."""

    def __init__(self):
        self.V, self.E, self.notes = {}, [], []

    def vertex(self, vid, vtype, name, visibility="public", **props):
        if vid in self.V:
            raise SystemExit(f"duplicate vertex id {vid}")
        self.V[vid] = {"id": vid, "type": vtype, "name": name, "visibility": visibility, **props}

    def edge(self, src, dst, rel, **props):
        self.E.append({"src": src, "dst": dst, "rel": rel, **props})

    def ensure(self, vid, vtype, name):
        if vid not in self.V:
            self.vertex(vid, vtype, name)

    def finish(self):
        for e in self.E:
            private = any(self.V[e[k]]["visibility"] == "private" for k in ("src", "dst") if e[k] in self.V)
            e["visibility"] = "private" if private else "public"


def frontmatter(path):
    m = re.match(r"---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def collect():
    """Read every source file and return a populated Builder."""
    inv = yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]
    conn = yaml.safe_load((ROOT / "connections.yaml").read_text())
    ov = yaml.safe_load((ROOT / "eurorack" / "overrides.yaml").read_text()) or {}
    att = yaml.safe_load((ROOT / "eurorack" / "attestations.yaml").read_text()) or []
    man = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    vocab = yaml.safe_load((ROOT / "VOCAB.yaml").read_text())["tags"]
    b = Builder()

    # ---- items, manufacturers, categories ----
    for i in inv:
        b.vertex(f"item:{i['id']}", "item", i["name"], category=i["category"], manufacturer=i.get("manufacturer"), status=i["status"],
                 in_use=i.get("in_use", True), format=i.get("format"), role=ov.get(i["id"], {}).get("role"))
        b.ensure(f"cat:{i['category']}", "category", i["category"])
        b.edge(f"item:{i['id']}", f"cat:{i['category']}", "IN_CATEGORY")
        if i.get("manufacturer"):
            b.ensure(f"mfr:{i['manufacturer']}", "manufacturer", i["manufacturer"])
            b.edge(f"item:{i['id']}", f"mfr:{i['manufacturer']}", "MADE_BY")

    # ---- Eurorack specs and the sources they came from ----
    for i in inv:
        ev = ROOT / "eurorack" / "evidence" / f"{i['id']}.json"
        if not i["category"].startswith("eurorack") or not ev.exists():
            continue
        rec, o = json.loads(ev.read_text()), ov.get(i["id"], {})
        for s in rec["sources"]:
            sid = f"src:{s['url']}"
            b.ensure(sid, "source", f"{s['tier']}: {urlparse(s['url']).netloc}")
            b.V[sid].update(tier=s["tier"], url=s["url"])
            b.edge(f"item:{i['id']}", sid, "CONSULTED", http=str(s["http"]))
        for field, label in be.FIELDS:
            r = be.resolve(field, rec["sources"], o)
            spid = f"spec:{i['id']}.{field}"
            role = o.get("role", "module")
            attested = next((a["id"] for a in att if field in a["fields"] and r["status"] in a["statuses"] and role in a["roles"]), None)
            b.vertex(spid, "spec", f"{i['name']} {label}", field=field, value=r["value"], status=r["status"], attested=attested)
            b.edge(f"item:{i['id']}", spid, "HAS_SPEC")
            for tier, url, value, line in r["seen"]:
                b.edge(spid, f"src:{url}", "SOURCED_FROM", value=value, line=line)

    # ---- manuals, tags, sections (sections are derived from copyrighted text: private) ----
    for t in vocab:
        b.vertex(f"tag:{t}", "tag", t)
    have = {i["id"] for i in inv}
    for m in man:
        if m["device"] not in have:
            b.notes.append(f"manual {m['id']}: device {m['device']} is not in the inventory; skipped")
            continue
        b.vertex(f"manual:{m['id']}", "manual", m["title"], doc_type=m["doc_type"], version=str(m.get("doc_version", "")))
        b.edge(f"item:{m['device']}", f"manual:{m['id']}", "HAS_MANUAL")
        for f in sorted((ROOT / "docs" / "manuals" / m["id"]).glob("[0-9]*.md")):
            fm = frontmatter(f)
            sid = f"section:{m['id']}/{f.name}"
            b.vertex(sid, "section", fm.get("title", f.stem), visibility="private")
            b.edge(f"manual:{m['id']}", sid, "HAS_SECTION")
            for t in fm.get("tags", []):
                b.edge(sid, f"tag:{t}", "TAGGED")
    if not any(v["type"] == "section" for v in b.V.values()):
        b.notes.append("docs/manuals/ not present: no section nodes (they are local-only); the public snapshot is unaffected")

    # ---- evaluation questions ----
    for line in (ROOT / "evals" / "golden.jsonl").read_text().splitlines():
        q = json.loads(line)
        b.vertex(f"q:{q['id']}", "question", q["question"])
        for page in q.get("expected_pages", []):
            if f"section:{page}" in b.V:
                b.edge(f"q:{q['id']}", f"section:{page}", "EXPECTS")

    # ---- routing and placement (connections.yaml) ----
    for l in conn.get("links", []):
        b.edge(f"item:{l['from']}", f"item:{l['to']}", "CONNECTS", setup=l["setup"], medium=l["medium"], from_port=l.get("from_port"),
               to_port=l.get("to_port"), status=l["status"], confirmed=str(l["confirmed"]) if l.get("confirmed") else None,
               swappable=l.get("swappable"), bidirectional=l.get("bidirectional"), note=l.get("note"))
    for p in conn.get("placements", []):
        common = dict(setup=p["setup"], status=p["status"], position=p.get("position"), row=p.get("row"))
        b.edge(f"item:{p['module']}", f"item:{p['case']}", "INSTALLED_IN", **common)
        if p["powered_by"] != p["module"]:               # a supply does not power itself
            b.edge(f"item:{p['module']}", f"item:{p['powered_by']}", "POWERED_BY", **common)
    b.finish()
    return b


def _coerce(x, dtype):
    """Spark's DoubleType rejects a Python int, and the spec values are ints; convert by declared column type."""
    if x is None:
        return None
    return float(x) if isinstance(dtype, DoubleType) else int(x) if isinstance(dtype, IntegerType) else x


def to_frames(spark, b):
    vt = [tuple(_coerce(v.get(f.name), f.dataType) for f in VSCHEMA) for v in b.V.values()]
    et = [tuple(_coerce(e.get(f.name), f.dataType) for f in ESCHEMA) for e in b.E]
    return spark.createDataFrame(vt, VSCHEMA), spark.createDataFrame(et, ESCHEMA)


def check(spark, v, e, pub_v, pub_e):
    """Integrity and privacy gates. Returns a list of failure messages."""
    bad = []
    if v.count() != v.select("id").distinct().count():
        bad.append("duplicate vertex ids")
    for name, df, vs in (("edge", e, v), ("public edge", pub_e, pub_v)):
        dangling = (df.join(vs.select(F.col("id").alias("s")), df.src == F.col("s"), "left_anti")
                    .union(df.join(vs.select(F.col("id").alias("d")), df.dst == F.col("d"), "left_anti")))
        if dangling.count():
            bad.append(f"{name}s with a missing endpoint: {dangling.select('src', 'dst', 'rel').collect()[:3]}")
    if pub_v.filter("type = 'section' OR visibility != 'public'").count():
        bad.append("public vertices contain a private node")
    if pub_e.filter("visibility != 'public'").count():
        bad.append("public edges contain a private edge")
    return bad


def power_budget(g, b):
    """Per-supply load, computed with graph motifs: (module)-[POWERED_BY]->(supply) joined to (module)-[HAS_SPEC]->(spec)."""
    fields = list(RAIL)
    load = (g.find("(m)-[p]->(s); (m)-[h]->(sp)")
            .filter("p.rel = 'POWERED_BY' AND p.status = 'confirmed' AND h.rel = 'HAS_SPEC' AND m.in_use = true")
            .filter(F.col("sp.field").isin(fields))
            .select(F.col("s.id").alias("supply"), F.col("p.setup").alias("setup"), F.col("sp.field").alias("field"),
                    F.col("m.id").alias("module"), F.col("m.name").alias("module_name"), F.col("sp.value").alias("value"), F.col("sp.status").alias("status"), F.col("sp.attested").alias("attested"))
            .collect())
    caps = (g.find("(s)-[h]->(sp)").filter("h.rel = 'HAS_SPEC' AND s.role = 'supply'").filter(F.col("sp.field").isin(fields))
            .select(F.col("s.id").alias("supply"), F.col("sp.field").alias("field"), F.col("sp.value").alias("value")).collect())
    capacity = {(r["supply"], r["field"]): r["value"] for r in caps}
    grouped = defaultdict(list)
    for r in load:
        grouped[(r["setup"], r["supply"])].append(r)
    setups = defaultdict(list)
    for (setup, supply), rows in sorted(grouped.items()):
        vert = b.V[supply]
        rails = {}
        for field, label in RAIL.items():
            rr = [r for r in rows if r["field"] == field]
            cap = capacity.get((supply, field))
            draw = sum(r["value"] for r in rr if r["value"] is not None)
            rails[label] = {"capacity_ma": int(cap) if cap is not None else None, "draw_ma": int(draw),
                            "pct": round(100 * draw / cap) if cap else None, "modules_counted": len(rr),
                            "modules_without_figure": sorted(r["module_name"] for r in rr if r["value"] is None),
                            "figure_status": dict(sorted(Counter(r["status"] for r in rr if r["value"] is not None).items())),
                            "owner_attested": sum(1 for r in rr if r["value"] is not None and r["attested"])}
        setups[setup].append({"id": supply.split(":", 1)[1], "name": vert["name"],
                              "kind": "peak" if vert["category"] == "eurorack-case" else "rated",
                              "modules": sorted({r["module"].split(":", 1)[1] for r in rows}), "rails": rails})
    return {"generated_by": "tools/build_graph.py", "inputs_sha256": be.inputs_digest(),
            "setups": {k: {"supplies": sorted(v, key=lambda s: s["name"])} for k, v in setups.items()}}


def dump_json(df, path, order):
    rows = []
    for r in df.orderBy(*order).collect():
        d = {k: x for k, x in r.asDict().items() if x is not None}          # omit nulls, like the sparse schema intends
        rows.append({k: (int(x) if isinstance(x, float) and x.is_integer() else x) for k, x in d.items()})
    path.write_text(json.dumps(rows, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(rows)


def main():
    b = collect()
    spark = spark_session("gear-graph-build")
    v, e = to_frames(spark, b)
    pub_v, pub_e = v.filter("visibility = 'public'"), e.filter("visibility = 'public'")
    failures = check(spark, v, e, pub_v, pub_e)
    if failures:
        print("\n".join("FAIL  " + f for f in failures))
        sys.exit(1)

    g = GraphFrame(v, e)
    budget = power_budget(g, b)

    OUT.mkdir(parents=True, exist_ok=True)
    PUB.mkdir(parents=True, exist_ok=True)
    v.write.mode("overwrite").parquet(str(OUT / "vertices.parquet"))
    e.write.mode("overwrite").parquet(str(OUT / "edges.parquet"))
    nv = dump_json(pub_v, PUB / "vertices.json", ["id"])
    ne = dump_json(pub_e, PUB / "edges.json", ["src", "rel", "dst", "from_port", "to_port"])
    (PUB / "budget.json").write_text(json.dumps(budget, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    pattern = leak_pattern()
    leaks = [(p.name, m.group(0)) for p in PUB.glob("*.json") for m in pattern.finditer(p.read_text(encoding="utf-8"))]
    if leaks:
        print("FAIL  leak scan over graph/public/:", leaks[:5])
        sys.exit(1)

    types = Counter(x["type"] for x in b.V.values())
    print(f"graph: {v.count()} vertices, {e.count()} edges  ({', '.join(f'{n} {t}' for t, n in sorted(types.items()))})")
    print(f"public snapshot: {nv} vertices, {ne} edges; leak scan clean; budget for {len(budget['setups'])} setup(s)")
    for note in b.notes:
        print("note:", note)
    spark.stop()


if __name__ == "__main__":
    main()
