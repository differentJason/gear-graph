# Knowledge graph (PySpark + GraphFrames)

Status: **builder written (`tools/build_graph.py`); the power budget is computed from the graph.** Remaining plan items are below. Decision D18 in
[`docs/about/decisions.md`](../docs/about/decisions.md).

The graph is **derived**. `inventory.yaml`, `connections.yaml`, `midi_channels.yaml`, `eurorack/`, `tools/manifest.yaml`,
`VOCAB.yaml`, `evals/golden.jsonl` and the converted manual sections are the sources; the graph is rebuilt from them
and never edited by hand, like `docs/eurorack/`.

## Environment

```bash
python3 -m venv .venv-graph && .venv-graph/bin/pip install -r requirements-graph.txt   # needs a JDK 17/21
.venv-graph/bin/python graph/check_env.py                                              # must print three "ok" lines
```

Kept separate from `.venv` on purpose: the site build and CI do not need a JVM. Use `graphframes-py`, not `graphframes`
(a 2018 stub). This is more machinery than a few hundred nodes need; it was chosen as a learning exercise, and the
same graph would fit in plain Python.

## Schema (property graph)

Vertices: `id`, `type`, `name`, `visibility`, plus sparse property columns. Edges: `src`, `dst`, `rel`, plus properties.

| Vertex `type` | Source | Visibility |
|---|---|---|
| `item` (device, module, supply, case, software; a case also carries `rows`, e.g. `1U:84,3U:84,3U:84`; an item with a recorded MIDI setting also carries `midi_in_ch`, `midi_out_ch`, `midi_thru_pass`, `midi_status`, `midi_confirmed`) | `inventory.yaml`, `connections.yaml`, `midi_channels.yaml` | public |
| `manufacturer`, `category` | `inventory.yaml` | public |
| `spec` (one item + one field, with `value`, evidence `status`, and `attested` if the owner has attested it) | `eurorack/` | public |
| `source` (a URL with a `tier`: official / retailer / community) | `eurorack/sources.yaml` | public |
| `manual` (title, doc type, version; not its text) | `tools/manifest.yaml` | public |
| `tag` | `VOCAB.yaml` | public |
| `question` | `evals/golden.jsonl` | public |
| `section` (one manual section) | converted manuals | **private**: derived from copyrighted text |

| Edge `rel` | From → to | Properties |
|---|---|---|
| `MADE_BY`, `IN_CATEGORY` | item → manufacturer / category | |
| `HAS_MANUAL` | item → manual | |
| `HAS_SECTION` | manual → section | private |
| `TAGGED` | section → tag | private |
| `HAS_SPEC` | item → spec | |
| `CONSULTED` | item → source | `http` (a 403 page was consulted but could not be read) |
| `SOURCED_FROM` | spec → source | `value`, `line` (the exact source text), so provenance is queryable |
| `CONNECTS` | item → item | `setup`, `medium`, `from_port`, `to_port`, `status` (from `connections.yaml`) |
| `INSTALLED_IN`, `POWERED_BY` | module → case / supply | `setup`, `status` (from `connections.yaml`) |
| `EXPECTS` | question → section | private (endpoint is private) |

**Visibility rule:** an edge is public only if both endpoints are. The public export is built by filtering, not by
hand-picking, so a new private node type cannot leak by omission.

## Outputs

| Path | Contents | In git? |
|---|---|---|
| `graph/out/` | full graph (Parquet), including manual-derived nodes | no (git-ignored) |
| `graph/public/vertices.json`, `edges.json` | public subgraph, a committed snapshot like `data/*.json` | yes |
| `graph/public/budget.json` | per-supply power load computed from the graph, with a digest of the inputs it used; read by `build_eurorack.py`, which refuses it if stale | yes |

Pages CI reads the committed snapshot and never runs Spark.

## Build plan

1. ~~**Vertices and edges from existing data**: `tools/build_graph.py`~~ (done).
2. **Routing layer**: `connections.yaml` filled for the main studio; `tools/validate_connections.py` checks ids, statuses, placement and
   case capacity. Still to add: check that every named port appears in that device's manual text, with misses reported.
3. **Graph checks in the validator style**: done in `build_graph.py` (unique ids, no dangling edge endpoints, no private node in the public export, leak scan over `graph/public/`). Not done: orphan-vertex report.
4. ~~**Query tests**: like `evals/golden.jsonl`, a small set of questions with known answers, run against the graph.~~ Done: `evals/graph_golden.yaml` and `tools/query_graph.py`; each answer is checked by hand-written expectation or by an independent implementation over the raw files.
5. ~~**Visualisation** on the public site from the committed snapshot.~~ Done: `tools/viz_graph.py` draws five views (schema, category composition, wiring, a hop-distance "reach" panel, rack) on the public `visuals/graph.md` page from `graph/public/*.json` only. The reach panel (`routing_diagram(..., root=<id>)`) computes hop distance over confirmed edges with a plain BFS, no Spark -- the same rule `query_graph.py`'s `reach()` uses, so the picture and q2's table agree by construction, not by re-checking.

## Questions the graph should be able to answer (acceptance tests)

1. What is downstream of the RD-9, and by which medium (audio, MIDI, clock)? (**done**: q1, q2)
2. Which modules draw from the same supply, and what is each supply's load? (**done**: this is how the power budget is computed)
3. Which specs rest on one community source only? (`spec` with one `SOURCED_FROM` edge, tier = community) (**done**: q5)
4. Which items have no recorded connection? (the honest answer is "not recorded", not "unconnected") (**done**: q6)
5. Everything that receives clock, directly or through other devices (GraphFrames `shortestPaths` on the reversed graph). (**done**: q2)
6. Which manual section describes the port on this cable? (private-only; partly done: `validate_connections.py` checks that each named port appears in the device's manual text)
7. Do any devices fed MIDI through a shared fan-out share the same recorded IN channel? (**done**: q7, `midi_conflicts`)

## Known limits, to be stated in the docs when the graph lands

- Only **confirmed** connections count in conclusions; `unconfirmed` ones are drawn differently and excluded from queries.
- The graph inherits the source data's trust levels; it cannot make a single-source spec more certain.
- Tags are keyword rules, so `TAGGED` edges are only as good as those rules.
- MIDI channel settings (`midi_channels.yaml`) are recorded **per device**, not per internal parameter: a device with
  several independent MIDI channels (e.g. Elektron's per-track/AUTO/PERF/program-change channels) has only its
  single most relevant live-performance channel recorded, named in that entry's `role:` field. The graph cannot
  answer "what channel does track 3 listen on."
- A "thru channel" is not tracked, because for this rack's gear it is not a coherent concept: a hardware MIDI thru
  jack re-sends every byte unchanged (no channel), and where a device does have a soft-thru toggle (Donner B1) it is
  an on/off routing choice, not a channel. `midi_channels.yaml` records `thru_pass_enabled: true/false` instead.
- `midi_in_ch`/`midi_out_ch` are stored as one item-vertex property each, so a device can carry at most one setup's
  worth of MIDI settings today. There is currently only one setup (`main-studio`); if a second setup ever needs its
  own MIDI channels for the same device, this would need to become a per-(setup, item) fact, the way `CONNECTS`
  already is.
