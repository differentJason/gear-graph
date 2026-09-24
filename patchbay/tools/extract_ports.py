"""Seed each device's patch points (jacks) from the gear-kb manuals -> data/ports.seed.yaml.

Read-only against the KB. Every port found here is tagged `source: manual` (unverified): it is a jack-like label the
manual prints in bold, whose description reads like a connector. Your own edits in ports.yaml always win (see
build_data.py). Devices with no hits fall back to a small per-category default set, tagged `source: default`.

Ports named in the KB's connections.yaml are added too (`source: connections`): those are wiring the owner stated.
"""
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import kb_path, load_yaml  # noqa: E402

# A label is a jack if its NAME contains one of these words...
JACK_WORDS = r"IN|OUT|INPUT|OUTPUT|INPUTS|OUTPUTS|THRU|THROUGH|MIDI|SYNC|CLOCK|CLK|CV|GATE|TRIG|TRIGGER|USB|PHONES|" \
             r"HEADPHONES?|MAIN|AUX|RETURN|SEND|FX|EXP|EXPRESSION|PEDAL|SUSTAIN|FOOTSWITCH|MONO|LINE|MIC|INST|" \
             r"RESET|RUN|ACCENT|PITCH|V/OCT|1V/OCT|VOCT|FM|AM|ENV|LFO|RESET|X-?MOD"
# ...and its DESCRIPTION reads like a connector (keeps bold UI terms such as **TEMPO** or **SAVE** out).
CONNECTOR_HINT = re.compile(
    r"\b(jack|connector|socket|input|output|inputs|outputs|send|receives?|accepts?|connect|cable|trs|ts|xlr|din|"
    r"mm|usb|signal|voltage|cv|gate|trigger|patch|headphones?|midi)\b", re.I)
# a name must carry at least one of these to count (MAIN, LFO, FX alone are product/section names, not jacks)
STRONG = re.compile(r"\b(IN|OUT|INPUTS?|OUTPUTS?|THRU|SYNC|CLOCK|CLK|CV|GATE|TRIG|TRIGGER|USB(-C)?|PHONES|HEADPHONES?|MONO|"
                    r"SEND|RETURN|RESET|ACCENT|PITCH|V/OCT|1V/OCT|FM|EXP|SUSTAIN|FOOTSWITCH)\b")
DIRECTIONAL = re.compile(r"\b(in|out|inputs?|outputs?|thru|phones|headphones?)\b", re.I)
PANEL_SECTION = re.compile(r"panel|connection|jack|input|output|patch|interface|i/o|rear|back|front|overview|midi|cv|sync",
                           re.I)
BOLD = re.compile(r"\*\*([^*\n]{2,40})\*\*\s*[-–—:]?\s*([^\n]*)")
NOT_PORT = re.compile(r"\b(button|knob|switch|led|mode|menu|page|screen|display|encoder|fader|slider|key|pad|"
                      r"level|volume|gain|tempo|setting|settings|parameter|function|chapter|section|note|message|devices|range|operations|"
                      r"power|adapter|attenuverter|attenuator|link|overdub|operation)\b", re.I)


def classify(name, desc=""):
    """(direction, medium) from the port name, then the description. Unknown direction = bidir."""
    n = name.upper()
    d = desc.lower()
    if "USB" in n:
        medium = "usb"
    elif "MIDI" in n or re.search(r"\bmidi\b", d) and not re.search(r"\b(cv|gate|audio)\b", n.lower()):
        medium = "midi"
    elif re.search(r"SYNC|CLOCK|CLK|RESET|RUN", n):
        medium = "clock"
    elif re.search(r"GATE|TRIG|ACCENT|END OF CYCLE|\bEOC\b", n):
        medium = "gate"
    elif re.search(r"ENVELOPE|SLEW|\bCV\b|PITCH|V/OCT|VOCT|\bFM\b|\bAM\b|\bENV\b|\bLFO\b|EXP|EXPRESSION|PEDAL|SUSTAIN|FOOTSWITCH|X-?MOD", n):
        medium = "cv"
    else:
        medium = "audio"
    if re.search(r"\bTHRU\b|THROUGH", n):
        direction = "out"
    elif re.search(r"\bIN\b|INPUTS?\b|RETURN|\bMIC\b|\bINST\b|PEDAL|SUSTAIN|FOOTSWITCH|EXP", n):
        direction = "in"
    elif re.search(r"\bOUT\b|OUTPUTS?\b|PHONES|HEADPHONE|\bSEND\b|\bMAIN\b|\bMONO\b", n):
        direction = "out"
    elif medium == "usb":
        direction = "bidir"
    elif re.search(r"\b(accepts?|receives?|input)\b", d):
        direction = "in"
    elif re.search(r"\b(outputs?|sends?)\b", d):
        direction = "out"
    elif medium in ("cv", "gate", "clock"):
        direction = "in"                           # a bare "PITCH CV" / "TRIGGER" jack is a control input
    else:
        direction = "bidir"
    return direction, medium


# section titles that talk ABOUT jacks rather than naming one
PROSE_TITLE = re.compile(r"\band\b|&|,|^connect|\b(layout|rate|assign|leds?|activity|real-time|direct|freezing|"
                         r"settings?|using|about|1U)\b|^\d+:", re.I)
LIST_JACK = re.compile(r"^\s*-\s+(?:\(?[^\s)]{0,3}\)\s*)?([A-Za-z0-9/ +-]{2,40}?)\s+(?:jacks?|connectors?|sockets?|terminals?)\b",
                       re.M)
NUMBERING = re.compile(r"^\s*(\(\d+\)|\[[A-Z0-9]{1,3}\]|[A-Z0-9]{1,2}\]|[.\d]+\.?(?=\s|$)|\.)\s*")
FOREIGN = re.compile(r"\b(MANUELL|MODO|DE|DEL|ENTRADA|SALIDA|SORTIE|ENTREE|EINGANG|AUSGANG|UND|ET|PER|DI)\b", re.I)


def clean_label(raw):
    s = raw.replace("\u200c", " ").replace("\u200b", " ").strip()
    prev = None
    while prev != s:                                  # "(70) ", "[A] ", "A] ", ".1.2.2. ", "7. " numbering, repeatedly
        prev, s = s, NUMBERING.sub("", s)
    s = re.split(r"\s[-–—]\s|[\[(]", s)[0]           # "CV IN - each channel..." / "TRIG (clock" -> the name only
    s = re.sub(r"^[^A-Za-z0-9]+", "", s)               # OCR debris before the name: "@ MONO"
    s = re.sub(r"^(connect(ing)?\s+)?(the|a|an)\s+", "", s, flags=re.I)   # "Connect the SYNC IN" -> "SYNC IN"
    s = re.sub(r"\s+", " ", s).strip(" .:-–—)]")
    s = re.sub(r"\s+(connector|interface|jacks?|port|connection)$", "", s, flags=re.I)
    return s.strip(" .,;:-–—")


def is_port_label(label, desc):
    if not label or len(label.split()) > 5 or len(label) < 2:
        return False
    if re.search(r"[^\x20-\x7e]", label) or FOREIGN.search(label):              # other-language blocks of multilingual sheets
        return False
    if not re.search(rf"\b({JACK_WORDS})\b", label.upper()) or not STRONG.search(label.upper()):
        return False
    letters = re.sub(r"[^A-Za-z]", "", label)
    if not letters.isupper() and not DIRECTIONAL.search(label):   # mixed case must say in/out ("Input 1", "Sync In")
        return False
    if NOT_PORT.search(label):
        return False
    return bool(CONNECTOR_HINT.search(desc) or CONNECTOR_HINT.search(label))


def front_matter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            try:
                return yaml.safe_load(text[3:end]) or {}, text[end + 4:]
            except yaml.YAMLError:
                pass
    return {}, text


def from_markdown(manuals_dir):
    """device id -> {port name: {dir, medium, evidence}} from bold labels in panel-ish sections."""
    found = defaultdict(dict)
    for md in sorted(manuals_dir.glob("*/*.md")):
        fm, body = front_matter(md.read_text(errors="replace"))
        dev = fm.get("device")
        if not dev:
            continue
        title = str(fm.get("title", "")) + " " + " ".join(map(str, fm.get("section_path") or []))
        # a section per jack (module manuals: "4. Gate Output (Purple Out)"): the title itself is the jack
        own = clean_label(str(fm.get("title", "")))
        text = re.sub(r"^#.*$|^>.*$", "", body, flags=re.M).strip()
        if is_port_label(own, text[:300]) and len(own.split()) <= 4 and not PROSE_TITLE.search(own):
            candidates = [(own, text[:120])]
        else:
            candidates = []
        if PANEL_SECTION.search(title):
            candidates += [(clean_label(m.group(1)), m.group(2).strip()) for m in BOLD.finditer(body)]
            # plain list items naming a jack: "- (3) MIDI OUT jack" (OCR'd manuals have no bold)
            candidates += [(clean_label(m.group(1)), m.group(0)) for m in LIST_JACK.finditer(body)]
        for label, desc in candidates:
            if not is_port_label(label, desc):
                continue
            key = label.upper()
            if key in (k.upper() for k in found[dev]):
                continue
            direction, medium = classify(label, desc)
            found[dev][label] = {"dir": direction, "medium": medium,
                                 "evidence": f"{md.parent.name}/{md.name} (bold jack label; manual text is not copied)"}
    return found


def from_eurorack_pdfs(pdf_dir, known_devices, have_md):
    """Fallback for Eurorack modules with a PDF but no converted markdown: ALL-CAPS jack-like lines from pdftotext."""
    found = defaultdict(dict)
    if not pdf_dir.is_dir():
        return found
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        stem = pdf.stem.split("__")[0]
        dev = next((d for d in known_devices if d == stem or d.startswith(stem) or stem.startswith(d)), None)
        if not dev:
            continue
        try:
            text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                                  timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in text.splitlines():
            for chunk in re.split(r"\s{3,}", line.strip()):
                chunk = clean_label(chunk)
                if chunk.isupper() and is_port_label(chunk, chunk + " jack"):
                    if chunk.upper() not in (k.upper() for k in found[dev]):
                        direction, medium = classify(chunk)
                        found[dev][chunk] = {"dir": direction, "medium": medium, "evidence": f"{pdf.name} (pdftotext)"}
    return found


def from_connections(conn):
    """Ports the owner named in connections.yaml, with direction from the cable's direction."""
    found = defaultdict(dict)
    for link in conn.get("links", []):
        both = link.get("bidirectional")
        for end, direction in (("from", "out"), ("to", "in")):
            port = link.get(f"{end}_port")
            if port:
                found[link[end]][port] = {"dir": "bidir" if both else direction, "medium": link["medium"],
                                          "evidence": "connections.yaml (owner-stated)"}
    return found


def main():
    kb = kb_path()
    inv_ids = [i["id"] for i in load_yaml(kb / "inventory.yaml")["items"]]
    md = from_markdown(kb / "docs" / "manuals")
    pdf = from_eurorack_pdfs(kb / "sources" / "eurorack", inv_ids, set(md))
    conn = from_connections(load_yaml(kb / "connections.yaml"))

    out = {}
    for dev in inv_ids:
        ports = {}
        for source, table in (("connections", conn), ("manual", md), ("manual", pdf)):
            for name, p in table.get(dev, {}).items():
                if name.upper() in (k.upper() for k in ports):
                    continue
                ports[name] = {"dir": p["dir"], "medium": p["medium"], "source": source, "evidence": p["evidence"]}
        if ports:
            out[dev] = ports

    dest = ROOT / "data" / "ports.seed.yaml"
    dest.parent.mkdir(exist_ok=True)
    header = "# GENERATED by tools/extract_ports.py from the gear-kb manuals. Do not edit: put changes in ports.yaml.\n"
    dest.write_text(header + yaml.safe_dump(out, sort_keys=True, allow_unicode=True, width=140))
    total = sum(len(v) for v in out.values())
    print(f"ports.seed.yaml: {total} ports on {len(out)} of {len(inv_ids)} devices "
          f"(manual md: {len(md)}, eurorack pdf: {len(pdf)}, connections: {len(conn)})")


if __name__ == "__main__":
    main()
