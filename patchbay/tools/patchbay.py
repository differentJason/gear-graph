"""gear-patchbay local server: serves the app and saves Songs/Sessions as YAML. Binds to 127.0.0.1 only.

  GET    /                       the app (web/)
  GET    /api/gear               data/gear.json with your ports.yaml edits overlaid
  GET    /api/sessions           [{slug, name, type, bpm, key, updated}]
  GET    /api/sessions/<slug>    one session (JSON)
  PUT    /api/sessions/<slug>    save (JSON body) -> sessions/<slug>.yaml
  DELETE /api/sessions/<slug>    move to sessions/.trash/ (recoverable)
  PUT    /api/ports/<device>     save your port list for one device -> ports.yaml

Usage: .venv/bin/python tools/patchbay.py [--port 8765] [--open]
"""
import argparse
import datetime
import json
import mimetypes
import os
import re
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import load_yaml, mirror_rack_io  # noqa: E402

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
DEVICE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
MEDIA = {"audio", "midi", "clock", "cv", "gate", "usb", "power"}
DIRS = {"in", "out", "bidir"}
STATIC = {"/icons/": ROOT / "icons", "/": ROOT / "web"}
LOCK = threading.Lock()
MAX_BODY = 5_000_000

# overridable in tests
PATHS = {"sessions": ROOT / "sessions", "ports": ROOT / "ports.yaml", "gear": ROOT / "data" / "gear.json",
         "panels": ROOT / "panels.yaml"}


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def merge_ports(seed, mine):
    """Seed ports overlaid with your edits, matched by name (case-insensitive). Yours win; `hidden` hides a seed."""
    mine = mine or []
    by_name = {p["name"].upper(): p for p in mine}
    out = []
    for p in seed:
        m = by_name.pop(p["name"].upper(), None)
        out.append({**p, **{k: v for k, v in m.items() if k in ("name", "dir", "medium", "hidden")}, "source": "you",
                    "seed_source": p["source"]} if m else p)
    for p in mine:
        if p["name"].upper() in by_name:
            out.append({"name": p["name"], "dir": p["dir"], "medium": p["medium"], "hidden": bool(p.get("hidden")),
                        "source": "you", "evidence": "added in gear-patchbay"})
    return out


def gear_payload():
    gear = json.loads(PATHS["gear"].read_text())
    mine = load_yaml(PATHS["ports"]) if PATHS["ports"].is_file() else {}
    for d in gear["devices"]:
        d["ports"] = merge_ports(d["ports"], mine.get(d["id"]))
        if not (ROOT / d["icon"]).is_file():  # drawn icon missing (make icons not run yet): fall back to the group glyph
            d["icon"], d["icon_kind"] = "icons/_glyph-utility.svg", "glyph"
    mirror_rack_io(gear["devices"])  # your edits to the Eurorack's jacks show up on Rack inputs/outputs too
    pos = load_yaml(PATHS["panels"]) if PATHS["panels"].is_file() else {}
    for d in gear["devices"]:
        if pos.get(d["id"]):
            d["jack_pos"] = pos[d["id"]]
    return gear


def clean_ports(body):
    ports = body.get("ports") if isinstance(body, dict) else None
    if not isinstance(ports, list):
        raise ValueError("body must be {ports: [...]}")
    out, seen = [], set()
    for p in ports:
        name = str(p.get("name", "")).strip()[:60]
        if not name or name.upper() in seen:
            continue
        if p.get("dir") not in DIRS or p.get("medium") not in MEDIA:
            raise ValueError(f"port {name!r}: dir must be one of {sorted(DIRS)}, medium one of {sorted(MEDIA)}")
        seen.add(name.upper())
        entry = {"name": name, "dir": p["dir"], "medium": p["medium"]}
        if p.get("hidden"):
            entry["hidden"] = True
        out.append(entry)
    return out


def clean_session(body, slug):
    if not isinstance(body, dict):
        raise ValueError("session must be an object")
    nodes, cables = body.get("nodes", []), body.get("cables", [])
    if not isinstance(nodes, list) or not isinstance(cables, list):
        raise ValueError("nodes and cables must be lists")
    uids = set()
    for n in nodes:
        if not isinstance(n, dict) or not n.get("uid") or not n.get("device"):
            raise ValueError("every node needs uid and device")
        uids.add(n["uid"])
    for c in cables:
        if not isinstance(c, dict) or c.get("from", {}).get("uid") not in uids or c.get("to", {}).get("uid") not in uids:
            raise ValueError("every cable must connect two nodes of this session")
    now = datetime.datetime.now().isoformat(timespec="seconds")
    return {"schema": 1, "slug": slug, "name": str(body.get("name") or slug)[:120],
            "type": body.get("type") if body.get("type") in ("song", "session") else "session",
            **{k: body[k] for k in ("bpm", "key", "date", "tags", "notes", "view", "gear_kb_commit") if k in body},
            "created": body.get("created") or now, "updated": now, "nodes": nodes, "cables": cables}


class Handler(BaseHTTPRequestHandler):
    server_version = "gear-patchbay/1"

    def log_message(self, fmt, *args):  # quieter: only errors
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def send(self, code, payload=None, ctype="application/json", raw=None):
        data = raw if raw is not None else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"null")

    def route(self):
        path = unquote(urlparse(self.path).path)
        parts = path.strip("/").split("/")
        return path, parts

    # --- GET ---
    def do_GET(self):
        path, parts = self.route()
        try:
            if path == "/api/gear":
                return self.send(200, gear_payload())
            if path == "/api/sessions":
                return self.send(200, self.list_sessions())
            if parts[:2] == ["api", "sessions"] and len(parts) == 3:
                f = self.session_file(parts[2])
                return self.send(200, load_yaml(f)) if f.is_file() else self.send(404, {"error": "no such session"})
            return self.static(path)
        except ValueError as e:
            return self.send(400, {"error": str(e)})

    def list_sessions(self):
        out = []
        for f in sorted(PATHS["sessions"].glob("*.yaml")):
            try:
                s = load_yaml(f)
            except yaml.YAMLError:
                continue
            out.append({"slug": f.stem, **{k: s.get(k) for k in ("name", "type", "bpm", "key", "date", "updated")},
                        "devices": len(s.get("nodes", [])), "cables": len(s.get("cables", []))})
        return sorted(out, key=lambda s: str(s.get("updated") or ""), reverse=True)

    def session_file(self, slug):
        if not SLUG.match(slug):
            raise ValueError("bad session name (use a-z, 0-9 and dashes)")
        return PATHS["sessions"] / f"{slug}.yaml"

    def static(self, path):
        for prefix, base in STATIC.items():
            if path.startswith(prefix):
                rel = path[len(prefix):] or "index.html"
                f = (base / rel).resolve()
                if base.resolve() not in f.parents and f != base.resolve():
                    return self.send(403, {"error": "forbidden"})
                if f.is_file():
                    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                    return self.send(200, ctype=ctype, raw=f.read_bytes())
                break
        return self.send(404, {"error": "not found"})

    # --- PUT / DELETE ---
    def do_PUT(self):
        path, parts = self.route()
        try:
            if parts[:2] == ["api", "sessions"] and len(parts) == 3:
                f = self.session_file(parts[2])
                doc = clean_session(self.body(), parts[2])
                with LOCK:
                    atomic_write(f, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120))
                return self.send(200, {"slug": parts[2], "updated": doc["updated"]})
            if parts[:2] == ["api", "panels"] and len(parts) == 3:
                dev = parts[2]
                if not DEVICE.match(dev):
                    raise ValueError("bad device id")
                raw = (self.body() or {}).get("positions")
                if not isinstance(raw, dict):
                    raise ValueError("body must be {positions: {jack name: [x, y]}}")
                clean = {}
                for name, xy in raw.items():
                    if not (isinstance(xy, list) and len(xy) == 2 and all(isinstance(v, (int, float)) for v in xy)):
                        raise ValueError(f"position for {name!r} must be [x, y]")
                    clean[str(name)[:60]] = [round(min(1, max(0, float(v))), 4) for v in xy]
                with LOCK:
                    allpos = load_yaml(PATHS["panels"]) if PATHS["panels"].is_file() else {}
                    if clean:
                        allpos[dev] = clean
                    else:
                        allpos.pop(dev, None)
                    atomic_write(PATHS["panels"],
                                 "# Where each jack sits on a module's panel photo, as fractions of width/height (0-1).\n"
                                 "# Written by gear-patchbay's 'Place jacks' tool. Safe to hand-edit.\n"
                                 + yaml.safe_dump(allpos, sort_keys=True, allow_unicode=True, width=120))
                return self.send(200, {"device": dev, "positions": len(clean)})
            if parts[:2] == ["api", "ports"] and len(parts) == 3:
                dev = parts[2]
                if not DEVICE.match(dev):
                    raise ValueError("bad device id")
                ports = clean_ports(self.body())
                with LOCK:
                    mine = load_yaml(PATHS["ports"]) if PATHS["ports"].is_file() else {}
                    if ports:
                        mine[dev] = ports
                    else:
                        mine.pop(dev, None)
                    atomic_write(PATHS["ports"],
                                 "# YOUR port edits (written by gear-patchbay). Overrides data/ports.seed.yaml by port name.\n"
                                 "# hidden: true hides a seeded port. Safe to hand-edit.\n"
                                 + yaml.safe_dump(mine, sort_keys=True, allow_unicode=True, width=120))
                return self.send(200, {"device": dev, "ports": len(ports)})
            return self.send(404, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as e:
            return self.send(400, {"error": str(e)})

    def do_DELETE(self):
        path, parts = self.route()
        try:
            if parts[:2] == ["api", "sessions"] and len(parts) == 3:
                f = self.session_file(parts[2])
                if not f.is_file():
                    return self.send(404, {"error": "no such session"})
                trash = PATHS["sessions"] / ".trash"
                trash.mkdir(exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                with LOCK:
                    os.replace(f, trash / f"{f.stem}.{stamp}.yaml")
                return self.send(200, {"deleted": parts[2], "recoverable_in": "sessions/.trash/"})
            return self.send(404, {"error": "not found"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})


def make_server(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(load_yaml(ROOT / "config.yaml").get("port", 8765)))
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    if not PATHS["gear"].is_file():
        raise SystemExit("data/gear.json missing: run `make data` first")
    srv = make_server(args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"gear-patchbay on {url}  (Ctrl+C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
