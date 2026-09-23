#!/usr/bin/env python3
"""Lint the knowledge base. Exit code 1 on any ERROR; WARNINGs do not fail.

    .venv/bin/python tools/validate.py
"""
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
# datasheet = a maker's spec sheet; product-page = a maker's web page printed to PDF (no manual exists);
# original-design-manual = the manual of the design a clone/redesign copies (e.g. Mutable Instruments for After Later)
SECTION_TYPES = {"user-manual", "quick-start", "datasheet", "product-page", "original-design-manual"}
SECTION_REQUIRED = ["title", "doc_id", "device", "manufacturer", "model", "doc_type", "doc_version",
                    "language", "applies_to", "source_url", "retrieved", "source_sha256", "content_status"]
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
errors, warnings = [], []


def err(f, msg): errors.append(f"ERROR   {f.relative_to(ROOT)}: {msg}")
def warn(f, msg): warnings.append(f"WARNING {f.relative_to(ROOT)}: {msg}")


def main():
    vocab = set(yaml.safe_load((ROOT / "VOCAB.yaml").read_text())["tags"])
    inv = yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]
    slice_ids = {i["id"] for i in inv if i.get("slice")}
    manifest = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]
    manual_ids = {m["id"] for m in manifest}
    titles = {}

    for f in sorted(DOCS.rglob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
        if not m:
            err(f, "missing YAML frontmatter"); continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            err(f, f"frontmatter is not valid YAML: {e}"); continue
        body = m.group(2)

        if fm.get("doc_type") in SECTION_TYPES:
            for k in SECTION_REQUIRED:
                if not fm.get(k):
                    err(f, f"missing required field {k!r}")
            for t in fm.get("tags", []):
                if t not in vocab:
                    err(f, f"tag {t!r} is not in VOCAB.yaml")
            if not fm.get("description"):
                warn(f, "empty description (agents use it to decide whether to open the page)")
            if fm.get("doc_id") not in manual_ids:
                err(f, f"doc_id {fm.get('doc_id')!r} not in tools/manifest.yaml")
            if fm.get("device") not in slice_ids:
                err(f, f"device {fm.get('device')!r} is not a slice device in inventory.yaml")
            if len(body.strip()) < 60:
                warn(f, f"very short section ({len(body.strip())} chars)")
            if len(body) > 30000:
                warn(f, f"very long section ({len(body)} chars): consider splitting")
            key = (fm.get("doc_id"), fm.get("title"))
            if key in titles:
                warn(f, f"duplicate title within manual (also {titles[key].name})")
            titles[key] = f

        if fm.get("doc_type") == "eurorack-module":
            for k in ("title", "module", "specs", "spec_status"):
                if not fm.get(k):
                    err(f, f"missing required field {k!r}")

        if fm.get("doc_type") == "device":
            for mid in fm.get("manuals", []):
                if mid not in manual_ids:
                    err(f, f"manual {mid!r} not in manifest")

        for target in LINK_RE.findall(body):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = (f.parent / target.split("#")[0]).resolve()
            if not path.exists():
                err(f, f"broken relative link: {target}")

    for mm in manifest:                                    # provenance: PDF still matches recorded hash
        pdf = ROOT / mm["pdf"]
        if not pdf.exists():
            continue
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        for f in (DOCS / "manuals" / mm["id"]).glob("[0-9]*.md"):
            fm = yaml.safe_load(re.match(r"---\n(.*?)\n---", f.read_text(), re.S).group(1))
            if fm.get("source_sha256") != sha:
                err(f, "source_sha256 does not match sources PDF (stale conversion?)")
            break

    for line in warnings + errors:
        print(line)
    n = len(list(DOCS.rglob("*.md")))
    print(f"\nchecked {n} markdown files: {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
