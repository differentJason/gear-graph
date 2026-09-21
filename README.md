# gear-kb

A personal, machine-readable knowledge base for a home music studio, built as a learning project about structuring,
verifying and measuring content for retrieval.

- Manufacturer manuals are converted to sectioned markdown with metadata and provenance (source URL, retrieval date,
  PDF hash).
- Eurorack modules get spec pages in which **every number keeps the source it came from and the exact line of text**;
  a value counts as *confirmed* only when two sources agree.
- A small retrieval evaluation (golden questions, hit@k, MRR) measures which indexing choices help.
- Everything is published as a static [MkDocs](https://www.mkdocs.org/) site.

How it works, how correctness is checked, the evaluation, a decision log, a runbook and the limitations are in
[`docs/about/`](docs/about/index.md).

## What is and is not in this repository

**Included:** the code (`tools/`), the owner's gear inventory, Eurorack spec data with evidence, the test questions,
and the project documentation.

**Not included, on purpose:** the manufacturers' PDFs and any text converted from their manuals. Those are copyright
their manufacturers, so they stay on the author's machine (`sources/`, `docs/manuals/`, and the pages derived from
them are git-ignored). Anyone re-creating the manual pages needs to obtain the manuals themselves.

## Layout

| Path | What |
|---|---|
| `inventory.yaml` | Source of truth for the gear and its status |
| `connections.yaml` | Source of truth for how the gear is wired and which case/supply each module sits in |
| `tools/manifest.yaml` | One entry per source PDF: page range, split rules |
| `VOCAB.yaml` | Controlled tag vocabulary |
| `eurorack/sources.yaml`, `eurorack/overrides.yaml`, `eurorack/evidence/` | Where Eurorack specs come from, the human decisions on top, and the raw evidence |
| `eurorack/attestations.yaml` | Owner statements that a class of values is correct, kept beside the evidence |
| `graph/`, `tools/build_graph.py` | Knowledge graph (PySpark + GraphFrames), derived from the files above; computes the power budget. See `graph/README.md` |
| `docs/about/` | Project documentation |
| `docs/eurorack/` | Generated Eurorack module pages and the power budget |
| `evals/golden.jsonl` | Test questions with the pages that answer them |
| `evals/graph_golden.yaml` | Questions asked of the knowledge graph, with the answers worked out by hand |

## Pipeline

```bash
.venv/bin/python tools/convert_manual.py [id ...]   # PDF -> sectioned tagged markdown (needs the PDFs)
.venv/bin/python tools/fetch_specs.py [id ...]      # Eurorack: fetch sources, extract numbers + raw lines
.venv/bin/python tools/build_site.py                # generate pages, nav, status
.venv/bin/python tools/validate.py                  # structure, tags, links, hashes
.venv/bin/python tools/check_coverage.py            # did conversion lose text?
.venv/bin/mkdocs build --strict                     # strict build; fails on broken links
```

See the [runbook](docs/about/runbook.md) for adding a manual or a Eurorack module.

## Latest measurements (2026-09-20, BM25 keyword baseline, retrieval only, no language model)

6 manuals, 198 pages, 633 chunks; 22 questions (17 answerable, 5 unanswerable or false-premise).

| Variant | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| baseline | 0.41 | 0.71 | 0.82 | 0.575 |
| + index manufacturer/model/device | 0.59 | 0.82 | 0.88 | 0.711 |
| + also tags | 0.59 | 0.82 | 0.88 | 0.701 |

Small sample; treat as leads, not conclusions. Keyword search cannot bridge synonyms ("back" vs "rear panel") and
cannot say "I don't know". Details and caveats: [evaluation](docs/about/evaluation.md).

## Site

The site is built from committed data only (no manual text). To build it locally:

```bash
python tools/build_public.py && mkdocs build --strict -f public/mkdocs.yml
```

It includes charts and diagrams (pipeline, coverage, evidence quality, power budget, the knowledge graph's schema, wiring and rack layout, what the checks caught, retrieval
results) generated as inline SVG, with a text description and data table beside each.

## Known limitations

Tags are keyword rules; three of the six manuals are quick starts; most Eurorack figures come from a single
source; no language-model-judged evaluation has been run. See [limitations](docs/about/limitations.md).
