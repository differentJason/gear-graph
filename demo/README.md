# Demo: an agent proposing a MIDI configuration

Run in front of the team:

```bash
demo/suggest_midi_config.sh 10
```

(`10` is the RD-9's MIDI OUT channel — swap in whatever number you want to demo with.)

## What happens

1. The script hands Claude Code one fact — the RD-9's output channel — and a pointer to three files
   to read first: `connections.yaml` (actual wiring), `inventory.yaml` (device names), and
   `midi_channels.yaml` (the schema + discipline for this fact type, see its header comment and
   `docs/about/decisions.md` D8/D22).
2. The agent works out, from the real wiring, which devices sit on the RD-9 → MIDI Thru5 fan-out,
   reasons about the fact that a Thru5 is a dumb, unfiltered splitter (so only a device listening
   on the RD-9's channel actually responds), and proposes a channel for each device on it.
3. It writes its proposal into `midi_channels.yaml` itself, as `status: unconfirmed` entries with
   its reasoning in a `note` — it does not claim to know your actual preference, and it will not
   touch any entry already marked `confirmed`.
4. It runs `tools/validate_midi.py` on its own output before finishing, live, and fixes anything
   that fails.

You'll be prompted to approve each file edit and command Claude Code wants to run — leave that on;
it's worth narrating to the team as the point, not a nuisance. **This is the same "unknown stays
unknown" discipline** the whole project is built on (see the demo deck's provenance/trust slide),
just applied live instead of quoted from documentation.

## Then: the cross-check (the second half of the demo)

Decision D21 in `docs/about/decisions.md`: *"a graph query that only agrees with itself proves
nothing."* Don't just take the agent's word for it — run the same two commands the project's own
pipeline uses, completely separate from the agent that just ran:

```bash
.venv-graph/bin/python tools/build_graph.py   # rebuild the graph from the new midi_channels.yaml
.venv-graph/bin/python tools/query_graph.py   # q7 (midi_conflicts) reports channel collisions,
                                               # checked by code that never touches the agent's output
```

If the agent did its job, `q7` should report no conflicts (or, if you deliberately asked for
layering, an intentional one it should have called out). This is the moment to make explicit to
the team: an LLM's answer and a piece of independent, boring, deterministic code both had to agree
before anyone should trust this.

## Resetting between runs

The proposal is appended to `midi_channels.yaml` as `unconfirmed` entries, so it's easy to see
exactly what the agent added (`git diff midi_channels.yaml`). To reset for a second live run:

```bash
git checkout -- midi_channels.yaml
```

(That's the only file this demo writes to.)
