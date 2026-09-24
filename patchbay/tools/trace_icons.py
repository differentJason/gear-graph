"""Device icons -> icons/<device>.svg, from gear-kb's ORIGINAL illustrations (gear-kb/images/<id>.svg, drawn by
gear-kb's tools/draw_devices.py from facts only -- no product photos anywhere). Each drawing is copied with its white
page background removed so it sits on the app's own tiles. Devices without a drawing get a hand-drawn line glyph
(icons/_glyph-*.svg). Nothing here is traced from a photo any more (the old vtracer pipeline was retired 2026-09-23
together with the cached photos).

Usage: trace_icons.py [--only id,id] [--sheet]   (--sheet also writes icons/_sheet.html, a contact sheet to eyeball)
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import kb_path, load_yaml  # noqa: E402

ICONS = ROOT / "icons"
MAX_BYTES = 16_000

GLYPHS = {  # 64x64 line glyphs, currentColor, for devices with no photo
    "synth": '<rect x="4" y="18" width="56" height="30" rx="4"/><path d="M10 48v-12m8 12v-12m8 12v-12m8 12v-12m8 12v-12m8 12v-12"/><circle cx="14" cy="26" r="3"/><circle cx="26" cy="26" r="3"/>',
    "controller": '<rect x="6" y="12" width="52" height="40" rx="4"/><rect x="12" y="20" width="10" height="10"/><rect x="27" y="20" width="10" height="10"/><rect x="42" y="20" width="10" height="10"/><path d="M12 42h40"/>',
    "module": '<rect x="20" y="4" width="24" height="56" rx="2"/><circle cx="32" cy="16" r="5"/><circle cx="27" cy="36" r="2.5"/><circle cx="37" cy="36" r="2.5"/><circle cx="27" cy="48" r="2.5"/><circle cx="37" cy="48" r="2.5"/>',
    "case": '<rect x="4" y="12" width="56" height="40" rx="3"/><path d="M4 32h56M14 12v40M24 12v40M34 12v40M44 12v40"/>',
    "interface": '<rect x="4" y="20" width="56" height="24" rx="3"/><circle cx="14" cy="32" r="4"/><circle cx="26" cy="32" r="4"/><path d="M36 28h18M36 36h18"/>',
    "utility": '<rect x="8" y="20" width="48" height="24" rx="3"/><circle cx="20" cy="32" r="4"/><circle cx="32" cy="32" r="4"/><circle cx="44" cy="32" r="4"/>',
    "pedal": '<rect x="14" y="6" width="36" height="52" rx="4"/><circle cx="32" cy="18" r="5"/><circle cx="32" cy="44" r="6"/>',
    "instrument": '<path d="M40 6l16 16-22 22"/><circle cx="20" cy="44" r="12"/><path d="M26 38l8-8"/>',
}


def write_glyphs():
    for key, body in GLYPHS.items():
        (ICONS / f"_glyph-{key}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="#8a93a6" '
            f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def as_icon(svg):
    """Drop the white page rect and the fixed width/height so the drawing scales into any tile."""
    svg = re.sub(r'<rect x="-?[\d.]+" y="-?[\d.]+" width="[\d.]+" height="[\d.]+" fill="#ffffff"/>', "", svg, count=1)
    return re.sub(r'<svg xmlns="http://www.w3.org/2000/svg" width="[\d.]+" height="[\d.]+" ',
                  '<svg xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" ', svg, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--sheet", action="store_true")
    args = ap.parse_args()
    kb = kb_path()
    ICONS.mkdir(exist_ok=True)
    write_glyphs()
    only = set(filter(None, args.only.split(",")))
    entries = load_yaml(kb / "tools" / "image_manifest.yaml").get("images", [])
    done, failed = [], []
    for e in entries:
        dev = e["device"]
        if only and dev not in only:
            continue
        src = kb / (e.get("svg") or f"images/{dev}.svg")
        if not src.is_file():
            failed.append((dev, "no drawing in gear-kb/images"))
            continue
        svg = as_icon(src.read_text(encoding="utf-8"))
        (ICONS / f"{dev}.svg").write_text(svg, encoding="utf-8")
        done.append((dev, len(svg)))
    for dev, n in done:
        print(f"  {dev:48s} {n:6d} B")
    for dev, why in failed:
        print(f"  FAILED {dev}: {why}")
    print(f"copied {len(done)} drawings, failed {len(failed)}, over budget {sum(n > MAX_BYTES for _, n in done)}")
    if args.sheet:
        cells = "".join(
            f'<figure><img src="{p.name}"><figcaption>{p.stem}</figcaption></figure>'
            for p in sorted(ICONS.glob("*.svg")))
        (ICONS / "_sheet.html").write_text(
            "<!doctype html><style>body{font:11px sans-serif;display:flex;flex-wrap:wrap;gap:8px;background:#fff}"
            "figure{margin:0;width:120px;text-align:center}img{width:96px;height:96px;background:#eef0f4;"
            "border-radius:8px}figcaption{overflow-wrap:anywhere}</style>" + cells)


if __name__ == "__main__":
    main()
