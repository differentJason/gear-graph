#!/usr/bin/env python3
"""Check midi_channels.yaml against inventory.yaml and connections.yaml. Exit code 1 on any ERROR.

    .venv/bin/python tools/validate_midi.py

Errors : unknown device/setup, an `in`/`out` value outside {1-16, omni, off}, a non-bool thru_pass_enabled, an
         unknown status, a confirmed entry with no date, the same (setup, device) recorded twice.
Warnings: unconfirmed entries (excluded from conclusions), a device with a channel recorded but no `medium: midi`
          entry anywhere in connections.yaml ("not wired" is not the same as "not MIDI-capable" -- connections.yaml
          is known to be incomplete), a device whose manual text (when present, local-only) never mentions "MIDI".
"""
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHANNELS = {*range(1, 17), "omni", "off"}
OUT_CHANNELS = {*range(1, 17), "off"}
STATUSES = {"confirmed", "unconfirmed"}


def norm(s):
    return " ".join(s.lower().replace("“", '"').replace("”", '"').replace("’", "'").split())


def main():
    inv = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    conn = yaml.safe_load((ROOT / "connections.yaml").read_text())
    setups = {s["id"] for s in conn.get("setups", [])}
    midi_wired = {l[k] for l in conn.get("links", []) if l.get("medium") == "midi" for k in ("from", "to")}

    m = yaml.safe_load((ROOT / "midi_channels.yaml").read_text()) or {}
    channels = m.get("channels", [])
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    seen = defaultdict(int)
    for n, c in enumerate(channels, 1):
        tag = f"entry {n} ({c.get('device')})"
        if c.get("device") not in inv:
            err(f"{tag}: device {c.get('device')!r} is not in inventory.yaml")
        if c.get("setup") not in setups:
            err(f"{tag}: unknown setup {c.get('setup')!r}")
        if "in" in c and c["in"] not in CHANNELS:
            err(f"{tag}: in {c['in']!r} not one of 1-16, 'omni', 'off'")
        if "out" in c and c["out"] not in OUT_CHANNELS:
            err(f"{tag}: out {c['out']!r} not one of 1-16, 'off'")
        if "thru_pass_enabled" in c and not isinstance(c["thru_pass_enabled"], bool):
            err(f"{tag}: thru_pass_enabled {c['thru_pass_enabled']!r} is not true/false")
        if c.get("status") not in STATUSES:
            err(f"{tag}: status {c.get('status')!r} not one of {sorted(STATUSES)}")
        if c.get("status") == "confirmed" and not c.get("confirmed"):
            err(f"{tag}: confirmed entry has no `confirmed:` date")
        if c.get("status") == "unconfirmed":
            warn(f"{tag}: unconfirmed, so it is excluded from conclusions")
        key = (c.get("setup"), c.get("device"))
        seen[key] += 1
        if seen[key] == 2:
            err(f"device {c.get('device')} is recorded twice for setup {c.get('setup')}")

        if c.get("device") in inv and c.get("device") not in midi_wired:
            warn(f"{tag}: no medium: midi entry for this device in connections.yaml "
                 "(not wired is not the same as not MIDI-capable; connections.yaml may simply be incomplete)")

    checked = found = unchecked = 0
    manuals = ROOT / "docs" / "manuals"
    if manuals.exists():
        by_device = defaultdict(list)
        for man in yaml.safe_load((ROOT / "tools" / "manifest.yaml").read_text())["manuals"]:
            by_device[man["device"]].append(man["id"])

        def text(device):
            return norm(" ".join(f.read_text(encoding="utf-8") for mid in by_device[device] for f in (manuals / mid).glob("*.md")))

        for c in channels:
            dev = c.get("device")
            if dev not in inv:
                continue
            if dev not in by_device:
                unchecked += 1
                continue
            checked += 1
            if "midi" in text(dev):
                found += 1
            else:
                warn(f"device {dev}: its manual text never mentions MIDI")

    for w in warnings:
        print("WARNING", w)
    for e in errors:
        print("ERROR  ", e)
    if manuals.exists():
        print(f"  manual cross-check: {found} of {checked} devices mention MIDI in their manual text; "
              f"{unchecked} on devices with no ingested manual (not checked)")
    else:
        print("  manual cross-check: not checked (docs/manuals/ is local-only and not present)")
    print(f"checked {len(channels)} midi_channels.yaml entries: {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
