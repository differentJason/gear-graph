#!/usr/bin/env python3
"""Check connections.yaml against inventory.yaml and the Eurorack spec pages. Exit code 1 on any ERROR.

    .venv/bin/python tools/validate_connections.py

Errors : unknown ids/setups/media/statuses, a confirmed link with no date, a module placed twice or not at all, a placement
         whose supply is not its case's supply, a case row that is over capacity.
Warnings: unconfirmed links (they are excluded from conclusions), missing HP figures, unused modules that are placed.
Ports  : when the converted manuals are present (local only), each named port is looked up in that device's manual text. A port that is
         not found is a WARNING (the manual may word it differently); devices with no ingested manual are reported as unchecked.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MEDIA = {"audio", "midi", "usb", "clock", "cv", "gate", "power"}
STATUSES = {"confirmed", "unconfirmed"}


def norm(s):
    """Lower-case, straighten quotes, collapse whitespace, so 'MAIN OUT L/R' matches however the manual wraps it."""
    return " ".join(s.lower().replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'").split())


def spec_hp():
    """{module_id: (hp, format)} from the generated Eurorack pages (committed; see docs/eurorack/)."""
    out = {}
    for f in (ROOT / "docs" / "eurorack").glob("*.md"):
        m = re.match(r"---\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
        fm = yaml.safe_load(m.group(1)) if m else {}
        if fm.get("doc_type") == "eurorack-module":
            out[fm["module"]] = (fm.get("specs", {}).get("hp"), fm.get("format", "3U"))
    return out


def main():
    inv = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    c = yaml.safe_load((ROOT / "connections.yaml").read_text())
    hp = spec_hp()
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    setups = {s["id"] for s in c.get("setups", [])}
    for s in c.get("setups", []):
        if s.get("interface") not in inv:
            err(f"setup {s['id']}: interface {s.get('interface')!r} is not in inventory.yaml")

    # ---- links ----
    for n, l in enumerate(c.get("links", []), 1):
        tag = f"link {n} ({l.get('from')} -> {l.get('to')})"
        for k in ("from", "to"):
            if l.get(k) not in inv:
                err(f"{tag}: {k} {l.get(k)!r} is not in inventory.yaml")
        if l.get("setup") not in setups:
            err(f"{tag}: unknown setup {l.get('setup')!r}")
        if l.get("medium") not in MEDIA:
            err(f"{tag}: medium {l.get('medium')!r} not one of {sorted(MEDIA)}")
        if l.get("status") not in STATUSES:
            err(f"{tag}: status {l.get('status')!r} not one of {sorted(STATUSES)}")
        if l.get("status") == "confirmed" and not l.get("confirmed"):
            err(f"{tag}: confirmed link has no `confirmed:` date")
        if l.get("status") == "unconfirmed":
            warn(f"{tag}: unconfirmed, so it is excluded from conclusions")

    # ---- cases and placements ----
    cases = {k["id"]: k for k in c.get("cases", [])}
    for cid, k in cases.items():
        for ref in [cid, k.get("supply"), *k.get("mounted", [])]:
            if ref not in inv:
                err(f"case {cid}: {ref!r} is not in inventory.yaml")
        if k.get("setup") not in setups:
            err(f"case {cid}: unknown setup {k.get('setup')!r}")

    placed = defaultdict(list)                      # (setup, module) -> [case]
    load = defaultdict(int)                         # (setup, case, format) -> HP used
    for n, p in enumerate(c.get("placements", []), 1):
        tag = f"placement {n} ({p.get('module')})"
        for k in ("module", "case", "powered_by"):
            if p.get(k) not in inv:
                err(f"{tag}: {k} {p.get(k)!r} is not in inventory.yaml")
        case = cases.get(p.get("case"))
        if case is None:
            err(f"{tag}: case {p.get('case')!r} has no entry under `cases`")
            continue
        if p.get("powered_by") != case.get("supply"):
            err(f"{tag}: powered_by {p.get('powered_by')!r} but case {p['case']} is fed by {case.get('supply')!r}")
        if p.get("status") not in STATUSES:
            err(f"{tag}: status {p.get('status')!r} not one of {sorted(STATUSES)}")
        placed[(p.get("setup"), p["module"])].append(p["case"])
        if inv.get(p["module"], {}).get("in_use") is False:
            warn(f"{tag}: marked unused in inventory.yaml but is placed")
        h, fmt = hp.get(p["module"], (None, "3U"))
        h = h if h is not None else (inv[p["module"]].get("hp") if p["module"] in inv else None)
        if h is None:
            warn(f"{tag}: no HP figure, so it is not counted against the case")
            continue
        load[(p.get("setup"), p["case"], p.get("row", fmt))] += h

    for (setup, mod), where in placed.items():
        if len(where) > 1:
            err(f"module {mod} is placed {len(where)} times in setup {setup}: {where}")
    for cid, k in cases.items():
        for m in k.get("mounted", []):
            if (k["setup"], m) not in placed:
                err(f"case {cid}: mounted item {m} has no placement")
        cap = Counter()
        for row in k.get("rows", []):
            cap[row["format"]] += row["hp"]
        for (setup, case, fmt), used in sorted(load.items()):
            if case == cid and used > cap.get(fmt, 0):
                err(f"case {cid}: {fmt} rows hold {cap.get(fmt, 0)} HP but {used} HP is placed in them")

    # every in-use Eurorack module with a spec page must be placed in each setup that has cases
    for setup in {k["setup"] for k in cases.values()}:
        for mid, i in inv.items():
            if i["category"] == "eurorack-module" and mid in hp and i.get("in_use", True) is not False and (setup, mid) not in placed:
                err(f"module {mid} is in use but not placed in setup {setup}")

    checked = found = unchecked = 0
    manuals = ROOT / "docs" / "manuals"
    if manuals.exists():
        by_device = defaultdict(list)
        for m in yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]:
            by_device[m["device"]].append(m["id"])

        def text(device):
            return norm(" ".join(f.read_text(encoding="utf-8") for mid in by_device[device] for f in (manuals / mid).glob("*.md")))

        cache = {}
        for l in c.get("links", []):
            if l.get("status") != "confirmed":
                continue
            for dev, port in ((l["from"], l.get("from_port")), (l["to"], l.get("to_port"))):
                if not port:
                    continue
                if dev not in by_device:
                    unchecked += 1
                    continue
                cache.setdefault(dev, text(dev))
                checked += 1
                if norm(port) in cache[dev]:
                    found += 1
                else:
                    warn(f"port {port!r} on {dev} was not found in its manual text")
    for w in warnings:
        print("WARNING", w)
    for e in errors:
        print("ERROR  ", e)
    for (setup, case, fmt), used in sorted(load.items()):
        cap = sum(r["hp"] for r in cases[case]["rows"] if r["format"] == fmt)
        print(f"  {case} [{fmt}]: {used}/{cap} HP")
    if manuals.exists():
        print(f"  ports: {found} of {checked} found in the device manuals; {unchecked} on devices with no ingested manual (not checked)")
    else:
        print("  ports: not checked (docs/manuals/ is local-only and not present)")
    print(f"checked {len(c.get('links', []))} links, {len(c.get('placements', []))} placements, {len(cases)} cases: "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
