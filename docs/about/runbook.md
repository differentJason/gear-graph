---
title: Runbook
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-20
---

# Runbook

All commands run from the repository root with the project's virtual environment (`.venv`).

## Everyday commands

```bash
.venv/bin/python tools/convert_manual.py [id ...]   # PDF -> sectioned tagged markdown
.venv/bin/python tools/fetch_specs.py [id ...]      # Eurorack: fetch sources, extract numbers + raw lines
.venv/bin/python tools/build_site.py                # inventory, devices, topics, Eurorack, budget, status, llms.txt, nav
.venv/bin/python tools/validate.py                  # structure, tags, links, hashes
.venv/bin/python tools/check_coverage.py            # did conversion lose text?
.venv/bin/mkdocs build --strict                     # strict build; fails on broken links
.venv/bin/mkdocs serve                              # preview at http://127.0.0.1:8000
```

Normal order after any change: convert or fetch, then `build_site`, then `validate`, `check_coverage`,
`mkdocs build --strict`. Anything under `docs/` marked GENERATED is rewritten by the build.

## The knowledge graph and the power budget

The graph runs in a separate environment (`.venv-graph`, needs a JDK; see `graph/README.md`). The power budget is
computed there and the site build only reads the result:

```bash
.venv/bin/python tools/validate_connections.py       # is connections.yaml consistent with the inventory? (no Spark needed)
.venv-graph/bin/python tools/build_graph.py          # build the graph, write graph/public/*.json and the budget snapshot
.venv/bin/python tools/build_site.py                 # renders the budget page from that snapshot
```

Run `build_graph.py` **before** `build_site.py` whenever placements (`connections.yaml`), specs, overrides,
`eurorack/attestations.yaml` or an item's `in_use` flag change. If you forget, `build_site.py` stops with
"budget.json is STALE" instead of publishing an out-of-date budget. Comment-only edits do not count as a change.
Commit the refreshed `graph/public/*.json` with the change that caused it.

To record wiring, edit `connections.yaml`: one entry per cable, a `status`, and a date. Record only what has been
stated; put anything vaguer under `open_statements`.

## Publish the site

The public site is built from committed data only (no manuals), so it can be rebuilt anywhere:

```bash
python tools/build_public.py                       # writes public/docs and public/mkdocs.yml
mkdocs build --strict -f public/mkdocs.yml         # strict build into public/site
mkdocs serve -f public/mkdocs.yml                  # preview
```

The site is not deployed anywhere yet. Charts are generated as inline SVG by `tools/viz.py`; numbers that come from local-only inputs are kept in
`data/snapshot.json`, `data/coverage.json` and `evals/results.json`, and are refreshed by `build_site.py` and
`check_coverage.py`. Re-run those, and commit the JSON, when the underlying data changes.

## Add a manual

1. Put the official PDF in `sources/` (git-ignored). If you downloaded it by hand, note that in `source_note`.
2. Check its structure: does it have an outline (`pymupdf`'s `get_toc()`)? Is it one language or several?
3. Add an entry to `tools/manifest.yaml`: `pages` (or `page_spec` with optional crop for multilingual sheets),
   `split: outline` or `split: headings` with a `heading_pattern`, and `applies_to` (which product and revision).
4. Run `convert_manual.py <id>` and read the warnings. "Heading not located" means a heading was not found on its page.
5. Run `check_coverage.py`. Below 95% means something was dropped. Look at the most-missing words.
6. **Read one converted section against the PDF.** Then `build_site`, `validate`, `mkdocs build --strict`.
7. Before trusting the file, confirm it is the right *product* and revision.

## Add a Eurorack module (or a case / supply)

1. Add an item to `inventory.yaml` (`category: eurorack-module`, or `eurorack-case` for a case; add `format: 1U` if it
   is Intellijel 1U format). Use the name as the owner gave it; note anything uncertain in `note` or `question`.
2. Add its pages to `eurorack/sources.yaml`, each with a tier (`official`, `retailer`, `community`). The module `id`
   must match the inventory id. Datasheet PDFs work as sources.
3. Run `fetch_specs.py <id>`. Read the summary: `[ag]` two sources agree, `[si]` one source, `[DI]` **disagree**, `[no]` none.
4. For anything odd, open `eurorack/evidence/<id>.json` and read the raw line. Fix the parser only if the *parser* is wrong.
5. Put decisions in `eurorack/overrides.yaml`: a `function` line; for a power supply or case, `role: supply` and
   `connections`; for conflicts or inferred values, `value`, `status` and a written `basis`.
6. Run `build_site.py` and read the module's page and the power budget.
7. After any change to `tools/fetch_specs.py`, snapshot `eurorack/evidence/`, re-run everything, and diff the values.

## When something looks wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| A number is `0` or absurd | parser misread it (thousands separator, sign, wrong line) | read the evidence line for that field |
| "heading not located" | multi-column reading order, odd characters, or a heading baked into a diagram | look at the page's raw markdown; adjust the pattern or window |
| Recall under 95% | content dropped (figure text, a language, a page range) | read the "most-missing" words; they name the culprit |
| Foreign-language text in a section | multilingual sheet | crop with `page_spec`, or `stop_at` the first non-English heading |
| A patched tool prints the same result as before | the patch did not apply | check the tool wrote its file; re-run a regression diff |
| A fetch returns HTTP 403 | the site blocks scripts | use another source tier, or download by hand and record it |
| Build fails on a link | a page was renamed or removed | fix the link; strict mode caught it |

## File map

`inventory.yaml` (gear) - `tools/` (all code) - `tools/manifest.yaml` (manual settings) - `VOCAB.yaml` (tags) -
`sources/` (PDFs, ignored) - `eurorack/{sources,overrides}.yaml`, `eurorack/evidence/` (spec inputs) -
`docs/` (the site; mostly generated) - `evals/golden.jsonl` (test questions) - `mkdocs.yml` (generated).
