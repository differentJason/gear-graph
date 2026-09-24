"""Shared helpers: where the gear-kb lives (config.yaml) and YAML loading. The KB is only ever READ."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def kb_path():
    env = os.environ.get("GEAR_KB")
    raw = env or load_yaml(ROOT / "config.yaml").get("kb_path", "~/gear-kb")
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():                     # e.g. ".." -- relative to this app, not the working dir
        path = (ROOT / path).resolve()
    if not (path / "inventory.yaml").is_file():
        raise SystemExit(f"gear-kb not found at {path} (set kb_path in config.yaml or GEAR_KB)")
    return path


RACK, RACK_IN, RACK_OUT = "eurorack", "eurorack-in", "eurorack-out"


def mirror_rack_io(devices):
    """The rack's boundary jacks, seen from inside: a rack INPUT is an output of the 'Rack inputs' node (the signal
    enters the patch there) and a rack OUTPUT is an input of 'Rack outputs'. Re-derived whenever the Eurorack's jacks
    change (including your ports.yaml edits), so the two levels can never disagree."""
    by_id = {d["id"]: d for d in devices}
    rack = by_id.get(RACK)
    if not rack:
        return
    visible = [p for p in rack["ports"] if not p.get("hidden")]
    if RACK_IN in by_id:
        by_id[RACK_IN]["ports"] = [{**p, "dir": "out"} for p in visible if p["dir"] == "in"]
    if RACK_OUT in by_id:
        by_id[RACK_OUT]["ports"] = [{**p, "dir": "in"} for p in visible if p["dir"] == "out"]
