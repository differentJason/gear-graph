---
title: Limitations and open questions
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-20
---

# Limitations and open questions

Written so a reader can judge how far to trust the project. Current counts are on the [status page](status.md).

## Content coverage

- **Three of the six manuals are Quick Starts, not full manuals** (APC20, UMC404HD, MPK mini MK3). The UMC404HD guide
  is shared by five products, and its spec tables list several models side by side; only the UMC404HD parts apply.
- **The MPK mini quick start was matched to the MK3 by content**, not by its own label (see D6 in the
  [decision log](decisions.md)). It is a judgment call.
- **Wiring is recorded for the main studio only**, and only what the owner stated (`connections.yaml`). The alternate jam-location setup is not recorded, Eurorack patch cables are deliberately not recorded (they change every session), and where swapped-in gear plugs in is not stated.
- **Software manuals are not ingested** (Logic Pro, Bitwig): far larger, and out of scope for the first slices.
- **Eurorack modules have specs, not manuals.** Operating instructions for most modules are not in the knowledge base.

## Conversion quality

- **Tags are keyword rules, not understanding.** `sequencer` still lands on about 70% of Analog Four sections.
- **Reading order inside multi-column pages** can differ from the printed order (for example the UMC controls list).
- **Coverage is measured on words, not layout.** Tables and diagrams are approximations of the printed page.

## Eurorack specifications

- **Most values are single-source**, usually ModularGrid (user-maintained). The two-source rule is the exception, not
  the norm. Each page shows which is which. The owner has attested the module draw values as correct (sourced from the manufacturers; D20), which is recorded separately and does not change the source count.
- **"Function" descriptions come from listing text** surfaced by web search, not from manuals.
- **Some figures are inferred** (two passive modules at 0 mA), labelled as such. An inferred zero for a jacks-only Intellijel module was removed when the owner said the Intellijel units do draw a small amount; that draw is treated as missing until it is found.
- **+5V and depth are often not stated**, so the +5V total is a lower bound.
- **Draw figures are published maximums or typical values**, not measurements. The NiftyCASE labels its rail outputs
  "peak"; a footnote explaining that was not found on its page.
- **The budget assumes every in-use module is running at once.** Placement is recorded, so each supply is compared with the modules it feeds; which 3U row and position each module occupies in the custom case is not recorded.
- **The Behringer Space FX has conflicting figures** in the wild; only one source could be parsed.
- **Three matches are closest-listing matches** the owner confirmed (Pico MODulator, Skew Fade LFO, Black Dual VCF
  listing); the owner's list wording differed slightly.

## Evaluation

- **The golden set is small** (22 questions, 17 answerable), and one label is known to be too strict.
- **Retrieval is a BM25 keyword baseline**, not a production search system.
- **No language-model-judged evaluation has been run**, so nothing here supports a claim about answer quality.
- **Keyword retrieval cannot abstain or bridge synonyms** (see [Evaluation](evaluation.md)).

## Process and legal

- Built in a single session with an AI assistant; the code has not had independent review.
- Manual content is copyright its manufacturers. The PDFs and all text converted from them are git-ignored and kept
  out of the published site.

## Open questions

- Where does swapped-in gear (Korg M1, Dreadbox Typhon, Behringer K2, Donner B1) plug in for audio?
- What does the alternate jam-location setup look like?
- Should Eurorack modules get golden questions and be added to the retrieval corpus?
- Would a plain-language summary or aliases per page fix the vocabulary-mismatch misses?
