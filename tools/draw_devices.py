#!/usr/bin/env python3
"""Draw an ORIGINAL illustration of every inventory item -> images/<id>.svg (+ images/<id>.jpg via Inkscape).

    .venv/bin/python tools/draw_devices.py            # all items
    .venv/bin/python tools/draw_devices.py korg-m1    # just these

Replaces the product photos this repo used to cache: nothing here is traced from, or copies, a photo or a maker's
panel. Every drawing is built from this repo's own facts only -- name, maker, category, and for Eurorack the width in
HP and the 1U/3U format (docs/eurorack/<id>.md, else the inventory's own hp/format) and, for cases, the recorded mounting order (connections.yaml).
Knobs, jacks, keys and pads are generic and deterministic (seeded by the id); they illustrate the KIND of device and
do not claim to show its real panel layout. Colors are neutral finishes picked per maker (not anyone's trade dress).
The visual grammar follows the gear-patchbay faceplates (corner screws, title at the top, accent rule).
"""
import hashlib
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "images"
HPX, U3, U1 = 15, 380, 117                       # px per HP, 3U and 1U panel heights (patchbay's scale)
FINISH = [("#2b2e34", "#eceef1"), ("#d5d8dc", "#1b1d21"), ("#33465b", "#eef2f7"), ("#e7e0cd", "#2b2620"),
          ("#20392f", "#e7f0ec"), ("#4a2b2b", "#f4eaea"), ("#b7bdc5", "#15171a"), ("#3a3350", "#eeeaf7"),
          ("#1c1d20", "#e4e6ea"), ("#8a5a2e", "#fbf3ea")]
ACCENT = ["#e0591a", "#0b7fe0", "#12a594", "#c29100", "#8e4ec6", "#d13b3f", "#5b8c32", "#d0579a"]
FONT = "DejaVu Sans, Arial, Helvetica, sans-serif"
KEYS = {"korg-m1": 30, "akai-timbre-wolf": 22, "arturia-keystep": 18, "akai-mpk-mini-mk3": 15,
        "sonicware-liven-texture-lab": 15}      # instruments with a keyboard: how many white keys to draw


def h(s):
    return int(hashlib.md5(str(s).encode()).hexdigest(), 16)


class Rng:                                        # tiny deterministic generator (same drawing every run)
    def __init__(self, seed):
        self.s = h(seed) & 0xFFFFFFFF or 1

    def __call__(self, n):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s % n


def finish(item):
    bg, ink = FINISH[h(item.get("manufacturer") or item["id"]) % len(FINISH)]
    return bg, ink, ACCENT[h(item["id"]) % len(ACCENT)]


def short_name(item):
    name, maker = item["name"], item.get("manufacturer") or ""
    return re.sub(r"^" + re.escape(maker) + r"\s+", "", name, flags=re.I) if maker else name


def wrap(text, width, lines):
    out, cur = [], ""
    for w in str(text).split():
        if len((cur + " " + w).strip()) > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    out = out[:lines]
    return [l if len(l) <= width else l[: max(1, width - 1)] + "…" for l in out]


def text(x, y, s, size, fill, anchor="middle", weight="bold", opacity=1):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" fill-opacity="{opacity}" text-anchor="{anchor}">{escape(s)}</text>')


def screw(x, y):
    return (f'<circle cx="{x}" cy="{y}" r="3.4" fill="#9aa0a8" stroke="#55595f" stroke-width=".8"/>'
            f'<path d="M{x - 2},{y} h4 M{x},{y - 2} v4" stroke="#44484e" stroke-width="1"/>')


def knob(x, y, r, ink, accent, rng):
    a = (rng(270) - 135) * 3.14159 / 180
    import math
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#16181b" stroke="{ink}" stroke-opacity=".35"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * .72:.1f}" fill="#2a2d31"/>'
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + math.sin(a) * r * .8:.1f}" y2="{y - math.cos(a) * r * .8:.1f}" '
            f'stroke="{accent}" stroke-width="{max(1.5, r / 5):.1f}" stroke-linecap="round"/>')


def jack(x, y, r, ring):
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#cfd3d8" stroke="{ring}" stroke-width="{r * .35:.1f}"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * .42:.1f}" fill="#101113"/>')


SHEEN = ('<defs><linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" '
         'stop-opacity=".10"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" '
         'stop-opacity=".12"/></linearGradient></defs>')


def svg(w, h_, body, pad=10):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad}" height="{h_ + 2 * pad}" '
            f'viewBox="{-pad} {-pad} {w + 2 * pad} {h_ + 2 * pad}">{SHEEN}'
            f'<rect x="{-pad}" y="{-pad}" width="{w + 2 * pad}" height="{h_ + 2 * pad}" fill="#ffffff"/>{body}</svg>\n')


# ---------- Eurorack: a faceplate at true HP width ----------
def euro(item, hp, fmt):
    rng, (bg, ink, acc) = Rng(item["id"]), finish(item)
    w, hh, one_u = hp * HPX, (U1 if fmt == "1U" else U3), fmt == "1U"
    fs = 7.5 if w < 70 else 10
    title = wrap(short_name(item).upper(), max(4, int((w - 8) / (fs * 0.62))), 1 if one_u else 3)
    title_h = 17 if one_u else 16 + len(title) * (fs + 2)
    b = [f'<rect width="{w}" height="{hh}" fill="{bg}"/><rect width="{w}" height="{hh}" fill="url(#sheen)"/>',
         screw(7.5, 7), screw(w - 7.5, hh - 7)]
    if hp >= 10:
        b += [screw(w - 7.5, 7), screw(7.5, hh - 7)]
    b.append(f'<rect x="{w * .2:.1f}" y="{title_h - 5}" width="{w * .6:.1f}" height="1.6" fill="{acc}"/>')
    b += [text(w / 2, (12 if one_u else 22 + i * (fs + 2)), t, fs, ink) for i, t in enumerate(title)]
    cols = max(1, int((w - 6) // 40))
    cw = (w - 6) / cols
    if one_u:                                     # 1U tile: one band of knobs over one band of jacks
        for c in range(cols):
            x = 3 + cw * (c + .5)
            b.append(knob(x, 48, min(11, cw * .3), ink, acc, rng))
            b.append(jack(x, 88, min(7, cw * .2), ACCENT[rng(len(ACCENT))]))
    else:
        krows = 1 + min(3, hp // 6) if hp >= 4 else 1
        y = title_h + 26
        for r in range(krows):
            n = cols if r % 2 == 0 or cols == 1 else max(1, cols - 1)
            step = (w - 6) / n
            for c in range(n):
                b.append(knob(3 + step * (c + .5), y, min(15 if r == 0 else 11, step * .34), ink, acc, rng))
            y += 50 if r == 0 else 40
        jrows = max(1, min(4, int((hh - 30 - y) // 38)))
        y0 = hh - 30 - jrows * 38
        for r in range(jrows):
            for c in range(cols):
                x, yy = 3 + cw * (c + .5), y0 + r * 38 + 19
                if r == jrows - 1:
                    b.append(f'<rect x="{x - cw / 2 + 3:.1f}" y="{yy - 15:.1f}" width="{cw - 6:.1f}" height="30" rx="4" '
                             f'fill="#000" fill-opacity=".28"/>')
                b.append(jack(x, yy, min(8, cw * .2), ACCENT[rng(len(ACCENT))]))
        maker = item.get("manufacturer") or ""
        b.append(text(w / 2, hh - 9, maker[: int(w / 4.6)], 7, ink, weight="normal", opacity=.8))
    return svg(w, hh, "".join(b))


# ---------- everything else: a stylized top-down / front view by category ----------
def card(item, draw_art, art_w=520, art_h=260):
    """Name block on the left, the category drawing on the right, in the item's finish."""
    bg, ink, acc = finish(item)
    W, H, NAME = 150 + art_w + 20, art_h + 40, 150
    b = [f'<rect width="{W}" height="{H}" rx="8" fill="{bg}"/><rect width="{W}" height="{H}" rx="8" fill="url(#sheen)"/>',
         f'<rect width="{W}" height="6" rx="3" fill="{acc}"/>']
    for i, t in enumerate(wrap(short_name(item), 16, 3)):
        b.append(text(14, 38 + i * 19, t, 16, ink, anchor="start"))
    b.append(text(14, 38 + 3 * 19 + 4, (item.get("manufacturer") or "")[:22], 11, ink, anchor="start", weight="normal", opacity=.8))
    b.append(text(14, H - 16, item.get("category", "").replace("-", " "), 10, ink, anchor="start", weight="normal", opacity=.6))
    b.append(f'<line x1="{NAME - 8}" y1="16" x2="{NAME - 8}" y2="{H - 16}" stroke="{ink}" stroke-opacity=".18"/>')
    b.append(f'<g transform="translate({NAME + 4},20)">{draw_art(art_w, art_h, ink, acc, Rng(item["id"]))}</g>')
    return svg(W, H, "".join(b))


def panel_knobs(w, y, n, r, ink, acc, rng, x0=0):
    if n <= 0:
        return ""
    step = w / n
    return "".join(knob(x0 + step * (i + .5), y, r, ink, acc, rng) for i in range(n))


def art_keyboard(nwhite):
    def f(w, h_, ink, acc, rng):
        body = f'<rect x="0" y="0" width="{w}" height="{h_}" rx="10" fill="#1b1d20"/>'
        body += panel_knobs(w * .55, 45, 5, 15, ink, acc, rng, x0=10)
        body += f'<rect x="{w * .62:.1f}" y="22" width="{w * .33:.1f}" height="46" rx="4" fill="#0e2a24" stroke="{acc}" stroke-opacity=".5"/>'
        kw, ky, kh = (w - 20) / nwhite, 95, h_ - 105
        for i in range(nwhite):
            body += f'<rect x="{10 + i * kw:.1f}" y="{ky}" width="{kw - 1.5:.1f}" height="{kh}" rx="2" fill="#f4f4f1"/>'
        for i in range(nwhite - 1):
            if i % 7 not in (2, 6):
                body += f'<rect x="{10 + (i + 1) * kw - kw * .3:.1f}" y="{ky}" width="{kw * .6:.1f}" height="{kh * .6:.1f}" rx="1.5" fill="#15171a"/>'
        return body
    return f


def art_pads(cols, rows, knobs=6):
    def f(w, h_, ink, acc, rng):
        body = f'<rect x="0" y="0" width="{w}" height="{h_}" rx="10" fill="#1b1d20"/>'
        body += panel_knobs(w - 20, 40, knobs, 14, ink, acc, rng, x0=10)
        pw, ph = (w - 30) / cols, (h_ - 90) / rows
        for r in range(rows):
            for c in range(cols):
                lit = rng(5) == 0
                body += (f'<rect x="{15 + c * pw + 3:.1f}" y="{75 + r * ph + 3:.1f}" width="{pw - 6:.1f}" height="{ph - 6:.1f}" '
                         f'rx="5" fill="{acc if lit else "#3a3d42"}" fill-opacity="{.85 if lit else 1}"/>')
        return body
    return f


def art_stomp(knobs):
    def f(w, h_, ink, acc, rng):
        bw = min(w * .45, h_ * .75)
        x0 = (w - bw) / 2
        body = f'<rect x="{x0:.1f}" y="0" width="{bw:.1f}" height="{h_}" rx="12" fill="{acc}" fill-opacity=".85"/>'
        body += panel_knobs(bw - 20, 45, knobs, min(20, bw / (knobs * 2.8)), "#fff", "#fff", rng, x0=x0 + 10)
        body += f'<circle cx="{w / 2:.1f}" cy="{h_ * .52:.1f}" r="5" fill="#ff4d3d"/>'
        body += f'<circle cx="{w / 2:.1f}" cy="{h_ * .8:.1f}" r="22" fill="#c9ccd1" stroke="#6b7078" stroke-width="3"/>'
        for x in (x0 - 10, x0 + bw):
            body += f'<rect x="{x:.1f}" y="{h_ * .25:.1f}" width="10" height="20" rx="2" fill="#7d8289"/>'
        return body
    return f


def art_cabinet(cones, grille=False):
    def f(w, h_, ink, acc, rng):
        cw = min(w * .9, h_ * (1.4 if cones > 1 else .8))
        x0 = (w - cw) / 2
        body = f'<rect x="{x0:.1f}" y="0" width="{cw:.1f}" height="{h_}" rx="10" fill="#202225"/>'
        if grille:
            body += f'<rect x="{x0 + 12:.1f}" y="40" width="{cw - 24:.1f}" height="{h_ - 52}" rx="6" fill="#2e3136"/>'
            body += panel_knobs(cw - 24, 20, 5, 9, ink, acc, rng, x0=x0 + 12)
        for i in range(cones):
            cx = x0 + cw * (i + .5) / cones
            cy, r = (h_ * .6 if grille else h_ * (.35 if cones == 1 else .5)), min(cw / cones * .38, h_ * .3)
            body += (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#111" stroke="#555a61" stroke-width="3"/>'
                     f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * .35:.1f}" fill="#3b3f45"/>')
            if cones == 1 and not grille:
                body += f'<circle cx="{cx:.1f}" cy="{h_ * .78:.1f}" r="{r * .45:.1f}" fill="#111" stroke="#555a61" stroke-width="2"/>'
        return body
    return f


def art_strip(njacks, meters=0, knobs=0):
    def f(w, h_, ink, acc, rng):
        sh = min(h_, 120)
        y0 = (h_ - sh) / 2
        body = f'<rect x="0" y="{y0:.1f}" width="{w}" height="{sh}" rx="8" fill="#1f2226"/>'
        x = 20
        for _ in range(knobs):
            body += knob(x + 16, y0 + sh * .5, 14, ink, acc, rng)
            x += 44
        for i in range(meters):
            for s in range(6):
                body += f'<rect x="{x + i * 14}" y="{y0 + 18 + s * 14:.1f}" width="9" height="10" rx="1" fill="{"#e24" if s == 0 else "#2c6" if s > 2 else "#eb3"}" fill-opacity=".9"/>'
        x += meters * 14 + (14 if meters else 0)
        step = (w - x - 15) / max(1, njacks)
        for i in range(njacks):
            body += jack(x + step * (i + .5), y0 + sh * .5, min(12, step * .3), ACCENT[rng(len(ACCENT))])
        return body
    return f


def art_headphones(w, h_, ink, acc, rng):
    cx = w / 2
    return (f'<path d="M{cx - 90},{h_ * .62} C{cx - 95},{h_ * .05} {cx + 95},{h_ * .05} {cx + 90},{h_ * .62}" fill="none" '
            f'stroke="#26292d" stroke-width="16" stroke-linecap="round"/>'
            f'<rect x="{cx - 120}" y="{h_ * .5:.1f}" width="55" height="{h_ * .42:.1f}" rx="22" fill="#2e3136"/>'
            f'<rect x="{cx + 65}" y="{h_ * .5:.1f}" width="55" height="{h_ * .42:.1f}" rx="22" fill="#2e3136"/>'
            f'<rect x="{cx - 112}" y="{h_ * .56:.1f}" width="39" height="{h_ * .3:.1f}" rx="16" fill="none" stroke="{acc}" stroke-width="3"/>'
            f'<rect x="{cx + 73}" y="{h_ * .56:.1f}" width="39" height="{h_ * .3:.1f}" rx="16" fill="none" stroke="{acc}" stroke-width="3"/>')


def art_string(bass):
    def f(w, h_, ink, acc, rng):
        y = h_ / 2
        n = 4 if bass else 6
        body = (f'<path d="M20,{y - 60} C60,{y - 90} 150,{y - 70} 170,{y - 35} C190,{y - 20} 210,{y - 45} 230,{y - 40} '
                f'L230,{y + 40} C210,{y + 45} 190,{y + 20} 170,{y + 35} C150,{y + 70} 60,{y + 90} 20,{y + 60} '
                f'C0,{y + 30} 0,{y - 30} 20,{y - 60} Z" fill="{acc}" fill-opacity=".9" stroke="#222" stroke-width="3"/>')
        body += f'<rect x="228" y="{y - 13}" width="{w - 300}" height="26" rx="3" fill="#6b4a2b"/>'
        for i in range(1, 14):
            body += f'<line x1="{228 + i * (w - 300) / 14:.1f}" y1="{y - 13}" x2="{228 + i * (w - 300) / 14:.1f}" y2="{y + 13}" stroke="#c8c8c8" stroke-width="1.5"/>'
        body += f'<rect x="{w - 74}" y="{y - 24}" width="66" height="48" rx="10" fill="#2a2a2a"/>'
        for i in range(n):
            yy = y - 10 + i * 20 / (n - 1)
            body += f'<line x1="60" y1="{yy:.1f}" x2="{w - 70}" y2="{yy:.1f}" stroke="#ddd" stroke-width="{1.8 if bass else 1}"/>'
        body += f'<rect x="80" y="{y - 20}" width="14" height="40" rx="3" fill="#111"/><rect x="120" y="{y - 20}" width="14" height="40" rx="3" fill="#111"/>'
        return body
    return f


def art_computer(w, h_, ink, acc, rng):
    bw = min(w * .55, 280)
    x0 = (w - bw) / 2
    return (f'<rect x="{x0:.1f}" y="{h_ * .25:.1f}" width="{bw:.1f}" height="{h_ * .5:.1f}" rx="18" fill="#c9ccd1" stroke="#8a8f96" stroke-width="2"/>'
            f'<circle cx="{x0 + bw - 30:.1f}" cy="{h_ * .5:.1f}" r="5" fill="{acc}"/>'
            f'<rect x="{x0 + 20:.1f}" y="{h_ * .62:.1f}" width="{bw * .3:.1f}" height="6" rx="3" fill="#8a8f96"/>')


def art_software(w, h_, ink, acc, rng):
    body = f'<rect x="10" y="10" width="{w - 20}" height="{h_ - 20}" rx="8" fill="#23262a"/>'
    body += f'<rect x="10" y="10" width="{w - 20}" height="26" rx="8" fill="#34383e"/>'
    body += "".join(f'<circle cx="{28 + i * 18}" cy="23" r="5" fill="{c}"/>' for i, c in enumerate(("#e0594a", "#e3b341", "#3fb950")))
    for t in range(5):
        y = 55 + t * (h_ - 80) / 5
        for c in range(1 + rng(3)):
            x = 30 + rng(int(w * .5))
            body += f'<rect x="{x}" y="{y:.1f}" width="{40 + rng(140)}" height="{(h_ - 80) / 5 - 8:.1f}" rx="4" fill="{ACCENT[(t + c) % len(ACCENT)]}" fill-opacity=".8"/>'
    return body


def art_rackcase(w, h_, ink, acc, rng):
    body = f'<rect x="0" y="0" width="{w}" height="{h_}" rx="8" fill="#9aa0a8"/>'
    for r in range(3):
        y = 12 + r * (h_ - 24) / 3
        body += f'<rect x="12" y="{y:.1f}" width="{w - 24}" height="{(h_ - 24) / 3 - 8:.1f}" fill="#2a2d31"/>'
    return body


ART = {
    "synth": None, "groovebox": art_pads(8, 2, 8), "drum-machine": art_pads(8, 2, 8), "sampler-drum-machine": art_pads(8, 2, 8),
    "sequencer": art_pads(8, 4, 4), "controller": art_pads(8, 5, 0), "midi-utility": art_strip(6),
    "audio-interface": art_strip(8, meters=2, knobs=3), "di-preamp": art_strip(3, knobs=2),
    "monitors": art_cabinet(1), "amp": art_cabinet(1, grille=True), "headphones": art_headphones,
    "guitar": art_string(False), "bass": art_string(True), "computer": art_computer, "software": art_software,
}


def art_for(item):
    iid, cat = item["id"], item.get("category", "")
    if iid in KEYS:
        return art_keyboard(KEYS[iid])
    if cat.startswith("pedal"):
        return art_stomp(2 + h(iid) % 3)
    if cat == "synth":
        return art_pads(8, 2, 8)
    return ART.get(cat) or art_rackcase


# ---------- cases: the rows drawn to scale with the recorded modules in their recorded order ----------
def case_drawing(case, items, specs, placements):
    rows = case["rows"]
    W = max(r["hp"] for r in rows) * HPX
    heights = [U1 if r["format"] == "1U" else U3 for r in rows]
    gap, pad = 14, 18
    H = sum(heights) + gap * (len(rows) - 1)
    item = items[case["id"]]
    bg, ink, acc = finish(item)
    b = [f'<rect x="{-pad}" y="{-pad - 30}" width="{W + 2 * pad}" height="{H + 2 * pad + 30}" rx="10" fill="#3a3d42"/>',
         text(0, -pad - 8, item["name"], 16, "#f0f1f3", anchor="start"),
         text(W, -pad - 8, "illustration: modules in recorded order, widths to scale", 10, "#c9ccd1", anchor="end", weight="normal")]
    y = 0
    for ri, (row, rh) in enumerate(zip(rows, heights), 1):
        b.append(f'<rect x="0" y="{y}" width="{row["hp"] * HPX}" height="{rh}" fill="#1a1c1f"/>')
        b.append(f'<rect x="0" y="{y}" width="{row["hp"] * HPX}" height="6" fill="#8d939b"/><rect x="0" y="{y + rh - 6}" width="{row["hp"] * HPX}" height="6" fill="#8d939b"/>')
        x = 0
        mods = sorted((p for p in placements if p["case"] == case["id"] and p.get("row_index", 1) == ri),
                      key=lambda p: p.get("position", 0))
        for p in mods:
            m = items.get(p["module"])
            hp = (specs.get(p["module"]) or {}).get("hp") or 4
            mbg, mink, macc = finish(m)
            mw = hp * HPX
            b.append(f'<rect x="{x + 1}" y="{y + 1}" width="{mw - 2}" height="{rh - 2}" fill="{mbg}" stroke="#000" stroke-opacity=".4"/>')
            b.append(f'<rect x="{x + mw * .2:.1f}" y="{y + 14}" width="{mw * .6:.1f}" height="1.6" fill="{macc}"/>')
            label = short_name(m).upper()
            if rh > 200 and hp >= 3:
                fs = 9 if hp >= 6 else 7
                b.append(f'<g transform="translate({x + mw / 2:.1f},{y + rh / 2:.1f}) rotate(-90)">'
                         f'{text(0, fs / 3, label[: int((rh - 40) / (fs * .62))], fs, mink)}</g>')
            else:
                b.append(text(x + mw / 2, y + rh / 2 + 3, label[: max(2, int(mw / 6))], 8, mink))
            x += mw
        free = row["hp"] - sum(((specs.get(p["module"]) or {}).get("hp") or 4) for p in mods)
        if free > 0:
            b.append(text(x + free * HPX / 2, y + rh / 2 + 4, f"{free} HP free", 11, "#8d939b", weight="normal"))
        y += rh + gap
    return svg(W, H, "".join(b), pad=pad + 30)


def load_specs():
    specs = {}
    for p in (ROOT / "docs" / "eurorack").glob("*.md"):
        m = re.match(r"---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
        fm = yaml.safe_load(m.group(1)) if m else {}
        if fm.get("module"):
            hp = (fm.get("specs") or {}).get("hp")
            specs[fm["module"]] = {"hp": hp.get("value") if isinstance(hp, dict) else hp, "format": fm.get("format", "3U")}
    return specs


def render_jpg(svg_path, jpg_path):
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "x.png"
        subprocess.run(["inkscape", str(svg_path), "--export-type=png", f"--export-filename={png}",
                        "--export-background=#ffffff", "--export-background-opacity=1", "--export-dpi=192"],
                       check=True, capture_output=True)
        subprocess.run(["convert", str(png), "-background", "white", "-flatten", "-quality", "90", str(jpg_path)],
                       check=True, capture_output=True)


def main():
    items = {i["id"]: i for i in yaml.safe_load((ROOT / "inventory.yaml").read_text())["items"]}
    conn = yaml.safe_load((ROOT / "connections.yaml").read_text())
    cases = {c["id"]: c for c in conn.get("cases", [])}
    placements = conn.get("placements", [])
    specs = load_specs()
    wanted = set(sys.argv[1:]) or set(items)
    OUT.mkdir(exist_ok=True)
    for iid in sorted(wanted):
        it = items[iid]
        cat = it.get("category", "")
        if iid in cases:
            doc = case_drawing(cases[iid], items, specs, placements)
        elif cat == "eurorack-module" and ((specs.get(iid) or {}).get("hp") or it.get("hp")):
            sp_ = specs.get(iid) or {}
            doc = euro(it, sp_.get("hp") or it["hp"], sp_.get("format") or it.get("format", "3U"))
        else:
            doc = card(it, art_for(it))
        sp = OUT / f"{iid}.svg"
        sp.write_text(doc, encoding="utf-8")
        render_jpg(sp, OUT / f"{iid}.jpg")
        print(f"drew {iid}")
    print(f"{len(wanted)} illustrations written to images/")


if __name__ == "__main__":
    main()
