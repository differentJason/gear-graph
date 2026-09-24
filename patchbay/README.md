# Gear Patchbay

A small local app for laying out a **Song** or **Session**. Drag your gear onto a canvas, patch jack to jack, write down
channels, presets, levels and notes, and save the layout so you can recall it later.

Part of the gear knowledge base (this folder lives at `patchbay/` in the repository). It **reads** the KB one level up
(inventory, recorded studio wiring, MIDI home channels, graph snapshot, manual jack labels, original device drawings) and
**never writes to it**. No product or panel photos are used anywhere: icons are the KB's own drawings
(`../images/`, from the KB's `../tools/draw_devices.py`) and faceplates are generated. Jack data cites the manual section it came from
but never copies manual text.

Two ways to run it:
- **Website** (published with the KB site as *Patchbay*): read-only, no server. Sessions are kept in your browser's
  localStorage only; editing jacks is off.
- **Locally** (`make serve`): the full app. Sessions are saved as `sessions/<name>.yaml`, and your jack/panel edits go
  to `ports.yaml` / `panels.yaml`. These are personal and git-ignored, so they are never published.

## Run it

```bash
make setup     # once: PyYAML into the KB's .venv (../.venv)
make data      # build data/gear.json from the KB (re-run after new manuals / inventory / wiring)
make icons     # copy gear-kb's original drawings -> icons/*.svg (after gear-kb redraws; a second)
make serve     # http://127.0.0.1:8765/ (opens the browser)
```

The KB location is `config.yaml`'s `kb_path` (`..`, relative to this folder) or the `GEAR_KB` environment variable.

## Using it

- **Add gear:** drag from the left palette, or double-click an item. "In use only" hides gear the KB marks unused.
- **Patch:** drag from one jack to another. The cable runs from output to input, whichever end you start from. Colors
  mean: audio orange, MIDI purple, clock teal (dashed), CV blue, gate yellow (dashed), USB gray (dotted).
  Jacks are ○ in/out and ◇ both ways (USB).
- **Select** a device or cable to edit it on the right: preset/pattern, MIDI in/out channel (the placeholder shows the
  KB's *home* channel), clock role, levels, notes, extra fields. Cables take a signal type, a MIDI channel, cable type,
  level and a label shown on the canvas.
- **Checks** (session panel): a MIDI channel received by two devices on one chain, two cables into one input, a signal
  on the wrong kind of jack (e.g. MIDI into CV needs a converter), and jacks that no longer exist.
- **Templates (New):** *Recording session* has the UMC1820, Mac Mini (Logic), RD-9, Digitakt, Analog Four and MIDI
  Thru5, wired as gear-kb records them. *Jam session* has the UMC404HD and the Linux workstation (Bitwig); that USB cable
  is an assumption, labelled "NOT recorded in gear-kb". *Studio default wiring* has every fixed cable in gear-kb.
  Templates are defined in `templates.yaml`: list the devices and the KB cables between them are added.
- **Auto-patch:** when you add a device, it is connected to gear already on the canvas with the cables gear-kb records
  between them (e.g. add the Typhon to a Recording session and it gets Thru5 Out 2 → MIDI In). An input that is already
  in use is left alone. Turn it off with *Auto-patch from gear-kb* in the palette. One undo removes the device and its
  cables.
- **Elektron start state** (Digitakt, Analog Four): select the box to set where each song starts. This covers project,
  play mode, bank/pattern, kit (A4), chain, song slot, tempo and length (SCALE, M.LEN/CH.LEN or LEN/CHNG), track mutes,
  per-track sounds, the Digitakt's MIDI tracks 9-16 (channel picker labelled with each synth's home channel), the A4's
  CV A-D outputs and their destinations, and the global MIDI CONFIG. *Fill studio defaults* copies in the settings
  recorded in gear-kb `midi_channels.yaml` (AUTO CHANNEL, clock/transport send/receive, ports). The canvas card shows a
  summary such as `B07 · 124 BPM`. Names and ranges come from the ingested manuals. The fields are defined in
  `device_fields.yaml`, which other devices can use too.
- **Save / Save as / Open.** Each session is one readable YAML file in `sessions/<name>.yaml`. Delete moves the file to
  `sessions/.trash/`, so it can be recovered. Unsaved work is also kept as a draft in the browser and offered back on
  the next visit.
- **SVG / PNG** export a picture of the layout (with title, BPM, key and date) for quick recall.
- Keys: `Ctrl+S` save, `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo, `Delete` remove, `Ctrl+D` duplicate, `F` fit, `Esc` deselect.
  Scroll zooms and dragging the background pans.
- Open a session directly: `http://127.0.0.1:8765/?session=<name>`.

## Faceplates (our own vectors)

Every piece on the canvas and in the palette is a **generated faceplate** (`web/faceplate.js`). It is drawn only from
gear-kb data: the name, the maker, the width in HP, 1U/3U, and the device's actual jacks. No product photos or anyone's
panel artwork are used. It borrows VCV Rack's visual grammar:

- **Eurorack modules** are vertical panels at true HP width (15 px/HP; 3U = 380 px, 1U = 117 px), with corner screws
  and the name at the top.
- **Other gear** gets a horizontal "rear panel" strip sized by its jack count, with the name block on the left.
- **Jacks:** outputs sit on dark inset cells, and jack rings are colored by signal. Jacks are placed exactly where
  the generator draws them, so cables always land on the drawn jack. Editing a device's jacks redraws its faceplate.
- **Colors:** the panel finish is chosen from a small neutral set by a hash of the maker's name (a brand keeps one
  look without copying its real trade dress). The accent line is picked per device.

Top bar: **Panels/Boxes** switches both the session and the rack between faceplates and the box view. **Photos** now
only swaps the palette's mini faceplates for the illustrated icons; there are no photo panels any more, so the rack
always uses generated faceplates (and *Place jacks* calibration in `panels.yaml` has nothing to calibrate against).

## Eurorack

At session level the whole rack is **one device, "Eurorack"**, shown with the Stereo Line Out Jacks icon. Its jacks
are the rack's boundary: *Audio Out L/R* (the Intellijel outs into the interface) and *Clock In* (RD-9 SYNC OUT into
Jake's clock), both from gear-kb, plus general CV/Gate/Audio/MIDI inputs and outputs for the gear that patches into
the rack.

**Double-click it** (or *Open rack patch*) to patch modules inside it:

- **Panel view** (default, VCV Rack style): generated faceplates at true HP width in your case rows (from gear-kb:
  cases, rows, and placements with `row_index` + `position`), with sagging cables. *Rack inputs* and *Rack outputs* are the Eurorack's jacks seen from
  inside. *Node view* shows the same patch as boxes.
- **Add installed modules** puts every module gear-kb places in a case on the canvas. **Arrange by case** lays them
  out by case, then row, then `position`. Set `row:` in a placement to a row number (1 = the case's first row in
  `rows:`) to pick one of several rows of the same format. A row that fills up spills into the next row of that
  format.
- **Place jacks…** (select a module): click where each jack is on the panel photo. Positions are saved per module
  in `panels.yaml` and reused in every session. Until a jack is placed it sits in a default grid, drawn as a dashed
  ring.
- Faceplates come from `images/<device-id>.jpg`. Modules without one get a plain panel. Drop a panel image there
  and run `make data`.

The rack patch is saved inside the session, under the Eurorack node (`rack: {nodes, cables, notes}`).

## Where the jacks come from

Each jack carries a **source**, shown in the jack editor:

| source        | meaning                                                                                                    |
|---------------|------------------------------------------------------------------------------------------------------------|
| `connections` | named in gear-kb `connections.yaml` (wiring the owner stated)                                              |
| `manual`      | a jack-like bold label in the device's manual panel/connection sections (`tools/extract_ports.py`). **Unverified.** |
| `default`     | a guess by category, used only when the manual gave nothing                                                |
| `you`         | your edit, saved in `ports.yaml`                                                                           |

To fix jacks, select a device, choose **Edit jacks…**, then rename, change direction or signal, hide (checkbox) or add
jacks, and **Save jacks**. Edits go to `ports.yaml`, keyed by device and matched by jack name. They apply in every
session and survive `make data`. Renaming a jack updates the cables in the open session. Other saved sessions that
used the old name show the jack struck through with a warning.

## Icons

`tools/trace_icons.py` copies the KB's original drawings (`../images/<id>.svg`, made by the KB's
`../tools/draw_devices.py` from facts only) into `icons/`, minus their white page background. **To change an icon**,
change the drawing in gear-kb and re-run `make icons`. Devices without a drawing get a simple line glyph.
`icons/_sheet.html` is a contact sheet of every icon.

## Session file format

```yaml
schema: 1
name: Night Jam
type: song            # song | session
bpm: '124'
key: F# minor
date: '2026-09-23'
tags: live, techno
notes: ...
created: 2026-09-23T18:00:00
updated: 2026-09-23T18:10:00
gear_kb_commit: 4f5c2eb   # which KB snapshot the gear data came from
view: {x: 40, y: 40, k: 1}
nodes:
  - {uid: n1, device: behringer-rd-9, x: 60, y: 40, collapsed: false,
     settings: {preset: 'Pattern A07', midi_out: '10', clock: master, notes: '...'}}
cables:
  - {uid: c1, from: {uid: n1, port: MIDI OUT}, to: {uid: n2, port: MIDI IN}, medium: midi,
     settings: {channel: '2', cable: MIDI DIN, label: bass line}}
```

`device` is a gear-kb inventory id. Ports are matched by name.

## Tests

```bash
make test                                   # server API, port merge, jack extraction, data build
python tests/e2e_ui.py --shots DIR    # headless Chromium: drop, patch, save, reload, undo, export
```

The e2e test needs a Python with PyYAML and Playwright's Chromium (`pip install pyyaml playwright` then `playwright install chromium`).

## Layout

```
tools/extract_ports.py   manuals -> data/ports.seed.yaml
tools/build_data.py      gear-kb -> data/gear.json (devices, jacks, MIDI home channels, specs, studio template)
tools/trace_icons.py     gear-kb drawings -> icons/*.svg
tools/patchbay.py        local server (127.0.0.1 only) + JSON API
web/                     the app (vanilla JS + SVG, no build step); web/faceplate.js draws the faceplates
templates.yaml           New-session templates (devices; KB cables are added automatically)
device_fields.yaml       per-device start-state fields (Elektron boxes)
ports.yaml               your jack edits
panels.yaml              where jacks sit on each module's panel photo (Place jacks)
sessions/                saved Songs / Sessions
```
