#!/usr/bin/env python3
"""Scan the writings tree and regenerate research/manifest.json.

Every document folder with an index.html becomes one manifest entry:
  - research/<slug>/index.html            -> section "research"
  - whitepaper/index.html, what-is-quirq/ -> section "foundations"

The loader at research/index.html fetches the manifest at runtime, so a new
log starts loading as soon as this script has run once:

    python3 tools/build-manifest.py
"""

import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "research" / "manifest.json"
FOUNDATIONS = ["whitepaper", "what-is-quirq"]
WORDS_PER_MINUTE = 220


def text_of(html_source: str) -> str:
    stripped = re.sub(r"<(script|style)\b.*?</\1>", " ", html_source, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return html.unescape(stripped)


def meta_of(path: Path) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    title = re.search(r"<title>(.*?)</title>", source, flags=re.S)
    title = html.unescape(title.group(1)).strip() if title else path.parent.name
    title = re.sub(r"\s*[—·|]\s*XO Research\s*$", "", re.sub(r"\s+", " ", title))

    desc = re.search(
        r'<meta\s[^>]*name="description"[^>]*content="([^"]*)"', source, flags=re.S
    ) or re.search(r'<meta\s[^>]*content="([^"]*)"[^>]*name="description"', source, flags=re.S)
    description = html.unescape(re.sub(r"\s+", " ", desc.group(1))).strip() if desc else ""

    words = len(text_of(source).split())
    return {
        "title": title,
        "description": description,
        "minutes": max(1, round(words / WORDS_PER_MINUTE)),
        "date": date_of(path),
    }


def date_of(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%as", "--", str(path.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    entries = []
    for name in FOUNDATIONS:
        index = ROOT / name / "index.html"
        if index.is_file():
            entries.append({"slug": name, "path": f"{name}/", "section": "foundations",
                            **meta_of(index)})

    for index in sorted((ROOT / "research").glob("*/index.html")):
        entries.append({"slug": index.parent.name, "path": f"research/{index.parent.name}/",
                        "section": "research", **meta_of(index)})

    entries.sort(key=lambda e: (e["section"] != "foundations", e["date"]), reverse=False)
    entries.reverse()  # newest research first, foundations keep their block

    MANIFEST.write_text(json.dumps({"entries": entries}, indent=2) + "\n", encoding="utf-8")
    for e in entries:
        print(f"{e['section']:11s} {e['date']}  {e['slug']:24s} {e['minutes']:>3d} min")
    print(f"\nwrote {MANIFEST.relative_to(ROOT)} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
