#!/usr/bin/env bash
# Live demo: give an agent one fact (the RD-9's MIDI OUT channel) and watch it work out a MIDI
# channel configuration for the rest of the studio from the knowledge base -- not from guessing.
#
# Usage:
#   demo/suggest_midi_config.sh <rd9-out-channel 1-16>
#
# What this shows an audience:
#   1. The agent reads connections.yaml to find the actual wiring (the RD-9 -> MIDI Thru5 fan-out)
#      instead of assuming it.
#   2. It reasons about a real constraint: a MIDI Thru5 is a dumb splitter with no filtering, so
#      every device on it gets the identical stream -- only a device listening on the RD-9's
#      channel (or omni) will respond.
#   3. It writes its proposal into midi_channels.yaml as `status: unconfirmed` with its reasoning
#      in a `note` field -- it does NOT claim to know the owner's actual preference. This is the
#      same "unknown stays unknown" discipline documented in docs/about/decisions.md (D8, D22).
#   4. It runs the repo's own validator on what it wrote, live, and fixes anything that fails.
#
# After the agent finishes, run the independent check (see the printed instructions at the end) --
# that second step is the point of decision D21: "a graph query that only agrees with itself
# proves nothing." The agent's proposal and the graph's cross-check are two separate pieces of code
# reaching the same, or a different, answer.
#
# Requires: the Claude Code CLI (`claude`), invoked from anywhere -- this script cd's into the repo.

set -euo pipefail

CH="${1:?Usage: demo/suggest_midi_config.sh <rd9-out-channel 1-16>}"
if ! [[ "$CH" =~ ^([1-9]|1[0-6])$ ]]; then
  echo "Channel must be 1-16, got: $CH" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROMPT="$(cat <<EOF
You are looking at the gear-kb repo: a personal Eurorack/music-gear knowledge base with a
documented data discipline (read docs/about/decisions.md D8 and D22 if you want the full context,
but the short version is: never state something as fact unless it is actually recorded or
confirmed; unknown stays unknown).

Before doing anything else, read these three files in full:
  - connections.yaml   (how the gear is actually wired -- do not assume, read it)
  - inventory.yaml     (device names and ids)
  - midi_channels.yaml (the schema and discipline for recording MIDI channel settings, plus any
                         entries already there -- read its header comment carefully)

Task: the Behringer RD-9's MIDI OUT is set to channel ${CH}. Find, from connections.yaml, exactly
which devices are wired downstream of the RD-9 over MIDI (it feeds a MIDI Thru5 box). A MIDI Thru5
is a dumb 1-in/5-out splitter with no filtering or channel translation: every device connected to
it receives the *exact same* MIDI stream the RD-9 sends. Only a device listening on channel ${CH}
(or set to omni) will actually respond to it right now.

Propose a MIDI IN channel for every device wired to that Thru5, following these rules:
  1. Pick exactly ONE of those devices to be reachable by the RD-9 right now, and say which one
     and why (e.g. "it's the one most useful to trigger live" -- your call, explain it). Assign it
     IN channel ${CH}.
  2. Give every other device on that Thru5 a distinct channel, different from ${CH} and from each
     other, so none of them respond to the RD-9 by accident right now -- but each is ready to be
     addressed individually later just by changing the RD-9's output channel to match it.
  3. Append your proposal to midi_channels.yaml as new entries with status: unconfirmed and a
     note field explaining your reasoning for that specific channel choice. Do not touch or
     overwrite any entry that is already status: confirmed. Do not invent a channel for a device
     that isn't actually wired to the Thru5 per connections.yaml.
  4. Run '.venv/bin/python tools/validate_midi.py' yourself when you're done and fix anything it
     flags as an ERROR before finishing.

Narrate your reasoning as you go -- this is being shown to a team live. When you're done, show a
diff of exactly what you changed in midi_channels.yaml.
EOF
)"

echo "############################################################################"
echo "# Asking the agent to propose a MIDI configuration for RD-9 OUT channel ${CH}"
echo "############################################################################"
echo

claude -p "$PROMPT"

echo
echo "############################################################################"
echo "# Now cross-check it: does the graph agree with itself for the wrong reason,"
echo "# or does an INDEPENDENT check of the same proposal come out clean?"
echo "############################################################################"
echo "Run these two commands next (separate from the agent, plain deterministic code):"
echo
echo "  .venv-graph/bin/python tools/build_graph.py    # rebuild the graph from the new midi_channels.yaml"
echo "  .venv-graph/bin/python tools/query_graph.py    # q7 (midi_conflicts) reports any channel collisions,"
echo "                                                  # checked by code that never touches the graph"
