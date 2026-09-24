# Patchbay user guide

The Patchbay is a drag-and-drop patch planner for a Song or a Session. You put gear on a canvas, patch cables jack to
jack, note channels, presets and start states, and save the layout so you can recall it. Everything it knows about the
gear (names, jacks, MIDI home channels, Eurorack widths, how the studio is wired) comes from the knowledge base.

Each section below ends with a hidden `covers:` note naming the buttons (`data-act` ids) and functions it documents.
`tools/build_code_graph.py` reads those notes to link this guide to the code, and fails the build if a button is left
undocumented or a note names something that no longer exists.

## Getting started

There are two ways to use it. **On the website** it runs without a server: the gear data is loaded from a file next to
the page, sessions are saved in your browser only, and editing jacks is off. **Locally** (`cd patchbay && make serve`)
it is the full app: sessions are written to `sessions/<name>.yaml`, and jack and panel edits are saved to your own
files. If you leave with unsaved work, the next visit offers to restore the draft.

<!-- covers: fn:staticApi fn:api fn:boot fn:saveDraft -->

## Adding gear from the palette

The palette on the left lists every device in the knowledge base, grouped (synths and drum machines, Eurorack,
controllers, effects, and so on). Type in the search box to filter it, and untick **In use only** to see gear that is
stored away. Drag a device onto the canvas to add it. With **Auto-patch from gear-kb** ticked, cables that the
knowledge base records between that device and gear already on the canvas are added for you.

<!-- covers: fn:renderPalette fn:addNode fn:autoPatch -->

## Patching cables

Drag from one jack to another to add a cable. Jacks are colored by signal: audio, MIDI, clock/sync, CV, gate/trigger
and USB (the legend at the bottom of the canvas); a diamond marks a bidirectional jack. Select a cable to see it in the
inspector, where **Reverse direction** swaps its ends and **Delete cable** removes it.

<!-- covers: fn:onPointerDown fn:addCable fn:renderLegend reverse -->

## Arranging the canvas

Drag boxes to move them; scroll to zoom. **Fit** frames the whole diagram. **Undo** and **Redo** (Ctrl+Z,
Ctrl+Shift+Z) step through your changes. With a device selected, **Duplicate** adds a second copy and **Remove from
session** takes it off the canvas (the Delete key does the same). Untick a device's jack list to collapse it to the
jacks that are patched (**Show all jacks on the canvas**), and **Hide jack names** / **Show jack names** declutters a
busy diagram.

<!-- covers: fit undo redo dup delete collapse jack-labels -->

## Faceplates, boxes and icons

**Boxes** switches between faceplates (each device drawn as a panel, Eurorack at its true width) and compact boxes.
**Photos** swaps the palette's mini faceplates for the illustrated icons; nothing in the app uses product photos. The
**◐** button (toggle light/dark) switches the theme.

<!-- covers: view-mode photos theme fn:iconHTML -->

## The Eurorack rack

At session level the whole rack is one device, **Eurorack**, whose jacks are the cables that cross the rack's edge.
Select it and choose **Open rack patch** to patch modules inside it: faceplates sit in your case rows in the order the
knowledge base records, at their true HP width, with the power load of each supply shown in the inspector.
**Add installed modules** brings in every module mounted in the cases, and **Arrange by case** lays them out row by
row. **Back to session** (or Esc) returns to the session.

<!-- covers: enter-rack exit-rack rack-add-all rack-arrange fn:rackPower fn:arrangePanels -->

## Placing jacks on a panel

In the local app, select a module and choose **Place jacks…** (or **Re-place all**) to click where each jack sits on
its panel; **Skip** moves to the next jack, **Reset** clears the positions, and **Done** saves them. Generated
faceplates already put every jack where they drew it, so this is only needed for custom panels.

<!-- covers: place-jacks place-skip place-reset place-done -->

## Device settings and start state

Select a device to note its settings: MIDI channels (the knowledge base's home channel is offered first), presets,
and a start state. **Fill studio defaults** fills any empty field that has a studio default recorded in the knowledge
base, **Clear start state** empties it again, **+ Add field** adds your own named field and **✕** (remove field)
deletes one.

<!-- covers: state-kb state-clear field-add field-del fn:stateInspector fn:homeChannelOptions -->

## Editing a device's jacks

Jacks come from the manuals, the recorded wiring, or a sensible default for the kind of device; the inspector shows
where each one came from. In the local app, **Edit jacks…** opens the list: rename a jack, change its direction or
signal, hide it, or add one with **+ Jack**, then **Save jacks** (or **Cancel**). Your edits are kept apart from the
generated data, so rebuilding the data never loses them.

<!-- covers: ports-edit port-add ports-cancel ports-save fn:savePorts -->

## Checks

The inspector's Checks list flags problems as you patch: two devices on one MIDI line sharing a channel, cables
between mismatched signals, modules missing from the rack, and similar. "No problems found" means none of the checks
fired, not that the patch is certainly right.

<!-- covers: fn:warnings -->

## Sessions and templates

**New** starts a blank session or one of the templates (recording, jam, the studio's default wiring). **Open** lists
saved sessions (and deletes one: on the local app it moves to a recoverable trash folder). **Save** keeps the current
session under its name and **Save as** saves a copy under a new name. The session's name, type, BPM, key, date, tags
and notes are edited in the inspector when nothing is selected.

<!-- covers: new open save saveas load-template fn:sessionInspector fn:openDialog -->

## Exporting a diagram

**SVG** and **PNG** download the current diagram, session or rack, as an image to share or print.

<!-- covers: export-svg export-png fn:exportFile -->
