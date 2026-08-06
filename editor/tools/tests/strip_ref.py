#!/usr/bin/env python3
"""strip_ref.py — independent reference implementation of composable-post/1
strip-equivalence (shared/composable-post.md §5.6), written from the spec for
cross-checking window.CPF.strip. Deliberately NOT imported from
tools/annotate.py and NOT transliterated from the editor's JS.

Per §5.6 (and the format preamble "annotations are inert"), stripping removes:
  * the leading ANATOMY banner comment (an annotation comment);
  * every fence comment line (BLOCK/END, on its own line);
  * the fenced data:manifest region in full (the manifest script element);
  * the line holding <meta name="post-format" content="composable-post/1" />;
  * every data-block* attribute and every data-for attribute, together with
    the single space that precedes each.

Usage: strip_ref.py <input.html> <output>
Writes exact bytes (UTF-8), no trailing newline added.
"""

import re
import sys

FENCE = "═" * 6  # ══════

MANIFEST_FENCE = re.compile(
    r"^<!-- " + FENCE + r" (?:BLOCK|END) data:manifest " + FENCE + r" -->$"
)
ANY_FENCE = re.compile(
    r"^<!-- " + FENCE + r" (?:BLOCK|END) [a-z]+:[a-z0-9-]+ " + FENCE + r" -->$"
)
ANATOMY_OPEN = "<!-- " + FENCE + " ANATOMY"
FORMAT_META = '<meta name="post-format" content="composable-post/1" />'

# one space + the annotation attribute; bare data-block-optional has no value
ANNOTATION_ATTR = re.compile(
    r" data-(?:"
    r'block(?:-title|-category|-status)?="[^"]*"'
    r"|block-optional\b"
    r'|for="[^"]*"'
    r")"
)


def strip(text: str) -> str:
    kept = []
    state = "text"  # text | anatomy | manifest
    for line in text.split("\n"):
        bare = line.strip()
        if state == "anatomy":
            if bare == "-->":
                state = "text"
            continue
        if bare.startswith(ANATOMY_OPEN):
            state = "anatomy"
            continue
        if MANIFEST_FENCE.match(bare):
            state = "text" if state == "manifest" else "manifest"
            continue
        if state == "manifest":
            continue
        if ANY_FENCE.match(bare):
            continue
        if bare == FORMAT_META:
            continue
        kept.append(ANNOTATION_ATTR.sub("", line))
    return "\n".join(kept)


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: strip_ref.py <input.html> <output>\n")
        return 2
    with open(sys.argv[1], encoding="utf-8", newline="") as f:
        text = f.read()
    out = strip(text)
    with open(sys.argv[2], "w", encoding="utf-8", newline="") as f:
        f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
