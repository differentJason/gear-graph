"""Build data/gear.json (everything the app needs about the gear) from the gear-kb, READ-ONLY.

Inputs (all in the KB): inventory.yaml, connections.yaml (placements + the studio's fixed wiring), midi_channels.yaml
(home channels), graph/public/{vertices,budget}.json (specs, supply loads), tools/image_manifest.yaml (which devices
have an original gear-kb drawing -> icon), plus this repo's data/ports.seed.yaml (tools/extract_ports.py).

Your own port edits (ports.yaml) are NOT baked in here: the server overlays them on every /api/gear request
(common_ports.merge_ports), so edits made in the app show up without a rebuild.
"""
import datetime
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import RACK, RACK_IN, RACK_OUT, kb_path, load_yaml, mirror_rack_io  # noqa: E402

# palette groups, in display order: group -> categories
GROUPS = {
    "Synths & drum machines": ["synth", "drum-machine", "sampler-drum-machine", "groovebox"],
    "Eurorack": ["eurorack"],
    "Controllers & sequencers": ["controller", "sequencer"],
    "Eurorack modules": ["eurorack-module"],
    "Eurorack cases & power": ["eurorack-case", "eurorack-power"],
    "Interface, monitoring & computer": ["audio-interface", "monitors", "headphones", "computer", "software"],
    "MIDI & utility": ["midi-utility", "di-preamp", "pedal-utility"],
    "Pedals & amps": ["pedal-time", "pedal-modulation", "pedal-distortion", "pedal-wah", "pedal-eq", "pedal-synth", "amp"],
    "Instruments": ["guitar", "bass"],
}
GLYPH = {  # fallback icon per group when a device has no photo (icons/_glyph-<key>.svg, drawn by trace_icons.py)
    "Synths & drum machines": "synth", "Controllers & sequencers": "controller", "Eurorack": "case", "Eurorack modules": "module",
    "Eurorack cases & power": "case", "Interface, monitoring & computer": "interface", "MIDI & utility": "utility",
    "Pedals & amps": "pedal", "Instruments": "instrument",
}


def P(name, d, m):
    return {"name": name, "dir": d, "medium": m}


# category defaults: used only when the manuals gave no ports for a device (source: default)
DEFAULTS = {
    "synth": [P("Audio Out", "out", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi")],
    "drum-machine": [P("Main Out", "out", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi"),
                     P("Sync In", "in", "clock"), P("Sync Out", "out", "clock")],
    "sampler-drum-machine": [P("Main Out", "out", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi")],
    "groovebox": [P("Main Out", "out", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi")],
    "controller": [P("USB", "bidir", "usb"), P("MIDI Out", "out", "midi"), P("CV Out", "out", "cv"),
                   P("Gate Out", "out", "gate"), P("Clock In", "in", "clock")],
    "sequencer": [P("MIDI Out", "out", "midi"), P("CV Out", "out", "cv"), P("Gate Out", "out", "gate"),
                  P("Clock In", "in", "clock"), P("Clock Out", "out", "clock")],
    "eurorack-module": [P("In", "in", "audio"), P("CV In", "in", "cv"), P("Gate In", "in", "gate"), P("Out", "out", "audio")],
    "eurorack-case": [], "eurorack-power": [],
    "audio-interface": [P("Input 1", "in", "audio"), P("Input 2", "in", "audio"), P("Main Out L/R", "out", "audio"),
                        P("Phones", "out", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi"),
                        P("USB", "bidir", "usb")],
    "monitors": [P("Input", "in", "audio")], "headphones": [P("Input", "in", "audio")],
    "computer": [P("USB", "bidir", "usb")],
    "software": [P("Audio In", "in", "audio"), P("MIDI In", "in", "midi"), P("MIDI Out", "out", "midi")],
    "midi-utility": [P("MIDI In", "in", "midi")] + [P(f"MIDI Out {n}", "out", "midi") for n in range(1, 6)],
    "di-preamp": [P("Input", "in", "audio"), P("Output", "out", "audio")],
    "amp": [P("Input", "in", "audio"), P("Speaker Out", "out", "audio")],
    "guitar": [P("Output", "out", "audio")], "bass": [P("Output", "out", "audio")],
}
PEDAL = [P("Input", "in", "audio"), P("Output", "out", "audio")]


def group_of(category):
    for g, cats in GROUPS.items():
        if category in cats:
            return g
    return "MIDI & utility"


def unnamed_port(ports, direction, medium, used=()):
    """A port for a recorded cable whose jack the owner did not name: the first matching port not already used by
    another recorded cable (so the Thru5's five cables land on five outputs), else any match, else add one."""
    match = [p["name"] for p in ports if p["medium"] == medium and p["dir"] in (direction, "bidir") and not p.get("hidden")]
    for name in match:
        if name not in used:
            return name
    if match:
        return match[0]
    name = f"{medium.upper() if medium in ('midi', 'usb', 'cv') else medium.title()} {'In' if direction == 'in' else 'Out'}"
    ports.append({"name": name, "dir": direction, "medium": medium, "source": "connections",
                  "evidence": "connections.yaml records the cable but not the jack name"})
    return name


def resolve_links(links, devices, setup="main-studio"):
    """The KB's recorded cables for one setup, with every jack NAMED: unnamed ends get a device jack (or a new one).
    Resolved once for the whole setup so templates and auto-patching always agree on which jack a cable uses."""
    by_id = {d["id"]: d for d in devices}
    edges = [l for l in links if l.get("setup") == setup and l["from"] in by_id and l["to"] in by_id]
    used = defaultdict(set)
    for l in edges:  # named jacks first, so unnamed ones never take a jack a named cable uses
        if l.get("from_port"):
            used[l["from"]].add(l["from_port"])
        if l.get("to_port"):
            used[l["to"]].add(l["to_port"])
    out = []
    for l in edges:
        both = bool(l.get("bidirectional"))
        fp = l.get("from_port") or unnamed_port(by_id[l["from"]]["ports"], "bidir" if both else "out", l["medium"], used[l["from"]])
        tp = l.get("to_port") or unnamed_port(by_id[l["to"]]["ports"], "bidir" if both else "in", l["medium"], used[l["to"]])
        used[l["from"]].add(fp)
        used[l["to"]].add(tp)
        out.append({"from": l["from"], "from_port": fp, "to": l["to"], "to_port": tp, "medium": l["medium"],
                    "bidirectional": both, "confirmed": l.get("status") == "confirmed",
                    "swappable": bool(l.get("swappable")), "note": l.get("note", "")})
    return out


def layout(ids, links):
    """Left->right columns by signal depth (longest path); a computer sits one column right of its interface."""
    depth = defaultdict(int)
    for _ in range(len(links)):
        for l in links:
            if not l["bidirectional"]:
                depth[l["to"]] = max(depth[l["to"]], depth[l["from"]] + 1)
    for l in links:
        if l["bidirectional"]:
            depth[l["to"]] = max(depth[l["to"]], depth[l["from"]] + 1)
    rows, pos = defaultdict(int), {}
    for dev in sorted(ids, key=lambda i: (depth[i], i)):
        col = depth[dev]
        pos[dev] = (60 + col * 300, 40 + rows[col] * 230)
        rows[col] += 1
    return pos


RACK_CATS = {"eurorack-module", "eurorack-case"}   # what lives INSIDE the Eurorack device
WORD = {"audio": "Audio", "midi": "MIDI", "clock": "Clock", "cv": "CV", "gate": "Gate", "usb": "USB"}
# general-purpose rack jacks: gear-kb says the A4, SQ-64, KeyStep and K2 send CV/gate into "various module inputs"
GENERIC_RACK = ([P(f"CV In {i}", "in", "cv") for i in range(1, 5)] + [P(f"Gate In {i}", "in", "gate") for i in range(1, 5)]
                + [P("Audio In 1", "in", "audio"), P("Audio In 2", "in", "audio"), P("MIDI In", "in", "midi")]
                + [P("CV Out 1", "out", "cv"), P("CV Out 2", "out", "cv"), P("Gate Out 1", "out", "gate")])


def split_rack(resolved, devices):
    """Split the KB cables at the rack boundary. A cable between two rack members stays inside the rack; a cable
    crossing the boundary becomes TWO: outside gear <-> a proxy jack on the Eurorack device (session level), and the
    same proxy jack on 'Rack inputs'/'Rack outputs' <-> the module (rack level)."""
    by_id = {d["id"]: d for d in devices}
    members = {d["id"] for d in devices if d["category"] in RACK_CATS}
    ext, proxies, session_links, rack_links = [], {}, [], []

    def proxy(mod, port, direction, medium):
        key = (mod, port, direction)
        if key not in proxies:
            base = f"{WORD.get(medium, medium)} {'Out' if direction == 'out' else 'In'}" + (" L/R" if "L/R" in port else "")
            name, k = base, 2
            while any(p["name"] == name for p in ext):
                name, k = f"{base} {k}", k + 1
            proxies[key] = name
            ext.append({"name": name, "dir": direction, "medium": medium, "source": "connections",
                        "evidence": f"gear-kb cable at {by_id[mod]['name']} · {port}"})
        return proxies[key]

    for l in resolved:
        fi, ti = l["from"] in members, l["to"] in members
        if fi and ti:
            rack_links.append(l)
        elif not fi and not ti:
            session_links.append(l)
        elif fi:  # leaves the rack
            name = proxy(l["from"], l["from_port"], "out", l["medium"])
            session_links.append({**l, "from": RACK, "from_port": name})
            rack_links.append({**l, "to": RACK_OUT, "to_port": name})
        else:     # enters the rack
            name = proxy(l["to"], l["to_port"], "in", l["medium"])
            session_links.append({**l, "to": RACK, "to_port": name})
            rack_links.append({**l, "from": RACK_IN, "from_port": name})
    have = {p["name"].upper() for p in ext}
    ext += [{**g, "source": "default", "evidence": "general-purpose rack jack (CV/gate sources go to 'various module inputs')"}
            for g in GENERIC_RACK if g["name"].upper() not in have]
    return members, ext, session_links, rack_links


def graph(ids, links, settings=None, prefix="n"):
    """Nodes (laid out by signal depth) + cables for the given devices and the links among them."""
    chosen = set(ids)
    links = [l for l in links if l["from"] in chosen and l["to"] in chosen]
    pos = layout(ids, links)
    settings = settings or {}
    nodes = [{"uid": f"{prefix}-{i}", "device": i, "x": pos[i][0], "y": pos[i][1], "settings": dict(settings.get(i, {}))}
             for i in ids]
    cables = []
    for l in links:
        note = l["note"]
        if l.get("extra"):
            note = ("NOT recorded in gear-kb. " + note).strip()
        elif not l["confirmed"]:
            note = ("UNCONFIRMED in gear-kb. " + note).strip()
        cables.append({"from": {"uid": f"{prefix}-{l['from']}", "port": l["from_port"]},
                       "to": {"uid": f"{prefix}-{l['to']}", "port": l["to_port"]},
                       "medium": l["medium"], "settings": {"notes": note} if note else {}})
    return {"nodes": nodes, "cables": cables}


def rack_graph(member_ids, rack_links):
    """The patch inside a Eurorack node: Rack inputs, the given modules, Rack outputs, and the KB cables among them."""
    return graph([RACK_IN] + sorted(member_ids) + [RACK_OUT], rack_links, prefix="r")


def make_template(spec, resolved, devices, rack):
    """A New-session template: the listed devices (or every wired one) + the KB cables between them + extra links.
    Rack members listed (or wired) collapse into one Eurorack node whose inside patch holds them."""
    members, session_links, rack_links = rack
    by_id = {d["id"]: d for d in devices}
    ids = [i for i in (spec.get("devices") or sorted({l["from"] for l in resolved} | {l["to"] for l in resolved}))
           if i in by_id]
    missing = [i for i in spec.get("devices") or [] if i not in by_id]
    if missing:
        raise SystemExit(f"templates.yaml: unknown device ids {missing}")
    inside = [i for i in ids if i in members]
    outside = [i for i in ids if i not in members] + ([RACK] if inside or RACK in ids else [])
    outside = list(dict.fromkeys(outside))
    links = list(session_links)
    for x in spec.get("extra_links") or []:  # cables the KB does not record (always labelled as such)
        dev_f, dev_t = by_id[x["from"]], by_id[x["to"]]
        both = bool(x.get("bidirectional"))
        links.append({"from": x["from"], "to": x["to"], "medium": x["medium"], "bidirectional": both, "confirmed": False,
                      "from_port": x.get("from_port") or unnamed_port(dev_f["ports"], "bidir" if both else "out", x["medium"]),
                      "to_port": x.get("to_port") or unnamed_port(dev_t["ports"], "bidir" if both else "in", x["medium"]),
                      "note": x.get("note", ""), "extra": True})
    g = graph(outside, links, spec.get("settings"))
    for n in g["nodes"]:
        if n["device"] == RACK:
            n["rack"] = rack_graph(inside, rack_links)
    return {"name": spec["name"], "type": spec.get("type", "session"), "description": spec.get("description", ""),
            "notes": spec.get("notes", ""), **g}


def kb_commit(kb):
    try:
        head = subprocess.run(["git", "-C", str(kb), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(kb), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return (head + ("-dirty" if dirty else "")) or None  # -dirty: built from uncommitted KB edits
    except OSError:
        return None


def hp_of(dev_id, spec, name="", id_fallback=True):
    """Width in HP: the KB spec, else a width in the NAME (owner-corrected, e.g. "Jake's snare/hats (8HP)"), else one
    in the id (ids are never renamed, so 'jakes-snare-hats-6hp' can be stale), else unknown (the app draws 8)."""
    v = (spec.get("hp") or {}).get("value")
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    for text in ((name, dev_id) if id_fallback else ()):
        m = re.search(r"(\d+)\s*hp\b", text, re.I)
        if m:
            return int(m.group(1))
    return None


def panel_of(dev_id):
    for ext in ("jpg", "jpeg", "png", "webp"):
        if (ROOT / "images" / f"{dev_id}.{ext}").is_file():
            return f"panels/{dev_id}.{ext}"
    return None


def build():
    kb = kb_path()
    items = load_yaml(kb / "inventory.yaml")["items"]
    conn = load_yaml(kb / "connections.yaml")
    midi = load_yaml(kb / "midi_channels.yaml").get("channels", []) if (kb / "midi_channels.yaml").is_file() else []
    manifest = load_yaml(kb / "tools" / "image_manifest.yaml").get("images", [])
    vertices = json.loads((kb / "graph" / "public" / "vertices.json").read_text())
    budget = json.loads((kb / "graph" / "public" / "budget.json").read_text())
    seed_path = ROOT / "data" / "ports.seed.yaml"
    seeds = load_yaml(seed_path) if seed_path.is_file() else {}

    specs = defaultdict(dict)
    for v in vertices:
        if v.get("type") == "spec":
            dev, field = v["id"][len("spec:"):].rsplit(".", 1)
            specs[dev][field] = {"value": v.get("value"), "status": v.get("status")}
    placement = {p["module"]: p for p in conn.get("placements", []) if p.get("setup") == "main-studio"}
    channels = {c["device"]: c for c in midi if c.get("setup") == "main-studio" and c.get("status") == "confirmed"}
    has_photo = {m["device"] for m in manifest if (kb / m["file"]).is_file()}
    supply_load = {}
    for s in budget.get("setups", {}).get("main-studio", {}).get("supplies", []):
        supply_load[s["id"]] = {r: {"draw_ma": x.get("draw_ma"), "capacity_ma": x.get("capacity_ma"), "pct": x.get("pct")}
                                for r, x in s.get("rails", {}).items()}

    devices = []
    for it in items:
        cat, dev_id = it["category"], it["id"]
        group = group_of(cat)
        ports = [{"name": n, **p} for n, p in sorted((seeds.get(dev_id) or {}).items())]
        # category defaults fill any (direction, signal) the seeds do not cover, so a partial manual extraction
        # (e.g. an OCR'd rear panel that only yielded MIDI THRU) never leaves a synth without a MIDI In
        have = {p["name"].upper() for p in ports}
        covered = {(p["dir"], p["medium"]) for p in ports} | {(d, p["medium"]) for p in ports if p["dir"] == "bidir"
                                                               for d in ("in", "out")}
        for d in (PEDAL if cat.startswith("pedal") else DEFAULTS.get(cat, [])):
            # coverage counts only manual/wiring jacks: a default set may hold several of one kind (Thru5 Out 1-5)
            if d["name"].upper() not in have and (d["dir"], d["medium"]) not in covered:
                ports.append({**d, "source": "default", "evidence": f"default for category '{cat}' (not found in the manual)"})
        facts = {}
        for field, s in sorted(specs.get(dev_id, {}).items()):
            facts[field] = s
        pl = placement.get(dev_id)
        ch = channels.get(dev_id)
        devices.append({
            "id": dev_id, "name": it["name"], "manufacturer": it.get("manufacturer", ""), "model": it.get("model", ""),
            "category": cat, "group": group, "in_use": it.get("in_use", True) is not False,
            "role": it.get("role", ""), "note": it.get("note", ""),
            "icon": f"icons/{dev_id}.svg" if dev_id in has_photo else f"icons/_glyph-{GLYPH[group]}.svg",
            "icon_kind": "drawn" if dev_id in has_photo else "glyph",
            "specs": facts,
            "placement": {k: v for k, v in pl.items() if k not in ("setup", "status", "confirmed", "module", "note")} if pl else None,
            # panel view: width in HP, 1U/3U (faceplates are generated by web/faceplate.js; no photo panels any more)
            # width/format: from gear-kb (specs, else the inventory hp/format, else an "NHP" in the name)
            "hp": hp_of(dev_id, specs.get(dev_id, {}), "", id_fallback=False) or it.get("hp") or hp_of(dev_id, {}, it["name"]),
            "format": it.get("format") or (str(pl.get("row")) if pl and str(pl.get("row", "")).upper() in ("1U", "3U") else None)
                      or "3U",
            "panel": panel_of(dev_id),
            "supply_load": supply_load.get(dev_id),
            "midi": {k: ch[k] for k in ("in", "out", "role", "note") if k in ch} if ch else None,
            "ports": ports,
        })

    resolved = resolve_links(conn.get("links", []), devices)
    members, rack_ports, session_links, rack_links = split_rack(resolved, devices)
    jacks_icon = next((d["icon"] for d in devices if d["id"] == "intellijel-audio-stereo-line-out-jacks-1u"),
                      "icons/_glyph-case.svg")
    supplies = [{"name": d["name"], "rails": d["supply_load"]} for d in devices if d.get("supply_load")]
    virtual = dict(manufacturer="", model="", in_use=True, note="", specs={}, placement=None, supply_load=None,
                   midi=None, virtual=True)
    devices.append({**virtual, "id": RACK, "name": "Eurorack", "category": "eurorack", "group": "Eurorack",
                    "icon": jacks_icon, "icon_kind": "drawn", "rack": True, "rack_supplies": supplies,
                    "role": "The whole rack as one device. Open it to patch modules.", "ports": rack_ports})
    for vid, name, role in ((RACK_IN, "Rack inputs", "Signals entering the rack from outside gear"),
                            (RACK_OUT, "Rack outputs", "Signals leaving the rack")):
        devices.append({**virtual, "id": vid, "name": name, "category": "rack-io", "group": None, "role": role,
                        "icon": "icons/_glyph-case.svg", "icon_kind": "glyph", "ports": []})
    mirror_rack_io(devices)
    specs = load_yaml(ROOT / "templates.yaml").get("templates", {})
    rack = (members, session_links, rack_links)
    templates = {tid: make_template(spec, resolved, devices, rack) for tid, spec in specs.items()}
    confirmed_rack = [l for l in rack_links if l["confirmed"]]
    seed_members = sorted({x for l in confirmed_rack for x in (l["from"], l["to"])} & members)
    fields = load_yaml(ROOT / "device_fields.yaml").get("devices", {})
    for d in devices:
        if d["id"] in fields:
            d["fields"] = fields[d["id"]]
    out = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "kb_commit": kb_commit(kb),
        "media": ["audio", "midi", "clock", "cv", "gate", "usb"],
        "groups": list(GROUPS),
        "devices": devices,
        "templates": templates,
        # confirmed KB cables with named jacks: the app auto-patches these when both devices are on the canvas
        "kb_links": [l for l in session_links if l["confirmed"]],
        # inside the rack: module <-> module, and Rack inputs/outputs <-> module (the boundary cables' inner half)
        "rack_links": confirmed_rack,
        "rack_seed": rack_graph(seed_members, confirmed_rack),   # what a freshly added Eurorack starts with
        # Eurorack cases and their rows, top to bottom (placements refer to them by case id + row)
        "cases": [{"id": c["id"], "name": next((d["name"] for d in devices if d["id"] == c["id"]), c["id"]),
                   "rows": c.get("rows") or [], "supply": c.get("supply")}
                  for c in conn.get("cases", []) if c.get("setup") == "main-studio"],
        "open_statements": [s["statement"] for s in conn.get("open_statements", []) if s.get("setup") == "main-studio"],
    }
    dest = ROOT / "data" / "gear.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    n_ports = defaultdict(int)
    for d in devices:
        for p in d["ports"]:
            n_ports[p["source"]] += 1
    print(f"gear.json: {len(devices)} devices, ports by source {dict(n_ports)}, "
          f"{sum(d['icon_kind'] == 'drawn' for d in devices)} drawn icons / "
          f"{sum(d['icon_kind'] == 'glyph' for d in devices)} glyphs, {len(out['kb_links'])} KB links, templates "
          + ", ".join(f"{k} ({len(t['nodes'])} devices/{len(t['cables'])} cables)" for k, t in templates.items())
          + f", kb {out['kb_commit']}")
    return out


if __name__ == "__main__":
    build()
