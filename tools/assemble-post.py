#!/usr/bin/env python3
"""Assemble a post from its article body + meta, using the canonical paper chrome.

Usage:  python3 tools/assemble-post.py <slug-dir>   (e.g. chromium/blink)
Inputs in <slug-dir>/:  meta.json, _article.html
Output:                 <slug-dir>/index.html   (then run with --validate to check)

meta.json keys: title, status_pill, kicker, dek, byline (text after "Suraj Sharma · XO Labs · "),
  description, og_description, twitter_description, canonical_slug (e.g. "chromium/blink"),
  sections: [{id, title, short}]  (short ≤ 23 chars; one per <h2 id> in order),
  footer_links: [{href, label}]  (relative to the post dir).
The chrome (tokens, CSS, threadbar, floating TOC, rail, masthead, footer, paper.js) is copied
byte-for-byte from TEMPLATE, so every post stays self-contained and identical in chrome (AGENTS.md §5).
"""
import html.parser, json, re, sys, os, pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = HERE / "liveblocks-for-xo-space" / "index.html"

def chrome():
    src = TEMPLATE.read_text(encoding="utf-8")
    style = src[src.index("    <style>"):src.index("    </style>") + len("    </style>")]
    script = src[src.rindex("    <script>"):src.rindex("    </script>") + len("    </script>")]
    logo = re.search(r'<header class="threadbar">.*?</header>', src, re.S).group(0)
    return style, script, logo

def build(slugdir: pathlib.Path):
    meta = json.loads((slugdir / "meta.json").read_text(encoding="utf-8"))
    article = (slugdir / "_article.html").read_text(encoding="utf-8")
    depth = len(pathlib.Path(meta["canonical_slug"]).parts)
    up = "../" * depth
    style, script, header = chrome()
    header = header.replace('href="../"', f'href="{up}"')
    secs = meta["sections"]
    for s in secs:
        assert len(s["short"]) + 5 <= 28, f"rail label too long: {s['short']}"
    menu = "\n".join(f'        <a class="toc-parent" href="#{s["id"]}">{n:02d} · {s["title"]}</a>' for n, s in enumerate(secs, 1))
    rail = "\n".join(f'        <a href="#{s["id"]}">{n:02d} · {s["short"]}</a>' for n, s in enumerate(secs, 1))
    toc = "\n".join(f'          <li><a href="#{s["id"]}">{s["title"]}</a></li>' for s in secs)
    footer = "\n".join(
        f'          <a href="{l["href"]}">{l["label"]}</a>' + ('\n          <span aria-hidden="true"> · </span>' if i < len(meta["footer_links"]) - 1 else '')
        for i, l in enumerate(meta["footer_links"]))
    e = lambda k: meta[k].replace('"', "&quot;")
    out = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta
      name="description"
      content="{e('description')}"
    />
    <meta name="author" content="Suraj Sharma" />
    <meta name="theme-color" content="#ffffff" />
    <link rel="icon" href="{up}assets/favicon.svg" />
    <link rel="canonical" href="https://quirq.ai/{meta['canonical_slug']}/" />
    <meta property="og:title" content="{e('title')}" />
    <meta property="og:description" content="{e('og_description')}" />
    <meta property="og:type" content="article" />
    <meta property="og:url" content="https://quirq.ai/{meta['canonical_slug']}/" />
    <meta property="og:image" content="https://quirq.ai/assets/og.jpg" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{e('title')}" />
    <meta name="twitter:description" content="{e('twitter_description')}" />
    <title>{meta['title']} — XO Research</title>
{style}
  </head>
  <body>
    <div class="progress" aria-hidden="true"></div>
    {header}

    <div class="floating-toc" aria-label="Floating contents">
      <button
        class="toc-button"
        type="button"
        aria-expanded="false"
        aria-controls="toc-menu"
      >
        <span aria-hidden="true">☰</span>
        <span class="toc-button-label">01 · {secs[0]['title']}</span>
      </button>
      <nav class="toc-menu" id="toc-menu" aria-label="Article sections">
{menu}
      </nav>
    </div>

    <aside class="contents-rail" aria-label="Contents">
      <p class="contents-rail-title">Contents</p>
      <nav aria-label="Article contents">
{rail}
      </nav>
    </aside>

    <section class="masthead">
      <div class="masthead-inner">
        <p class="kicker">{meta['kicker']}</p>
        <h1>{meta['title']}<span class="status-pill">{meta['status_pill']}</span></h1>
        <p class="dek">
          {meta['dek']}
        </p>
        <p class="masthead-byline">Suraj Sharma · XO Labs · {meta['byline']}</p>
      </div>
    </section>

    <main>
      <nav class="toc" aria-label="Article sections">
        <p class="toc-title">Contents</p>
        <ol>
{toc}
        </ol>
      </nav>

{article}
    </main>

    <footer class="site-footer">
      <div class="footer-inner">
        <p>
{footer}
        </p>
      </div>
    </footer>
{script}
  </body>
</html>
"""
    (slugdir / "index.html").write_text(out, encoding="utf-8")
    return validate(slugdir)

def validate(slugdir: pathlib.Path):
    s = (slugdir / "index.html").read_text(encoding="utf-8")
    class P(html.parser.HTMLParser):
        VOID = {'meta','link','br','hr','img','input','polyline','line','rect','circle','path','source','use','ellipse'}
        def __init__(self): super().__init__(convert_charrefs=True); self.stack=[]; self.errs=[]
        def handle_starttag(self,t,a):
            if t not in self.VOID: self.stack.append(t)
        def handle_endtag(self,t):
            if t in self.VOID: return
            if self.stack and self.stack[-1]==t: self.stack.pop()
            else: self.errs.append(f"</{t}> at line {self.getpos()[0]}")
    p = P(); p.feed(s)
    problems = []
    if p.stack or p.errs: problems.append(f"unbalanced tags: open={p.stack[:5]} errs={p.errs[:5]}")
    h2 = re.findall(r'<h2 id="([^"]+)">', s)
    for nav in ('contents-rail','toc-menu'):
        m = re.search(rf'class="{nav}".*?</(aside|nav)>', s, re.S)
        if not m: problems.append(f"missing {nav}")
        elif re.findall(r'href="#([^"]+)"', m.group(0)) != h2: problems.append(f"{nav} != h2 ids")
    m = re.search(r'<nav class="toc".*?</nav>', s, re.S)
    if not m or re.findall(r'href="#([^"]+)"', m.group(0)) != h2: problems.append("in-flow toc != h2 ids")
    if s.count('class="progress"') != 1 or 'IntersectionObserver' not in s: problems.append("chrome missing")
    ids = set(re.findall(r'\bid="([^"]+)"', s))
    dangling = sorted(h for h in set(re.findall(r'href="#([^"]+)"', s)) if h not in ids and h != '<id>')
    if dangling: problems.append(f"dangling anchors: {dangling}")
    for m in re.finditer(r'(?:href|src)="((?:\.\./)[^"#]+)"', s):
        t = (slugdir / m.group(1)).resolve()
        if not (t.exists() or (t / "index.html").exists()): problems.append(f"missing relative target {m.group(1)}")
    secnums = re.findall(r'<span class="secnum">(\d+)</span>', s)
    if secnums != [f"{i:02d}" for i in range(1, len(h2)+1)]: problems.append(f"secnum sequence off: {secnums}")
    main = re.search(r'<main>.*?</main>', s, re.S).group(0)
    t = re.sub(r'<svg.*?</svg>', ' ', main, flags=re.S); t = re.sub(r'<[^>]+>', ' ', t)
    words = len(t.split())
    figs = len(re.findall(r'<figure class="figure', s))
    report = {"words": words, "minutes": round(words/225), "figures": figs, "sections": len(h2), "problems": problems}
    print(json.dumps(report, indent=1))
    return report

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slugdir = (HERE / args[0]).resolve()
    if "--validate" in sys.argv: r = validate(slugdir)
    else: r = build(slugdir)
    sys.exit(1 if r["problems"] else 0)
