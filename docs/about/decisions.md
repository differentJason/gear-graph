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
| D1 | Markdown with frontmatter is the source of truth; **no graph database** *(graph part superseded by D18)* | keeps content portable, diffable and easy to check; a graph can be derived from plain fields later | no graph queries now | owner |
| D2 | Build pipeline is **deterministic**: no language model at build time | reproducible, auditable, cheap to re-run; failures are debuggable | tags are keyword heuristics, not understanding | assistant (not explicitly reviewed by the owner) |
| D3 | Manuals come from **official manufacturer sources** only; files the owner downloaded by hand are recorded with a `source_note` | manual-aggregator sites host unverified copies and wrong revisions | some official hosts are unreadable to a script, so the owner downloaded three | owner chose "I find them on manufacturer sites"; assistant executed |
| D4 | Ingest **what actually exists, labelled honestly**: a Quick Start is marked `quick-start` and never presented as a full manual | an agent must know how complete its source is | thinner coverage for the APC20, UMC404HD and MPK mini | assistant |
| D5 | **Never ingest a manual for a different product**, even if it looks close | a plausible manual for the wrong unit yields confidently wrong answers | one download (MPK mini *Play* mk3) was set aside | assistant flagged, owner supplied the right file |
| D6 | Match an unlabelled document to a product **by content evidence**, and record the reasoning | the MPK quick start says only "MPK mini" | a judgment call, not proof | assistant (owner supplied the file and did not dispute the match) |
| D7 | Spec values follow a **two-source rule**; disagreements are flagged; overrides must carry written reasoning | ModularGrid is user-maintained and retailers copy each other | most values remain single-source | assistant |
| D8 | **Unknown stays unknown.** Inference is allowed only when labelled `inferred` (for example a passive mult drawing 0 mA) | silent estimates make a budget look more certain than it is | some totals are "lower bounds" | assistant |
| D9 | Keep the original **evidence lines** next to every number | anyone can check the parse instead of trusting it | larger pages | assistant |
| D10 | 1U-format (Intellijel) modules are counted **separately from 3U width** | they sit in a different row type | HP totals show two figures | assistant |
| D11 | *(superseded by D19)* Power budget compared **each supply against the whole load**, plus a combined column | which module sits in which case is unknown | no single verdict | assistant (after the owner added a second supply, the NiftyCASE) |
| D12 | Generated files carry a banner and are **never hand-edited**; inputs are edited instead | prevents drift between source and output | changes need a rebuild | assistant |
| D13 | Quality **gates**: validator, coverage check, `mkdocs build --strict`, and a regression diff after parser changes | a clean build proved little (see [Verification](verification.md)) | slower iteration | assistant |
| D14 | Start with a vertical slice (the studio signal chain), then Eurorack | prove the pipeline on a few devices before scaling | broad coverage came later | owner chose the slice |
| D15 | Retrieval tests use a **BM25 keyword baseline**, labelled as such | simple, dependency-free and transparent | results do not transfer to other search systems | assistant |
| D16 | Keep PDFs **and text converted from them** out of git and out of any published site | manuals are copyrighted | a clone cannot rebuild the manual pages without the owner's PDFs | assistant |
| D17 | Owner-supplied identifications (a screenshot of two Intellijel modules; a datasheet link; corrected names) **override the assistant's guesses**, and the source of each is recorded | the owner holds the physical modules | recorded as "confirmed by the owner" | owner |
| D18 | Add a **knowledge graph**, built with **PySpark + GraphFrames**, **derived** from the existing files. Markdown/YAML stays the source of truth; the graph is a rebuildable artifact like `docs/eurorack/`. Supersedes the graph part of D1 | relationships (what feeds what, which module draws from which supply, which page answers which question) are awkward to query as flat pages; D1 already kept them as plain fields so a graph could be derived | a second environment (JVM + Spark, kept in its own venv, not needed to build the site); output that includes manual-derived nodes stays local | owner chose the tool; assistant proposed the schema (see `graph/README.md`) |
| D19 | The power budget is **computed by the knowledge graph** over recorded placement (which case, which supply feeds each module), and the site build only *reads* the result, refusing a snapshot whose input digest no longer matches | placement is now recorded (D18 routing work), so each supply can be compared with the modules it actually feeds; keeping Spark out of the site build keeps CI simple | editing placements, specs or in-use flags requires re-running `build_graph.py` before `build_site.py` | owner supplied the placement; assistant designed it |
| D20 | An **owner attestation** (module draw values sourced from the manufacturers by the owner are correct) is recorded in `eurorack/attestations.yaml` **beside** the evidence, never replacing a field's evidence status; inferred zeros and supply capacities are excluded | the owner holds knowledge the fetched pages cannot show, but 'how many sources agreed' should stay an honest count | two kinds of trust are shown side by side | owner stated it; assistant chose the scoping |
| D21 | Every answer the graph gives is **checked against something that is not the graph**: a hand-written expectation, or separate code reading the raw files | a graph query that only agrees with itself proves nothing; the query tests were mutation-tested (a wrong expectation and a changed source both fail) | more test code than query code | assistant |
| D22 | Track the owner's intended **MIDI channel settings** (`midi_channels.yaml`) as **item-vertex properties** on the graph, not `CONNECTS`-edge properties; only one channel is recorded per device even when the device has several independent MIDI channels (e.g. Elektron's per-track/AUTO/PERF/program-change channels); no "thru channel" is tracked, only `thru_pass_enabled: true/false` | it's a device setting independent of any one cable, so it should survive even for a device with no recorded wiring yet; recording every internal channel of every device is out of scope for the first slice (same vertical-slice-first approach as D14); this rack's "thru" is not channel-based for any device that actually has one | a multi-channel device's full MIDI configuration is not fully captured -- only the channel most relevant to live performance, named in `role:`; the file starts empty, since the assistant does not know the owner's actual channel choices and will not fabricate them (D8 applies) | owner asked for it; assistant proposed the schema |

## Choices the owner made that changed the outcome

- Dropped the graph database (D1) after the assistant found one was already running locally.
- Pruned the inventory: removed sold or dead gear, and supplied the complete list including Eurorack.
- Supplied the Analog Four revision (MKII), the Intellijel module identifications, the Quadratt format (1U),
  the mixer's real name, the maker of the clock module, and its datasheet: each closed an open question.
- Owned a NiftyCASE with its own built-in supply (the assistant added it at the owner's request), which exposed that the power-budget code assumed a single supply.
- Described the real housing (a NiftyCASE plus an owner-built case with the CP1A mounted), which turned the budget's apparent 119% overload on one supply into 80% once each supply is compared only with the modules it feeds.
- Stated that the draw values were sourced from the manufacturers and are correct (D20), and corrected one of the assistant's inferences: the Intellijel units draw a small amount, so the inferred 0 mA for the Jacks module was removed and its draw is missing until found (D8 applied to the assistant's own guess).
