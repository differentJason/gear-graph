#!/usr/bin/env python3
"""Graph the Patchbay app's CODE against its USER DOCUMENTATION and the knowledge-base DATA it reads/writes.

    .venv/bin/python tools/build_code_graph.py          # writes graph/public/code.json; exit 1 on any ERROR

Reads patchbay/ only (web/*.js, web/index.html, tools/*.py, docs/user-guide.md, README.md). Produces vertices and typed
edges that tools/build_graph.py merges into the main knowledge graph, where each dataset vertex is tied to the
knowledge-graph vertices it defines (inventory.yaml -> item:*, and so on).

Vertices: app, code_file, function, ui_action, api_route, doc_section, dataset, system
Edges   : CONTAINS (app->code_file, app->doc_section), DEFINES (code_file->function), CALLS (function->function),
          HANDLED_BY (ui_action->function), REQUESTS (function->api_route), SERVED_BY (api_route->function),
          READS / WRITES (code_file->dataset), DOCUMENTS (doc_section->ui_action|function|code_file),
          PART_OF (dataset->system), USES (app->system)

How docs link to code: every user-guide section ends with an HTML comment `<!-- covers: save saveas fn:addNode -->`
naming the buttons (data-act ids) and functions it documents. README sections link to the code files they name.

Checks (ERROR = exit 1): a UI action no user-guide section covers; a `covers` entry naming an action or function that
does not exist; a covered action whose on-screen label never appears in the covering section (doc drift); a README
path that does not exist; a route the client requests that no server function serves; a declared WRITE the module
never performs.
"""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "patchbay"
OUT = ROOT / "graph" / "public" / "code.json"
JS_FILES = ["web/app.js", "web/faceplate.js"]
GUIDE, README = "docs/user-guide.md", "README.md"

# Data the app touches. key -> (vertex id, system, how the path appears in code)
DATASETS = {
    "inventory": ("data:inventory.yaml", "gear-kb", r"inventory\.yaml"),
    "connections": ("data:connections.yaml", "gear-kb", r"connections\.yaml"),
    "midi": ("data:midi_channels.yaml", "gear-kb", r"midi_channels\.yaml"),
    "images_manifest": ("data:tools/image_manifest.yaml", "gear-kb", r"image_manifest\.yaml"),
    "manuals_manifest": ("data:tools/manifest.yaml", "gear-kb", r"(?<!image_)manifest\.yaml"),
    "graph_vertices": ("data:graph/public/vertices.json", "gear-kb", r"vertices\.json"),
    "graph_budget": ("data:graph/public/budget.json", "gear-kb", r"budget\.json"),
    "manual_sections": ("data:docs/manuals", "gear-kb", r"[\"']manuals[\"']|docs/manuals"),
    "eurorack_pdfs": ("data:sources/eurorack", "gear-kb", r"sources/eurorack|[\"']sources[\"']\s*/\s*[\"']eurorack"),
    "drawings": ("data:images", "gear-kb", r"images/<id>\.svg|[\"']images[\"']"),
    "gear_json": ("data:patchbay/data/gear.json", "patchbay", r"gear\.json"),
    "ports_seed": ("data:patchbay/data/ports.seed.yaml", "patchbay", r"ports\.seed\.yaml"),
    "ports_edits": ("data:patchbay/ports.yaml", "patchbay", r"[\"']ports\.yaml[\"']|ports\.yaml"),
    "panels_edits": ("data:patchbay/panels.yaml", "patchbay", r"panels\.yaml"),
    "sessions": ("data:patchbay/sessions", "patchbay", r"[\"']sessions[\"']"),
    "templates": ("data:patchbay/templates.yaml", "patchbay", r"templates\.yaml"),
    "device_fields": ("data:patchbay/device_fields.yaml", "patchbay", r"device_fields\.yaml"),
    "icons": ("data:patchbay/icons", "patchbay", r"ICONS|[\"']icons[\"']"),
}
# What each module WRITES (declared, then verified against the code: the dataset must appear AND a write call must).
WRITES = {
    "tools/build_data.py": ["gear_json"],
    "tools/extract_ports.py": ["ports_seed"],
    "tools/trace_icons.py": ["icons"],
    "tools/patchbay.py": ["sessions", "ports_edits", "panels_edits"],
}
WRITE_CALLS = re.compile(r"write_text|atomic_write|\.dump\(|safe_dump|shutil\.(copy|move)|\.replace\(|rename\(")
SYSTEMS = {"gear-kb": "Gear knowledge base (this repository)", "patchbay": "Patchbay app state"}

errors, warnings = [], []
V, E = {}, []


def vertex(vid, vtype, name, **props):
    if vid not in V:
        V[vid] = {"id": vid, "type": vtype, "name": name, **{k: v for k, v in props.items() if v not in (None, "", [])}}
    return vid


def edge(src, dst, rel, **props):
    E.append({"src": src, "dst": dst, "rel": rel, **props})


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ---------------- JavaScript: top-level functions, calls, actions, labels, requests ----------------
def js_functions(rel):
    text = (APP / rel).read_text(encoding="utf-8")
    starts = [(m.start(), m.group(2)) for m in re.finditer(r"^(async )?function ([A-Za-z_]\w*)", text, re.M)]
    starts += [(m.start(), m.group(1)) for m in re.finditer(r"^const ([A-Za-z_]\w*) = (?:async )?(?:\([^)]*\)|\w+) =>", text, re.M)]
    starts.sort()
    funcs = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        funcs[name] = {"body": text[pos:end], "line": text.count("\n", 0, pos) + 1}
    return text, funcs


def js_route(raw):
    raw = re.sub(r"\$\{[^}]+\}", ":id", raw)
    return raw.rstrip("/")


def labels_from_html(text):
    out = {}
    for m in re.finditer(r'<button[^>]*data-act="([a-z-]+)"([^>]*)>([^<]*)', text):
        act, attrs, inner = m.groups()
        cand = out.setdefault(act, set())
        t = re.search(r'title="([^"]*)"', attrs)
        for s in (inner, t.group(1) if t else ""):
            s = re.sub(r"\$\{[^}]*\}?", " ", s)                     # template placeholders
            s = re.sub(r"\([^)]*\)", " ", s).strip()                # "(Ctrl+Z)"
            if re.search(r"[A-Za-z]{3}", s):
                cand.add(s)
            elif s:
                cand.add(s)                                          # a symbol label such as ◐ or ✕
    return out


# ---------------- Python: functions and calls via ast ----------------
def py_module(rel):
    src = (APP / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for f in node.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs[f"{node.name}.{f.name}"] = f
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
    return src, funcs


def main():
    app = vertex("app:patchbay", "app", "Patchbay", path="patchbay/")
    for sid, name in SYSTEMS.items():
        vertex(f"system:{sid}", "system", name)
    edge(app, "system:gear-kb", "USES")
    edge(app, "system:patchbay", "USES")
    for key, (vid, system, _) in DATASETS.items():
        vertex(vid, "dataset", vid.split(":", 1)[1], system=system)
        edge(vid, f"system:{system}", "PART_OF")

    fn_ids = {}                                                   # bare name -> vertex id (JS and Python kept apart)
    # ---- JavaScript ----
    js_text_all, js_funcs_all = "", {}
    for rel in JS_FILES:
        text, funcs = js_functions(rel)
        js_text_all += text
        fid = vertex(f"file:patchbay/{rel}", "code_file", f"patchbay/{rel}", language="javascript")
        edge(app, fid, "CONTAINS")
        for name, f in funcs.items():
            vid = vertex(f"fn:patchbay/{rel}:{name}", "function", name, language="javascript", line=f["line"])
            edge(fid, vid, "DEFINES")
            fn_ids[("js", name)] = vid
            js_funcs_all[name] = (rel, f)
        for key, (vid, _, pat) in DATASETS.items():
            if key == "gear_json" and re.search(pat, text):
                edge(fid, vid, "READS")                           # static mode loads gear.json beside the page
    for name, (rel, f) in js_funcs_all.items():
        body = f["body"].split("\n", 1)[1] if "\n" in f["body"] else ""
        for callee in sorted(set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\s*\(", body)) & set(js_funcs_all) - {name}):
            edge(fn_ids[("js", name)], fn_ids[("js", callee)], "CALLS")
        for m in re.finditer(r"api\('(GET|PUT|DELETE|POST)',\s*[`']([^`']+)[`']", f["body"]):
            rid = vertex(f"route:{m.group(1)} {js_route(m.group(2))}", "api_route", f"{m.group(1)} {js_route(m.group(2))}")
            edge(fn_ids[("js", name)], rid, "REQUESTS")

    # ---- UI actions: the onAction switch, with on-screen labels from index.html and app.js templates ----
    body = js_funcs_all["onAction"][1]["body"]
    cases = list(re.finditer(r"case '([a-z-]+)':", body))
    labels = labels_from_html((APP / "web/index.html").read_text(encoding="utf-8"))
    for act, cand in labels_from_html(js_text_all).items():
        labels.setdefault(act, set()).update(cand)
    actions = {}
    for i, m in enumerate(cases):
        seg = body[m.end(): cases[i + 1].start() if i + 1 < len(cases) else len(body)]
        act = m.group(1)
        lab = sorted(labels.get(act, []))
        aid = vertex(f"action:{act}", "ui_action", act, label=" | ".join(lab))
        actions[act] = lab
        handlers = sorted(set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\s*\(", seg)) & set(js_funcs_all))
        for h in handlers or ["onAction"]:
            edge(aid, fn_ids[("js", h)], "HANDLED_BY")
    if "load-template" not in actions and "load-template" in js_text_all:
        warnings.append("load-template is not a case in onAction")

    # ---- Python ----
    py_all = {}
    for p in sorted((APP / "tools").glob("*.py")):
        rel = f"tools/{p.name}"
        src, funcs = py_module(rel)
        fid = vertex(f"file:patchbay/{rel}", "code_file", f"patchbay/{rel}", language="python")
        edge(app, fid, "CONTAINS")
        for name, node in funcs.items():
            vid = vertex(f"fn:patchbay/{rel}:{name}", "function", name, language="python", line=node.lineno)
            edge(fid, vid, "DEFINES")
            fn_ids[("py", rel, name)] = vid
        py_all[rel] = (src, funcs)
        for key, (vid, _, pat) in DATASETS.items():
            if key == "gear_json" and rel == "tools/build_data.py":
                continue                                          # build_data only WRITES gear.json
            if re.search(pat, src) and key not in WRITES.get(rel, []):
                edge(fid, vid, "READS")
        for key in WRITES.get(rel, []):
            vid, _, pat = DATASETS[key]
            if not (re.search(pat, src) and WRITE_CALLS.search(src)):
                errors.append(f"{rel}: declared to write {vid} but the code shows no such write")
            edge(fid, vid, "WRITES")
    imported = {}                                                 # `from common import kb_path` -> tools/common.py
    for rel, (src, funcs) in py_all.items():
        for m in re.finditer(r"^from (\w+) import ([\w, ]+)", src, re.M):
            if f"tools/{m.group(1)}.py" in py_all:
                for n in m.group(2).split(","):
                    imported[(rel, n.strip())] = f"tools/{m.group(1)}.py"
    for rel, (src, funcs) in py_all.items():
        for name, node in funcs.items():
            called = set()
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    f = c.func
                    called.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None)
            for cn in sorted(filter(None, called)):
                tgt = None
                if cn in funcs and cn != name:
                    tgt = fn_ids[("py", rel, cn)]
                elif (rel, cn) in imported and cn in py_all[imported[(rel, cn)]][1]:
                    tgt = fn_ids[("py", imported[(rel, cn)], cn)]
                else:
                    cls = name.split(".")[0] if "." in name else None
                    if cls and f"{cls}.{cn}" in funcs:
                        tgt = fn_ids[("py", rel, f"{cls}.{cn}")]
                if tgt:
                    edge(fn_ids[("py", rel, name)], tgt, "CALLS")

    # ---- server routes: which function serves each request ----
    src, funcs = py_all["tools/patchbay.py"]
    served = set()
    for name, node in funcs.items():
        m = re.match(r".*do_(GET|PUT|DELETE|POST)$", name)
        if not m:
            continue
        seg = ast.get_source_segment(src, node)
        for r in re.findall(r'path == "(/api/[\w/]+)"', seg):
            rid = vertex(f"route:{m.group(1)} {r}", "api_route", f"{m.group(1)} {r}")
            edge(rid, fn_ids[("py", "tools/patchbay.py", name)], "SERVED_BY", mode="local server")
            served.add(rid)
        for r in re.findall(r'parts\[:2\] == \["api", "(\w+)"\] and len\(parts\) == 3', seg):
            rid = vertex(f"route:{m.group(1)} /api/{r}/:id", "api_route", f"{m.group(1)} /api/{r}/:id")
            edge(rid, fn_ids[("py", "tools/patchbay.py", name)], "SERVED_BY", mode="local server")
            served.add(rid)
    sbody = js_funcs_all["staticApi"][1]["body"]                  # the website's stand-in for the server
    for rid, v in list(V.items()):
        if v["type"] != "api_route":
            continue
        meth, path = v["name"].split(" ", 1)
        literal = path.replace("/:id", "")
        pat_ok = (f"'{path}'" in sbody) if ":id" not in path else (re.escape(literal).replace("/", "\\\\/") in sbody
                                                                   or literal.replace("/", "\\/") in sbody)
        if pat_ok and (":id" not in path or f"'{meth}'" in sbody):
            edge(rid, fn_ids[("js", "staticApi")], "SERVED_BY", mode="website (static)")
    requested = {e["dst"] for e in E if e["rel"] == "REQUESTS"}
    for rid in sorted(requested - served):
        errors.append(f"{V[rid]['name']} is requested by the client but no server function serves it")

    # ---- documentation: user guide (covers notes) and README (code paths) ----
    all_fn_names = {k[-1]: v for k, v in fn_ids.items() if k[0] == "js"}
    covered = {}
    for docrel, kind in ((GUIDE, "user"), (README, "developer")):
        text = (APP / docrel).read_text(encoding="utf-8")
        parts = re.split(r"^## (.+)$", text, flags=re.M)
        for title, sec in zip(parts[1::2], parts[2::2]):
            did = vertex(f"doc:patchbay/{docrel}#{slug(title)}", "doc_section", title, doc=f"patchbay/{docrel}", audience=kind)
            edge(app, did, "CONTAINS")
            for c in re.findall(r"<!--\s*covers:(.*?)-->", sec, re.S):
                for tok in c.split():
                    if tok.startswith("fn:"):
                        n = tok[3:]
                        if n not in all_fn_names:
                            errors.append(f"{docrel} '{title}': covers fn:{n}, which is not a function in web/")
                            continue
                        edge(did, all_fn_names[n], "DOCUMENTS")
                    else:
                        if tok not in actions:
                            errors.append(f"{docrel} '{title}': covers '{tok}', which is not a UI action")
                            continue
                        edge(did, f"action:{tok}", "DOCUMENTS")
                        covered.setdefault(tok, []).append(title)
                        body_n = norm(re.sub(r"<!--.*?-->", "", sec, flags=re.S))
                        cands = actions[tok]
                        if cands and not any((norm(x) and norm(x) in body_n) or (x in sec) for x in cands):
                            errors.append(f"doc drift: '{title}' covers '{tok}' but never shows its label {cands}")
            if kind == "developer":
                for path in sorted(set(re.findall(r"`((?:tools|web|tests|data|docs)/[\w./-]+)`", sec))):
                    fid = f"file:patchbay/{path}"
                    if (APP / path).exists():
                        if fid in V:
                            edge(did, fid, "DOCUMENTS")
                    else:
                        errors.append(f"README '{title}' names `{path}`, which does not exist")
    for act in sorted(set(actions) - set(covered)):
        errors.append(f"UI action '{act}' is not covered by any user-guide section")

    # ---- output ----
    inputs = sorted([*(APP / r for r in JS_FILES), APP / "web/index.html", *(APP / "tools").glob("*.py"),
                     APP / GUIDE, APP / README])
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in inputs)).hexdigest()
    counts = {}
    for v in V.values():
        counts[v["type"]] = counts.get(v["type"], 0) + 1
    rels = {}
    for e in E:
        rels[e["rel"]] = rels.get(e["rel"], 0) + 1
    OUT.write_text(json.dumps({
        "generated_by": "tools/build_code_graph.py", "inputs_sha256": digest,
        "inputs": [str(p.relative_to(ROOT)) for p in inputs],
        "counts": {"vertices": counts, "edges": rels},
        "coverage": {a: covered.get(a, []) for a in sorted(actions)},
        "vertices": sorted(V.values(), key=lambda v: v["id"]),
        "edges": sorted(E, key=lambda e: (e["rel"], e["src"], e["dst"])),
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for w in warnings:
        print("WARNING", w)
    for e in errors:
        print("ERROR  ", e)
    print(f"code graph: {len(V)} vertices {dict(sorted(counts.items()))}, {len(E)} edges {dict(sorted(rels.items()))}")
    print(f"{len(actions)} UI actions, {len(covered)} covered by the user guide; {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


def inputs_digest():
    """Same digest main() writes, for build_graph.py's staleness check."""
    inputs = sorted([*(APP / r for r in JS_FILES), APP / "web/index.html", *(APP / "tools").glob("*.py"),
                     APP / GUIDE, APP / README])
    return hashlib.sha256(b"".join(p.read_bytes() for p in inputs)).hexdigest()


if __name__ == "__main__":
    main()
