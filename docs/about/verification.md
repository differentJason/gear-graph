---
title: How correctness is checked
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-23
---

# How correctness is checked

A clean build does not mean correct content. This project uses several independent checks, and most of the real
defects it found were caught by a check *other than* the one designed for that failure.

## The layers

| Check | What it proves | What it cannot prove |
|---|---|---|
| `tools/validate.py` | frontmatter parses; required fields present; every tag is in `VOCAB.yaml`; every relative link resolves; each section's recorded PDF hash matches the PDF on disk | that the text is faithful |
| `tools/check_coverage.py` | how much of the PDF's text survived: unique-word recall and occurrence recall against `pdftotext`, flagged below 95% | that the words are in the right section or order |
| Spot checks against the source | a chosen section compared word for word with the PDF (RD-9 rear panel, Analog Four rear connectors) | anything not sampled |
| Two-source rule (Eurorack) | a spec value is `confirmed` only when two independent sources agree; disagreements are flagged, never picked silently | that both sources are right |
| Evidence tables | every number can be traced to the page and the exact line it came from | that the parse chose the right line (check the line) |
| Regression diff | after changing the spec parser, all modules were re-fetched and every field reading compared with the previous run (0 of 135 changed) | pages that changed at the source |
| `mkdocs build --strict` | the whole site builds and no link is broken | content correctness |
| Golden questions | retrieval finds the right pages for known questions (see [Evaluation](evaluation.md)) | answer quality (no LLM judge has been run) |

Coverage at last measurement (2026-09-20): Analog Four MKII 99.9% unique / 98.7% occurrence, APC20 100/100,
Donner B1 99.6/99.7, RD-9 99.6/98.7, UMC404HD quick start 98.9/96.0. The MPK mini quick start is not measured,
because its PDF text includes Spanish and French and no English-only reference exists. The check says so, and does
not report a misleading number.

## Failures actually found

These are the real defects from building the system, and what exposed each. They are the most useful part of this
page: they show where content pipelines break.

| # | Failure | How it was caught | Fix |
|---|---|---|---|
| 1 | Removing "picture text" as OCR noise **silently deleted real instructions**, including the Donner B1 factory-reset procedure, which the manual prints beside a diagram | coverage check: recall 97.5%, missing words like `boot`, `hold`, `press` | keep figure text, dropping only lines that are pure note names or numbers |
| 2 | Assuming headings appear in the extracted text in outline order; two-column pages are read in a different order, so six RD-9 headings were "not located" and merged into their neighbours | converter warnings ("heading not located") | locate each heading inside its own page window; slice by text order, keep files in outline order |
| 3 | Hidden BEL control characters inside Behringer's PDF outline titles broke title matching | same warnings | strip control characters from titles |
| 4 | A bare `**13**` page-number footer leaked into the middle of a section; some chapters were empty stubs holding only a duplicated heading | spot check against the PDF | strip page-number lines; skip title-only stubs |
| 5 | The download named `MPK_mini_Play_mk3_User_Guide` is a **different product** from the owner's MPK mini MK3 | the PDF's own title ("MPK mini Play mk3 User Guide") versus the product the owner has | not ingested. A later download that only says "MPK mini" was matched to the MK3 by its content (a display showing program and BPM, no speaker or headphone output) and the reasoning recorded in the manual's `source_note` |
| 6 | Spanish and French text leaked into the English sections of multilingual sheets | reading the converted output | crop to the English column, cut at the first non-English heading, drop other-language figure text |
| 7 | Running page headers ("U-PHORIA UMC404HD/... Controls") were used as section titles | reading the converted output | explicit heading patterns per manual |
| 8 | Spec parser: `1,000 mA` read as `0`; `+12V` and `-12V` confused across a line break; labels and values on separate lines; After Later's pages print the positive rail without a `+`; a retailer's "84HP row" read as a module width | wrong-looking numbers and the *Disagree* flag, then reading the raw evidence lines | anchored patterns that never cross a line; thousands separators; sign-aware rules; the width conflict resolved by an override with the reasoning recorded |
| 9 | A non-UTF-8 retailer page crashed the fetcher | crash | tolerant decoding |
| 10 | **A fix silently did not apply** (a patch script failed before writing) and the printed table looked like a fresh result | the CP1A value still read `0` | rule adopted: after every change, confirm the output actually changed, and re-run a regression diff |
| 11 | Tags that match everywhere carry no information (`controls-overview` on every page, `cv-gate` on "gate length") | reading tag frequencies | `heading_only` tags; the bare word "gate" removed from `cv-gate` |

Failure 10 was an error by the AI assistant, caught by inspection. It is listed because pipelines fail this way in
practice: a change that did not take effect looks exactly like a change that did.

## What "confirmed" means in the Eurorack pages

Two agreeing sources is a weak guarantee, not proof: retailers usually copy the maker's figures, and ModularGrid is
user-maintained. The pages therefore show the tier of each source (official, retailer, community) and the raw
line. A value with a single community source is labelled `single` and is not presented as fact.

## Patterns in these failures

Grouped by kind, because the same kinds recur in any content pipeline:

| Kind of failure | Examples here | What catches it |
|---|---|---|
| **Silent loss**: content disappears and nothing errors | 1 (factory-reset procedure deleted), 10 (a fix that never applied) | A completeness measure (coverage recall) and before/after diffs; nothing that looks only at the output's shape |
| **Layout and order** | 2 (two-column reading order), 6 (other languages leaking in), 7 (running headers used as titles) | Reading the converted output against the page; warnings for "expected but not found" |
| **Invisible characters and encodings** | 3 (BEL characters in titles), 9 (non-UTF-8 page) | Crashes and match failures; strip or decode defensively at the boundary |
| **Wrong identity**: the right-looking file for the wrong thing | 5 (a different product's manual) | Comparing the document's own title and content with the object it is meant to describe |
| **Parsing numbers** | 8 (thousands separators, signs, line breaks) | Storing the raw line beside the value, and a second source that disagrees |
| **Rules that match too much** | 11 (tags on every page); the terminology's homographs and feature names ([How the terminology was built](terminology.md)) | Looking at frequencies: a label on 90% of pages, or in a manual where it makes no sense, is a rule problem |
| **Checks that do not check** | two early graph mutation tests were ineffective and had to be redone; one terminology test failed for the wrong reason ("does not exist" instead of the rule it targeted) | Reading the failure *message*, not just the exit code, and confirming the test hits the rule it names |

Three rules follow from these:

- **Measure completeness, not just validity.** A validator proves the structure is right; only a comparison with the
  source proves nothing was lost.
- **After every change, confirm the output changed, and only where intended.** Diff all of it, not just the part you meant to change.
- **Prove each check can fail.** Break the input on purpose and confirm the check fails with the expected message.
