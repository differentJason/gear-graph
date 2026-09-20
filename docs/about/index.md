---
title: About this project
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-20
---

# About this project

## What it is

A personal, machine-readable knowledge base for a home music studio: manufacturer manuals converted to
sectioned, metadata-tagged markdown, plus structured spec pages for Eurorack modules, published as a static
[MkDocs](https://www.mkdocs.org/) site.

Current counts live on the [status page](status.md). This page does not quote them, because they change.

## Why it exists

A personal learning project about preparing content so software can retrieve and use it reliably: how to structure it,
how to verify it, and how to measure whether it works. Studio gear is content the owner fully controls, is messy in
realistic ways (PDFs with odd layouts, multilingual sheets, wrong-product downloads, conflicting web sources), and has
questions with checkable answers.

What the project practices, and where to read about each:

| Skill | Where it shows up |
|---|---|
| Structuring content for machine consumption | [Architecture](architecture.md): section-per-file, frontmatter schema, `llms.txt`, controlled tag vocabulary |
| Provenance and trust in content | [Verification](verification.md): source URL, retrieval date, PDF hash on every section; two-source rule for specs |
| Measuring retrieval quality | [Evaluation](evaluation.md): golden questions, hit@k and MRR, A/B of indexing choices |
| Making and recording judgment calls | [Decision log](decisions.md) |
| Operating and extending a content pipeline | [Runbook](runbook.md) |

## What it deliberately is not

- Not a replacement for the manufacturers' manuals. Manual text is copyright its manufacturers, so it is kept out of
  version control and out of the published site; only the code, the owner's inventory, Eurorack spec facts with their
  sources, and these documents are published.
- Not a production system.
- Not a search product. Retrieval tests use a small local keyword-search baseline (BM25).
- Not an LLM-judged evaluation. The judge code exists in a separate notebook but has only been run with a fake model
  to test the plumbing. See [Limitations](limitations.md).

## How it was built

Built in one working session by the owner directing an AI coding assistant (Claude Code). The owner set the goals,
made the scope and sourcing decisions, supplied the gear list and corrections, and confirmed identifications; the
assistant wrote the code and documentation and ran the checks. The [decision log](decisions.md) records who decided
what where that matters.
