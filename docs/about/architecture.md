---
title: Architecture
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-20
---

# Architecture

## Shape of the system

Two pipelines feed one site. Both are deterministic (no language model runs at build time), and both keep the
original source next to the derived content.

```
MANUALS                                             EURORACK
sources/*.pdf (git-ignored)                         eurorack/sources.yaml   (which pages to read)
   |  tools/manifest.yaml (page ranges, split rules)   |
   v                                                    v
tools/convert_manual.py                             tools/fetch_specs.py
   |  -> docs/manuals/<id>/NN-section.md               |  -> eurorack/evidence/<id>.json
   |     (frontmatter + provenance)                    |     (numbers + the raw line each came from)
   |                                                    |  eurorack/overrides.yaml (human decisions + reasons)
   +-------------------+--------------------------------+
                       v
        inventory.yaml  ->  tools/build_site.py  ->  tools/build_eurorack.py
                       |
                       v
   docs/ (inventory, device pages, topic pages, Eurorack pages, power budget, llms.txt, status)  +  mkdocs.yml
                       |
        gates:  tools/validate.py   tools/check_coverage.py   mkdocs build --strict
                       |
                       v
            static site (MkDocs)                 evals/golden.jsonl -> retrieval eval (separate notebook)
```

## Components

| Component | Input | Output | Why it exists |
|---|---|---|---|
| `inventory.yaml` | the owner's gear list | source of truth for what exists, its status, its format (3U/1U) | one place to correct the inventory; everything else is derived |
| `tools/manifest.yaml` | one entry per PDF | conversion settings: page range or `page_spec` (with crop), split strategy, `stop_at`, heading pattern | manuals differ; the differences are data, not code |
| `tools/convert_manual.py` | PDF + manifest | one markdown file per section, with frontmatter | sections are the unit an agent should retrieve |
| `VOCAB.yaml` | keyword rules | controlled tag list | consistent tags; `heading_only` tags avoid "button" matching every page |
| `eurorack/sources.yaml` | module id | list of source URLs with a trust tier (official / retailer / community) | every number must come from a named page |
| `tools/fetch_specs.py` | those URLs | extracted values plus the exact source line, per source | evidence is stored before it is interpreted |
| `eurorack/overrides.yaml` | human decisions | value + status + written reasoning | a judgment call is visible, not buried in code |
| `tools/build_site.py`, `build_eurorack.py` | all of the above | generated pages, nav, `llms.txt`, power budget, status page | generated files are never hand-edited |
| `tools/validate.py` | `docs/` | errors and warnings | structural correctness |
| `tools/check_coverage.py` | PDFs vs converted markdown | word-recall per manual | did the conversion lose content? |

## Data model

**Manual section** (one file each). Frontmatter fields: `title`, `description` (first sentence, so an agent can
decide whether to open the page), `doc_id`, `device`, `manufacturer`, `model`, `doc_type` (`user-manual` or
`quick-start`), `doc_version`, `language`, `section_number`, `section_path` (parent headings), `pdf_pages`, `tags`
(from the controlled vocabulary), `applies_to` (which product and revision this is valid for), `source_url`,
`source_note` (for files downloaded by hand), `retrieved`, `source_sha256`, `content_status`.

**Eurorack module page.** `specs` (`hp`, `depth_mm`, and `power_ma` for modules or `capacity_ma` for supplies),
`spec_status` per field, `format` (3U or 1U), `function`, `identified_as` (how the module was matched to a listing),
and an *Evidence* table giving, for every number, the source tier, the value, the exact line, and the page.

**Field status** (the trust vocabulary used everywhere): `confirmed` = two or more sources agree; `single` = one
source; `conflict` = sources disagree; `override` / `inferred` = a human decision with written reasoning;
`missing` = no source stated it.

## Design principles

1. **Markdown with metadata is the source of truth.** No graph database (an explicit owner decision); relationships
   are plain fields, so a graph could be derived later.
2. **Derived files are reproducible.** Delete `docs/manuals/` and regenerate it from the PDFs and manifest.
3. **Provenance travels with the content.** Every section carries where it came from and a hash of the exact PDF.
4. **Evidence before interpretation.** Numbers are stored with their raw source lines first; decisions are layered
   on top and visible.
5. **Unknown stays unknown.** Nothing is estimated silently. Gaps are shown as gaps, and the budget says when it is
   a lower bound.
6. **Build strictly.** The site is built with `mkdocs build --strict`, so a broken link fails the build instead of
   shipping.
