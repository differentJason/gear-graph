"""End-to-end UI check in headless Chromium (Playwright). Not part of `make test` (needs a browser):

    ~/.venvs/webfetch/bin/python tests/e2e_ui.py [--shots DIR]

Starts its own server on a scratch sessions dir, then: blank canvas -> drop two devices from the palette -> drag a
MIDI cable jack to jack -> set channel -> save -> reload -> assert the saved YAML; plus the studio-default template.
Fails on any browser console error.
"""
import argparse
import sys
import tempfile
import threading
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import patchbay  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()
    shots = Path(args.shots) if args.shots else None
    tmp = Path(tempfile.mkdtemp(prefix="gpb-e2e-"))
    patchbay.PATHS["sessions"] = tmp / "sessions"
    patchbay.PATHS["ports"] = tmp / "ports.yaml"
    patchbay.PATHS["panels"] = tmp / "panels.yaml"
    srv = patchbay.make_server(0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    errors = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        for scheme in ("dark", "light"):
            pg = b.new_page(viewport={"width": 1500, "height": 900}, color_scheme=scheme)
            pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base)
            pg.wait_for_selector(".pal-item")

            if scheme == "dark":
                # 1. drop two devices from the palette onto the canvas (HTML5 drag and drop)
                pg.fill("#search", "RD-9")
                pg.drag_and_drop('.pal-item[data-device="behringer-rd-9"]', "#stage", target_position={"x": 250, "y": 220})
                pg.fill("#search", "Typhon")
                pg.drag_and_drop('.pal-item[data-device="dreadbox-typhon"]', "#stage", target_position={"x": 750, "y": 260})
                pg.fill("#search", "")
                assert pg.locator("#nodes .node").count() == 2, "two nodes on canvas"

                # 2. drag a cable from RD-9 MIDI OUT to Typhon MIDI In
                src = pg.locator('.port[data-port="MIDI OUT"] .jack-hit').first.bounding_box()
                dst_sel = '.node[data-device*="dreadbox-typhon"] .port[data-port="MIDI In"] .jack-hit'
                if pg.locator(dst_sel).count() == 0:  # typhon's manual may give a different in-jack name
                    dst_sel = '.node[data-device*="dreadbox-typhon"] .port .jack-hit'
                dst = pg.locator(dst_sel).first.bounding_box()
                pg.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
                pg.mouse.down()
                pg.mouse.move((src["x"] + dst["x"]) / 2, (src["y"] + dst["y"]) / 2, steps=5)
                pg.mouse.move(dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] / 2, steps=5)
                pg.mouse.up()
                assert pg.locator("#cables .cable").count() == 1, "one cable drawn"

                # 3. the new cable is selected: set the MIDI channel + a label; name the session and save
                pg.fill('[data-bind="cable.settings.channel"]', "2")
                pg.fill('[data-bind="cable.settings.label"]', "bass line")
                pg.keyboard.press("Escape")
                pg.fill('[data-bind="session.name"]', "E2E Test Song")
                pg.select_option('[data-bind="session.type"]', "song")
                pg.fill('[data-bind="session.bpm"]', "124")
                pg.wait_for_timeout(200)
                if shots:
                    pg.screenshot(path=str(shots / "e2e-patched-dark.png"))
                pg.keyboard.press("Control+s")
                pg.wait_for_selector("#ask-in")
                pg.click('#modal button[value="ok"]')
                pg.wait_for_selector("#toast:not([hidden])")
                saved = tmp / "sessions" / "e2e-test-song.yaml"
                assert saved.is_file(), "session file written"
                doc = yaml.safe_load(saved.read_text())
                assert doc["type"] == "song" and str(doc["bpm"]) == "124", doc
                (c,) = doc["cables"]
                assert c["from"]["port"] == "MIDI OUT" and c["medium"] == "midi", c
                assert c["settings"] == {"channel": "2", "label": "bass line"}, c["settings"]
                assert {n["device"] for n in doc["nodes"]} == {"behringer-rd-9", "dreadbox-typhon"}

                # 4. reload from the file via ?session= and check it renders the same
                pg.goto(base + "?session=e2e-test-song")
                pg.wait_for_selector("#cables .cable")
                assert pg.locator("#cables .cable").count() == 1
                assert "bass line" in pg.locator("#cables").text_content()

                # 5. undo/redo round trip on a delete
                pg.click("#cables .cable .cable-hit", force=True)
                pg.keyboard.press("Delete")
                assert pg.locator("#cables .cable").count() == 0
                pg.keyboard.press("Control+z")
                assert pg.locator("#cables .cable").count() == 1

            if scheme == "dark":
                # 7. Recording template + auto-patch + Elektron start state
                pg.evaluate("() => localStorage.clear()")
                pg.goto(base)
                pg.wait_for_selector(".pal-item")
                pg.click('[data-act="load-template"][data-template="recording-session"]')
                pg.wait_for_timeout(200)
                assert pg.locator("#nodes .node").count() == 6 and pg.locator("#cables .cable").count() == 8
                pg.fill("#search", "Typhon")
                pg.drag_and_drop('.pal-item[data-device="dreadbox-typhon"]', "#stage", target_position={"x": 900, "y": 600})
                pg.fill("#search", "")
                assert pg.locator("#cables .cable").count() == 9, "Typhon auto-patched from the Thru5"
                auto = pg.evaluate("() => S.session.cables.at(-1)")
                assert auto["from"]["port"] == "MIDI Out 2" and auto["medium"] == "midi", auto
                # undo removes the device and its auto cable in one step
                pg.keyboard.press("Escape"); pg.keyboard.press("Control+z")
                assert pg.locator("#nodes .node").count() == 6 and pg.locator("#cables .cable").count() == 8
                # Digitakt start state
                pg.locator('.node[data-device*="elektron-digitakt"]').first.click()
                pg.select_option('[data-bind="node.settings.state.bank"]', "B")
                pg.select_option('[data-bind="node.settings.state.pattern"]', "07")
                pg.fill('[data-bind="node.settings.state.bpm"]', "124")
                pg.click('label:has([data-mute="mutes|3"])')
                pg.select_option('[data-bind="node.settings.state.midi_tracks.9.channel"]', "2")
                pg.fill('[data-bind="node.settings.state.midi_tracks.9.part"]', "Typhon bass")
                pg.click('[data-act="state-kb"]')
                pg.wait_for_timeout(200)
                st = pg.evaluate("() => S.session.nodes.find(n => n.device === 'elektron-digitakt-mk1').settings.state")
                assert st["bank"] == "B" and st["pattern"] == "07" and st["mutes"] == ["3"], st
                assert st["midi_tracks"] == {"9": {"channel": "2", "part": "Typhon bass"}}, st["midi_tracks"]
                assert st["auto_channel"] == "14" and st["clock_send"] == "ON" and st["input_from"] == "MIDI", st
                assert "B07 · 124 BPM" in pg.locator("#nodes").text_content()
                if shots:
                    pg.screenshot(path=str(shots / "recording-elektron-dark.png"))
                    pg.locator("#inspector").screenshot(path=str(shots / "elektron-panel.png"))
                pg.fill('[data-bind="node.label"]', "Digitakt")
                pg.keyboard.press("Escape")
                pg.fill('[data-bind="session.name"]', "Rec Test")
                pg.keyboard.press("Control+s")
                pg.wait_for_selector("#ask-in")
                pg.click('#modal button[value="ok"]')
                pg.wait_for_function("() => document.querySelector('#toast').textContent.startsWith('Saved')")
                doc = yaml.safe_load((tmp / "sessions" / "rec-test.yaml").read_text())
                dt = next(n for n in doc["nodes"] if n["device"] == "elektron-digitakt-mk1")
                assert dt["settings"]["state"]["midi_tracks"]["9"]["channel"] == "2", dt
                # jam template
                pg.evaluate("() => localStorage.clear()")
                pg.goto(base)
                pg.wait_for_selector(".pal-item")
                if pg.locator("#modal[open]").count():
                    pg.click('#modal button[value="cancel"]')
                pg.click('[data-act="load-template"][data-template="jam-session"]')
                pg.wait_for_timeout(200)
                assert pg.locator("#nodes .node").count() == 2 and pg.locator("#cables .cable").count() == 1

            if scheme == "dark":
                # 8. Eurorack as one device; module patching inside it
                pg.evaluate("() => localStorage.clear()")
                pg.goto(base)
                pg.wait_for_selector(".pal-item")
                pg.click('[data-act="load-template"][data-template="studio-default"]')
                pg.wait_for_timeout(200)
                devs = pg.evaluate("() => S.session.nodes.map(n => n.device)")
                assert "eurorack" in devs and not any(d.startswith("intellijel") for d in devs), devs
                assert pg.locator('.pal-item[data-device="after-later-audio-pixie"]').count() == 0, "modules live inside the rack"
                pg.locator('.node[data-device="eurorack"]').first.dblclick()
                pg.wait_for_selector("#crumbs:not([hidden])")
                inside = pg.evaluate("() => G().nodes.map(n => n.device)")
                assert {"eurorack-in", "eurorack-out", "jakes-clock-and-musical-divider"} <= set(inside), inside
                pg.click('[data-act="rack-add-all"]')
                pg.wait_for_timeout(300)
                n_mods = pg.evaluate("() => G().nodes.filter(n => !n.device.startsWith('eurorack-')).length")
                assert n_mods >= 20, n_mods
                # patch Pixie -> Four Play VCA (expand both first: added modules start collapsed)
                pg.evaluate("""() => { for (const n of G().nodes) if (['after-later-audio-pixie','behringer-four-play-vca'].includes(n.device)) n.collapsed = false; renderAll(); }""")
                src = pg.locator('.node[data-device*="after-later-audio-pixie"] .port[data-port="Outputs"] .jack-hit').first
                dst = pg.locator('.node[data-device*="behringer-four-play-vca"] .port[data-port="INPUTS"] .jack-hit').first
                src.scroll_into_view_if_needed(); ba = src.bounding_box(); bb = dst.bounding_box()
                pg.mouse.move(ba["x"] + 5, ba["y"] + 5); pg.mouse.down(); pg.mouse.move(bb["x"] + 5, bb["y"] + 5, steps=8); pg.mouse.up()
                rc = pg.evaluate("() => G().cables.map(c => [c.from.port, c.to.port])")
                assert ["Outputs", "INPUTS"] in rc, rc
                # generated faceplates export as our own vectors (no photos)
                pg.keyboard.press("Escape")
                gsvg = pg.evaluate("() => exportSVG()")
                assert "fp-bg" in gsvg and "data:image/jpeg" not in gsvg, "generated export has no photos"
                # photo panels were retired 2026-09-23: even with Photos on, the rack keeps generated faceplates
                pg.click('[data-act="photos"]'); pg.wait_for_timeout(200)
                psvg = pg.evaluate("() => exportSVG()")
                assert "fp-bg" in psvg and "data:image/jpeg" not in psvg, "no photo faceplates exist any more"
                pg.click('[data-act="photos"]'); pg.wait_for_timeout(200)
                if shots:
                    pg.click('[data-act="fit"]'); pg.wait_for_timeout(300)
                    pg.screenshot(path=str(shots / "rack-panels-dark.png"))
                    pg.click('[data-act="view-mode"]'); pg.wait_for_timeout(200)
                    pg.screenshot(path=str(shots / "rack-nodes-dark.png"))
                    pg.click('[data-act="view-mode"]')
                pg.keyboard.press("Escape"); pg.keyboard.press("Escape")
                pg.wait_for_selector("#crumbs", state="hidden")
                assert "modules ·" in pg.locator("#nodes").text_content()
                if shots:
                    pg.screenshot(path=str(shots / "session-with-rack-dark.png"))
                pg.fill('[data-bind="session.name"]', "Rack Test")
                pg.keyboard.press("Control+s"); pg.wait_for_selector("#ask-in"); pg.click('#modal button[value="ok"]')
                pg.wait_for_function("() => document.querySelector('#toast').textContent.startsWith('Saved')")
                doc = yaml.safe_load((tmp / "sessions" / "rack-test.yaml").read_text())
                rack = next(n for n in doc["nodes"] if n["device"] == "eurorack")["rack"]
                assert any(c["from"]["port"] == "Outputs" and c["to"]["port"] == "INPUTS" for c in rack["cables"]), rack["cables"]

            # 6. studio default template (both themes, for screenshots)
            pg.evaluate("() => localStorage.clear()")
            pg.goto(base)
            pg.wait_for_selector(".pal-item")
            if pg.locator("#modal[open]").count():
                pg.click('#modal button[value="cancel"]')
            pg.click('[data-act="load-template"][data-template="studio-default"]')
            pg.wait_for_timeout(300)
            n_nodes, n_cables = pg.locator("#nodes .node").count(), pg.locator("#cables .cable").count()
            assert n_nodes >= 10 and n_cables >= 15, (n_nodes, n_cables)
            pg.click('[data-act="fit"]')
            pg.wait_for_timeout(200)
            if scheme == "dark":
                # MIDI check: Typhon set to ch 3 collides with the Korg M1's home channel 3 on the Thru5 chain
                warns = pg.evaluate("""() => { const n = S.session.nodes.find(n => n.device === 'dreadbox-typhon');
                    n.settings.midi_in = '3'; return warnings().map(w => w.text); }""")
                assert any("MIDI ch 3" in w for w in warns), warns
                pg.evaluate("() => { S.session.nodes.find(n => n.device === 'dreadbox-typhon').settings = {}; }")
                assert not pg.evaluate("() => warnings().length"), "template is clean"
                svg = pg.evaluate("() => exportSVG()")
                assert svg.startswith("<svg") and svg.count("fp-bg") >= 10 and "</svg>" in svg and "data:image" not in svg
                if shots:
                    (shots / "export.svg").write_text(svg)
            if shots:
                pg.screenshot(path=str(shots / f"studio-default-{scheme}.png"))
                pg.locator('.node[data-device*="midi-thru5"]').first.click()
                pg.wait_for_timeout(100)
                pg.screenshot(path=str(shots / f"inspector-{scheme}.png"))
            pg.close()
        b.close()
    srv.shutdown()
    if errors:
        print("BROWSER ERRORS:\n  " + "\n  ".join(errors))
        sys.exit(1)
    print("e2e OK:", tmp)


if __name__ == "__main__":
    main()
