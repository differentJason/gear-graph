#!/usr/bin/env python3
"""Convert manual PDFs (tools/manifest.yaml) into sectioned, metadata-tagged markdown.

    .venv/bin/python tools/convert_manual.py            # all manuals
    .venv/bin/python tools/convert_manual.py <id> ...   # only these ids

Output per manual: docs/manuals/<id>/index.md + NN-<section>.md (one file per section).
Deterministic: no LLM. Every file carries provenance (source URL, retrieval date, PDF sha256).
"""
import hashlib
import re
import sys
from pathlib import Path

import pymupdf
import pymupdf4llm
import yaml

ROOT = Path(__file__).resolve().parent.parent
MARK = "\x00P{}\x00"
MARK_RE = re.compile(r"\x00P(\d+)\x00\n?")
NOTICE = ("Converted from the manufacturer's PDF for personal reference. Copyright remains with the "
          "manufacturer. Not for redistribution.")


def norm(s):
    s = re.sub(r"[*_#`]", "", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def slugify(s, maxlen=60):
    s = re.sub(r"^\d+(\.\d+)*\.?\s*", "", s.strip())        # drop leading "3.1 "
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "section"


def figure_text(m, keep_all=False):
    """Text embedded in diagrams. Often noise (note names, numbering) but sometimes real instructions
    (e.g. a factory-reset procedure printed beside a keyboard diagram), so keep the wordy lines only.
    keep_all (manifest `figure_text: all`): on an OCR'd scan every page is an image, so parameter tables land
    here too; keep every line that has any word in it."""
    if re.search(r"\((ES|FR|DE|PT|IT|NL|PL|SE)\)\s", m.group(1)):        # other-language block on a multilingual page
        return ""
    lines = [re.sub(r"\s+", " ", l).strip() for l in re.split(r"<br>|\n", m.group(1))]
    need = 1 if keep_all else 2
    keep = [l for l in lines if len(re.findall(r"[A-Za-z]{3,}", l)) >= need]
    return ("\n\n> **Figure text (from a diagram in the PDF):** " + " / ".join(keep) + "\n\n") if keep else ""


def clean_page(md, ocr=False):
    md = re.sub("[\u200b\u200c\u200d\ufeff]", "", md)                        # zero-width chars (Intellijel PDFs put one between every word)
    md = re.sub(r"<!-- Start of picture text -->(.*?)<!-- End of picture text -->", lambda m: figure_text(m, ocr), md, flags=re.S)
    if ocr:
        md = md.replace("](", "] (")                                            # OCR brackets+parens are not links
    md = re.sub(r"</?(mark|u|sub|sup)>", "", md)                              # inline styling tags from the PDF
    md = re.sub(r"^(#{1,6})\s*\*\*(.*?)\*\*\s*$", r"\1 \2", md, flags=re.M)   # "## **X**" -> "## X"
    md = re.sub(r"^\s*\*\*\d{1,3}\*\*\s*$", "", md, flags=re.M)                # bare page-number footers
    md = re.sub(r"[ \t]+$", "", md, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", md).strip("\n")


def load_pages(entry):
    """Text per page, tagged with ORIGINAL pdf page numbers.
    `pages: [lo, hi]` = contiguous range. `page_spec: [{page: N, clip: [x0,y0,x1,y1]}, ...]` = chosen pages,
    optionally cropped (multilingual spreads keep each language in its own column)."""
    doc = pymupdf.open(ROOT / entry["pdf"])
    if entry.get("page_spec"):
        spec = entry["page_spec"]
        work = pymupdf.open()
        for sp in spec:
            work.insert_pdf(doc, from_page=sp["page"] - 1, to_page=sp["page"] - 1)
            if sp.get("clip"):
                # `clip` is in top-down page coordinates (what get_text reports). set_mediabox takes PDF coordinates
                # (y measured from the bottom) and resets the cropbox to match, so flip y and set nothing else.
                # Shrinking the mediabox, not just the cropbox, keeps text outside the clip out of the reading order.
                x0, y0, x1, y1 = sp["clip"]
                page_h = work[-1].mediabox.height
                work[-1].set_mediabox(pymupdf.Rect(x0, page_h - y1, x1, page_h - y0))
        numbers = [sp["page"] for sp in spec]
        chunks = pymupdf4llm.to_markdown(work, page_chunks=True, use_ocr=False)
    else:
        first, last = entry["pages"]
        numbers = list(range(first, last + 1))
        chunks = pymupdf4llm.to_markdown(doc, pages=[n - 1 for n in numbers], page_chunks=True, use_ocr=False)
    text = ""
    drop = [re.compile(rx) for rx in entry.get("drop_lines", [])]   # per-manual leftovers (running headers, stray captions)
    for n, ch in zip(numbers, chunks):
        page = clean_page(ch["text"], ocr=entry.get("figure_text") == "all")
        if drop:
            page = "\n".join(l for l in page.split("\n") if not any(rx.search(l) for rx in drop))
        text += MARK.format(n) + "\n" + page + "\n\n"
    if entry.get("stop_at"):                                   # multilingual sheet: English precedes this marker
        m = re.search(entry["stop_at"], text, re.M)
        if m:
            text = text[: m.start()]
    return doc, text


def _title_regex(title):
    """Words joined by any whitespace; numeric tokens like 3.1.11 tolerate stray spaces ('3. 1.11')."""
    def word(w):
        return r"\s*\.\s*".join(re.escape(x) for x in w.split(".")) if re.fullmatch(r"\d+(\.\d+)+\.?", w) else re.escape(w)
    return r"\s+".join(word(w) for w in title.split())


def find_heading(text, title, start, end=None):
    """Position of `title` within text[start:end]: a markdown heading line, else a bare line, else a line
    starting with it, else inside a figure-text block (heading baked into a diagram)."""
    words = _title_regex(title)
    end = len(text) if end is None else end
    for pat in (rf"^[ \t]*#+[ \t]*\**[ \t]*{words}[ \t]*\**[ \t]*$",
                rf"^[ \t]*\**[ \t]*{words}[ \t]*\**[ \t]*$",
                rf"^[ \t]*#*[ \t]*\**[ \t]*{words}"):
        m = re.compile(pat, re.M | re.I).search(text, start, end)
        if m:
            return m.start()
    m = re.compile(words, re.I).search(text, start, end)          # last resort: anywhere in the window
    if m:
        ls = text.rfind("\n", 0, m.start()) + 1                  # ...but start at the beginning of that line
        return ls
    return -1


def sections_from_outline(doc, text, entry, warnings):
    lo, hi = entry["pages"]
    skip = {norm(t) for t in entry.get("skip_titles", [])}
    maxlvl = entry.get("split_level", 2)
    toc = [(l, re.sub(r"[\x00-\x1f]+", " ", t).strip(), p) for l, t, p in doc.get_toc() if lo <= p <= hi and l <= maxlvl and norm(t) not in skip]
    off = {int(m.group(1)): m.start() for m in MARK_RE.finditer(text)}
    found, used, parents = [], set(), {}
    for lvl, title, page in toc:
        # Each heading is located independently inside its own page window. Multi-column pages can be read
        # in a different order than the outline lists them, so document order is NOT assumed.
        lo_at, hi_at = off.get(page, 0), off.get(page + 2, len(text))
        at = find_heading(text, title, lo_at, hi_at)
        while at in used and at >= 0:                              # same spot already claimed: look further on
            at = find_heading(text, title, at + 1, hi_at)
        if at < 0:
            warnings.append(f"heading not located in text: {title!r} (p{page}); merged into previous section")
            continue
        used.add(at)
        parents[lvl] = title
        found.append({"title": title, "level": lvl, "at": at, "path": [parents[k] for k in sorted(parents) if k < lvl]})
    return found


def sections_from_headings(text, entry, warnings):
    pat = re.compile(entry.get("heading_pattern", r"^#{1,2}\s+"), re.M)
    skip = {norm(t) for t in entry.get("skip_titles", [])}
    found, seen_titles = [], {}
    for m in pat.finditer(text):
        line_end = text.find("\n", m.start())
        line = text[m.start(): line_end if line_end > 0 else len(text)]
        title = re.sub(r"^(#+\s*|[-*]\s+)|\*\*", "", line).strip()
        title = re.sub(r"^\(EN\)\s*", "", title)
        title = re.sub(r"^\|?\s*\(EN\)\s*\|", "", title).strip("| ")         # "(EN) Controls" set as a table row
        if norm(title) in skip or not title:
            continue
        seen_titles[norm(title)] = seen_titles.get(norm(title), 0) + 1
        if seen_titles[norm(title)] > 1:
            title += " (continued)"
        found.append({"title": title, "level": 1, "at": m.start(), "path": []})
    return found


def describe(body):
    for para in re.split(r"\n\s*\n", body):
        p = re.sub(r"\s+", " ", re.sub(r"^[#>*\-\d.\s]+|\*\*|`", "", para.strip()))
        if len(p) >= 40 and not p.startswith("<!--"):
            return (p[:197].rsplit(" ", 1)[0] + "...") if len(p) > 200 else p
    return ""


def auto_tags(vocab, heading_only, title, body):
    tags, t, b = [], title.casefold(), body.casefold()
    for tag, kws in vocab.items():
        head_hit = any(re.search(rf"\b{re.escape(k.casefold())}", t) for k in kws)
        body_hits = sum(len(re.findall(rf"\b{re.escape(k.casefold())}", b)) for k in kws)
        if head_hit or (body_hits >= 3 and tag not in heading_only):
            tags.append(tag)
    return tags


def write_manual(entry, vocab, heading_only):
    warnings = []
    doc, text = load_pages(entry)
    if entry["split"] == "outline":
        secs = sections_from_outline(doc, text, entry, warnings)
    elif entry["split"] == "whole":                            # one section: short docs such as a printed product page
        secs = [{"title": entry["title"], "level": 1, "at": 0, "path": []}]
    else:
        secs = sections_from_headings(text, entry, warnings)
    if not secs:
        raise SystemExit(f"{entry['id']}: no sections found")
    sha = hashlib.sha256((ROOT / entry["pdf"]).read_bytes()).hexdigest()
    out = ROOT / "docs" / "manuals" / entry["id"]
    for old in out.glob("*.md"):
        old.unlink()
    out.mkdir(parents=True, exist_ok=True)

    ats = sorted(x["at"] for x in secs)
    listing, skipped = [], []
    for i, s in enumerate(secs):
        end = next((a for a in ats if a > s["at"]), len(text))
        raw = text[s["at"]:end]
        pages = sorted({int(p) for p in MARK_RE.findall(raw)})
        before = MARK_RE.findall(text[: s["at"]])          # page in effect where the section starts
        if before:
            pages = sorted(set(pages) | {int(before[-1])})
        body = MARK_RE.sub("", raw).strip()
        body = re.sub(r"\A[ \t]*#*[ \t]*\**[ \t]*" + r"\s+".join(re.escape(w) for w in s["title"].split()) +
                      r"[ \t]*\**[ \t]*\n", "", body, count=1, flags=re.I).strip()   # drop the heading line itself
        # remove running headers: bare lines identical to a section title
        titles = {norm(x["title"]) for x in secs}
        body = "\n".join(l for l in body.split("\n") if norm(l) not in titles or l.lstrip().startswith("#"))
        own = norm(s["title"])
        body = "\n".join(l for l in body.split("\n") if not (l.lstrip().startswith("#") and norm(l) == own))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if len(body) < 20:                                   # title-only chapter stub: content lives in its subsections
            skipped.append(s["title"])
            continue
        num = re.match(r"^(\d+(?:\.\d+)*)\.?\s", s["title"])
        fname = f"{len(listing) + 1:02d}-{slugify(s['title'])}.md"
        fm = {
            "title": s["title"].title() if s["title"].isupper() else s["title"],
            "description": describe(body),
            "doc_id": entry["id"],
            "device": entry["device"],
            "manufacturer": entry["manufacturer"],
            "model": entry["model"],
            "doc_type": entry["doc_type"],
            "doc_version": entry["doc_version"],
            "language": entry["language"],
            "section_number": num.group(1) if num else None,
            "section_path": s["path"],
            "pdf_pages": f"{pages[0]}-{pages[-1]}" if pages else None,
            "tags": auto_tags(vocab, heading_only, s["title"], body),
            "applies_to": entry["applies_to"],
            "source_url": entry["source_url"],
            "source_note": entry.get("source_note"),
            "retrieved": str(entry["retrieved"]),
            "source_sha256": sha,
            "content_status": "auto-converted",
        }
        fm = {k: v for k, v in fm.items() if v not in (None, [], "")}
        page = f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000)}---\n\n# {fm['title']}\n\n{body}\n"
        (out / fname).write_text(page, encoding="utf-8")
        listing.append((fname, fm["title"], fm.get("description", ""), s["level"], fm.get("tags", [])))

    lines = [f"- [{t}]({f}): {d}" if d else f"- [{t}]({f})" for f, t, d, _, _ in listing]
    index_fm = {"title": entry["title"], "doc_id": entry["id"], "device": entry["device"], "doc_type": "manual-index",
                "doc_version": entry["doc_version"], "applies_to": entry["applies_to"], "source_url": entry["source_url"],
                "retrieved": str(entry["retrieved"]), "source_sha256": sha, "content_status": "auto-converted"}
    (out / "index.md").write_text(
        f"---\n{yaml.safe_dump(index_fm, sort_keys=False, allow_unicode=True, width=1000)}---\n\n# {entry['title']}\n\n"
        f"> {entry['manufacturer']} {entry['model']}, {entry['doc_type']}, {entry['doc_version']}. "
        f"Source: <{entry['source_url']}> (retrieved {entry['retrieved']}).\n>\n> {entry['applies_to']}\n>\n> {NOTICE}\n\n"
        f"## Sections\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"{entry['id']}: {len(listing)} sections, {sum(1 for x in listing if x[4])} tagged"
          + (f", {len(skipped)} empty chapter stub(s) skipped" if skipped else "")
          + (f", {len(warnings)} warning(s)" if warnings else ""))
    for w in warnings:
        print("   WARN", w)
    return len(warnings)


def main():
    cfg = yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())
    vcfg = yaml.safe_load((ROOT / "VOCAB.yaml").read_text())
    vocab, heading_only = vcfg["tags"], set(vcfg.get("heading_only", []))
    wanted = set(sys.argv[1:])
    for entry in cfg["manuals"]:
        if wanted and entry["id"] not in wanted:
            continue
        if not (ROOT / entry["pdf"]).exists():
            print(f"{entry['id']}: SKIPPED, PDF missing at {entry['pdf']}")
            continue
        write_manual(entry, vocab, heading_only)


if __name__ == "__main__":
    main()
