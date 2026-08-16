# /editor/ — the composable-post editor

A single self-contained HTML app (`index.html`) for editing posts in the
`composable-post/1` format (spec: `../shared/composable-post.md`; reference
document: `../what-is-quirq-test/index.html`; human docs: `wiki/`).
Works opened directly via `file://` — no build step, no external resources,
no network calls.

## Feature contract (normative for implementation and docs)

1. **Open** — drag-drop a file onto the window, or use the file picker;
   `?src=<relative-path>` auto-loads when served over http. Files without
   `<meta name="post-format" content="composable-post/1" />` are refused
   with a clear message (no guessing).
2. **Outline panel** — the block tree from the manifest: chapters with
   their parts, category chips, `complete`/`placeholder` status pills.
   Checkboxes include/exclude `optional` blocks; drag handles reorder
   `movable` siblings. Chrome/css/script blocks listed read-only under
   "infrastructure".
3. **Live preview** — an iframe (`srcdoc`) rendering the current
   composition. **Click any text element to edit it in place**
   (contenteditable); commit on blur or Ctrl/Cmd+Enter, cancel on Esc.
   Edits write back into the block's source.
4. **HTML drawer** — per block, "Edit HTML" opens the block's raw
   fence-to-fence source in a textarea; Apply replaces the block after a
   fence/anchor sanity check.
5. **Composition ops** — remove (optional blocks), reorder (movable
   siblings). Both nav surfaces (`.toc-menu`, `.contents-rail`) and
   `nav.order` in the manifest are regenerated per spec §5; section numbers
   are names, never renumbered. Optional conservative CSS pruning using
   `deps.css` (off by default).
6. **Export** — download or copy: (a) the annotated composable file,
   (b) a stripped plain file per spec §5.6.
7. **Safety** — validation panel per spec §5.5 (fence pairing, anchor
   resolution, dangling in-text hrefs after removals, tag-balance check);
   undo/redo; beforeunload warning on unsaved changes.
8. **Testable core** — all parsing/composition is pure string/model
   functions with **no DOM access**, exposed as `window.CPF`:
   `parse(text) → model`, `serialize(model) → text`,
   `reorder(model, id, beforeId|null)`, `remove(model, id)`,
   `replaceBlockHtml(model, id, html)`, `regenNav(model)`,
   `strip(text) → text`, `validate(text) → issues[]`.
   `serialize(parse(text))` must equal `text` byte-for-byte. The UI layer
   lives in a separate script block and is the only place touching the DOM.

## Files

- `index.html` — the app (single file).
- `wiki/index.html` — documentation, paper-format, with diagrams.
- `tools/annotate.py` — deterministic annotator that produced the reference
  document from the un-annotated flagship (re-run it after upstream edits;
  it proves strip-equivalence before writing).
- `tools/tests/` — node test harness for `window.CPF` (extracts the core
  script; runs without a browser).

## Repo constraints inherited from AGENTS.md

Single-file artifacts, `file://`-safe, system fonts only, no external JS,
never commit/push unless asked. The editor is a tool, not a post — it does
not use the paper design system, and its styles must never leak into posts.
