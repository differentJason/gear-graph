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
- **No routing or wiring data.** How devices connect in the studio has not been confirmed, so none is recorded.
- **Software manuals are not ingested** (Logic Pro, Bitwig): far larger, and out of scope for the first slices.
- **Eurorack modules have specs, not manuals.** Operating instructions for most modules are not in the knowledge base.

## Conversion quality

- **Tags are keyword rules, not understanding.** `sequencer` still lands on about 70% of Analog Four sections.
- **Reading order inside multi-column pages** can differ from the printed order (for example the UMC controls list).
- **Coverage is measured on words, not layout.** Tables and diagrams are approximations of the printed page.

## Eurorack specifications

- **Most values are single-source**, usually ModularGrid (user-maintained). The two-source rule is the exception, not
  the norm. Each page shows which is which.
- **"Function" descriptions come from listing text** surfaced by web search, not from manuals.
- **Some figures are inferred** (passive or jacks-only modules at 0 mA), labelled as such.
- **+5V and depth are often not stated**, so the +5V total is a lower bound.
- **Draw figures are published maximums or typical values**, not measurements. The NiftyCASE labels its rail outputs
  "peak"; a footnote explaining that was not found on its page.
- **The budget assumes every in-use module is installed at once.** Which module sits in which case, and which supply
  feeds it, is not recorded. The modules also total more width than the recorded case space, so at least one more
  case or rack exists.
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

- Which modules are actually installed together, in which case, on which supply?
- Where is the additional case or rack that holds the modules beyond the NiftyCASE's 84 HP?
- Should Eurorack modules get golden questions and be added to the retrieval corpus?
- Would a plain-language summary or aliases per page fix the vocabulary-mismatch misses?
