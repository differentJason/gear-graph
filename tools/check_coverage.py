#!/usr/bin/env python3
"""Conversion completeness check: how much of each PDF's text survived into the markdown?

    .venv/bin/python tools/check_coverage.py

Compares word tokens (>=4 letters) from `pdftotext` over the manual's page range against the
converted section bodies. Recall below 95% is flagged. Missing words are listed so you can see
whether they are real losses or expected removals (running headers, page numbers, figure labels).
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"[a-z]{4,}")


def body(path):
    t = path.read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", t, flags=re.S)


def main():
    manifest = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    failed = False
    for m in manifest:
        pdf, out = ROOT / m["pdf"], ROOT / "docs" / "manuals" / m["id"]
        if not pdf.exists() or not out.exists():
            print(f"{m['id']}: skipped (no PDF or no conversion)")
            continue
        if m.get("coverage_skip"):
            print(f"{m['id']}: coverage not measured ({m['coverage_skip']})")
            continue
        if m.get("page_spec"):                              # chosen/cropped pages: read them with pymupdf
            import pymupdf
            d = pymupdf.open(pdf)
            src = "\n".join(d[sp["page"] - 1].get_text(clip=pymupdf.Rect(*sp["clip"]) if sp.get("clip") else None)
                            for sp in m["page_spec"]).lower()
        else:
            lo, hi = m["pages"]
            src = subprocess.run(["pdftotext", "-f", str(lo), "-l", str(hi), str(pdf), "-"],
                                 capture_output=True, text=True).stdout.lower()
        dst = "\n".join(body(f) for f in sorted(out.glob("[0-9]*.md"))).lower()
        a, b = Counter(TOKEN.findall(src)), Counter(TOKEN.findall(dst))
        uniq = sum(1 for t in a if t in b) / max(len(a), 1)
        occ = sum(min(n, b[t]) for t, n in a.items()) / max(sum(a.values()), 1)
        missing = sorted(((a[t] - b[t], t) for t in a if b[t] < a[t]), reverse=True)[:12]
        flag = "" if min(uniq, occ) >= 0.95 else "   <-- BELOW 95%"
        failed |= bool(flag)
        print(f"{m['id']}: unique-word recall {uniq:.1%}, occurrence recall {occ:.1%}{flag}")
        print("   most-missing:", ", ".join(f"{t}(-{n})" for n, t in missing))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
