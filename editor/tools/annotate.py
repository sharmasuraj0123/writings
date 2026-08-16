#!/usr/bin/env python3
"""Annotate what-is-quirq/index.html per composable-post/1.
Deterministic transform with a strip-equivalence proof before writing."""
import html.parser, json, re, sys

PATH = "what-is-quirq-test/index.html"
src = open(PATH, encoding="utf-8").read()
orig = src
lines = src.split("\n")  # 0-based; report 1-based
NL = len(lines)

def find_line(pred, start=0, end=None, what=""):
    for i in range(start, end if end is not None else NL):
        if pred(lines[i]):
            return i
    sys.exit(f"landmark not found: {what}")

def only_line(sub):
    hits = [i for i, l in enumerate(lines) if sub in l]
    assert len(hits) == 1, (sub, hits[:5])
    return hits[0]

# ---------- element boundaries via parser ----------
class Map(html.parser.HTMLParser):
    VOID = {'meta','link','br','hr','img','input','polyline','line','rect',
            'circle','path','source','use','ellipse'}
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []; self.elems = []
    def handle_starttag(self, t, attrs):
        if t in self.VOID: return
        self.stack.append({"tag": t, "attrs": dict(attrs), "start": self.getpos()[0]})
    def handle_endtag(self, t):
        if t in self.VOID: return
        while self.stack:
            n = self.stack.pop()
            if n["tag"] == t:
                n["end"] = self.getpos()[0]
                self.elems.append(n); break
m = Map(); m.feed(src)

def elem(pred, what):
    hits = [e for e in m.elems if pred(e)]
    assert len(hits) == 1, (what, [(e["start"], e.get("attrs")) for e in hits[:4]])
    return hits[0]
def by_id(i):
    return elem(lambda e: e["attrs"].get("id") == i, f"#{i}")
def by_class(tag, cls):
    return elem(lambda e: e["tag"] == tag and cls in (e["attrs"].get("class") or "").split(), f"{tag}.{cls}")

head_el   = elem(lambda e: e["tag"] == "head", "head")
style_el  = elem(lambda e: e["tag"] == "style", "style")
scripts   = sorted([e for e in m.elems if e["tag"] == "script"], key=lambda e: e["start"])
assert len(scripts) == 2, [s["start"] for s in scripts]
progress_line = only_line('class="progress"')
threadbar = by_class("header", "threadbar")
floating  = by_class("div", "floating-toc")
rail      = by_class("aside", "contents-rail")
masthead  = by_class("section", "masthead")
footer    = elem(lambda e: e["tag"] == "footer", "footer")

chapters_def = [
    ("chapter:introduction", by_class("section", "intro-chapter"),   "introduction",   "narrative",  "complete"),
    ("chapter:measure",      by_class("section", "measure-chapter"), "measure",        "calculus",   "complete"),
    ("chapter:impact",       by_class("section", "impact-chapter"),  "business-impact","impact",     "complete"),
    ("chapter:research",     by_id("research"),                      "research",       "placeholder","placeholder"),
    ("chapter:other-applications", by_id("other-applications"), "other-applications", "placeholder","placeholder"),
    ("chapter:data-experiments",   by_id("data-experiments"),   "data-experiments",   "placeholder","placeholder"),
    ("chapter:roadmap",      by_id("roadmap"),                       "roadmap",        "placeholder","placeholder"),
    ("chapter:references",   by_class("section", "refs-chapter"),    "references",     "meta",       "complete"),
]
parts_def = {
    "chapter:introduction": ["workspace","continuity","space","boundary","unit","graph","status"],
    "chapter:measure": ["measure-score","measure-mint","measure-cost","measure-unit","measure-portfolio",
                        "measure-estimation","measure-validity","measure-time","measure-identification",
                        "measure-bridge","measure-limitations"],
    "chapter:impact": ["impact-observability","impact-roi","impact-capacity","impact-process","impact-governance"],
    "chapter:references": ["open-discussion"],
}
part_elems = {p: by_id(p) for ps in parts_def.values() for p in ps}
part_cat = {"chapter:introduction": "narrative", "chapter:measure": "calculus",
            "chapter:impact": "impact", "chapter:references": "meta"}

# ---------- nav labels ----------
def nav_labels(e):
    text = "\n".join(lines[e["start"]-1:e["end"]])
    out = {}
    for mm in re.finditer(r'<a\b[^>]*?href="#([^"]+)"[^>]*?>(.*?)</a\s*>', text, re.S):
        label = re.sub(r"<[^>]+>", "", mm.group(2))
        out[mm.group(1)] = re.sub(r"\s+", " ", label).strip()
    return out
toc_nav  = elem(lambda e: e["tag"] == "nav" and "toc-menu" in (e["attrs"].get("class") or ""), "toc-menu")
full_lab  = nav_labels(toc_nav)
short_lab = nav_labels(rail)
for a in ["introduction","workspace","measure","open-discussion","references"]:
    assert a in full_lab and a in short_lab, a

# ---------- css regions ----------
style_s, style_e = style_el["start"], style_el["end"]  # 1-based lines of <style>/</style>
banners = [
    ("Research-paper treatment for the calculus chapter", "css:calculus-treatment"),
    ("Section 2 — research-paper primitives",             "css:research-primitives"),
    ("Section 3 — Business Impact",                       "css:impact"),
    ("References — inline citations and the bibliography","css:references"),
    ("Introduction — How to measure work",                "css:intro-environment"),
    ("Operating loop + evaluation map",                   "css:operating-loop"),
    ("THREE CANVAS SIZES",                                "css:canvas-sizes"),
    ("COLLAPSIBLE CONTENTS RAIL",                         "css:collapsible-rail"),
    ("STICKY TOP BAR",                                    "css:sticky-topbar"),
]
marks = []
for text, name in banners:
    i = only_line(text)  # 0-based line of banner text
    # banner may be the comment line itself or the line after a `/* ===` opener
    start = i if "/*" in lines[i] else i - 1
    assert "/*" in lines[start], (name, lines[start])
    marks.append((start, name))  # 0-based first line of region
marks.sort()
assert [n for _, n in marks] == [n for _, n in banners], "banner order"
# tokens region: :root { ... }
root_i = find_line(lambda l: l.strip() == ":root {", style_s, style_e, ":root")
depth = 0; tok_end = None
for i in range(root_i, style_e):
    depth += lines[i].count("{") - lines[i].count("}")
    if depth == 0 and i > root_i: tok_end = i; break
assert tok_end and tok_end < marks[0][0]
regions = [("css:tokens", root_i, tok_end), ("css:base", tok_end + 1, marks[0][0] - 1)]
for k, (s0, name) in enumerate(marks):
    e0 = (marks[k+1][0] - 1) if k + 1 < len(marks) else (style_e - 2)  # up to line before </style>
    regions.append((name, s0, e0))
SHARED_CSS = {"css:tokens","css:base","css:canvas-sizes","css:collapsible-rail","css:sticky-topbar"}

# ---------- deps ----------
def sel_tokens(s0, e0):
    css = "\n".join(lines[s0:e0+1])
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    sels = re.findall(r"(?:^|})([^{}]*){", css, re.S)
    toks = set()
    for s in sels:
        toks |= set(re.findall(r"\.([A-Za-z][\w-]*)", s))
        toks |= set(re.findall(r"#([A-Za-z][\w-]*)", s))
    return toks
region_tokens = {n: sel_tokens(s0, e0) for n, s0, e0 in regions if n not in SHARED_CSS}

def markup_tokens(e):
    t = "\n".join(lines[e["start"]-1:e["end"]])
    toks = set()
    for mm in re.finditer(r'class="([^"]+)"', t): toks |= set(mm.group(1).split())
    toks |= set(re.findall(r'id="([^"]+)"', t))
    return toks

JS_FEATURES = [("data-tabs", "tabs"), ("data-measure-weight", "measure-weights"),
               ("data-cost-input", "cost-model"), ("settlement-mode", "settlement")]
def js_deps(e):
    t = "\n".join(lines[e["start"]-1:e["end"]])
    s2 = "\n".join(lines[scripts[1]["start"]-1:scripts[1]["end"]])
    s1 = "\n".join(lines[scripts[0]["start"]-1:scripts[0]["end"]])
    out = []
    for hook, feat in JS_FEATURES:
        if hook in t:
            home = "script:widgets" if hook in s2 else ("script:reading-chrome" if hook in s1 else None)
            if home: out.append(f"{home}#{feat}")
    return out

def css_deps(e):
    mt = markup_tokens(e)
    return sorted(n for n, toks in region_tokens.items() if mt & toks)

# ---------- manifest ----------
CATS = [
    {"id": "meta", "label": "Page furniture", "note": "masthead, references, footer"},
    {"id": "narrative", "label": "Section 1 — the environment"},
    {"id": "calculus", "label": "Section 2 — the measurement calculus"},
    {"id": "impact", "label": "Section 3 — business impact"},
    {"id": "placeholder", "label": "Future chapters (skeletons)"},
]
blocks = []
def add(bid, kind, e=None, title=None, railL=None, anchor=None, category="meta",
        status="n/a", movable=False, optional=False, parent=None, children=None, deps=None):
    blocks.append({"id": bid, "kind": kind, "title": title, "railLabel": railL,
                   "anchor": anchor, "category": category, "status": status,
                   "movable": movable, "optional": optional, "parent": parent,
                   "children": children or [], "deps": deps or {"css": [], "js": []}})

add("doc:head", "doc", title="Document head")
for n, s0, e0 in regions:
    add(n, "css", title=n.split(":")[1].replace("-", " "))
for cid, t in [("chrome:progress","Progress bar"),("chrome:threadbar","Threadbar"),
               ("chrome:floating-toc","Floating TOC"),("chrome:contents-rail","Contents rail")]:
    add(cid, "chrome", title=t)
add("doc:masthead", "doc", title="Masthead", category="meta")
for bid, e, anchor, cat, status in chapters_def:
    kids = [f"part:{p}" for p in parts_def.get(bid, [])]
    add(bid, "chapter", title=full_lab.get(anchor, anchor), railL=short_lab.get(anchor),
        anchor=anchor, category=cat, status=status, movable=True,
        optional=(bid != "chapter:references"), children=kids,
        deps={"css": css_deps(e), "js": js_deps(e)})
    for p in parts_def.get(bid, []):
        pe = part_elems[p]
        add(f"part:{p}", "part", title=full_lab.get(p, p), railL=short_lab.get(p),
            anchor=p, category=part_cat[bid], status="complete", movable=True,
            optional=True, parent=bid, deps={"css": css_deps(pe), "js": js_deps(pe)})
add("doc:footer", "doc", title="Footer", optional=True)
add("script:reading-chrome", "script", title="Reading chrome script")
add("script:widgets", "script", title="Widget script")
add("data:manifest", "data", title="Block manifest")

manifest = {
    "format": "composable-post/1",
    "page": {"slug": "what-is-quirq", "title": "What Is a Unit of Work?"},
    "categories": CATS,
    "blocks": blocks,
    "shared": sorted(SHARED_CSS) + ["chrome:progress","chrome:threadbar","chrome:floating-toc",
                                     "chrome:contents-rail","script:reading-chrome","doc:head"],
    "nav": {"order": [c[0] for c in chapters_def]},
}

# ---------- build edits ----------
FENCE = "══════"
def fence(bid, end=False, indent=""):
    return f"{indent}<!-- {FENCE} {'END' if end else 'BLOCK'} {bid} {FENCE} -->"
ops = []  # (line0, prio, kind, payload); applied descending
def ind(i): return re.match(r"\s*", lines[i]).group(0)
def wrap(bid, s1, e1):  # 1-based inclusive lines
    ops.append((s1 - 1, 1, "before", fence(bid, False, ind(s1 - 1))))
    ops.append((e1 - 1, 1, "after",  fence(bid, True,  ind(s1 - 1))))

wrap("doc:head", head_el["start"] + 1, head_el["end"] - 1)  # inner content
for n, s0, e0 in regions: wrap(n, s0 + 1, e0 + 1)
ops.append((progress_line, 1, "before", fence("chrome:progress", False, ind(progress_line))))
ops.append((progress_line, 1, "after",  fence("chrome:progress", True,  ind(progress_line))))
wrap("chrome:threadbar", threadbar["start"], threadbar["end"])
wrap("chrome:floating-toc", floating["start"], floating["end"])
wrap("chrome:contents-rail", rail["start"], rail["end"])
wrap("doc:masthead", masthead["start"], masthead["end"])
for bid, e, *_ in chapters_def: wrap(bid, e["start"], e["end"])
for p, pe in part_elems.items(): wrap(f"part:{p}", pe["start"], pe["end"])
wrap("doc:footer", footer["start"], footer["end"])
wrap("script:reading-chrome", scripts[0]["start"], scripts[0]["end"])
wrap("script:widgets", scripts[1]["start"], scripts[1]["end"])

# data attributes on chapter/part opening tags
def add_attrs(e, attrs):
    i = e["start"] - 1
    while ">" not in lines[i]:
        i += 1
        assert i < e["end"], ("no tag close", e["start"])
    l = lines[i]
    pos = l.index(">")
    assert l[pos + 1:].strip() == "", (i + 1, l)
    ops.append((i, 0, "replace", l[:pos] + attrs + l[pos:]))
for bid, e, anchor, cat, status in chapters_def:
    b = next(x for x in blocks if x["id"] == bid)
    add_attrs(e, f' data-block="{bid}" data-block-title="{b["title"]}"'
                 f' data-block-category="{cat}" data-block-status="{status}"'
                 + (" data-block-optional" if b["optional"] else ""))
for p, pe in part_elems.items():
    b = next(x for x in blocks if x["id"] == f"part:{p}")
    add_attrs(pe, f' data-block="part:{p}" data-block-title="{b["title"]}"'
                  f' data-block-category="{b["category"]}" data-block-status="complete"'
                  " data-block-optional")

# data-for on nav links (toc-menu, floating toc list, contents-rail)
for e in (toc_nav, rail):
    for i in range(e["start"] - 1, e["end"]):
        mm = re.search(r'href="#([^"]+)"', lines[i])
        if mm and "data-for=" not in lines[i]:
            ops.append((i, 0, "replace",
                        lines[i].replace(mm.group(0), f'{mm.group(0)} data-for="{mm.group(1)}"', 1)))

# format meta in head (after icon link)
icon_i = only_line('rel="icon"')
ops.append((icon_i, 2, "after", ind(icon_i) + '<meta name="post-format" content="composable-post/1" />'))

# manifest before first script
mi = scripts[0]["start"] - 1
mjson = json.dumps(manifest, indent=2, ensure_ascii=False)
mblock = "\n".join([fence("data:manifest", False, ind(mi)),
                    ind(mi) + '<script type="application/json" id="block-manifest">',
                    mjson,
                    ind(mi) + "</script>",
                    fence("data:manifest", True, ind(mi))])
ops.append((mi, 2, "before", mblock))

# anatomy header after doctype
anat = ["<!-- " + FENCE + " ANATOMY · composable-post/1 " + FENCE,
        "  This page is block-annotated. Spec: shared/composable-post.md · editor: /editor/ · wiki: /editor/wiki/",
        "  Every region is fenced by paired comments:  <!═ BLOCK ns:id ═> … <!═ END ns:id ═>  (grep: 'BLOCK \\|END ')",
        "  Namespaces: doc (head/masthead/footer) · css (style regions) · chrome (reading chrome) ·",
        "  chapter (top-level sections, movable) · part (subsections, movable/optional) · script · data (manifest).",
        "  The machine-readable index is <script id=\"block-manifest\"> near the end of the file.",
        "  Stripping every fence comment, data-block*/data-for attribute, the manifest and the",
        "  post-format meta reproduces the un-annotated page byte-for-byte.",
        "-->"]
assert lines[0].strip() == "<!doctype html>"
ops.append((0, 2, "after", "\n".join(anat)))

# ---------- apply ----------
new = lines[:]
for i, prio, kind, payload in sorted(ops, key=lambda o: (-o[0], o[1])):
    if kind == "replace": new[i] = payload
    elif kind == "before": new.insert(i, payload)
    elif kind == "after": new.insert(i + 1, payload)
out = "\n".join(new)

# ---------- strip-equivalence proof ----------
def strip(s):
    ls = s.split("\n"); r = []; skip = 0; in_anat = False; in_manifest = False
    for l in ls:
        t = l.strip()
        if in_anat:
            if t == "-->": in_anat = False
            continue
        if t.startswith(f"<!-- {FENCE} ANATOMY"): in_anat = True; continue
        if re.fullmatch(rf"<!-- {FENCE} (BLOCK|END) data:manifest {FENCE} -->", t):
            in_manifest = not in_manifest; continue
        if in_manifest: continue
        if re.fullmatch(rf"<!-- {FENCE} (BLOCK|END) [a-z]+:[a-z0-9-]+ {FENCE} -->", t): continue
        if t == '<meta name="post-format" content="composable-post/1" />': continue
        l = re.sub(r' data-block(?:-title|-category|-status)?="[^"]*"', "", l)
        l = re.sub(r" data-block-optional\b", "", l)
        l = re.sub(r' data-for="[^"]*"', "", l)
        r.append(l)
    return "\n".join(r)

stripped = strip(out)
if stripped != orig:
    a, b = stripped.split("\n"), orig.split("\n")
    for k in range(min(len(a), len(b))):
        if a[k] != b[k]:
            sys.exit(f"STRIP MISMATCH at line {k+1}:\n  got: {a[k][:160]}\n  want: {b[k][:160]}")
    sys.exit(f"STRIP MISMATCH: length {len(a)} vs {len(b)}")

open(PATH, "w", encoding="utf-8").write(out)
print(f"OK: annotated ({len(orig.splitlines())} -> {len(new)} lines), strip-equivalence proven")
print(f"blocks: {len(blocks)}  css regions: {len(regions)}  fences: {sum(1 for o in ops if 'BLOCK' in str(o[3]) or 'END' in str(o[3]))}")
