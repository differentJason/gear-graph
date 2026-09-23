"""Render midi_channels.yaml as a one-page quick reference (a channel-by-channel table), shared by build_site.py and
build_public.py. Reads only midi_channels.yaml + inventory.yaml; the channel plan itself lives in the YAML."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# channels a device occupies beyond its recorded `in` (the Timbre Wolf's voices 2-4 answer on the next three channels)
EXTRA = {"akai-timbre-wolf": 3}
# reserved for a device whose channel is not (yet) recorded as settable
RESERVED = {}


def markdown(setup="main-studio"):
    names = {i["id"]: i["name"] for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    rows = [c for c in yaml.safe_load((ROOT / "midi_channels.yaml").read_text())["channels"] if c.get("setup") == setup]
    by_ch = {}
    for c in rows:
        ch = c.get("in") if isinstance(c.get("in"), int) else c.get("out") if isinstance(c.get("out"), int) else None
        if ch is None:
            continue
        by_ch[ch] = (c, "")
        for k in range(1, EXTRA.get(c["device"], 0) + 1):
            by_ch[ch + k] = (c, f"voice {k + 1}")
    for ch, dev in RESERVED.items():
        by_ch.setdefault(ch, (next((c for c in rows if c["device"] == dev), {"device": dev}), "reserved"))

    def cell(v):
        return "-" if v is None else str(v)

    out = ["# MIDI channels", "",
           "Every instrument keeps one **home channel** for good. When you swap gear, change the *trigger source's* "
           "output channel (for example a Digitakt MIDI track), never the instrument. Audio follows the slot: gear "
           "swapped in takes the interface input of what it replaced.", "",
           "| Ch | Instrument | In | Out | Set it here / notes |", "|---|---|---|---|---|"]
    for ch in range(1, 17):
        if ch not in by_ch:
            out.append(f"| {ch} | *spare* | | | |")
            continue
        c, tag = by_ch[ch]
        name = names.get(c["device"], c["device"]) + (f" ({tag})" if tag else "")
        if tag:
            out.append(f"| {ch} | {name} | | | {'held for it' if tag == 'reserved' else 'part of the block above'} |")
            continue
        note = ((f"*{c['role']}.* " if c.get("role") else "") + c.get("note", "")).replace("|", "/")
        if c.get("status") != "confirmed":
            note = "**unconfirmed.** " + note
        out.append(f"| {ch} | {name} | {cell(c.get('in'))} | {cell(c.get('out'))} | {note} |")
    loose = [c for c in rows if not isinstance(c.get("in"), int) and not isinstance(c.get("out"), int)
             and c["device"] not in RESERVED.values()]
    if loose:
        out += ["", "**Not on a home channel of its own** (no settable channel; keep each on its own MIDI line)", ""]
        out += [f"- **{names.get(c['device'], c['device'])}** ({c.get('in') or c.get('role') or 'no channel'}): {c.get('note', '')}" for c in loose]
    out += ["", "Generated from `midi_channels.yaml`. Channel 10 is the RD-9's drums; nothing else listens on it."]
    return "\n".join(out)
