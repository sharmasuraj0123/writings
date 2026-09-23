#!/usr/bin/env python3
"""Report content a reader would see clipped: anything whose scrollWidth exceeds
its own box, plus a page that scrolls horizontally. Complements
measure-svg-text.py, which only sees inside <svg>.

The usual culprit is an inline <code> longer than the 704px text column: `code`
is `white-space: nowrap`, so a long command, path or URL cannot break and pushes
its paragraph out. Put commands in <pre>, or split the span so a break exists —
two adjacent <code> spans with no whitespace between them still form one
unbreakable run.

Usage: python3 tools/measure-overflow.py <slug-dir> [...]
Checks 1400 / 1100 / 820px (rail, below-rail, narrow). Set CHROME to override.
"""
import json, os, pathlib, re, subprocess, sys, tempfile, html as H

CHROME = os.environ.get("CHROME",
    "/home/coder/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell")

PROBE = """
<script>
window.addEventListener('load', function () {
  var out = [];
  document.querySelectorAll('main *').forEach(function (el) {
    if (el.closest('svg')) return;
    var cs = getComputedStyle(el);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') return;   // <pre> may scroll
    var over = el.scrollWidth - el.clientWidth;
    if (el.clientWidth > 0 && over > 1) {
      var fig = el.closest('figure');
      out.push({ where: fig ? fig.id : '(prose)', el: el.tagName.toLowerCase(),
                 px: over, text: (el.textContent || '').trim().slice(0, 50) });
    }
  });
  if (document.documentElement.scrollWidth > window.innerWidth + 1)
    out.push({ where: '(page)', el: 'html',
               px: document.documentElement.scrollWidth - window.innerWidth,
               text: 'page scrolls horizontally' });
  // the widest unbreakable inline runs, to name the cause
  document.querySelectorAll('main code, main a').forEach(function (c) {
    if (c.closest('pre')) return;
    var w = c.getBoundingClientRect().width;
    if (w > 660) out.push({ where: '(inline)', el: c.tagName.toLowerCase(), px: Math.round(w),
                            text: (c.textContent || '').trim().slice(0, 60) });
  });
  var p = document.createElement('pre');
  p.id = 'overflow-report';
  p.textContent = JSON.stringify(out);
  document.body.appendChild(p);
});
</script>
"""

def run(slugdir, width):
    src = pathlib.Path(slugdir, "index.html").read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(src.replace("</body>", PROBE + "</body>")); tmp = f.name
    dom = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu",
                          f"--window-size={width},2000", "--virtual-time-budget=8000",
                          "--dump-dom", "file://" + tmp],
                         capture_output=True, text=True, timeout=180).stdout
    os.unlink(tmp)
    m = re.search(r'<pre id="overflow-report">(.*?)</pre>', dom, re.S)
    if not m:
        print(f"{slugdir}@{width}: probe did not report", file=sys.stderr); return []
    return [dict(slug=slugdir, w=width, **h) for h in json.loads(H.unescape(m.group(1)))]

if __name__ == "__main__":
    hits = []
    for d in sys.argv[1:]:
        for w in (1400, 1100, 820):
            hits += run(d, w)
    defects = [h for h in hits if h["where"] != "(inline)"]
    advisory = {(h["slug"], h["text"]): h for h in hits if h["where"] == "(inline)"}
    for h in sorted(defects, key=lambda h: -h["px"]):
        print(f'CLIPPED  {h["slug"]:30s} @{h["w"]:<5} {h["where"]:20s} {h["el"]:8s} {h["px"]:>5}px  {h["text"][:52]}')
    for h in sorted(advisory.values(), key=lambda h: -h["px"]):
        print(f'wide     {h["slug"]:30s}        {h["el"]:8s} {h["px"]:>5}px  {h["text"][:52]}')
    print(f'\n{len(defects)} clipped (fix these) · {len(advisory)} wide-but-fitting inline runs (watch)')
    sys.exit(1 if defects else 0)
