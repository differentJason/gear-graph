#!/usr/bin/env python3
"""Check tools/image_manifest.yaml against inventory.yaml and images/ (original illustrations, committed).

    .venv/bin/python tools/validate_images.py

Errors : a manifest entry whose device is not in inventory.yaml, whose file/svg does not exist under images/, whose
         photo_type is not 'original', or with no source; an images/ file with no manifest entry (orphaned).
Warnings: an inventory item with no image at all (run tools/draw_devices.py).
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PHOTO_TYPES = {"original"}   # drawn by tools/draw_devices.py; no product photos are kept


def main():
    inv = {i["id"] for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    images_dir = ROOT / "images"
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    if not images_dir.exists():
        print("  not checked (images/ is missing: run tools/draw_devices.py)")
        print("checked 0 image_manifest.yaml entries: 0 error(s), 0 warning(s)")
        sys.exit(0)

    m = yaml.safe_load((ROOT / "tools" / "image_manifest.yaml").read_text()) or {}
    entries = m.get("images", [])
    on_disk = {p.name for p in images_dir.iterdir() if p.is_file()}
    documented = set()

    for n, e in enumerate(entries, 1):
        tag = f"entry {n} ({e.get('device')})"
        if e.get("device") not in inv:
            err(f"{tag}: device {e.get('device')!r} is not in inventory.yaml")
        f = Path(e.get("file", ""))
        if f.name not in on_disk:
            err(f"{tag}: file {e.get('file')!r} does not exist under images/")
        else:
            documented.add(f.name)
        if e.get("photo_type") not in PHOTO_TYPES:
            err(f"{tag}: photo_type {e.get('photo_type')!r} not one of {sorted(PHOTO_TYPES)}")
        if e.get("svg"):
            if Path(e["svg"]).name not in on_disk:
                err(f"{tag}: svg {e['svg']!r} does not exist under images/")
            else:
                documented.add(Path(e["svg"]).name)
        if not e.get("source"):
            err(f"{tag}: no source (generator) recorded")

    for name in sorted(on_disk - documented):
        err(f"images/{name}: no image_manifest.yaml entry (orphaned, undocumented)")

    photographed = {e["device"] for e in entries}
    for mid in sorted(inv - photographed):
        warn(f"{mid}: no image recorded yet")

    for w in warnings:
        print("WARNING", w)
    for e in errors:
        print("ERROR  ", e)
    print(f"checked {len(entries)} image_manifest.yaml entries, {len(on_disk)} files on disk: "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
