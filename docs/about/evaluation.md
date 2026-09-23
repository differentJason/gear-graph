---
title: Retrieval evaluation
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-23
---

# Retrieval evaluation

## Question being asked

If an agent searches this knowledge base, does it find the right page, and which structuring choices help?
Retrieval is scored on its own first, with no language model involved, because a question cannot be answered well
if the right page is never retrieved.

## Method

- **Corpus:** the converted manual sections (the run below covered 6 manuals, 198 pages, 633 chunks; Eurorack pages
  were not yet in the corpus).
- **Retriever:** a small BM25 keyword index written with the Python standard library. It is a **baseline**, not a
  search product; results say nothing about other search systems.
- **Golden set:** `evals/golden.jsonl`, 22 questions written from the content, each with the page(s) that answer it.
  17 are answerable; 5 are unanswerable or have a false premise (for example asking about a feature the manual
  never mentions). The unanswerable ones test whether a system can say "I don't know".
- **Metrics:** hit@k (an expected page is in the top k) and MRR (mean reciprocal rank of the first expected page),
  on the 17 answerable questions.
- **Variants:** what gets indexed alongside the page text. Each variant changes one thing.
- **Tool:** a standard-library notebook (`kb_eval_starter`), kept outside this repository, designed so a real search
  backend can replace the two retrieval functions later.

## Results (2026-09-20, 17 answerable questions)

| Variant | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| Baseline: page text, title and heading path | 0.41 | 0.71 | 0.82 | 0.575 |
| + index manufacturer, model and device fields | 0.59 | 0.82 | 0.88 | 0.711 |
| + also index the tags | 0.59 | 0.82 | 0.88 | 0.701 |

## What the results say (and do not)

- **Metadata helped.** Adding device identity to the index improved five questions and made one slightly worse.
  With 17 questions, treat this as a lead worth re-testing, not a settled result.
- **The tags added nothing** beyond that. They are keyword-derived and over-broad (see [Limitations](limitations.md)).
- **A vocabulary mismatch is a content problem, not a search bug.** "What outputs are on the *back* of the RD-9?"
  missed, because the manual only ever says "rear panel"; the right page contains zero occurrences of "back".
  Rephrased with "rear panel" it ranks second. Keyword search cannot bridge synonyms. A plain-language summary or
  alias list per page is the obvious next experiment.
- **One miss was the test's fault.** "Does the Analog Four have CV outputs?" accepted only one page, but three pages
  legitimately answer it. The label was left unedited on purpose, and recorded as too strict.
- **Retrieval cannot abstain.** For the five unanswerable questions it still returned pages with confident scores
  (the MPK mini "velocity curve" question returned the MPK features page at a score of 24.9, though no such information
  exists). Deciding "the answer is not here" needs either a score threshold, device-name filtering, or a model.

## Not yet done

- The answer-quality stage (groundedness, relevance, correctness, abstention judged by a language model) is written but
  has only been run against a fake model to test the plumbing. No claim is made about answer quality.
- The Eurorack pages have no golden questions yet (a natural first one: "will the supplies cover everything?").

## Pitfalls in measuring retrieval

What this evaluation ran into, and what it suggests for any retrieval test:

- **Small numbers move a lot.** With 17 questions, one question is about 6 points of hit@k. A change that moves one
  or two questions is a lead, not a result. Report how many questions moved in each direction, not just the average.
- **Change one thing per run.** Each variant above changes one indexing choice, which is why "metadata helped, tags did
  not" can be said at all.
- **The labels can be wrong.** One miss was a too-strict expected answer. It was recorded and left unedited, because
  editing labels after seeing results makes a test flatter the system.
- **Unanswerable questions are part of the test.** A retriever always returns *something*, often with a confident
  score; without questions whose correct answer is "not here", that failure mode stays invisible.
- **Vocabulary mismatch is a content problem.** The "back" vs "rear panel" miss cannot be fixed by the ranking
  function. The terminology layer ([How the terminology was built](terminology.md)) records exactly this kind of
  synonym (for example *EG* = *envelope*, *phones* = *headphone*), so expanding queries with its alternative labels is
  a natural experiment. **It has not been run**, so no improvement is claimed; note that "back" is not yet in the
  terminology at all.

## Re-running

Point the notebook's `DOCS_ROOT` at `docs/manuals`, keep `golden.jsonl` beside it, and run the retrieval cells.
Change one knob per run, save each run, and compare (`compare_runs`). Any change to the corpus or structure should be
re-measured before it is trusted.
