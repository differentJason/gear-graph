#!/usr/bin/env python3
"""Check tools/image_manifest.yaml against inventory.yaml and images/ (local-only, gitignored gear photos).

    .venv/bin/python tools/validate_images.py

Errors : a manifest entry whose device is not in inventory.yaml, whose file does not exist under images/, or whose
         photo_type is not official/retailer; an images/ file with no manifest entry (orphaned, undocumented).
Warnings: an inventory item with no image at all (images/ is local-only, so this is expected until fetched, not a
          failure).
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PHOTO_TYPES = {"official", "retailer"}


def main():
    inv = {i["id"] for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    images_dir = ROOT / "images"
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    if not images_dir.exists():
        print("  not checked (images/ is local-only and not present)")
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
        if not e.get("source_url"):
            err(f"{tag}: no source_url recorded")

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
