---
title: Decision log
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-20
---

# Decision log

Short records of choices that shaped the project. "Owner" = the person the project is for; "assistant" = the AI
coding assistant that implemented it.

| # | Decision | Why | Trade-off | Made by |
|---|---|---|---|---|
| D1 | Markdown with frontmatter is the source of truth; **no graph database** | keeps content portable, diffable and easy to check; a graph can be derived from plain fields later | no graph queries now | owner |
| D2 | Build pipeline is **deterministic**: no language model at build time | reproducible, auditable, cheap to re-run; failures are debuggable | tags are keyword heuristics, not understanding | assistant (not explicitly reviewed by the owner) |
| D3 | Manuals come from **official manufacturer sources** only; files the owner downloaded by hand are recorded with a `source_note` | manual-aggregator sites host unverified copies and wrong revisions | some official hosts are unreadable to a script, so the owner downloaded three | owner chose "I find them on manufacturer sites"; assistant executed |
| D4 | Ingest **what actually exists, labelled honestly**: a Quick Start is marked `quick-start` and never presented as a full manual | an agent must know how complete its source is | thinner coverage for the APC20, UMC404HD and MPK mini | assistant |
| D5 | **Never ingest a manual for a different product**, even if it looks close | a plausible manual for the wrong unit yields confidently wrong answers | one download (MPK mini *Play* mk3) was set aside | assistant flagged, owner supplied the right file |
| D6 | Match an unlabelled document to a product **by content evidence**, and record the reasoning | the MPK quick start says only "MPK mini" | a judgment call, not proof | assistant (owner supplied the file and did not dispute the match) |
| D7 | Spec values follow a **two-source rule**; disagreements are flagged; overrides must carry written reasoning | ModularGrid is user-maintained and retailers copy each other | most values remain single-source | assistant |
| D8 | **Unknown stays unknown.** Inference is allowed only when labelled `inferred` (for example a passive mult drawing 0 mA) | silent estimates make a budget look more certain than it is | some totals are "lower bounds" | assistant |
| D9 | Keep the original **evidence lines** next to every number | anyone can check the parse instead of trusting it | larger pages | assistant |
| D10 | 1U-format (Intellijel) modules are counted **separately from 3U width** | they sit in a different row type | HP totals show two figures | assistant |
| D11 | Power budget compares **each supply against the whole load**, plus a combined column | which module sits in which case is unknown | no single verdict | assistant (after the owner added a second supply, the NiftyCASE) |
| D12 | Generated files carry a banner and are **never hand-edited**; inputs are edited instead | prevents drift between source and output | changes need a rebuild | assistant |
| D13 | Quality **gates**: validator, coverage check, `mkdocs build --strict`, and a regression diff after parser changes | a clean build proved little (see [Verification](verification.md)) | slower iteration | assistant |
| D14 | Start with a vertical slice (the studio signal chain), then Eurorack | prove the pipeline on a few devices before scaling | broad coverage came later | owner chose the slice |
| D15 | Retrieval tests use a **BM25 keyword baseline**, labelled as such | simple, dependency-free and transparent | results do not transfer to other search systems | assistant |
| D16 | Keep PDFs **and text converted from them** out of git and out of any published site | manuals are copyrighted | a clone cannot rebuild the manual pages without the owner's PDFs | assistant |
| D17 | Owner-supplied identifications (a screenshot of two Intellijel modules; a datasheet link; corrected names) **override the assistant's guesses**, and the source of each is recorded | the owner holds the physical modules | recorded as "confirmed by the owner" | owner |

## Choices the owner made that changed the outcome

- Dropped the graph database (D1) after the assistant found one was already running locally.
- Pruned the inventory: removed sold or dead gear, and supplied the complete list including Eurorack.
- Supplied the Analog Four revision (MKII), the Intellijel module identifications, the Quadratt format (1U),
  the mixer's real name, the maker of the clock module, and its datasheet: each closed an open question.
- Owned a NiftyCASE with its own built-in supply (the assistant added it at the owner's request), which exposed that the power-budget code assumed a single supply.
