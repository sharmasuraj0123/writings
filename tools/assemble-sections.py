#!/usr/bin/env python3
"""Stitch per-section files into a post and build it.

Usage: python3 tools/assemble-sections.py <slug-dir>      (e.g. chromium/blink)

Reads   <slug-dir>/_plan.json        — the outline (schema below)
        <slug-dir>/_sections/*.html  — one file per <h2> section, named NN-<id>.html
Writes  <slug-dir>/meta.json         — derived from the plan
        <slug-dir>/_article.html     — the stitched body, figures renumbered
        <slug-dir>/index.html        — via tools/assemble-post.py, then validated

_plan.json: { "title", "status_pill", "kicker", "dek", "byline", "description",
  "og_description", "twitter_description", "canonical_slug", "badges_callout" (HTML for the
  leading .callout, optional), "footer_links": [{href,label}] (optional),
  "sections": [ { "id", "title", "short", "brief", "target_words", "figures": [...] } ] }

Section files use placeholders the stitcher resolves in document order:
  <span class="figure-label">Figure {{N}}</span>   → Figure 1, Figure 2, …
  Figure {{fig-some-id}}  (in prose)               → the number of <figure id="fig-some-id">
  <span class="secnum">{{S}}</span>                → 01, 02, … (any value is overwritten)
"""
import json, pathlib, re, sys, importlib.util

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("assemble_post", HERE / "assemble-post.py")
ap = importlib.util.module_from_spec(spec); spec.loader.exec_module(ap)

DEFAULT_CALLOUT = """          <div class="callout">
            <span class="k">How to read the badges</span>
            <p>
              <span class="src">from the tree</span> marks facts read from a checkout of
              <code>chromium/src</code>, <code>depot_tools</code>, or <code>v8</code> — quoted with
              file paths and line numbers. <span class="src">from the docs</span> marks facts from
              Chromium's own documentation and announcements. <span class="recon">reconstruction</span>
              marks mechanism I have worked out from the sources but which no single file states
              outright. The closing provenance note says what was not verified.
            </p>
          </div>
"""

def main(slugdir: pathlib.Path):
    plan = json.loads((slugdir / "_plan.json").read_text(encoding="utf-8"))
    order = [s["id"] for s in plan["sections"]]
    files = {}
    for f in sorted((slugdir / "_sections").glob("*.html")):
        sid = re.sub(r"^\d+-", "", f.stem)
        files[sid] = f
    missing = [s for s in order if s not in files]
    if missing:
        print(json.dumps({"problems": [f"missing section files: {missing}"]})); sys.exit(1)
    extra = sorted(set(files) - set(order))
    if extra: print("note: section files not in plan, ignored:", extra)

    body = []
    for n, sid in enumerate(order, 1):
        s = files[sid].read_text(encoding="utf-8").strip("\n")
        # enforce the h2 contract for this section
        h2s = re.findall(r'<h2 id="([^"]+)">', s)
        if h2s != [sid]:
            print(json.dumps({"problems": [f"section {files[sid].name}: expected exactly one <h2 id=\"{sid}\">, found {h2s}"]})); sys.exit(1)
        s = re.sub(r'<span class="secnum">[^<]*</span>', f'<span class="secnum">{n:02d}</span>', s, count=1)
        body.append(s)
    article = "\n\n".join(body)

    # figure numbering in document order
    fig_ids = re.findall(r'<figure class="figure[^"]*" id="([^"]+)">', article)
    dup = {x for x in fig_ids if fig_ids.count(x) > 1}
    if dup:
        print(json.dumps({"problems": [f"duplicate figure ids: {sorted(dup)}"]})); sys.exit(1)
    counter = iter(range(1, len(fig_ids) + 1))
    article = re.sub(r'Figure \{\{N\}\}', lambda m: f"Figure {next(counter)}", article)
    for k, fid in enumerate(fig_ids, 1):
        article = article.replace("{{" + fid + "}}", str(k))
    unresolved = sorted(set(re.findall(r"\{\{[^}]+\}\}", article)))

    callout = plan.get("badges_callout") or DEFAULT_CALLOUT
    full = "      <article>\n        <section class=\"prose\">\n" + callout + "\n" + article + "\n        </section>\n      </article>\n"
    (slugdir / "_article.html").write_text(full, encoding="utf-8")

    meta = {k: plan[k] for k in ("title", "status_pill", "kicker", "dek", "byline", "description", "og_description", "twitter_description", "canonical_slug")}
    meta["sections"] = [{"id": s["id"], "title": s["title"], "short": s["short"]} for s in plan["sections"]]
    depth = len(pathlib.Path(plan["canonical_slug"]).parts); up = "../" * depth
    meta["footer_links"] = plan.get("footer_links") or [
        {"href": up, "label": "Writings"}, {"href": "../", "label": "Chromium collection"},
        {"href": f"{up}whitepaper/", "label": "quirq whitepaper"}, {"href": "mailto:suraj@xo.builders", "label": "suraj@xo.builders"}]
    (slugdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = ap.build(slugdir)
    if unresolved: report["problems"].append(f"unresolved placeholders: {unresolved}")
    report["figure_ids"] = fig_ids
    print(json.dumps({"figures_numbered": len(fig_ids), "unresolved": unresolved}))
    return report

if __name__ == "__main__":
    r = main((HERE.parent / sys.argv[1]).resolve())
    sys.exit(1 if r["problems"] else 0)
