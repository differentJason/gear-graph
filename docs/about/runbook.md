---
title: Runbook
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-23
---

# Runbook

All commands run from the repository root with the project's virtual environment (`.venv`).

## Everyday commands

```bash
.venv/bin/python tools/convert_manual.py [id ...]   # PDF -> sectioned tagged markdown
.venv/bin/python tools/fetch_specs.py [id ...]      # Eurorack: fetch sources, extract numbers + raw lines
.venv/bin/python tools/build_site.py                # inventory, devices, topics, Eurorack, budget, status, llms.txt, nav
.venv/bin/python tools/validate.py                  # structure, tags, links, hashes
.venv/bin/python tools/draw_devices.py            # redraw the original device illustrations -> images/<id>.svg + .jpg (needs Inkscape)
.venv/bin/python tools/validate_images.py          # is image_manifest.yaml consistent with inventory.yaml and images/?
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
.venv/bin/python tools/validate_midi.py              # is midi_channels.yaml consistent with the inventory and connections.yaml? (no Spark needed)
.venv/bin/python tools/build_terms.py                # check TERMS.yaml and recount labels in the manuals (writes graph/public/terms.json)
.venv/bin/python tools/build_code_graph.py           # Patchbay code <-> user-guide graph (writes graph/public/code.json; fails on doc drift)
.venv-graph/bin/python tools/build_graph.py          # build the graph, write graph/public/*.json and the budget snapshot
.venv/bin/python tools/build_site.py                 # renders the budget page from that snapshot
```

```bash
.venv-graph/bin/python tools/query_graph.py          # ask the graph its questions and check every answer (writes graph/public/answers.json)
```

`query_graph.py` runs the questions in `evals/graph_golden.yaml` against the committed snapshot. Each answer is checked against a hand-written
expectation or against separate code that reads the raw files, and it exits non-zero on any mismatch. Re-run it after `build_graph.py`;
`build_public.py` refuses `answers.json` if the snapshot changed since.

After editing `TERMS.yaml`, run `build_terms.py` first: `build_graph.py` and `build_public.py` stop with "terms.json is STALE"
otherwise. `build_terms.py --check` checks the rules without the manuals but cannot recount.
Likewise after changing anything in `patchbay/` (code, `docs/user-guide.md`, README): run `build_code_graph.py` before
`build_graph.py`, which refuses a stale `code.json`. A new button needs a `covers:` note in the user guide or the build fails.

Run `build_graph.py` **before** `build_site.py` whenever placements (`connections.yaml`), specs, overrides,
`eurorack/attestations.yaml`, `midi_channels.yaml`, or an item's `in_use` flag change. If you forget, `build_site.py`
stops with "budget.json is STALE" instead of publishing an out-of-date budget. Comment-only edits do not count as a
change. Commit the refreshed `graph/public/*.json` with the change that caused it.

To record wiring, edit `connections.yaml`: one entry per cable, a `status`, and a date. Record only what has been
stated; put anything vaguer under `open_statements`.

To record a device's intended MIDI channel, edit `midi_channels.yaml`: one entry per device per setup, a `status`,
and a date. Run `validate_midi.py` after.

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

## Patchbay app

`patchbay/` is a drag-and-drop patch planner that reads this repository (never writes it). After new manuals,
inventory, wiring or drawings, refresh its data and icons, then rebuild the public site (which publishes it read-only):

```bash
cd patchbay && make data icons && make test      # data/gear.json + icons/ from the KB; unit tests
make serve                                       # the full local app (saves sessions/, ports.yaml, panels.yaml -- git-ignored)
```

The website copy has no server: sessions stay in the visitor's browser and jack editing is off. Jack evidence cites the
manual section, never its text; icons are `images/` drawings. See `patchbay/README.md`.

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

## Mistakes that are easy to make

Each of these happened at least once while building the project:

- **Running steps out of order.** The graph must be built before the site that reads it, and the terminology before
  the graph. The builds refuse a stale snapshot ("is STALE") instead of guessing; when you see that, run the step it
  names rather than working around it.
- **Forgetting to rebuild a committed snapshot.** 18 manuals were ingested without rebuilding the graph, and the
  committed snapshot quietly missed them. After adding content, rebuild the whole chain and look at the diff of
  `graph/public/`: new content should appear there.
- **Ignore rules that hide more than intended.** An unanchored `public/` line in `.gitignore` also ignored
  `graph/public/`, which is meant to be committed. It was caught before pushing by listing what git would actually
  include. Anchor patterns (`/public/`) and check `git status` after editing ignore rules.
- **Believing a patch applied.** A tool that prints the same table after a "fix" may not have been changed at all.
  Confirm the file changed and the output moved.
- **Trusting a number without its source line.** For any surprising figure, open the evidence (Eurorack) or the
  section text (manuals, terminology counts) before changing code.
- **Publishing without a leak scan.** Anything pushed is public and permanent. Scan every file about to be committed,
  and read the hand-written pages yourself; a pattern list only catches what it knows about.

## File map

`inventory.yaml` (gear) - `connections.yaml` (wiring) - `midi_channels.yaml` (intended MIDI channel settings) -
`tools/` (all code) - `tools/manifest.yaml` (manual settings) - `VOCAB.yaml` (tags) -
`sources/` (PDFs, ignored) - `images/` (original illustrations drawn by `tools/draw_devices.py`, committed; no product photos) - `eurorack/{sources,overrides}.yaml`, `eurorack/evidence/` (spec inputs) -
`docs/` (the site; mostly generated) - `evals/golden.jsonl`, `evals/graph_golden.yaml` (test questions) - `mkdocs.yml` (generated).
