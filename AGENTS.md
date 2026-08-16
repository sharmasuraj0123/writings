# AGENTS.md — operating contract for `writings/`

You are working in a publication, not an app. A folder is a post; each post is
one **self-contained static HTML document** in the visual and structural
format of `what-is-quirq/index.html` (the flagship); a thin viewer at
`/index.html` indexes them all via `posts.json`. Architecture, history, and
rationale live in [README.md](README.md) — read it once. This file is the
contract you follow every time you create or edit a page.

## 1. Hard rules

1. **A post is one file.** `<slug>/index.html` with an inline `<style>` block
   and inline `<script>` blocks. It must render correctly opened directly via
   `file://` — no webfonts, no external JS, no chart libraries, no build step.
   `shared/paper.css` / `shared/paper.js` exist as references; posts **inline**
   their copies (the flagship does the same) so each file stays archivable.
2. **A post never depends on the viewer; the viewer never rewrites a post.**
3. **Two design languages exist — never mix them.** Research posts use the
   light paper system defined here. `/quirq/` (product landing) and
   `/whitepaper/` (dark editorial deck) are the product voice: do **not**
   copy their styles into posts, and do not restyle them into the paper
   system without an explicit ask.
4. **`what-is-quirq/` is the reference.** When this file and that page
   disagree, the page wins; update this file.
5. **Never commit or push unless explicitly asked.**

## 2. Required page skeleton, in order

```
<head>   description · author · theme-color #ffffff · icon ../assets/favicon.svg
         canonical https://quirq.ai/<slug>/ · og:* + twitter:* incl. og:image
         <title>… — XO Research</title> · inline <style> (tokens + chrome + page CSS)
<body>
  <div class="progress" aria-hidden="true"></div>
  <header class="threadbar">        XO logo + "Writings" + author status
  <div class="floating-toc">        collapsing TOC — narrow screens        (§5)
  <aside class="contents-rail">     fixed sidebar — wide screens           (§5)
  <section class="masthead">        kicker · h1 + status-pill · .dek · byline
  <main>
    <nav class="toc">               in-flow contents box (kept — all 3 surfaces ship)
    <article>                       sections: <h2 id="…"><span class="secnum">NN</span>Title
                                    figures per §6 · ends with .footnote provenance
  <footer class="site-footer">      links to ../, sibling posts, contact
  <script>                          inline copy of shared/paper.js           (§5)
```

## 3. Design tokens and type

Copy the `:root` token block verbatim from an existing post (or
`shared/paper.css`) — do not invent values. The rules that matter:

- **No webfonts.** System stacks only (`--sans`, `--serif`, `--mono`).
- **`--orange` is the only chrome accent** (progress, secnum, figure labels,
  claim rules, focus ring). Green/blue/purple/red exist **only inside
  figures**, encoding meaning — never decoration, links, or emphasis.
- Widths: prose `--text` 704px · figures `--middle` 1000px · wide figures
  `--page` 1120px. Body 17px/1.62.
- The XO mark in the threadbar keeps its `#83d63a`/`#000` strokes (logo, not
  chrome).

## 4. Voice and epistemics

Short declaratives. Numbers carry their derivation. Quote sources verbatim
and cite exactly (file paths and constants for teardowns; equations and
section names for paper readings). Every claim carries its epistemic status:
figure status pills, or inline badges when the page mixes sourced material
with your own reconstruction (see `j-space/` — `from the paper` vs
`reconstruction`). The closing `.footnote` states what is sourced, what is
yours, and what you did not verify. No marketing language.

## 5. The reading chrome (the sidebar contract)

Every post ships **all four**: the `.progress` bar, the in-flow `.toc` box,
the `.contents-rail` (≥1180px), and the `.floating-toc` (<1180px), driven by
one inline scroll-spy script. This is the part most recently standardized —
do not ship a post without it.

- **CSS**: the canonical chrome block (selectors `.progress`, `.floating-toc`,
  `.toc-button`, `.toc-menu`, `.contents-rail`, breakpoints at 1180px, the
  1180–1319px `.figure.wide` clamp, reduced-motion and print blocks) is
  identical across posts — copy it from any retrofitted post, byte for byte.
  It shifts `main` right of the rail on wide screens:
  `margin-left: calc(184px + max(0px, (100vw - 184px - var(--middle)) / 2))`.
- **Markup**: `.floating-toc` + `.contents-rail` sit between `</header>` and
  the masthead. One entry per `<h2>` section, same ids, same order.
  - `toc-menu` entries: full section title, prefixed `NN · `, each with class
    `toc-parent`; the `toc-button-label` seeds with entry 1.
  - rail entries: short label ≤ 28 chars including the `NN · ` prefix,
    distinct and unambiguous; no class attribute (use
    `contents-parent`/`contents-subsections` only if you add h3 nesting).
- **Script**: an inline copy of `shared/paper.js` immediately before
  `</body>`. It is defensive — every feature no-ops if its hook is absent.
  If you change behavior, change `shared/paper.js` first, then re-inline.
- **Anchors are a contract**: every rail/TOC `href="#id"` must match an
  existing `<h2 id>`; scroll-spy silently ignores mismatches, so validate
  (§8), don't eyeball.

## 6. Figures

Hand-authored HTML/CSS/SVG only — no screenshots, no chart libraries, no
generated imagery. The pattern:

```html
<figure class="figure [wide]" id="fig-…">
  <div class="figure-head">
    <span class="figure-label">Figure N</span>
    <p class="figure-title">What it shows — one line</p>
  </div>
  <div class="figure-body [plain]"> …diagram or table… </div>
  <p class="figure-caption">The takeaway, not a label.</p>
</figure>
```

SVG text uses the shared classes (`svg-lane`, `svg-step`, `svg-sub`,
`svg-num`, `svg-note`). Edge conventions in diagrams: thin blue = data,
thick black = control/sequence, dashed purple = state/effect — keep them
consistent across posts. Interactive elements: native controls only, with
ARIA per the flagship.

## 7. Publishing checklist for a new post

1. `mkdir <slug>/ <slug>/assets/` — kebab-case, no dates.
2. Write `<slug>/index.html` per §2–§6. Start from the most recent post, not
   from scratch.
3. `assets/thumb.svg` — 320×160, pulled from a *real figure in the post*
   reduced to silhouette: `#f7f7f5` ground, 4px `--orange` title strip, mono
   uppercase eyebrow (`CATEGORY / KIND`), palette colors as in the source
   figure.
4. Append the entry to `posts.json` — `slug` (= dir name), `title`,
   `subtitle` (the dek), `authors`, `published` (ISO), `status`, `kind`
   (`essay`/`note`/`spec`/`whitepaper`), `topics` (lowercase kebab),
   `readingMinutes` (**measured**: strip tags/SVG/styles, words ÷ 225 — do
   not guess), `thumbnail`, `attachments`.
5. Add the `feed.xml` item (link/guid `https://quirq.ai/<slug>/`, RFC-822
   pubDate, description = one-line dek).
6. Validate (§8). 7. Do not commit unless asked.

## 8. Validation — run before calling any page done

```bash
python3 - <<'PY'
import html.parser, json, re, sys
import xml.dom.minidom as xml
slug = "<slug>"
s = open(f"{slug}/index.html", encoding="utf-8").read()
class P(html.parser.HTMLParser):
    VOID={'meta','link','br','hr','img','input','polyline','line','rect',
          'circle','path','source','use','ellipse'}
    def __init__(self): super().__init__(convert_charrefs=True); self.stack=[]; self.errs=[]
    def handle_starttag(self,t,a):
        if t not in self.VOID: self.stack.append(t)
    def handle_endtag(self,t):
        if t in self.VOID: return
        if self.stack and self.stack[-1]==t: self.stack.pop()
        else: self.errs.append(f"</{t}> at line {self.getpos()[0]}")
p=P(); p.feed(s)
assert not p.stack and not p.errs, (p.stack[:5], p.errs[:5])
h2 = re.findall(r'<h2 id="([^"]+)">', s)
for nav in ('contents-rail','toc-menu'):
    m = re.search(rf'class="{nav}".*?</(aside|nav)>', s, re.S)
    assert m, f"missing {nav}"
    assert re.findall(r'href="#([^"]+)"', m.group(0)) == h2, f"{nav} != h2 ids"
assert s.count('class="progress"')==1 and 'IntersectionObserver' in s
json.load(open("posts.json")); xml.parse("feed.xml"); xml.parse(f"{slug}/assets/thumb.svg")
print("OK")
PY
```

Also confirm: every `posts.json` thumbnail path exists; the post opens with
correct layout at <1180px and ≥1180px widths (rail clears `main`, wide
figures clamp in the 1180–1319px band).

## 9. Reference pages

| Page | Use it for |
|---|---|
| `what-is-quirq/` | the flagship: full format, subgrid layout, publication-meta, claim ledger |
| `personal-memory-engine/` | the standard post layout most pages use (centered `main`, `.prose` + `.figure`) |
| `j-space/` | sourced-vs-reconstruction badging, equation blocks |
| `sea-of-nodes/` + `sea-of-nodes-paper/` | short explainer ↔ close reading pairing, cross-linking |
