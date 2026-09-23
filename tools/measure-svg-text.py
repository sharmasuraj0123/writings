#!/usr/bin/env python3
"""Measure a post's figures with a real browser: text overlaps and shapes that escape the viewBox.

Injects a probe that uses getBBox() on every <text> inside every figure <svg>,
then reports (a) text whose box escapes the viewBox and (b) pairs of text boxes
that actually intersect. Unlike an estimate, this is what a reader sees.

Usage: python3 tools/measure-svg-text.py <slug-dir> [...]
Needs chrome-headless-shell; set CHROME to override the path.
"""
import json, os, pathlib, re, subprocess, sys, tempfile

CHROME = os.environ.get("CHROME",
    "/home/coder/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell")

PROBE = """
<script>
window.addEventListener('load', function () {
  // Screen space via getBoundingClientRect(): transform-aware, and it is what a
  // reader actually sees. getBBox() reports the element's own user space and so
  // mis-compares any text inside a <g transform>.
  var out = [];
  document.querySelectorAll('figure svg').forEach(function (svg) {
    var fid = svg.closest('figure').id;
    var box = svg.getBoundingClientRect();
    var items = [];
    svg.querySelectorAll('text').forEach(function (t) {
      var r = t.getBoundingClientRect();
      if (!r.width) return;
      items.push({ t: (t.textContent || '').trim().slice(0, 60), r: r });
    });
    // Shapes can escape the viewBox too — a rect or arrow drawn past the right
    // edge is clipped silently. Check them for containment only, not overlap.
    svg.querySelectorAll('rect, line, path, polyline, circle, ellipse').forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (!r.width && !r.height) return;
      var tag = el.tagName + (el.getAttribute('class') ? '.' + el.getAttribute('class') : '');
      if (r.right - box.right > 1) out.push({ fig: fid, kind: 'shape-past-right', px: Math.round(r.right - box.right), a: tag });
      if (box.left - r.left > 1) out.push({ fig: fid, kind: 'shape-past-left', px: Math.round(box.left - r.left), a: tag });
      if (r.bottom - box.bottom > 1) out.push({ fig: fid, kind: 'shape-past-bottom', px: Math.round(r.bottom - box.bottom), a: tag });
    });
    items.forEach(function (i) {
      var over = i.r.right - box.right;
      if (over > 1) out.push({ fig: fid, kind: 'overflow-right', px: Math.round(over), a: i.t });
      if (box.left - i.r.left > 1) out.push({ fig: fid, kind: 'overflow-left', px: Math.round(box.left - i.r.left), a: i.t });
      if (i.r.bottom - box.bottom > 1) out.push({ fig: fid, kind: 'overflow-bottom', px: Math.round(i.r.bottom - box.bottom), a: i.t });
    });
    for (var i = 0; i < items.length; i++) {
      for (var j = i + 1; j < items.length; j++) {
        var A = items[i].r, B = items[j].r;
        var ox = Math.min(A.right, B.right) - Math.max(A.left, B.left);
        var oy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
        if (ox > 1 && oy > 1) out.push({ fig: fid, kind: 'overlap', px: Math.round(ox), a: items[i].t, b: items[j].t });
      }
    }
  });
  var pre = document.createElement('pre');
  pre.id = 'svg-text-report';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
});
</script>
"""

def run(slugdir):
    src = pathlib.Path(slugdir, "index.html").read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(src.replace("</body>", PROBE + "</body>")); tmp = f.name
    dom = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu",
                          "--virtual-time-budget=8000", "--dump-dom", "file://" + tmp],
                         capture_output=True, text=True, timeout=180).stdout
    os.unlink(tmp)
    m = re.search(r'<pre id="svg-text-report">(.*?)</pre>', dom, re.S)
    if not m:
        print(f"{slugdir}: probe did not report", file=sys.stderr); return []
    import html as H
    return [dict(slug=slugdir, **h) for h in json.loads(H.unescape(m.group(1)))]

if __name__ == "__main__":
    hits = []
    for d in sys.argv[1:]:
        hits += run(d)
    for h in sorted(hits, key=lambda h: -h["px"]):
        print(f'{h["slug"]:32s} {h["fig"]:26s} {h["kind"]:16s} {h["px"]:>4}px  {h["a"][:46]}'
              + (f'  ||  {h["b"][:46]}' if h.get("b") else ""))
    print(f'\n{len(hits)} real issues')
    sys.exit(1 if hits else 0)
