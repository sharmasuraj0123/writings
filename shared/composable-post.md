# Composable Post Format — `composable-post/1`

Normative spec for block-annotated posts in this repo. The flagship
(`what-is-quirq/index.html`) is the reference implementation; the editor
(`/editor/`) consumes and emits this format; the wiki (`/editor/wiki/`)
documents it for humans. Annotations are **inert**: comments, `data-*`
attributes, and one JSON `<script>` — stripping them all must reproduce the
un-annotated page byte-for-byte. A post remains one self-contained file that
renders over `file://`.

## 1. Block markers

Every extractable region is fenced by a comment pair, greppable with one
regex:

```
<!-- ══════ BLOCK <ns>:<id> ══════ -->
…
<!-- ══════ END <ns>:<id> ══════ -->
```

Regex: `<!-- ═+ (BLOCK|END) ([a-z]+:[a-z0-9-]+) ═+ -->`. Fences sit on their
own lines, indented to match the fenced content. Namespaces:

| ns | fences | notes |
|---|---|---|
| `doc` | `doc:head`, `doc:masthead`, `doc:footer` | document furniture |
| `css` | one per style region (e.g. `css:tokens`, `css:intro-environment`) | inside the single `<style>`; regions never overlap |
| `chrome` | `chrome:progress`, `chrome:threadbar`, `chrome:floating-toc`, `chrome:contents-rail` | the reading chrome; global, not removable |
| `chapter` | one per top-level `<section>` in `<main>` (e.g. `chapter:introduction`) | the movable unit |
| `part` | one per sub-section with an anchor (e.g. `part:workspace`) | movable within its chapter |
| `script` | `script:reading-chrome`, `script:widgets` | inline JS |
| `data` | `data:manifest` | the embedded manifest |

Blocks nest (`part` inside `chapter`); fences never interleave.

## 2. Data attributes

The opening tag of each `chapter`/`part` element carries:

- `data-block="<ns>:<id>"` — matches its fence.
- `data-block-title="…"` — the full nav label, `NN · Title` form.
- `data-block-category="<category-id>"` — see §4.
- `data-block-status="complete|placeholder"`.
- `data-block-optional` — present iff the page still works with the block
  removed (nav is regenerated; no other block references it).

Nav entries (`.toc-menu` and `.contents-rail` links) carry
`data-for="<anchor>"` naming the target anchor, so tooling can rebuild nav
without parsing hrefs.

## 3. The manifest

One `<script type="application/json" id="block-manifest">` before the first
runtime script, fenced as `data:manifest`. Schema (all fields required
unless noted):

```jsonc
{
  "format": "composable-post/1",
  "page": { "slug": "…", "title": "…" },
  "categories": [ { "id": "…", "label": "…", "note": "…" } ],
  "blocks": [ {
    "id": "chapter:introduction",     // ns:id, matches fence
    "kind": "chapter",                // doc|css|chrome|chapter|part|script|data
    "title": "01 · Introduction",     // display title (nav form)
    "railLabel": "01 · Introduction", // ≤28 chars, contents-rail form
    "anchor": "introduction",         // in-page id nav points at; null if none
    "category": "narrative",
    "status": "complete",             // complete|placeholder|n/a
    "movable": true,                  // may be reordered among siblings
    "optional": false,                // may be removed entirely
    "parent": null,                   // enclosing block id or null
    "children": ["part:workspace"],  // ordered; [] if none
    "deps": {
      "css": ["css:intro-environment"],   // non-shared css regions it needs
      "js": ["script:widgets#tabs"]       // script block, #feature optional
    }
  } ],
  "shared": ["css:tokens", "css:base", "script:reading-chrome"],  // needed by every composition
  "nav": { "order": ["chapter:introduction", "…"] }               // current chapter order
}
```

Truth rules: **markers are truth for extraction** (byte ranges), **the
manifest is truth for tooling** (order, titles, deps, categories). The
editor regenerates both together; hand edits must keep them consistent.

## 4. Categories (flagship taxonomy — extend per post)

| id | label |
|---|---|
| `meta` | masthead, references, footer — page furniture with prose |
| `narrative` | Section 1 — the environment, illustrated explainer |
| `calculus` | Section 2 — the measurement calculus, research-paper voice |
| `impact` | Section 3 — business impact |
| `placeholder` | future chapters, skeleton only |

## 5. Composition rules (what tooling must enforce)

1. Removing a block removes its fence-to-fence bytes, its nav entries
   (matched by `data-for` against the block's `anchor` and its children's),
   and nothing else. Only `optional` blocks may be removed.
2. Reordering `movable` siblings reorders their fence-to-fence byte ranges
   and regenerates both nav surfaces and `nav.order` to match document
   order. Section numbers inside headings/`data-block-title` are **names,
   not positions** — never renumber on move.
3. A composition always keeps every block listed in `shared`.
4. CSS pruning is optional and conservative: a `css:*` region may be dropped
   only when no remaining block lists it in `deps.css` and it is not in
   `shared`.
5. After any operation: every nav `href="#…"`/`data-for` resolves to an
   existing anchor, fences still pair, the manifest matches the DOM
   (order, presence), and the §8 validation in `AGENTS.md` (adapted: nav
   anchors must *resolve*, not equal the h2 list) passes.
6. Strip-equivalence: removing every fence comment, every `data-block*`
   and `data-for` attribute (with the single space that precedes each), the
   manifest script element and the format meta tag reproduces a valid,
   identically-rendering page.

## 6. Identification

Annotated pages carry `<meta name="post-format" content="composable-post/1" />`
in `<head>` (inside `doc:head`). Tooling must refuse files without it rather
than guess.
