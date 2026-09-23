# Writing a post body for `tools/assemble-post.py`

This is the brief for anyone (human or agent) producing a post in the light
"paper" system. AGENTS.md is the contract; this file is the working recipe.
You produce three files inside `<slug-dir>/` and never touch the chrome:

| file | what |
|---|---|
| `_article.html` | the `<article>` … `</article>` body only (see skeleton) |
| `meta.json` | title, dek, sections, etc. (schema in `tools/assemble-post.py`) |
| `assets/thumb.svg` | 320×160 silhouette of one real figure from the post (AGENTS.md §7.3) |

Then run `python3 tools/assemble-post.py <slug-dir>` — it writes `index.html`
with the canonical chrome and prints a validation report; iterate until
`"problems": []`.

## Skeleton of `_article.html`

```html
      <article>
        <section class="prose">
          <div class="callout">
            <span class="k">How to read the badges</span>
            <p>… <span class="src">from the source</span> … <span class="recon">reconstruction</span> …</p>
          </div>

          <h2 id="why"><span class="secnum">01</span>Title of section one</h2>
          <p class="lede">One-paragraph thesis in short declaratives.</p>
          <p>…</p>
          <h3>Optional subsection</h3>
          <p>…</p>

          <figure class="figure wide" id="fig-shape">           <!-- "wide" = 1120px; omit for 1000px -->
            <div class="figure-head">
              <span class="figure-label">Figure 1</span>
              <p class="figure-title">What it shows — one line</p>
            </div>
            <div class="figure-body plain"> …SVG diagram… </div> <!-- "plain" = no inner padding/border -->
            <p class="figure-caption">The takeaway, not a label.</p>
          </figure>

          <h2 id="sources"><span class="secnum">NN</span>Sources</h2>
          <ul><li><a href="…">…</a> — what it was used for.</li></ul>
          <p class="footnote"><strong>Provenance.</strong> what is sourced, what is yours, what you did not verify.</p>
        </section>
      </article>
```

Rules that the validator enforces or that break the page silently:

- `<h2 id="…">` ids and order must equal `meta.json → sections[].id`; `secnum`
  runs `01, 02, …` in order. Only `<h2>` sections appear in nav; use `<h3>` freely.
- Everything is one file: no `<img>`, no `<link>`, no external `<script>`, no
  webfonts. Figures are hand-authored SVG/HTML/CSS. Escape `<`, `>`, `&` inside
  `<code>`/`<pre>`.
- Every `id` unique; SVG `<marker id>` names unique per figure (prefix them).
- Relative links go up `../` per path depth (`chromium/blink` → `../../assets/`).

## The vocabulary you have (all CSS is already in the chrome)

- Text: `.prose p`, `p.lede`, `h3`, `code`, `pre > code` (13px mono, soft ground),
  `ul`/`ol`, `table` (`thead th` uppercase mono; use for ledgers and mappings).
- `.callout` with a leading `<span class="k">Label</span>` then `<p>` — for design rules, how-to-read, warnings.
- Badges: `<span class="src">from the source</span>` (paper-soft) and
  `<span class="recon">reconstruction</span>` (warm) — inline, after the claim.
- Stat tiles: `<div class="measured"><div><div class="n">4</div><div class="k">meaning</div></div>…</div>` (4 per row).
- Stack rows: `<div class="stack"><div class="stack-row"><div class="stack-cell head">Label</div><div class="stack-cell hl-blue">…</div></div>…</div>`
  (`hl-blue|hl-green|hl-purple|hl-orange|hl-red` tint the cell — encode meaning, not decoration).
- Cards: `<div class="tier-grid"><div class="tier-card ep"><h4>…</h4><p class="sub">EYEBROW</p><p>…</p></div>…</div>` (3 per row; `ep` blue, `se` purple, `pr` green).
- Journey cards: `<div class="journeys"><div class="jcard"><h4>…</h4><p class="who">…</p><p>…</p></div>…</div>` (2 per row).
- SVG text classes: `svg-lane` (uppercase mono lane labels), `svg-step` (node titles), `svg-sub` (mono detail),
  `svg-num` (orange step numbers), `svg-note` (italic serif notes). Fill colours in figures:
  blue `#3c6f97`/`#e0ebf2`, green `#367f59`/`#dfede5`, purple `#765b98`/`#ece6f3`, orange `#d98226`/`#f7e3c8`,
  red `#ad4b43`/`#f3dfdc`, ink `#252525`, paper-soft `#f7f7f5`, line `#deded9`/`#b8b8b1`.
- Edge conventions in diagrams (keep across posts): thin blue = data, thick black = control/sequence,
  dashed purple = state/effect. Arrowheads via `<marker>`.

## Voice and epistemics (AGENTS.md §4, restated)

Short declaratives. Numbers carry their derivation. Quote sources verbatim and
cite exactly — file paths with line numbers for teardowns, section names for
docs. Every claim carries its status: figure captions say what is measured and
what is reconstructed; inline badges when a paragraph mixes both. The closing
`.footnote` states what is sourced, what is yours, and what you did not verify.
No marketing language, no "powerful", no "seamless". Prefer the concrete file,
constant, flag, or commit over the adjective.

## Size for a "very detailed" explainer

9,000–12,000 words in `<main>` (the validator prints the count), 12–16
figures, 10–14 `<h2>` sections, 8–15 verbatim code excerpts (≤ 25 lines each,
with path and line numbers in a preceding sentence), a Sources section, a
provenance footnote. Write the article in chunks (append to `_article.html`),
assemble and validate after each chunk.
