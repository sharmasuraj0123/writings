# writings

A publication surface for long-form research essays, in the tradition of
[transformer-circuits.pub](https://transformer-circuits.pub) and
[distill.pub](https://distill.pub): each piece is a **self-contained static HTML document**
with its own illustrations, its own interactive figures, and no build step — and a thin
**viewer** at the root that indexes them all.

Repo: `github.com/sharmasuraj0123/writings` (branch `main`)
Author: Suraj Sharma — XO Labs
Referenced canonical hosts today: `quirq.ai` (OG tags) and `xo.builders` (whitepaper canonical)

---

## 1. What is here today

```
writings/
├── index.html                  50 KB   quirq product landing page (dark, marketing)
├── whitepaper/
│   └── index.html              82 KB   whitepaper narrative page (dark, editorial deck)
├── what-is-quirq/
│   ├── index.html             484 KB   "What is a unit of work?" — the research essay
│   └── section-2-spec.md               formal companion: every quantity + its arithmetic
├── assets/
│   ├── favicon.svg                     XO mark
│   ├── quirq-mark.jpg                  apple-touch-icon
│   ├── mobius.jpg                      hero imagery
│   └── og.jpg                          social card (shared by all pages)
├── quirq-whitepaper.pdf       532 KB   canonical PDF, Draft v3
├── llm.txt                     39 KB   whitepaper as plain text, prepared for LLMs/agents
└── vectors.json                23 KB   12-dim toy token vectors for a visualization
```

No build tooling, no `package.json`, no bundler, no external JS libraries. Every page is
one HTML file with an inline `<style>` block and (at most) one inline `<script>`. All
figures are hand-authored HTML/CSS/SVG. This is a deliberate property and the viewer
should preserve it — see §6.

### 1.1 The three surfaces, and their two design languages

The folder currently mixes **two unrelated visual systems**. This matters for the viewer,
because only one of them is the blog voice.

| Surface | Mode | Type | Character |
|---|---|---|---|
| `/index.html` | Dark `#000` | Inter + IBM Plex Mono + Quicksand | Product landing. Spectrum gradients, WebGL hero (`#gl`), film grain, live-ticking ledger demo, scroll-reveal animations. |
| `/whitepaper/index.html` | Dark `#000` | Inter + IBM Plex Mono + Instrument Serif | Editorial deck. Section-per-idea, large pull-quotes, spectrum accents, grain. |
| `/what-is-quirq/index.html` | **Light `#fff`** | **System serif/sans, no webfonts** | **Research paper.** Reading rail, progress bar, numbered sections, 12 captioned figures, claim callouts, 48-entry bibliography. |

**`what-is-quirq/` is the aesthetic target.** It is already an almost-exact structural
match for transformer-circuits: light paper ground, restrained ink, a single warm accent,
a fixed contents rail, subgrid text/middle/wide columns, framed figures with eyebrows and
status pills. The viewer's design system is derived from it (§5), not from the dark pages.

### 1.2 The research essay in detail

`what-is-quirq/index.html` is the reference implementation of a post.

- **Masthead** — kicker (`XO Labs · Applied Agent Research`), title, dek, and a
  `<dl class="publication-meta">` with Author / Published / Reading / Status.
  Reading time is computed at runtime from `main`'s word count at 225 wpm.
- **Two navigations** — a fixed `.contents-rail` on wide screens, and a collapsing
  `.floating-toc` button below the rail breakpoint. Both are driven by one
  scroll-spy that highlights the active section and updates a top progress bar.
- **Sections 1–3 are written** (Introduction, How to measure, Business Impact, with
  sub-sections 1.1–1.8, 2.1–2.11, 3.1–3.5). **Sections 4–7 are placeholders**
  (`Research`, `Other Applications`, `Data and Experiments`, `Roadmap`) rendering a
  skeleton and the note "Chapter outline to be developed."
- **Section 8 — References** — 48 entries in 5 groups, each with a `ref-use` field
  explaining what constraint that literature imposes on the proposal, not just a citation.
- **12 figures**, all hand-built: system maps, a unit lifecycle, a runtime clock, an
  islands-vs-continuity tab pair, a storage contract, an outcome graph, and interactive
  calculators (6 `<input type="range">` controls that recompute V, B, and minted quirqs
  live).
- **`section-2-spec.md`** is the formal companion — definitions, propositions, and a
  **claim ledger** marking every statement `derived` / `illustrative` / `open`. That
  honesty convention (a claim carries its own epistemic status) is a core part of the
  voice and should be kept for future posts.

---

## 2. The idea: a viewer

Turn this folder into a personal research blog where **a folder is a post**. The root
becomes an index that lists every essay; each essay stays exactly what it is today — one
standalone HTML file you can open with `file://`, email as an attachment, or archive.

That is precisely the transformer-circuits model: `/2021/framework/`, `/2022/toy-model/`
etc. are independent documents, and the site root is a curated card index over them.

### 2.1 Decision to make first

`/index.html` is currently the **quirq marketing page**. The blog index wants that URL.
Recommended resolution:

1. Move the landing page to `/quirq/index.html` (one `git mv`, then fix its
   `assets/…` paths to `../assets/…`).
2. Write the new viewer index at `/index.html`.
3. Leave `/whitepaper/` and `/what-is-quirq/` where they are — they become the first two
   entries in the index.

Alternative: keep the marketing page in a separate repo entirely and let `writings/` be
purely editorial. Cleaner separation, one more deploy to manage.

### 2.2 Architecture

Static-first, no framework, no build step required to *read* the site.

```
/index.html            the viewer — reads posts.json, renders the index
/posts.json            the manifest — one entry per post
/shared/paper.css      the design system (§5), available to future posts
/shared/paper.js       progress bar, contents rail scroll-spy, TOC toggle, reading time
                       (the index and existing posts inline their own styles and stay
                        self-contained; shared/ is a convenience for new posts, not a dependency)
/<slug>/index.html     one post
/<slug>/assets/…       post-local images (keep post assets with the post)
/assets/…              site-level assets (favicon, og, marks)
```

Two rules keep this honest:

- **A post never depends on the viewer.** `/<slug>/index.html` must render correctly
  when opened directly. `shared/paper.css` is an *include for convenience*, not a
  requirement; a post may keep its styles inline (as `what-is-quirq` does today) and
  still be listed.
- **The viewer never rewrites a post.** No iframe, no HTML injection, no client-side
  transclusion. The index links out; the post owns its own page. This is what makes each
  essay archivable and citable, and it is why the site needs no server.

### 2.3 The manifest — `posts.json`

The viewer's only data source. Hand-edited, or regenerated by an optional
`scripts/build-manifest.mjs` that scrapes `<title>`, `<meta name="description">`, and the
`.publication-meta` block out of each `*/index.html`. Hand-editing is fine at this scale;
generation matters once there are ~15 posts.

```json
{
  "site": {
    "title": "Writings",
    "author": "Suraj Sharma",
    "affiliation": "XO Labs",
    "description": "Long-form research on agentic systems and the measurement of work.",
    "canonical": "https://xo.builders"
  },
  "posts": [
    {
      "slug": "what-is-quirq",
      "title": "What is a unit of work?",
      "subtitle": "A prompt asks for an action. A unit of work owns an outcome.",
      "authors": ["Suraj Sharma"],
      "published": "2026-07-31",
      "updated": "2026-07-31",
      "status": "working-proposal",
      "kind": "essay",
      "topics": ["measurement", "agentic-systems", "unit-of-work"],
      "readingMinutes": 80,
      "featured": true,
      "thumbnail": "what-is-quirq/assets/thumb.svg",
      "attachments": [
        { "label": "Section 2 spec", "href": "what-is-quirq/section-2-spec.md" }
      ]
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `slug` | ✅ | Must equal the directory name. The URL is `/<slug>/`. |
| `title` | ✅ | Sentence case. Matches the post's `<h1>`. |
| `subtitle` | ✅ | One or two sentences — the dek. Shown on the index card. |
| `published` | ✅ | ISO `YYYY-MM-DD`. Sort key, newest first. |
| `status` | ✅ | `working-proposal` · `draft` · `published` · `superseded`. Renders as a status pill. |
| `kind` | ✅ | `essay` · `whitepaper` · `note` · `spec`. Drives grouping on the index. |
| `topics` | — | Lowercase kebab tags. Powers filtering. |
| `readingMinutes` | — | Omit and the index shows nothing rather than guessing. |
| `featured` | — | Promotes the post to the lead slot. At most one. |
| `thumbnail` | — | An SVG figure lifted from the post, not a stock image (see §5.6). |
| `attachments` | — | PDFs, specs, data files shown as secondary links on the card. |

### 2.4 Optional: zero-manifest discovery

If maintaining `posts.json` by hand ever grates, the viewer can fall back to fetching a
`dirs.json` list and `HEAD`-ing each `<slug>/index.html`. Not recommended — it costs one
request per post, breaks under `file://`, and gives you no place to put status, topics, or
ordering. Keep the manifest.

### 2.5 The index page

Not a blog roll. A table of contents for a body of work.

- **Masthead** — site title, one-line description of what this publication is about, and
  the author line. Same type treatment as a post masthead so the two feel continuous.
- **Lead entry** — the `featured` post gets a full-width row: title, dek, meta line, and
  its pulled figure at ~2:1.
- **Index rows** — everything else in reverse-chronological order, one row per post,
  hairline-separated. Each row: date (mono, small), title, dek, then a meta line of
  status pill · reading time · topics. Hover raises nothing and moves nothing; the title
  underline thickens. Restraint is the point.
- **Filters** — a single row of topic chips plus `kind`. Filtering is a
  `hidden` toggle over already-rendered rows, and it writes to `?topic=` so a filtered
  view is linkable. No search index until there are enough posts to need one.
- **Footer** — RSS, the GitHub repo, contact, and the `llm.txt` convention (§7.3).

---

## 3. Reference: how transformer-circuits does it

Worth naming explicitly, because "match the aesthetic" means matching these decisions, not
copying a stylesheet:

1. **The document is the unit.** Each paper is one long page. No pagination, no
   "continue reading", no infinite scroll. The reader gets everything at once.
2. **One column of text, wide gutters, wide figures.** Prose stays at a fixed measure
   (~700px); figures escape to a wider column when they need to. Nothing is full-bleed
   for effect.
3. **Figures are first-class and hand-made.** They are diagrams that carry argument, each
   with a title, an eyebrow, and a caption. No screenshots, no stock illustration.
4. **Light ground, black text, one accent.** Color is used to encode meaning inside
   figures, never as decoration in the chrome.
5. **Persistent contents rail.** The reader always knows where they are in a 20,000-word
   document.
6. **Epistemic honesty in the layout.** Status markers, "still to prove" sections,
   explicit limitations. The design has affordances for uncertainty.
7. **No motion.** Nothing fades in on scroll. Interactivity exists only where a slider or
   toggle genuinely teaches something.

Points 4 and 7 are where the current dark pages diverge hardest — grain, spectrum
gradients, and scroll-reveals belong to the product voice, not the research voice.

---

## 4. Proposed roadmap

| # | Work | Notes |
|---|---|---|
| 1 | Move `/index.html` → `/quirq/index.html` | §2.1. Fix relative asset paths. |
| 2 | Extract `shared/paper.css` from `what-is-quirq` | Tokens, layout grid, figure, claim, refs, rail. |
| 3 | Extract `shared/paper.js` | Progress, scroll-spy, TOC toggle, reading time — already generic. |
| 4 | Write `posts.json` | Three entries: `what-is-quirq`, `whitepaper`, `quirq`. |
| 5 | Build `/index.html` viewer | ~200 lines of HTML + a fetch + a render loop. |
| 6 | Repoint `what-is-quirq` at the shared CSS | Delete the duplicated inline block; keep post-specific figure CSS local. |
| 7 | Decide the whitepaper's fate | Either restyle `/whitepaper/` into the light system, or list it as `kind: "whitepaper"` and accept it looks different. |
| 8 | Add `feed.xml` + `.gitignore` + `CNAME`/`vercel.json` | §7. |
| 9 | Fill sections 4–7 of the essay | Currently placeholders. |

---

## 5. Design system

Lifted from `what-is-quirq/index.html` — these are the values already in use. Formalize
them into `shared/paper.css` verbatim; do not redesign.

### 5.1 Tokens

```css
:root {
  color-scheme: light;

  --paper:      #ffffff;   /* page ground            */
  --paper-soft: #f7f7f5;   /* figure frames, wells   */
  --paper-warm: #fff8ea;   /* claim callouts only    */

  --ink:        #252525;   /* body text              */
  --ink-soft:   #4f4f4b;   /* ledes, secondary prose */
  --ink-faint:  #777772;   /* captions, meta, eyebrows */

  --line:       #deded9;   /* hairlines              */
  --line-dark:  #b8b8b1;   /* emphasized rules       */

  --orange: #d98226;  --orange-soft: #f7e3c8;   /* the accent */
  --green:  #367f59;  --green-soft:  #dfede5;
  --blue:   #3c6f97;  --blue-soft:   #e0ebf2;
  --purple: #765b98;  --purple-soft: #ece6f3;
  --red:    #ad4b43;  --red-soft:    #f3dfdc;

  --sans:  -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, …, sans-serif;
  --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
  --mono:  "SFMono-Regular", Consolas, "Liberation Mono", monospace;

  --text:   704px;   /* prose measure   */
  --middle: 1000px;  /* wider figures   */
  --page:   1120px;  /* full-bleed cap  */
  --shadow: 0 12px 38px rgba(30, 30, 25, 0.08);
}
```

**No webfonts.** The research pages load zero external font files — the system stack is
part of the seriousness. Do not add Google Fonts to a post.

Color rule: `--orange` is the one chrome accent (progress bar, focus ring, claim rule,
selection). Green / blue / purple / red exist **only inside figures**, where they encode
distinct quantities. Never use them for chrome, links, or emphasis. One standing
exception: the XO brand mark in the threadbar keeps its `#83d63a`/`#000` strokes — it is
a logo, copied verbatim between pages, not a chrome color choice.

### 5.2 Layout grid

The article is a CSS subgrid with three named spans:

```css
.article {
  display: grid;
  grid-template-columns:
    [screen-start] minmax(24px, 1fr)
    [middle-start] minmax(0, 148px)
    [text-start]   minmax(0, var(--text))
    [text-end]     minmax(0, 148px)
    [middle-end]   minmax(24px, 1fr)
    [screen-end];
}
```

- `.text` — all prose. 704px measure.
- `.middle` — figures that need ~1000px.
- `.wide` — figures that need the full 1120px page.

Sections declare `grid-template-columns: subgrid` so every child inherits the same
columns. Adding a post means writing `<div class="text">` / `<figure class="middle">`; the
alignment is free.

### 5.3 Type scale

| Element | Size | Weight | Tracking |
|---|---|---|---|
| Body | 17px / 1.62 | 400 | — |
| `.lede` | 20px / 1.56 | 400 | `--ink-soft` |
| `.subheading` (h3) | clamp(22, 3vw, 29) | 690 | −0.03em |
| `.section-heading` (h2) | clamp(31, 4.2vw, 44) | 720 | −0.04em, bottom hairline |
| `h1` (masthead) | display | 700+ | −0.04em |
| `.kicker` / `.intro-marker` / `.figure-eyebrow` | 9–11px mono | — | uppercase, ~0.09em |
| `figcaption` | 13px | 400 | `--ink-faint` |

Section numbers hang in the left gutter via `.section-number { position: absolute; right: calc(100% + 18px) }`.

### 5.4 Figures

Every figure follows one pattern:

```html
<figure class="figure middle">
  <div class="figure-frame">
    <div class="figure-head">
      <h3 class="figure-title" id="…-title">
        <span class="figure-eyebrow">Conceptual system map</span>
        The environment is the instrument
      </h3>
      <span class="figure-status">Illustrative</span>
    </div>
    <!-- hand-authored HTML/CSS/SVG diagram -->
  </div>
  <figcaption>What the reader should take away, in one or two sentences.</figcaption>
</figure>
```

- `figure-eyebrow` — what *kind* of thing this is ("Unit lifecycle", "Interactive system map").
- `figure-status` — the claim ledger: `Derived` · `Illustrative` · `Open`.
- The caption states the takeaway. It is not a label.
- Interactive figures use native `<input type="range">` + `<output>` and native
  `role="tab"` panels. No chart libraries.

### 5.5 Claims and callouts

```html
<div class="claim"><p><strong>Claim.</strong> …</p></div>
```

Left rule in `--orange`, ground in `--paper-warm`. Reserved for load-bearing assertions —
if everything is a claim, nothing is.

### 5.6 Index thumbnails

Each post's index card art should be an SVG **pulled from a real figure in the post**,
reduced to its silhouette. transformer-circuits does exactly this, and it's why its index
reads as a map of ideas rather than a list of links. No photography, no gradients, no
generated imagery.

### 5.7 Motion and accessibility

- **No scroll-triggered reveals.** No grain. No parallax. The only moving elements are
  the reading progress bar and figure controls the reader drives.
- `:focus-visible { outline: 3px solid rgba(217,130,38,.58); outline-offset: 3px }` — keep it.
- Every figure control is a native form element with a label and an `<output>`.
- Tabs implement the ARIA tab pattern (`role="tab"` / `aria-controls` / `aria-selected`).
- `html { scroll-padding-top: 84px }` so anchors clear the fixed header.
- Honor `prefers-reduced-motion` for the progress bar transition.
- Target contrast ≥ 4.5:1 for body ink; `--ink-faint` on `--paper` is for meta text only.

---

## 6. Why no framework

Stated plainly so it survives the next refactor impulse:

- A 484 KB HTML file with inline CSS renders in one round trip and will still open in
  2040. A React bundle will not.
- Long-form documents get read on hotel wifi, in airplane mode, and by scrapers.
  Server-side or client-side hydration buys nothing here and costs both.
- Hand-authored SVG figures are diffable in git. Chart-library figures are not.
- The whole viewer is a `fetch('posts.json')` and a render loop. Introducing Next.js to
  render a list of nine links would be the least serious thing on the site.

If a build step ever becomes necessary, make it *optional and additive*: a Node script
that regenerates `posts.json` and `feed.xml` from the HTML that already exists. The site
must keep working if the script is never run.

---

## 7. Housekeeping — known gaps

These are real inconsistencies in the folder as it stands:

1. **Two canonical domains.** `llm.txt` and `vectors.json` declare
   `https://xo.builders/whitepaper`; every OG/Twitter tag declares `https://quirq.ai`.
   Pick one and make it the site canonical, then fix the other set.
2. **`vectors.json` points at a route that does not exist** — it says its visualization
   lives at `/whitepaper/ai`. There is no `whitepaper/ai/`. Either build it or drop the
   reference.
3. **`what-is-quirq/index.html` has no OG or Twitter tags.** It is the flagship piece and
   the one most likely to be shared. It also has no `og:image`.
4. **`.DS_Store` is committed and there is no `.gitignore`.** Add one
   (`.DS_Store`, `node_modules/`, `.vercel/`).
5. **Whitepaper artifacts live at the root** — `quirq-whitepaper.pdf`, `llm.txt`, and
   `vectors.json` all belong to `/whitepaper/`. Moving them under that folder makes the
   "a folder is a post, and it owns its assets" rule true everywhere. Leave redirects or
   accept the broken external links knowingly.
6. **Sections 4–7 of the essay are placeholders** rendering "Chapter outline to be
   developed." Either finish them or trim them out of the TOC before wide sharing —
   a visible skeleton undercuts a working proposal.
7. **Brand collision.** The root page is `quirq` (product); the essay is `XO Labs ·
   Research`. Decide whether this publication is *XO Research* or *Suraj Sharma's
   writings*, and make the masthead, favicon, and footer agree.
8. **No deploy config.** No `CNAME`, `vercel.json`, or Pages workflow is checked in.
   Whatever is serving this today is configured outside the repo.

### 7.1 Adding a post

1. `mkdir <slug>/` — kebab-case, no dates in the slug.
2. Copy the skeleton from `what-is-quirq/index.html` (masthead → contents rail →
   `.article` grid → references).
3. Write the masthead: kicker, `<h1>`, `.dek`, and the `publication-meta` `<dl>`
   (Author / Published / Reading / Status).
4. Build figures with the §5.4 pattern. Give each a status from the claim ledger.
5. Add head metadata: `description`, `author`, `theme-color: #ffffff`,
   `<link rel="icon" href="../assets/favicon.svg">`, canonical URL, and OG/Twitter tags
   with a real `og:image`.
6. Append the entry to `posts.json`.
7. If the post makes formal claims, write a `section-N-spec.md` companion beside it and
   list it under `attachments`.

### 7.2 Voice

Short declaratives. Numbers with their derivation. Every hypothesis carries its
falsifier — the essay already commits to this in §2 and the reference section
("each body of work supplies a constraint, not just a citation"). Keep marketing language
out of `/writings/`; it has its own page.

### 7.3 `llm.txt`

The convention already established at the root: a plain-text rendering of a document,
prepared for language models and agents, with a header block declaring source, canonical
URL, and what was lossy in extraction. Worth doing per-post as `<slug>/llm.txt` and
listing in `attachments` — it costs one export and makes the work legible to the readers
who are increasingly doing the reading.

---

## 8. Local development

```bash
# any static server; the viewer's fetch('posts.json') needs http://, not file://
python3 -m http.server 8000
# → http://localhost:8000
```

Individual posts open fine over `file://` — that's the point of §2.2.

Deploy: any static host. GitHub Pages from `main` needs nothing but the repo. Vercel needs
a `vercel.json` with no build command and `outputDirectory: "."`.
