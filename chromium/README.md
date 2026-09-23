# chromium/

A collection: `index.html` is the section landing page, each sub-folder is one post.

| folder | what |
|---|---|
| `blink/` | Blink, taken apart — the rendering engine at `chromium/src@f288fed6` |
| `deps-and-goma/` | DEPS, gclient and what replaced goma |
| `ci-cd-and-releases/` | The tree that configures the fleet — LUCI, the CQ, the release train |
| `sea-of-nodes/`, `sea-of-nodes-paper/` | V8's TurboFan graph IR (moved here 2026-09-18) |

## Editing a post

The three 2026-09 posts are **built from parts** — do not edit `index.html` or
`_article.html` by hand, they are generated:

```
<slug>/_plan.json          outline + masthead metadata (sections, rail labels, dek)
<slug>/_sections/NN-id.html    one file per <h2> section  ← edit these
<slug>/_sections/*.checked.json  the fact-checker's report for that section
<slug>/assets/thumb.svg    320×160 silhouette of one real figure
```

```bash
python3 tools/assemble-sections.py chromium/<slug>   # stitch → index.html + validate
python3 tools/measure-svg-text.py  chromium/<slug>   # SVG text/shape geometry
python3 tools/measure-overflow.py  chromium/<slug>   # clipped content, 3 widths
```

`tools/post-brief.md` is the writing recipe (vocabulary, figure markup, voice).

## Provenance

Claims cite `chromium/src@f288fed6` (Chrome 156.0.8067.0, 18 September 2026),
`depot_tools@0306e468`, or a standalone `v8` checkout — note that checkout's HEAD
reads 15.6.0 while that Chromium commit pins V8 15.6.19 via `src/DEPS`.

The consolidated research dossiers (~3.3 MB, ~3,700 sourced facts, one
`DOSSIER.md` per topic plus the raw per-section JSON) live **outside this
publication**, at `~/chromium-ref/dossiers/`, beside the checkouts they were read
from (`~/chromium-ref/{src,depot_tools,v8}`). They are the source for any
follow-up edit; this repo keeps only what renders.
