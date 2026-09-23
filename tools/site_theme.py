"""MkDocs Material theme settings shared by build_site.py and build_public.py.

Colours, type and marks live in docs/stylesheets/tni.css.
Scheme names stay default/slate because viz.css keys its dark-mode colours on "slate"."""
import hashlib
from pathlib import Path

THEME = {"name": "material", "font": False, "palette": [
    {"media": "(prefers-color-scheme: light)", "scheme": "default", "primary": "custom", "accent": "custom",
     "toggle": {"icon": "material/circle-half-full", "name": "Switch to dark mode"}},
    {"media": "(prefers-color-scheme: dark)", "scheme": "slate", "primary": "custom", "accent": "custom",
     "toggle": {"icon": "material/circle-half", "name": "Switch to light mode"}}]}
EXTRA_CSS = ["stylesheets/tni.css"]


def versioned(paths, stylesheets_dir):
    """Append a short content-hash query string to each stylesheet path. Material's own bundle is
    content-hashed into its filename (main.<hash>.min.css), so it busts cache on every change; these
    two hand-written sheets are not, so without this a browser can keep serving a stale copy of the
    theme or the chart CSS across a redeploy."""
    out = []
    for p in paths:
        f = Path(stylesheets_dir) / Path(p).name
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:8] if f.exists() else "0"
        out.append(f"{p}?v={h}")
    return out
