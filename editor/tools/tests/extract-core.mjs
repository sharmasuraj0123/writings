// extract-core.mjs — pull the <script id="cpf-core"> text out of the editor
// and evaluate it in a bare vm context with a stub `window` object.
// No DOM, no browser: the core is contractually pure (README §8).

import { readFileSync } from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const EDITOR_HTML = path.resolve(HERE, "..", "..", "index.html");
export const REFERENCE_HTML = path.resolve(
  HERE, "..", "..", "..", "what-is-quirq-test", "index.html"
);

export function extractCoreSource() {
  const html = readFileSync(EDITOR_HTML, "utf8");
  const openTag = '<script id="cpf-core">';
  const start = html.indexOf(openTag);
  if (start === -1) {
    throw new Error(`no ${openTag} in ${EDITOR_HTML}`);
  }
  const bodyStart = start + openTag.length;
  const end = html.indexOf("</script>", bodyStart);
  if (end === -1) {
    throw new Error("cpf-core script never closed");
  }
  return html.slice(bodyStart, end);
}

export function loadCPF() {
  const src = extractCoreSource();
  const windowStub = {};
  const ctx = vm.createContext({ window: windowStub });
  vm.runInContext(src, ctx, { filename: "cpf-core.inline.js" });
  if (!windowStub.CPF) {
    throw new Error("evaluating cpf-core did not define window.CPF");
  }
  const CPF = windowStub.CPF;
  const expected = [
    "parse", "serialize", "reorder", "remove", "replaceBlockHtml",
    "regenNav", "strip", "validate"
  ];
  for (const name of expected) {
    if (typeof CPF[name] !== "function") {
      throw new Error(`window.CPF.${name} is not a function`);
    }
  }
  return CPF;
}
