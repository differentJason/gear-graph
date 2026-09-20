#!/usr/bin/env python3
"""Fetch each Eurorack module's spec pages and record extracted numbers WITH their raw source lines.

    .venv/bin/python tools/fetch_specs.py [module-id ...]

Reads eurorack/sources.yaml, writes eurorack/evidence/<id>.json. Nothing is interpreted as final here:
this only extracts candidate values per source and reports where sources agree or disagree.
"""
import html
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["hp", "depth_mm", "ma_p12", "ma_m12", "ma_p5"]
H = r"[ \t]*"          # horizontal whitespace only: patterns must never cross a line break

# Signs are required for the rails, so "+12V" and "-12V" cannot be confused.
PATTERNS = {
    "hp": [rf"(?:width|size){H}[:\-]?{H}(\d{{1,3}}){H}hp\b", rf"^{H}(\d{{1,3}}){H}hp{H}$", rf"\((\d{{1,3}}){H}hp\)", rf"\b(\d{{1,3}}){H}hp\b",
           rf"\b(\d{{1,3}}){H}hp{H}x{H}3u"],                            # datasheet panel size: "(8HPX3U)"
    "depth_mm": [rf"depth{H}[:=\-]?{H}(\d{{1,3}}){H}mm", rf"\b(\d{{1,3}}){H}mm{H}deep", rf"depth{H}of{H}module{H}(\d{{1,3}}){H}mm"],
    "ma_p12": [rf"(\d{{1,4}}){H}ma{H}(?:@|at)?{H}\+{H}12{H}v", rf"\+{H}12{H}v{H}[:=\-]{H}(\d{{1,4}}){H}(?:ma)?\b",
               rf"power{H}[:\-]?{H}\+(\d{{1,4}}){H}ma{H}/",
               rf"(?<![-+\d])12{H}v{H}[:=]{H}(\d{{1,4}}){H}ma",
               rf"^{H}\+{H}12{H}v{H}(\d{{1,4}}){H}$"],                 # datasheet table row: "+12V   90"       # unsigned "12V: 80mA" (After Later pages drop the +)
    "ma_m12": [rf"(\d{{1,4}}){H}ma{H}(?:@|at)?{H}-{H}12{H}v", rf"-{H}12{H}v{H}[:=\-]{H}(\d{{1,4}}){H}(?:ma)?\b",
               rf"power{H}[:\-]?{H}\+\d{{1,4}}{H}ma{H}/{H}-(\d{{1,4}}){H}ma",
               rf"^{H}-{H}12{H}v{H}(\d{{1,4}}){H}$"],
    "ma_p5": [rf"(\d{{1,4}}){H}ma{H}(?:@|at)?{H}\+?{H}5{H}v\b", rf"\+?{H}5{H}v{H}[:=\-]{H}(\d{{1,4}}){H}(?:ma)?\b",
              rf"^{H}\+?{H}5{H}v{H}(\d{{1,4}}){H}$"],
}


def fetch(url):
    r = subprocess.run(["curl", "-sL", "-m", "30", "-A", "Mozilla/5.0 (X11; Linux x86_64) gear-kb/0.1", "-w", "\n@@%{http_code}", url],
                       capture_output=True)                          # bytes: some pages are not UTF-8
    raw = r.stdout
    head, _, code = raw.rpartition(b"\n@@")
    if head[:4] == b"%PDF":                                          # datasheets: convert to text with pdftotext
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
            tf.write(head); tf.flush()
            return code.decode().strip(), subprocess.run(["pdftotext", "-layout", tf.name, "-"], capture_output=True).stdout.decode("utf-8", errors="replace")
    return code.decode().strip(), head.decode("utf-8", errors="replace")


def to_text(body):
    body = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", body)
    body = re.sub(r"(?s)<[^>]+>", "\n", body)
    body = html.unescape(body)
    body = re.sub("[−–—]", "-", body)                       # unicode minus/dashes -> "-"
    body = re.sub("[ \t ]+", " ", body)
    body = re.sub(r"(?<=\d),(?=\d{3}\b)", "", body)                        # 1,000 -> 1000
    # label on one line and value on the next ("+12V" / "130mA") -> one line
    body = re.sub(r"(?im)^[ \t]*([+\-]?[ \t]*(?:12|5)[ \t]*v)[ \t]*:?[ \t]*\n[ \t]*(\d{1,4}[ \t]*ma)\b", r"\1: \2", body)
    return body


def extract(text):
    out, lines, low = {}, text.split("\n"), text.lower()
    for field, pats in PATTERNS.items():
        for pat in pats:
            m = re.search(pat, low, re.I | re.M)
            if m:
                out[field] = int(m.group(1))
                out[field + "_line"] = " ".join(lines[low.count("\n", 0, m.start())].split())[:160]   # raw line it came from
                break
    return out


def main():
    cfg = yaml.safe_load((ROOT / "eurorack" / "sources.yaml").read_text())["modules"]
    (ROOT / "eurorack" / "evidence").mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[1:])
    for mid, spec in cfg.items():
        if wanted and mid not in wanted:
            continue
        rec = {"id": mid, "fetched": str(date.today()), "match_note": spec.get("match_note"), "sources": []}
        for src in spec["sources"]:
            code, body = fetch(src["url"])
            ex = extract(to_text(body)) if code == "200" else {}
            rec["sources"].append({"tier": src["tier"], "url": src["url"], "http": code, "values": ex})
            time.sleep(1.0)
        agree = {}
        for f in FIELDS:
            vals = [(s["tier"], s["values"][f]) for s in rec["sources"] if f in s["values"]]
            distinct = {v for _, v in vals}
            agree[f] = ("none" if not vals else "single" if len(vals) == 1 else "agree" if len(distinct) == 1 else "DISAGREE", vals)
        rec["agreement"] = {f: {"status": s, "values": v} for f, (s, v) in agree.items()}
        (ROOT / "eurorack" / "evidence" / f"{mid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        row = " ".join(f"{f}={'/'.join(str(v) for _, v in agree[f][1]) or '-':>9}[{agree[f][0][:2]}]" for f in FIELDS)
        print(f"{mid:42s} http={','.join(s['http'] for s in rec['sources']):12s} {row}")


if __name__ == "__main__":
    main()
