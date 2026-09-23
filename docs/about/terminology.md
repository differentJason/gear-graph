---
title: How the terminology was built
doc_type: project-doc
content_status: hand-authored
updated: 2026-09-23
---

# How the terminology was built

This page records how the terminology layer (`TERMS.yaml` → `tools/build_terms.py` → `graph/public/terms.json` → the
graph and the public site's *Terminology* page, under Visual explanations) was made, and the pitfalls that came up while making it. Most
of the pitfalls below actually happened on this project; they are the kind of problem to look for whenever a
vocabulary is built from real documents.

Built by the AI coding assistant at the owner's request (decision D23). **The owner has not yet reviewed the concept
list**, so treat the model as a draft that passes its checks, not as settled.

## What was built

| Part | What it is |
|---|---|
| `TERMS.yaml` | The source of truth, written by hand: 8 facets (top classes), 119 concepts, 9 relation types with domain and range, 48 relation statements, 6 homographs, 1 stop phrase |
| `tools/build_terms.py` | Checks the taxonomy and ontology rules, then counts every label in the converted manuals (numbers only) into `graph/public/terms.json` |
| `tools/build_graph.py` | Adds `term` nodes and `BROADER`, `CLOSE_MATCH`, `UNDER_TAG`, `USES_TERM` and the typed-relation edges to the graph |
| `tools/query_graph.py` | q8 (which concepts makers name differently) and q9 (which devices document a modulator of filter cutoff, including narrower kinds), each cross-checked by separate code that does not use the graph |
| `tools/viz_terms.py` | The taxonomy tree, the class-level ontology diagram, the filter worked example and the naming heatmap |

## The process, in order

1. **Look at the text before modelling it.** A throwaway script counted about 240 candidate words across all 24
   manuals, per manual. Each concept went into `TERMS.yaml` only after it had been seen in the text. The same counts
   showed the vendor differences (EG vs envelope, HPF vs highpass, trig vs step) before any model existed.
2. **Write the scheme in a SKOS-like shape.** The `pref`/`alt` labels, `broader` and `close` fields are borrowed from
   the SKOS standard for thesauri. The typed relations and their domain/range rules are the small ontology part.
3. **Write the checker, then break it on purpose.** Deliberate errors were introduced one at a time: a domain
   violation, a cycle, a label shared by two concepts, an unknown tag, a close match that duplicates a hierarchy link,
   a concept reaching two facets, a homograph that is also a concept label, and an invented term ("flux capacitor").
   Each one failed the build with the right message (one only after it was redone: pitfall 13). The first run had
   passed everything, and a first run that passes proves nothing until the checks have been seen to fail.
4. **Count, then read the counts.** A few surprising numbers were checked in the manual text itself (see pitfalls 5 and 6).
5. **Put it in the graph and ask it questions.** Each answer is checked by separate code that reads the raw files.
   Both checks were broken on purpose too: removing one `BROADER` edge and one `USES_TERM` edge from the snapshot made
   q9 and q8 fail.
6. **Draw it, then look at the drawings.** Screenshots in light and dark mode showed overlapping labels and text that
   was too small, which no automated check catches.
7. **Sanity-check the headline claims against the numbers underneath.** That step caught the worst error (pitfall 4).

## Pitfalls, and what caught each

| # | Pitfall | What happened here | Caught by | Fix |
|---|---|---|---|---|
| 1 | **Homographs**: one word, two meanings | *HP* is high-pass in the Elektron manuals and panel width in Eurorack. *Pad* is a drum pad on the controllers but an input attenuation switch on the audio interfaces. *Pad* was first modelled as a controller. | Counting where each word occurs, per manual, and asking why the audio-interface manuals use it | A `homographs` list: counted, assigned to no concept, senses stated |
| 2 | **Overlapping labels counted twice** | *sub oscillator* contains *oscillator*; *gate length* and *gate output* contain *gate* | Designed in from the start | Leftmost-longest matching: one pass, longest label first |
| 3 | **Collapsing things that are only similar** | A VCO is a *kind* of oscillator, not a synonym. An Elektron *trig* is an event on a step, not the step. *BPM* is the unit of tempo. Treating any of these as synonyms would make the makers look more alike, or less alike, than they are. | Modelling judgement | Three separate relations: `alt` (same concept), `broader` (a kind of), `close` (related but different) |
| 4 | **A tie-break that invented a finding** | Donner's manual uses *emphasis* and *resonance* once each. The first version broke ties alphabetically, reported "Donner says emphasis", and the page's opening sentence was built on that. | Checking the raw numbers behind the headline sentence | A tie is reported as a tie and decides nothing. The resonance example dropped out of the results, and the opening sentence now uses examples with clear majorities. |
| 5 | **Product feature names that contain a term** | 21 of Behringer's 26 *wave* hits were the RD-9's **Wave Designer** (a transient shaper), not waveforms. That was enough to flip Behringer's most-used word for waveform. | Reading a suspicious count in context | A `stop_phrases` list: matched first, never counted |
| 6 | **Conversion artefacts** | A lowercase *eg* left over from a converted spec table made a studio-monitor manual appear to use *EG* (envelope generator) | Reading a suspicious count in context | Two-letter abbreviations are not counted when written all-lowercase |
| 7 | **A fix that also removed real matches** | The first fix for pitfall 6 matched *all* abbreviations case-sensitively. It also dropped real uses: title-cased headings like "Lfo Shapes" and plain "120 bpm". | Diffing every count before and after the fix, not just the one being fixed | Narrowed the rule to two-letter abbreviations. The diff then showed only the two intended changes. |
| 8 | **Relations that pass the rules but are wrong** | A draft statement, "amplifier modulates velocity", had the direction backwards. Domain and range allowed it (a block modulating a parameter is legal). | Re-reading the statements | Removed. Domain/range rules catch *category* errors, not wrong facts inside allowed categories; only review catches those. |
| 9 | **Invented terms** | A plausible-sounding concept can slip in without being in any manual | The grounding check (tested with "flux capacitor") | Every non-grouping concept must occur in at least one manual |
| 10 | **Everyday words** | *release*, *step*, *trigger* also have ordinary meanings ("release the key", "firmware release") | Known limit | Counts are stated as upper bounds, with notes on the concepts |
| 11 | **Missing metadata** | The MIDI Thru5's maker is unconfirmed in the inventory, and the naming query crashed on it | The query crashing | Reported as "maker not recorded". The manual manifest lists CME, but the inventory records only what the owner has confirmed, and the query follows the inventory. |
| 12 | **Stale derived data** | Rebuilding the graph added 18 manual nodes that should have been there already: the committed snapshot had not been rebuilt after those manuals were ingested | Diffing the snapshot before and after (0 old nodes or edges changed, 145 nodes added: 127 terms and those 18 manuals) | Rebuilt. `build_graph.py` and `build_public.py` now refuse a `terms.json` that is stale for `TERMS.yaml`. |
| 13 | **A test that fails for the wrong reason** | The first "close match duplicates a hierarchy link" test pointed at a facet, so it failed with "does not exist" and never reached the rule it was meant to test | Reading the failure message, not just the exit code | Re-tested with a real ancestor (VCO close to oscillator); the intended message appeared |

## Lessons worth keeping

- **Frequency is evidence, not meaning.** A count says a string occurs; only reading it in context says what it means.
  Spot-check the surprising numbers.
- **Check the sentence, not just the data.** The worst error here (pitfall 4) passed every automated check. It sat in
  one tie-break and in the prose written on top of it.
- **Diff every output when fixing one input.** A narrow fix to the counting rules changed counts it was not meant to
  touch (pitfall 7).
- **Keep "same", "kind of" and "similar" apart.** Most arguments about a vocabulary are really about which of the three
  applies. Writing it down per concept makes the disagreement visible and reviewable.
- **Rules catch categories, people catch facts.** Domain and range stopped "filter carries MIDI", but "amplifier
  modulates velocity" needed a reader.
- **A check is only trusted once it has been seen to fail.** Every check here was broken on purpose at least once.

## Next step: owner review

Planned, not yet done. The owner will review `TERMS.yaml`; until then the scheme stays a draft. The review checklist:

1. **Same, kind of, or similar?** For each word pair, is it modelled the way the owner describes the gear? The pairs
   most worth a second look: *slide* / *glide*, *trig* / *step*, *ratchet* / *retrig* / *roll* / *flam*,
   *BPM* / *tempo*, *probability* / *trig condition*, *parameter lock* / *automation*.
2. **Relations.** Read the 48 statements (the table on the Terminology page) and mark any that are wrong, backwards
   or missing. The domain/range rules cannot catch a wrong fact inside an allowed category (pitfall 8).
3. **Homographs.** Are *HP*, *gate*, *patch*, *sound*, *pad* and *program* really two-sense words in this gear, and
   are any missing?
4. **Gaps.** Terms the owner uses at the rig that are absent, for example *back panel* (the retrieval miss in
   [Evaluation](evaluation.md)).
5. **Record the outcome.** Update D23's "who decided" column to say the owner reviewed it, and remove this section
   (and the matching open question in [Limitations](limitations.md)).

After any edit, rebuild in order: `build_terms` → `build_graph` → `query_graph` → `build_site` → `build_public`.

## How to change it

Edit `TERMS.yaml`, then run the chain in [the runbook](runbook.md): `build_terms.py` (needs the local manuals to
recount), then `build_graph.py`, `query_graph.py`, `build_site.py`, `build_public.py`. `build_terms.py --check` runs
the rules without the manuals (for example from a fresh clone), but cannot recount.
