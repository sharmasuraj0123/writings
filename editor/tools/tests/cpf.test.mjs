// cpf.test.mjs — node harness for the editor's pure core (window.CPF),
// run against the real reference document what-is-quirq-test/index.html.
//
//   node cpf.test.mjs
//
// Each test gets a fresh parse of the reference text; nothing mutates shared
// state. Exit code 0 iff every test passed. Emits a JSON summary on the last
// line for machine consumption.

import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadCPF, REFERENCE_HTML } from "./extract-core.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STRIP_PY = path.join(HERE, "strip_ref.py");

/* ---------- tiny runner ---------- */

const results = [];
function test(name, fn) {
  try {
    fn();
    results.push({ name, pass: true });
    console.log(`PASS  ${name}`);
  } catch (e) {
    const detail = e && e.stack ? String(e.stack) : String(e);
    results.push({ name, pass: false, detail });
    console.log(`FAIL  ${name}\n      ${detail.split("\n").join("\n      ")}`);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}
function assertEq(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

/* ---------- shared fixtures / helpers ---------- */

const rawBytes = readFileSync(REFERENCE_HTML); // Buffer, exact bytes on disk
const text = rawBytes.toString("utf8");
// guard: utf8 decode/encode must be lossless or "byte equality" via strings lies
assert(Buffer.from(text, "utf8").equals(rawBytes),
  "reference file is not clean UTF-8; string comparison would not prove byte equality");

const CPF = loadCPF();

const FENCE_RE = /<!-- ═+ (BLOCK|END) ([a-z]+:[a-z0-9-]+) ═+ -->/g;

function navRegions(doc) {
  const toc = /<nav class="toc-menu"[^>]*>[\s\S]*?<\/nav>/.exec(doc);
  const rail = /<aside class="contents-rail"[\s\S]*?<\/aside>/.exec(doc);
  assert(toc, "toc-menu nav region not found");
  assert(rail, "contents-rail region not found");
  return { "toc-menu": toc[0], "contents-rail": rail[0] };
}
function dataForSeq(region) {
  return [...region.matchAll(/data-for="([^"]+)"/g)].map((m) => m[1]);
}
function hrefAnchors(region) {
  return [...region.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]);
}
function idSet(doc) {
  const ids = new Set();
  for (const m of doc.matchAll(/\bid="([^"]+)"/g)) ids.add(m[1]);
  return ids;
}
function assertNavResolves(doc, label) {
  const ids = idSet(doc);
  for (const [name, region] of Object.entries(navRegions(doc))) {
    for (const a of hrefAnchors(region)) {
      assert(ids.has(a), `${label}: ${name} href="#${a}" does not resolve to any id`);
    }
  }
}

const IMPACT_ANCHORS = ["business-impact", "impact-observability", "impact-roi",
  "impact-capacity", "impact-process", "impact-governance"];
const MEASURE_ANCHORS = ["measure", "measure-score", "measure-mint", "measure-cost",
  "measure-unit", "measure-portfolio", "measure-estimation", "measure-validity",
  "measure-time", "measure-identification", "measure-bridge", "measure-limitations"];

/* ---------- 1. round-trip ---------- */

test("1 round-trip: serialize(parse(text)) === text byte-for-byte", () => {
  const out = CPF.serialize(CPF.parse(text));
  assert(typeof out === "string", "serialize did not return a string");
  if (out !== text) {
    // locate first divergence for the report
    let i = 0;
    while (i < out.length && i < text.length && out[i] === text[i]) i++;
    const line = text.slice(0, i).split("\n").length;
    throw new Error(`round-trip diverges at char ${i} (line ~${line}); ` +
      `lengths ${out.length} vs ${text.length}`);
  }
  assert(Buffer.from(out, "utf8").equals(rawBytes), "round-trip bytes differ from file bytes");
});

/* ---------- 2. parse: block count, manifest format, nav.order ---------- */

test("2 parse: 53 blocks, manifest format, nav.order has the 8 chapters", () => {
  const model = CPF.parse(text);
  const ids = CPF.docOrder(model);
  assertEq(ids.length, 53, "block count");
  assert(model.manifest, `manifest not parsed: ${model.manifestError}`);
  assertEq(model.manifest.format, "composable-post/1", "manifest.format");
  const order = model.manifest.nav && model.manifest.nav.order;
  assert(Array.isArray(order), "manifest.nav.order missing");
  assertEq(order.length, 8, "nav.order length");
  const kinds = new Map(model.manifest.blocks.map((b) => [b.id, b.kind]));
  for (const id of order) {
    assertEq(kinds.get(id), "chapter", `nav.order entry ${id} kind`);
  }
  // nav.order must equal the chapters in document order
  const chDoc = ids.filter((id) => kinds.get(id) === "chapter");
  assertEq(order.join("|"), chDoc.join("|"), "nav.order vs document chapter order");
});

/* ---------- 3. reorder chapter:impact before chapter:measure ---------- */

test("3 reorder impact before measure: navs, nav.order, validate, anchors", () => {
  const model = CPF.parse(text);
  CPF.reorder(model, "chapter:impact", "chapter:measure");
  const out = CPF.serialize(model);

  // manifest nav.order updated
  const reparsed = CPF.parse(out);
  assert(reparsed.manifest, `reordered doc manifest unparsable: ${reparsed.manifestError}`);
  assertEq(
    reparsed.manifest.nav.order.join("|"),
    ["chapter:introduction", "chapter:impact", "chapter:measure", "chapter:research",
      "chapter:other-applications", "chapter:data-experiments", "chapter:roadmap",
      "chapter:references"].join("|"),
    "nav.order after reorder"
  );

  // both navs list every impact anchor before every measure anchor
  for (const [name, region] of Object.entries(navRegions(out))) {
    const seq = dataForSeq(region);
    for (const a of [...IMPACT_ANCHORS, ...MEASURE_ANCHORS]) {
      assert(seq.includes(a), `${name} lost anchor ${a} after reorder`);
    }
    const lastImpact = Math.max(...IMPACT_ANCHORS.map((a) => seq.indexOf(a)));
    const firstMeasure = Math.min(...MEASURE_ANCHORS.map((a) => seq.indexOf(a)));
    assert(lastImpact < firstMeasure,
      `${name}: impact anchors not all before measure anchors ` +
      `(last impact at ${lastImpact}, first measure at ${firstMeasure}; seq=${seq.join(",")})`);
  }

  // every nav href resolves
  assertNavResolves(out, "after reorder");

  // validate reports no issues
  const issues = CPF.validate(out);
  assert(Array.isArray(issues), "validate did not return an array");
  assertEq(issues.length, 0,
    `validate issues after reorder: ${JSON.stringify(issues, null, 1)}`);
});

/* ---------- 4. remove part:measure-limitations ---------- */

test("4 remove part:measure-limitations: fences+nav entries gone, validate lists dangling", () => {
  const model = CPF.parse(text);
  const res = CPF.remove(model, "part:measure-limitations");
  const out = CPF.serialize(model);

  // fence-to-fence bytes gone
  assert(!/(BLOCK|END) part:measure-limitations/.test(out),
    "fences for part:measure-limitations still present");
  assert(!out.includes('id="measure-limitations"'),
    "section body (anchor id) still present after removal");

  // nav entries gone from both navs
  for (const [name, region] of Object.entries(navRegions(out))) {
    assert(!region.includes('data-for="measure-limitations"'),
      `${name} still has a data-for="measure-limitations" entry`);
    assert(!hrefAnchors(region).includes("measure-limitations"),
      `${name} still links #measure-limitations`);
  }
  assert(!out.includes('data-for="measure-limitations"'),
    'data-for="measure-limitations" still present somewhere in the document');

  // remaining nav anchors all resolve
  assertNavResolves(out, "after removal");

  // the reference doc has one in-text href="#measure-limitations" inside the
  // chapter:measure intro; it now dangles. validate() must list it, not crash.
  assert(out.includes('href="#measure-limitations"'),
    "expected the in-text link to #measure-limitations to remain (fixture assumption)");
  let issues;
  try {
    issues = CPF.validate(out);
  } catch (e) {
    throw new Error(`validate() crashed on post-removal document: ${e.message}`);
  }
  assert(Array.isArray(issues), "validate did not return an array");
  const dangling = issues.filter((i) =>
    i.code === "dangling-href" && /measure-limitations/.test(i.message));
  assert(dangling.length >= 1,
    `validate() did not list the dangling in-text href; issues=${JSON.stringify(issues, null, 1)}`);
  // no other classes of error may appear
  const other = issues.filter((i) => i.code !== "dangling-href");
  assertEq(other.length, 0,
    `unexpected non-dangling issues after removal: ${JSON.stringify(other, null, 1)}`);
  // remove() itself reported the same dangling href as a warning
  assert(res && Array.isArray(res.warnings), "remove() did not return warnings[]");
  assert(res.warnings.some((w) => w.code === "dangling-href" && /measure-limitations/.test(w.message)),
    `remove() warnings missed the dangling href: ${JSON.stringify(res.warnings, null, 1)}`);
});

/* ---------- 5. remove refuses a non-optional block ---------- */

test("5 remove refuses non-optional chapter:references and leaves model intact", () => {
  const model = CPF.parse(text);
  let threw = null;
  try {
    CPF.remove(model, "chapter:references");
  } catch (e) {
    threw = e;
  }
  assert(threw, "remove(chapter:references) did not throw despite optional=false");
  assert(/optional/.test(String(threw.message)),
    `refusal message does not mention optional: ${threw.message}`);
  assertEq(CPF.serialize(model), text, "model was mutated by the refused remove");
});

/* ---------- 6. strip vs independent python implementation ---------- */

test("6 strip: byte-equal to independent python §5.6 strip; no annotations left", () => {
  const jsStripped = CPF.strip(text);

  const tmp = mkdtempSync(path.join(os.tmpdir(), "cpf-strip-"));
  try {
    const pyOut = path.join(tmp, "stripped-py.html");
    execFileSync("python3", [STRIP_PY, REFERENCE_HTML, pyOut], { stdio: "pipe" });
    const pyBytes = readFileSync(pyOut);
    const jsBytes = Buffer.from(jsStripped, "utf8");
    if (!jsBytes.equals(pyBytes)) {
      const a = jsStripped;
      const b = pyBytes.toString("utf8");
      let i = 0;
      while (i < a.length && i < b.length && a[i] === b[i]) i++;
      const line = a.slice(0, i).split("\n").length;
      writeFileSync(path.join(tmp, "stripped-js.html"), jsBytes);
      throw new Error(
        `strip outputs differ at char ${i} (js line ~${line}); ` +
        `js ${jsBytes.length} bytes vs py ${pyBytes.length} bytes; ` +
        `js: ${JSON.stringify(a.slice(Math.max(0, i - 40), i + 40))} ` +
        `py: ${JSON.stringify(b.slice(Math.max(0, i - 40), i + 40))}`);
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }

  assert(!jsStripped.includes("data-block"), "stripped output still contains 'data-block'");
  FENCE_RE.lastIndex = 0;
  assert(!FENCE_RE.test(jsStripped), "stripped output still contains fence comments");
  assert(!jsStripped.includes("block-manifest"), "stripped output still contains the block-manifest");
  assert(!jsStripped.includes("data-for="), "stripped output still contains data-for attributes");
  assert(!jsStripped.includes('name="post-format"'), "stripped output still contains the format meta");
  assert(!jsStripped.includes("ANATOMY"), "stripped output still contains the ANATOMY banner");
});

/* ---------- summary ---------- */

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} tests passed`);
console.log("RESULTS_JSON " + JSON.stringify(results));
process.exit(failed.length ? 1 : 0);
