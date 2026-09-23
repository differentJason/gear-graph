"""MkDocs Material theme settings shared by build_site.py and build_public.py.

Colours, type and marks live in docs/stylesheets/tni.css.
Scheme names stay default/slate because viz.css keys its dark-mode colours on "slate"."""

THEME = {"name": "material", "font": False, "palette": [
    {"media": "(prefers-color-scheme: light)", "scheme": "default", "primary": "custom", "accent": "custom",
     "toggle": {"icon": "material/circle-half-full", "name": "Switch to dark mode"}},
    {"media": "(prefers-color-scheme: dark)", "scheme": "slate", "primary": "custom", "accent": "custom",
     "toggle": {"icon": "material/circle-half", "name": "Switch to light mode"}}]}
EXTRA_CSS = ["stylesheets/tni.css"]
