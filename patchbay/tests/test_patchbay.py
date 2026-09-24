"""Unit tests: server API round trip, port-merge precedence, jack extraction, data build. `make test`."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import extract_ports  # noqa: E402
import patchbay  # noqa: E402


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="gpb-test-"))
        cls.saved = dict(patchbay.PATHS)
        patchbay.PATHS["sessions"] = cls.tmp / "sessions"
        patchbay.PATHS["ports"] = cls.tmp / "ports.yaml"
        patchbay.PATHS["panels"] = cls.tmp / "panels.yaml"
        cls.srv = patchbay.make_server(0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        patchbay.PATHS.update(cls.saved)

    SESSION = {"name": "Night Jam", "type": "song", "bpm": 122,
               "nodes": [{"uid": "a", "device": "behringer-rd-9", "x": 0, "y": 0, "settings": {"preset": "P 03"}},
                         {"uid": "b", "device": "dreadbox-typhon", "x": 300, "y": 0, "settings": {}}],
               "cables": [{"uid": "c1", "from": {"uid": "a", "port": "MIDI OUT"}, "to": {"uid": "b", "port": "MIDI In"},
                           "medium": "midi", "settings": {"channel": "2"}}]}

    def test_session_round_trip(self):
        code, r = call(self.base, "PUT", "/api/sessions/night-jam", self.SESSION)
        self.assertEqual(code, 200, r)
        doc = yaml.safe_load((self.tmp / "sessions" / "night-jam.yaml").read_text())
        self.assertEqual(doc["cables"][0]["settings"], {"channel": "2"})
        self.assertEqual(doc["type"], "song")
        code, got = call(self.base, "GET", "/api/sessions/night-jam")
        self.assertEqual((code, got["name"], got["nodes"][0]["settings"]["preset"]), (200, "Night Jam", "P 03"))
        code, lst = call(self.base, "GET", "/api/sessions")
        self.assertIn("night-jam", [s["slug"] for s in lst])

    def test_created_is_kept_on_resave(self):
        call(self.base, "PUT", "/api/sessions/keep-created", self.SESSION)
        first = yaml.safe_load((self.tmp / "sessions" / "keep-created.yaml").read_text())
        call(self.base, "PUT", "/api/sessions/keep-created", {**self.SESSION, "created": first["created"]})
        again = yaml.safe_load((self.tmp / "sessions" / "keep-created.yaml").read_text())
        self.assertEqual(first["created"], again["created"])

    def test_bad_slugs_rejected(self):
        for slug in ("Bad Name", "UPPER", "-lead", "a" * 81, "x.yaml"):
            code, _ = call(self.base, "PUT", f"/api/sessions/{urllib.request.quote(slug)}", self.SESSION)
            self.assertEqual(code, 400, slug)

    def test_dangling_cable_rejected(self):
        bad = {**self.SESSION, "cables": [{"from": {"uid": "a", "port": "x"}, "to": {"uid": "zzz", "port": "y"}}]}
        code, r = call(self.base, "PUT", "/api/sessions/dangling", bad)
        self.assertEqual(code, 400)
        self.assertIn("two nodes", r["error"])

    def test_delete_moves_to_trash(self):
        call(self.base, "PUT", "/api/sessions/to-trash", self.SESSION)
        code, _ = call(self.base, "DELETE", "/api/sessions/to-trash")
        self.assertEqual(code, 200)
        self.assertFalse((self.tmp / "sessions" / "to-trash.yaml").exists())
        self.assertTrue(list((self.tmp / "sessions" / ".trash").glob("to-trash.*.yaml")))
        self.assertEqual(call(self.base, "DELETE", "/api/sessions/to-trash")[0], 404)

    def test_ports_edit_overlays_gear(self):
        code, _ = call(self.base, "PUT", "/api/ports/behringer-rd-9", {"ports": [
            {"name": "MIDI OUT", "dir": "out", "medium": "midi", "hidden": True},
            {"name": "Accent CV", "dir": "in", "medium": "cv"}]})
        self.assertEqual(code, 200)
        _, gear = call(self.base, "GET", "/api/gear")
        rd9 = {p["name"]: p for p in next(d for d in gear["devices"] if d["id"] == "behringer-rd-9")["ports"]}
        self.assertTrue(rd9["MIDI OUT"]["hidden"])
        self.assertEqual(rd9["MIDI OUT"]["source"], "you")
        self.assertEqual(rd9["Accent CV"]["source"], "you")
        self.assertIn("SYNC OUT", rd9)  # untouched seeds remain
        code, r = call(self.base, "PUT", "/api/ports/behringer-rd-9", {"ports": [{"name": "X", "dir": "sideways", "medium": "cv"}]})
        self.assertEqual(code, 400)


    def test_panel_positions(self):
        code, _ = call(self.base, "PUT", "/api/panels/after-later-audio-pixie", {"positions": {"Outputs": [0.5, 1.7], "In": [0.1, 0.2]}})
        self.assertEqual(code, 200)
        saved = yaml.safe_load((self.tmp / "panels.yaml").read_text())["after-later-audio-pixie"]
        self.assertEqual(saved, {"Outputs": [0.5, 1.0], "In": [0.1, 0.2]})  # clamped to the panel
        _, gear = call(self.base, "GET", "/api/gear")
        pix = next(d for d in gear["devices"] if d["id"] == "after-later-audio-pixie")
        self.assertEqual(pix["jack_pos"]["In"], [0.1, 0.2])
        self.assertIsNone(pix["panel"])  # photo panels retired 2026-09-23: faceplates are always generated
        self.assertEqual(call(self.base, "PUT", "/api/panels/x", {"positions": {"a": "nope"}})[0], 400)


class MergeTest(unittest.TestCase):
    SEED = [{"name": "MIDI IN", "dir": "in", "medium": "midi", "source": "manual"},
            {"name": "Out", "dir": "out", "medium": "audio", "source": "default"}]

    def test_yours_beat_seed_case_insensitive(self):
        out = patchbay.merge_ports(self.SEED, [{"name": "midi in", "dir": "in", "medium": "clock"}])
        (m,) = [p for p in out if p["name"].upper() == "MIDI IN"]
        self.assertEqual((m["medium"], m["source"], m["seed_source"]), ("clock", "you", "manual"))
        self.assertEqual(len(out), 2)

    def test_no_edits_is_identity(self):
        self.assertEqual(patchbay.merge_ports(self.SEED, None), self.SEED)


class ExtractTest(unittest.TestCase):
    def test_classify(self):
        cases = {"MIDI OUT": ("out", "midi"), "MIDI THRU": ("out", "midi"), "SYNC OUT": ("out", "clock"),
                 "MONO": ("out", "audio"), "V/OCT": ("in", "cv"), "GATE IN": ("in", "gate"), "USB": ("bidir", "usb"),
                 "END OF CYCLE OUT": ("out", "gate"), "PHONES": ("out", "audio"), "PITCH CV": ("in", "cv")}
        for name, want in cases.items():
            self.assertEqual(extract_ports.classify(name), want, name)

    def test_clean_label(self):
        self.assertEqual(extract_ports.clean_label("(70) MIDI IN"), "MIDI IN")
        self.assertEqual(extract_ports.clean_label("[A] IN‌‌A‌"), "IN A")
        self.assertEqual(extract_ports.clean_label("CV IN - each channel has"), "CV IN")
        self.assertEqual(extract_ports.clean_label("AUX IN connector"), "AUX IN")
        self.assertEqual(extract_ports.clean_label("7. Outputs"), "Outputs")

    def test_rejects_non_jacks(self):
        for label in ("TEMPO", "MIDI message", "SPACE FX", "MODO DE TRIGGER", "CV アッテネーター", "LFO"):
            self.assertFalse(extract_ports.is_port_label(extract_ports.clean_label(label), "connect a cable"), label)
        self.assertTrue(extract_ports.is_port_label("MIDI IN", "Accepts MIDI data"))


class DataTest(unittest.TestCase):
    def test_gear_json_covers_inventory(self):
        from common import kb_path, load_yaml
        gear = json.loads((ROOT / "data" / "gear.json").read_text())
        inv = {i["id"] for i in load_yaml(kb_path() / "inventory.yaml")["items"]}
        real = {d["id"] for d in gear["devices"] if not d.get("virtual")}
        self.assertEqual(real, inv, "run `make data` after inventory changes")
        # the rack's boundary jacks agree at both levels
        dev = {d["id"]: d for d in gear["devices"]}
        rack_jacks = {p["name"] for p in dev["eurorack"]["ports"]}
        for l in gear["kb_links"]:
            for end in ("from", "to"):
                if l[end] == "eurorack":
                    self.assertIn(l[f"{end}_port"], rack_jacks)
        inner = {p["name"] for d in ("eurorack-in", "eurorack-out") for p in dev[d]["ports"]}
        for l in gear["rack_links"]:
            for end in ("from", "to"):
                if l[end] in ("eurorack-in", "eurorack-out"):
                    self.assertIn(l[f"{end}_port"], inner)
        self.assertFalse([l for l in gear["kb_links"] if dev[l["from"]]["category"] == "eurorack-module"
                          or dev[l["to"]]["category"] == "eurorack-module"], "modules never appear at session level")
        for d in gear["devices"]:
            self.assertTrue((ROOT / d["icon"]).is_file() or d["icon_kind"] == "drawn", d["id"])
        self.assertEqual(set(gear["templates"]), {"recording-session", "jam-session", "studio-default"})
        tpl = gear["templates"]["studio-default"]
        uids = {n["uid"] for n in tpl["nodes"]}
        by_uid = {n["uid"]: n["device"] for n in tpl["nodes"]}
        ports = {d["id"]: {p["name"] for p in d["ports"]} for d in gear["devices"]}
        thru = [(l["from_port"], l["to"]) for l in gear["kb_links"] if l["from"] == "midi-thru5"]
        self.assertEqual(len({fp for fp, _ in thru}), len(thru), f"each Thru5 cable needs its own output: {thru}")
        for c in tpl["cables"]:
            self.assertIn(c["from"]["uid"], uids)
            self.assertIn(c["from"]["port"], ports[by_uid[c["from"]["uid"]]])
            self.assertIn(c["to"]["port"], ports[by_uid[c["to"]["uid"]]])


if __name__ == "__main__":
    unittest.main()
