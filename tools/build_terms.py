#!/usr/bin/env python3
"""Check the terminology (TERMS.yaml) and count where each term is used in the ingested manuals.

    .venv/bin/python tools/build_terms.py            # check + count, writes graph/public/terms.json
    .venv/bin/python tools/build_terms.py --check    # check only (no manuals needed; a fresh clone can run this)

TERMS.yaml is the source of truth; terms.json is a committed snapshot of it plus per-manual label COUNTS (numbers only,
never manual text), so the public site and the graph can use it without the copyrighted manuals.

Checks (exit 1 on any failure):
  taxonomy   every `broader` exists, no cycles, every concept reaches exactly one facet, labels are unique
             (after case, hyphen and plural folding), `close` never points up or down its own hierarchy
  ontology   every relation uses a declared predicate, and its subject and object fall in the predicate's
             domain and range facets
  grounding  every concept that is not a `grouping` occurs in at least one manual: a term nobody uses is invented
"""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TERMS, OUT = ROOT / "TERMS.yaml", ROOT / "graph" / "public" / "terms.json"


def fold(label):
    """Comparison key: case, hyphen/space and a trailing plural do not make two labels different."""
    k = re.sub(r"[\s-]+", " ", label.lower()).strip()
    return re.sub(r"(es|s)$", "", k) if len(k) > 3 else k


def is_short_acronym(label):
    """A two-letter capitals abbreviation (EG, CC, CV, TS, HP). An all-lowercase match of one ('eg' left over from a converted
    table cell) is far more often a fragment than the abbreviation, so it is not counted. 'Cc' and 'CC' are."""
    return bool(re.fullmatch(r"[A-Z]{2}", label))


def label_regex(label):
    words = [re.escape(w) for w in re.split(r"[\s-]+", label.strip())]
    body = r"[\s-]+".join(words) + r"(?:e?s)?"
    guard = r"(?![a-z]{2}(?![A-Za-z0-9]|e?s(?![A-Za-z0-9])))" if is_short_acronym(label) else ""
    return r"(?<![A-Za-z0-9])" + guard + f"(?i:{body})" + r"(?![A-Za-z0-9])"


def load():
    t = yaml.safe_load(TERMS.read_text(encoding="utf-8"))
    for c in t["concepts"]:
        c.setdefault("alt", [])
        c.setdefault("close", [])
        c["alt"] = [str(a) for a in c["alt"]]
        c["pref"] = str(c["pref"])
    return t


def labels_of(c):
    return [c["pref"]] + c["alt"]


def check(t, vocab_tags):
    """Taxonomy and ontology integrity. Returns (errors, facet_of) where facet_of maps every node id to its facet."""
    err = []
    facets = t["facets"]
    concepts = {}
    for c in t["concepts"]:
        if c["id"] in concepts or c["id"] in facets:
            err.append(f"duplicate id {c['id']}")
        concepts[c["id"]] = c
    nodes = set(concepts) | set(facets)

    for c in concepts.values():
        if not c.get("broader"):
            err.append(f"{c['id']}: no broader concept (every concept must sit under a facet)")
        for b in c.get("broader", []):
            if b not in nodes:
                err.append(f"{c['id']}: broader {b!r} does not exist")
        if c.get("tag") not in vocab_tags:
            err.append(f"{c['id']}: tag {c.get('tag')!r} is not in VOCAB.yaml")

    # ancestors, with cycle detection
    anc_cache = {}

    def ancestors(cid, path=()):
        if cid in path:
            err.append("cycle in broader: " + " -> ".join(path + (cid,)))
            return set()
        if cid in anc_cache:
            return anc_cache[cid]
        out = set()
        for b in concepts.get(cid, {}).get("broader", []):
            if b in nodes:
                out |= {b} | ancestors(b, path + (cid,))
        anc_cache[cid] = out
        return out

    facet_of = {f: f for f in facets}
    for cid in concepts:
        fs = ancestors(cid) & set(facets)
        if len(fs) != 1:
            err.append(f"{cid}: reaches {len(fs)} facets {sorted(fs)}; must reach exactly one")
        facet_of[cid] = next(iter(fs)) if len(fs) == 1 else None

    # labels: one concept per label, and a homograph is never also a concept label
    owner = {}
    for c in concepts.values():
        for lab in labels_of(c):
            k = fold(lab)
            if k in owner and owner[k] != c["id"]:
                err.append(f"label {lab!r} belongs to both {owner[k]} and {c['id']}; list it under homographs instead")
            owner[k] = c["id"]
    for h in t.get("homographs", []):
        if fold(h["label"]) in owner:
            err.append(f"homograph {h['label']!r} is also a label of {owner[fold(h['label'])]}")
        if len(h.get("senses", [])) < 2:
            err.append(f"homograph {h['label']!r} needs at least two senses")

    # close matches: must exist, and must not duplicate a hierarchical link (SKOS keeps the two disjoint)
    for c in concepts.values():
        for x in c["close"]:
            if x not in concepts:
                err.append(f"{c['id']}: close match {x!r} does not exist")
            elif x == c["id"] or x in ancestors(c["id"]) or c["id"] in ancestors(x):
                err.append(f"{c['id']}: close match {x!r} is already its broader/narrower; use one or the other")

    # relations: declared predicate, subject in domain, object in range
    seen = set()
    for r in t.get("relations", []):
        s, p, o = r
        pred = t["predicates"].get(p)
        if pred is None:
            err.append(f"relation {r}: predicate {p!r} is not declared")
            continue
        for end, which in ((s, "domain"), (o, "range")):
            if end not in nodes:
                err.append(f"relation {r}: {end!r} does not exist")
            elif facet_of.get(end) not in pred[which]:
                err.append(f"relation {r}: {end} is a {facet_of.get(end)}, outside the {which} of {p} {pred[which]}")
        if tuple(r) in seen:
            err.append(f"relation {r} is listed twice")
        seen.add(tuple(r))
    return err, facet_of


def section_text(manual_dir):
    parts = []
    for f in sorted(manual_dir.glob("[0-9]*.md")):
        parts.append(re.sub(r"\A---\n.*?\n---\n", "", f.read_text(encoding="utf-8"), flags=re.S))
    return "\n".join(parts)


def count(t, manuals):
    """Per manual, per label: whole-word matches, leftmost-longest, so overlapping labels are never double-counted.
    Case-insensitive except for all-capitals abbreviations. A stop phrase (a product feature's proper name, like the RD-9's
    'Wave Designer') is matched like a label so that its words are consumed, and its count is thrown away."""
    labels = ([(lab, c["id"]) for c in t["concepts"] for lab in labels_of(c)] + [(h["label"], None) for h in t.get("homographs", [])]
              + [(sp["phrase"], None) for sp in t.get("stop_phrases", [])])     # matched first when longer, then discarded
    labels.sort(key=lambda x: -len(x[0]))                         # longest first: the alternation tries them in order
    groups = {f"g{i}": lab for i, (lab, _) in enumerate(labels)}
    rx = re.compile("|".join(f"(?P<g{i}>{label_regex(lab)})" for i, (lab, _) in enumerate(labels)))
    counts, sizes = defaultdict(Counter), {}
    for m in manuals:
        d = ROOT / "docs" / "manuals" / m["id"]
        if not d.exists():
            continue
        text = section_text(d)
        sizes[m["id"]] = len(list(d.glob("[0-9]*.md")))
        for hit in rx.finditer(text):
            counts[hit.lastgroup and groups[hit.lastgroup]][m["id"]] += 1
    return counts, sizes


def main():
    only_check = "--check" in sys.argv
    t = load()
    vocab_tags = set(yaml.safe_load((ROOT / "VOCAB.yaml").read_text())["tags"])
    manuals = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    errors, facet_of = check(t, vocab_tags)
    digest = hashlib.sha256(TERMS.read_bytes()).hexdigest()
    have_manuals = any((ROOT / "docs" / "manuals" / m["id"]).exists() for m in manuals)

    if only_check or not have_manuals:
        if not have_manuals and not only_check:
            print("note: docs/manuals/ not present (local-only); checked TERMS.yaml but did not recount")
        if OUT.exists() and json.loads(OUT.read_text())["terms_sha256"] != digest:
            print("note: graph/public/terms.json is stale for this TERMS.yaml; recount on a machine with the manuals")
        for e in errors:
            print("FAIL  " + e)
        print(f"{len(t['concepts'])} concepts, {len(t.get('relations', []))} relations: {len(errors)} error(s)")
        sys.exit(1 if errors else 0)

    counts, sizes = count(t, manuals)
    for c in t["concepts"]:
        used = sum(sum(counts[lab].values()) for lab in labels_of(c))
        if not c.get("grouping") and used == 0:
            errors.append(f"{c['id']}: no label ({', '.join(labels_of(c))}) occurs in any manual; remove it or mark it grouping")
    for e in errors:
        print("FAIL  " + e)
    if errors:
        print(f"{len(errors)} error(s); graph/public/terms.json not written")
        sys.exit(1)

    mfr = {m["id"]: m["manufacturer"] for m in manuals if m["id"] in sizes}
    out = {
        "generated_by": "tools/build_terms.py",
        "terms_sha256": digest,
        "corpus": {"manuals": len(sizes), "sections": sum(sizes.values()),
                   "manufacturers": len(set(mfr.values())), "manual_manufacturer": dict(sorted(mfr.items()))},
        "facets": [{"id": f, "pref": v["pref"], "note": v["note"]} for f, v in t["facets"].items()],
        "predicates": [{"id": p, **v} for p, v in t["predicates"].items()],
        "concepts": [{
            "id": c["id"], "pref": c["pref"], "alt": c["alt"], "broader": c["broader"], "close": c["close"],
            "facet": facet_of[c["id"]], "tag": c["tag"], "grouping": bool(c.get("grouping")), **({"note": " ".join(c["note"].split())} if c.get("note") else {}),
            "labels": {lab: dict(sorted(counts[lab].items())) for lab in labels_of(c)}} for c in t["concepts"]],
        "relations": [{"s": s, "p": p, "o": o} for s, p, o in t.get("relations", [])],
        "homographs": [{"label": h["label"], "senses": h["senses"], "counts": dict(sorted(counts[h["label"]].items()))} for h in t.get("homographs", [])],
        "stop_phrases": [{"phrase": sp["phrase"], "reason": sp["reason"], "masked": sum(counts[sp["phrase"]].values())} for sp in t.get("stop_phrases", [])],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    attested = sum(1 for c in out["concepts"] if any(c["labels"].values()))
    by_facet = Counter(c["facet"] for c in out["concepts"])
    variants = [c for c in out["concepts"] if sum(1 for v in c["labels"].values() if v) > 1]
    print(f"{len(out['concepts'])} concepts in {len(by_facet)} facets ({', '.join(f'{f} {n}' for f, n in by_facet.items())})")
    print(f"{attested} attested in {len(sizes)} manuals ({sum(sizes.values())} sections); {len(variants)} concepts use more than one label; "
          f"{len(out['relations'])} typed relations; {len(out['homographs'])} homographs")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
