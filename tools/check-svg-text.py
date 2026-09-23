#!/usr/bin/env python3
"""Flag SVG <text> in a post's figures that overflows its viewBox or collides with
a neighbour. Width is estimated from the class's font (mono ~0.60em, sans ~0.52em,
serif-italic ~0.46em); anchors are honoured. Estimates are deliberately generous,
so review each hit rather than trusting the count.

Usage: python3 tools/check-svg-text.py <slug-dir> [...]
"""
import html, re, sys, pathlib

EM = {"svg-lane": (11, 0.60, 0.06), "svg-step": (12, 0.52, 0), "svg-sub": (10.5, 0.60, 0),
      "svg-num": (10, 0.60, 0), "svg-note": (11, 0.46, 0), None: (12, 0.52, 0)}

def width(txt, cls):
    size, ratio, ls = EM.get(cls, EM[None])
    return len(txt) * (size * ratio + size * ls)

def run(slugdir):
    s = pathlib.Path(slugdir, "index.html").read_text(encoding="utf-8")
    hits = []
    for fig in re.finditer(r'<figure class="figure[^"]*" id="([^"]+)">(.*?)</figure>', s, re.S):
        fid, body = fig.group(1), fig.group(2)
        for svg in re.finditer(r'<svg[^>]*viewBox="([^"]+)"(.*?)</svg>', body, re.S):
            vb = [float(x) for x in svg.group(1).split()]
            x0, y0, w, h = vb
            items = []
            for t in re.finditer(r'<text\b([^>]*)>(.*?)</text>', svg.group(2), re.S):
                attrs, inner = t.group(1), t.group(2)
                if "<tspan" in inner:      # multi-line runs carry their own x/y
                    continue
                txt = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
                if not txt:
                    continue
                gx = re.search(r'\bx="([-\d.]+)"', attrs); gy = re.search(r'\by="([-\d.]+)"', attrs)
                if not gx or not gy:
                    continue
                x, y = float(gx.group(1)), float(gy.group(1))
                cls = (re.search(r'class="([^"]+)"', attrs) or [None, None])[1]
                cls = cls.split()[0] if cls else None
                anchor = (re.search(r'text-anchor="(\w+)"', attrs) or [None, "start"])[1]
                wd = width(txt, cls)
                left = x - wd/2 if anchor == "middle" else (x - wd if anchor == "end" else x)
                items.append({"t": txt, "x": x, "y": y, "l": left, "r": left + wd, "c": cls})
            for it in items:
                if it["r"] > x0 + w + 2:
                    hits.append((slugdir, fid, "overflow-right", round(it["r"] - (x0+w)), it["t"][:70]))
                if it["l"] < x0 - 2:
                    hits.append((slugdir, fid, "overflow-left", round(x0 - it["l"]), it["t"][:70]))
            items.sort(key=lambda i: (i["y"], i["l"]))
            for a, b in zip(items, items[1:]):
                if abs(a["y"] - b["y"]) < 4 and b["l"] < a["r"] - 2:
                    hits.append((slugdir, fid, "collision", round(a["r"] - b["l"]),
                                 f'{a["t"][:40]} || {b["t"][:40]}'))
    return hits

if __name__ == "__main__":
    all_hits = []
    for d in sys.argv[1:]:
        all_hits += run(d)
    for h in all_hits:
        print(f"{h[0]:32s} {h[1]:28s} {h[2]:15s} {h[3]:>5}px  {h[4]}")
    print(f"\n{len(all_hits)} potential issues")
    sys.exit(1 if all_hits else 0)
