# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = [
#   "PyYAML==6.0.3",
#   "ruamel.yaml==0.19.1",
#   "tomli==2.5.0",
#   "tomlkit==0.15.1",
#   "json5==0.15.0",
# ]
# [tool.uv]
# exclude-newer = "2026-10-09T00:00:00Z"
# ///
"""What the Parser Hears: the measured pitfall matrix.

Run:   uv run ~/xo-projects/writings/what-the-parser-hears/_compute.py
Writes _numbers.json (and an exact-bytes mirror of every case in _cases/) next to this file.

The same bytes go to every parser that claims the format, each called the way a config
loader without a schema would call it (defaults, untyped target). Python parsers run in
process. Node, Rust and Go probes live outside the publication in BENCH/hears/ and are
driven over a JSON request file; a missing toolchain or probe is recorded as "skipped".
jq is run as a subprocess. Python 3.15's tomllib (a release candidate on 2026-10-08) is
included if the interpreter in PY315 exists.

Value encoding in results: every leaf is "<native type>:<repr>", e.g. "bool:False" (Python),
"boolean:false" (JS), "Bool:false" (Rust serde), "bool:false" (Go). Maps with only string keys
are JSON objects in the order the parser returned them (Go maps are unordered; the Go probe
sorts keys; Rust serde_json/toml maps are BTreeMaps and come back sorted). Maps with any
non-string key are {"__pairs__": [[key, value], ...]}.
"""
from __future__ import annotations

import base64
import datetime as dt
import difflib
import hashlib
import io
import json
import math
import os
import platform
import re
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import warnings
from collections.abc import Mapping
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = Path("/home/coder/config-ref/bench")            # probe code lives outside the publication
HEARS = BENCH / "hears"
NODE_DIR = HEARS / "node"
RUST_DIR = HEARS / "rust"
GO_DIR = HEARS / "go"
GO_BIN = BENCH / "toolchains" / "go" / "bin" / "go"      # Go 1.27.2, SHA-256 checked when downloaded
GO_CACHE = BENCH / "toolchains" / "gocache"
PY315 = BENCH / "toml" / ".pythons" / "cpython-3.15.0rc1-linux-x86_64-gnu" / "bin" / "python3"
OUT_JSON = HERE / "_numbers.json"
CASES_DIR = HERE / "_cases"

DEPTH_CAP = 100_000
TIMING_REPEATS = 501
TIMING_WARMUP = 50
MAXERR = 600
CHILD_MEM_BYTES = 4 << 30   # address-space cap for Python/Rust/Go children (bomb, depth)
CHILD_TIMEOUT_S = 300

# ----------------------------------------------------------------------------------------
# Cases. Inputs are the exact bytes. "trap" is the one-line reason the case exists.
# ----------------------------------------------------------------------------------------
CASES: list[dict] = []


def case(cid, fmt, title, trap, src, mode="doc", source="constructed for this post", extra=(), order_matters=False):
    b = src if isinstance(src, bytes) else src.encode("utf-8")
    CASES.append(dict(id=cid, format=fmt, title=title, trap=trap, input=b, mode=mode, source=source,
                      extra=list(extra), order_matters=order_matters))


YAML11_TYPES = "https://yaml.org/type/ (YAML 1.1 type repository: bool, int, float, timestamp, merge)"
YAML122 = "https://yaml.org/spec/1.2.2/"
# --- YAML ---
case("y_norway", "yaml", "Country codes", "NO is false under YAML 1.1 bool rules (the 'Norway problem')",
     "countries: [GB, IE, FR, DE, NO, SE]\n",
     source="name from StrictYAML docs, https://hitchdev.com/strictyaml/why/implicit-typing-removed/")
case("y_bools", "yaml", "Ten spellings of yes and no", "1.1 accepts y/n/yes/no/on/off in several cases; 1.2 core only true/false",
     "a: yes\nb: no\nc: on\nd: off\ne: y\nf: n\ng: Yes\nh: ON\ni: True\nj: TRUE\n", source=YAML11_TYPES)
case("y_on_key", "yaml", "GitHub-Actions-style top-level on:", "the key `on` itself becomes boolean True under 1.1",
     "name: CI\non:\n  push:\n    branches: [main]\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
     source="https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#on")
case("y_octal", "yaml", "File modes and hex", "0755 is octal 493 in 1.1 and decimal 755 in 1.2; 0o755 is the reverse",
     "a: 0755\nb: 0o755\nc: 012\nd: 0x1F\n", source=YAML11_TYPES)
case("y_sexagesimal", "yaml", "Times and durations", "1.1 reads 22:22 as base-60 integer 1342",
     "a: 22:22\nb: 1:30:00\n", source=YAML11_TYPES)
case("y_versions", "yaml", "Version numbers", "3.10 is the float 3.1 in every schema that has floats",
     "python: 3.10\ngo: 1.20\n", source=YAML122 + "#1023-core-schema")
case("y_exponent", "yaml", "Exponent without a dot", "1.1's float regexp needs a dot, so 1e3 stays a string there",
     "a: 1e3\nb: 1.0e+3\n", source=YAML11_TYPES)
case("y_underscore", "yaml", "Digit separators", "1.1 allows 1_000; 1.2 core does not",
     "a: 1_000\n", source=YAML11_TYPES)
case("y_inf_nan", "yaml", "Infinity and NaN", ".inf/.NaN are floats in both 1.1 and 1.2 core",
     "a: .inf\nb: -.Inf\nc: .NaN\n", source=YAML122 + "#1023-core-schema")
case("y_nulls", "yaml", "Four nulls", "~, null, empty and Null are all null; 'Christopher Null'",
     "a: ~\nb: null\nc:\nd: Null\n", source=YAML122 + "#1023-core-schema")
case("y_timestamps", "yaml", "Dates", "1.1 timestamps become native date/datetime; 1.2 core has no timestamp type",
     "a: 2001-12-14\nb: 2001-12-14T21:59:43.10-05:00\n", source=YAML11_TYPES)
case("y_zip", "yaml", "ZIP codes with a leading zero", "01234 is octal 668 in 1.1; 08540 is not octal, so 1.1 keeps it a string",
     "zip: 01234\nzip_nj: 08540\n", source=YAML11_TYPES)
case("y_colon_space", "yaml", "A value containing ': '", "': ' inside a plain scalar starts a nested mapping, which is an error here",
     "cmd: echo key: value\n", source=YAML122 + "#733-plain-style")
case("y_hash", "yaml", "A value containing ' #'", "' #' starts a comment; '#' without a space does not",
     "msg: hello #world\nurl: http://example.com/#frag\n", source=YAML122 + "#62-separation-spaces")
case("y_tab", "yaml", "Tab indentation", "tabs are forbidden in indentation",
     "a:\n\tb: 1\n", source=YAML122 + "#61-indentation-spaces")
case("y_dup_keys", "yaml", "Duplicate keys", "the spec requires unique keys; loaders differ on error vs last-wins",
     "a: 1\na: 2\n", source=YAML122 + "#3211-nodes")
case("y_merge", "yaml", "Merge key <<", "<< is a 1.1 type, not part of 1.2; a 1.2 loader may keep a literal '<<' key",
     "base: &base {x: 1, y: 2}\nderived:\n  <<: *base\n  y: 3\n", source="https://yaml.org/type/merge.html")
case("y_anchor_alias", "yaml", "Anchors and aliases", "aliases are shared references in some loaders and copies in others",
     "defaults: &d\n  retries: 3\n  timeout: 30\nprod: *d\nstaging: *d\n", source=YAML122 + "#3222-anchors-and-aliases")
case("y_misindent_list", "yaml", "Mis-indented list (constructed)", "ports meant for the container lands on spec; still valid YAML",
     "spec:\n  containers:\n  - name: app\n    image: nginx\n  ports:\n  - 80\n",
     source="constructed for this post (same shape as yaml dossier F62); not a documented incident")
case("y_misindent_helm9793", "yaml", "First line indented (real report)", "helm#9793: 'lines with no indent are ignored'",
     ("  kind: DaemonSet\n  podLabels:\n    es-index: traefik2-ingress-controller\n\n"
      "additionalArguments:\n"
      "  - \"--providers.kubernetesingress.ingressclass=traefik2\"\n"
      "  - \"--providers.kubernetescrd.ingressclass=traefik2\"\n"
      "  - \"--entryPoints.web.forwardedHeaders.insecure\"\n"
      "  #- \"--entryPoints.web.proxyProtocol.insecure\"\n"
      "  - \"--api.insecure=true\"\n"
      "  - \"--metrics.prometheus=true\"\n"
      "  - \"--entryPoints.web.transport.lifeCycle.requestAcceptGraceTimeout=20\"\n"),
     source="https://github.com/helm/helm/issues/9793 (values.yaml as printed by `cat` in the report, Helm v3.6.0; CRLF of the issue body normalised to LF)")
case("y_block_scalars", "yaml", "Block scalar chomping", "| keeps one final newline, |- none, |+ all; > folds lines",
     "clip: |\n  line one\n  line two\n\nstrip: |-\n  line one\n  line two\n\nkeep: |+\n  line one\n  line two\n\n"
     "fold: >\n  line one\n  line two\nfold_strip: >-\n  line one\n  line two\nend: 1\n",
     source=YAML122 + "#8112-block-chomping-indicator")
case("y_python_tag", "yaml", "Python object tag (harmless payload)", "!!python/object/apply calls a function under unsafe loaders",
     'x: !!python/object/apply:builtins.str ["hi"]\n', extra=["py:pyyaml.full_load", "py:pyyaml.unsafe_load"],
     source="https://pyyaml.org/wiki/PyYAMLDocumentation (Loader classes)")
case("y_js_function", "yaml", "JS function tag", "js-yaml 3 constructed functions from !!js/function; 4 moved it out",
     'f: !!js/function "function () { return 1 }"\n', source="https://github.com/nodeca/js-yaml/blob/master/migrate_v3_to_v4.md")
case("y_unknown_local_tag", "yaml", "A value that starts with '!'", "'!.git' is a local tag with an empty value, not the string '!.git'",
     "exclude: !.git\n", source=YAML122 + "#6922-tag-shorthands (yaml dossier M11)")
case("y_multidoc", "yaml", "Two documents to a single-document API", "some loaders error, some silently return the first document",
     "a: 1\n---\nb: 2\n", source="RFC 9512 §3.2 'YAML Streams'")
case("y_separator_comment", "yaml", "'--- # comment' separator (real report)",
     "kubernetes#103185: kubectl's splitter dropped the document after '--- # something'",
     ("apiVersion: v1\nkind: Namespace\nmetadata:\n  name: foo\n--- # something\n"
      "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: bar\n---            \n"
      "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: baz\n"),
     mode="stream", source="https://github.com/kubernetes/kubernetes/issues/103185 (fixed by PR #103457, v1.22)")
_bomb_levels = "abcdefghi"


def _bomb(levels):
    rows = ['  a: &a ["web","web","web","web","web","web","web","web","web"]\n']
    for prev, cur in zip(levels, levels[1:]):
        rows.append(f"  {cur}: &{cur} [{','.join(['*' + prev] * 9)}]\n")
    return ("apiVersion: v1\ndata:\n" + "".join(rows) +
            "kind: ConfigMap\nmetadata:\n  name: yaml-bomb\n  namespace: default\n")


case("y_bomb9", "yaml", "Alias bomb, 9 levels x 9 (CVE-2019-11253 payload)", "446 bytes that name 9^9 = 387,420,489 strings",
     _bomb(_bomb_levels), mode="bomb", source="https://nvd.nist.gov/vuln/detail/CVE-2019-11253 (payload shape from the Kubernetes report)")
case("y_bomb6", "yaml", "Alias bomb, 6 levels x 9", "same shape, 9^6 = 531,441 strings: small enough to materialise",
     _bomb(_bomb_levels[:6]), mode="bomb", source="truncated CVE-2019-11253 payload")
case("y_depth", "yaml", "Nesting depth limit (flow sequences)", "how deep [[[...]]] can go before the loader refuses or crashes",
     b"", mode="depth")

# --- JSON ---
RFC8259 = "https://www.rfc-editor.org/rfc/rfc8259"
case("j_dup_keys", "json", "Duplicate keys", "RFC 8259: names SHOULD be unique; behaviour is unpredictable when not",
     '{"a": 1, "a": 2}\n', source=RFC8259 + "#section-4")
case("j_int_2p53p1", "json", "2^53 + 1", "IEEE doubles cannot hold 9007199254740993",
     '{"id": 9007199254740993}\n', source=RFC8259 + "#section-6")
case("j_int_u64", "json", "Above int64", "12345678901234567890 fits u64 but not i64 or a double",
     '{"id": 12345678901234567890}\n', source=RFC8259 + "#section-6")
case("j_1e400", "json", "Overflowing exponent", "1e400 is valid JSON grammar and exceeds every double",
     '{"x": 1e400}\n', source=RFC8259 + "#section-6")
case("j_nan_inf", "json", "NaN / Infinity tokens", "not JSON, but Python's json reads them",
     '{"a": NaN, "b": Infinity, "c": -Infinity}\n', source=RFC8259 + "#section-6")
case("j_trailing_comma", "json", "Trailing comma", "not JSON; JSON5/JSONC tooling accepts it",
     '{\n  "a": 1,\n  "b": 2,\n}\n', source=RFC8259 + "#section-4")
case("j_line_comment", "json", "// comment", "JSON has no comments",
     '{\n  // port for the admin UI\n  "port": 8080\n}\n', source=RFC8259)
case("j_block_comment", "json", "/* */ comment", "JSON has no comments",
     '{\n  /* port for the admin UI */\n  "port": 8080\n}\n', source=RFC8259)
case("j_bom", "json", "UTF-8 byte order mark", "RFC 8259: implementations MUST NOT add a BOM; MAY ignore one",
     b'\xef\xbb\xbf{"a": 1}\n', source=RFC8259 + "#section-8.1")
case("j_lone_surrogate", "json", "Lone surrogate escape", "\\ud800 is grammatical JSON but not a Unicode scalar value",
     '{"s": "\\ud800"}\n', source=RFC8259 + "#section-8.2")
case("j_top_scalar", "json", "Top-level scalar", "RFC 8259 allows any value at the top; RFC 4627 required object/array",
     '"just a string"\n', source=RFC8259 + "#section-2")
case("j_neg_zero", "json", "Negative zero", "-0 is an integer in some parsers (losing the sign) and a float in others",
     '{"x": -0, "y": -0.0}\n', source=RFC8259 + "#section-6")
case("j_key_order", "json", "Key order", "objects are unordered in the RFC; JS puts integer-like keys first",
     '{"b": 1, "a": 2, "10": 3, "2": 4}\n', source=RFC8259 + "#section-4", order_matters=True)
case("j_proto", "json", "__proto__ key", "an own property after JSON.parse; json5 < 2.2.2 polluted the prototype (CVE-2022-46175)",
     '{"__proto__": {"isAdmin": true}}\n', source="https://nvd.nist.gov/vuln/detail/CVE-2022-46175")
case("j_python_nan", "json", "What Python's json.dumps writes for NaN/inf", "json.dumps(allow_nan=True by default) emits non-JSON tokens",
     json.dumps({"ratio": float("nan"), "limit": float("inf")}) + "\n",
     source="https://docs.python.org/3/library/json.html (allow_nan); bytes produced by this harness")
case("j_depth", "json", "Nesting depth limit", "how deep [[[...]]] can go before the parser refuses or crashes", b"", mode="depth")

# --- TOML ---
TOML10 = "https://toml.io/en/v1.0.0"
TOML11 = "https://toml.io/en/v1.1.0"
case("t_scope_trap", "toml", "Key after a table header", "everything after [server] belongs to server until the next header",
     'title = "app"\n[server]\nhost = "0.0.0.0"\nport = 8080\n\n# meant as a top-level setting\ndebug = true\n', source=TOML10 + "#table")
case("t_table_twice", "toml", "Same table defined twice", "invalid: tables cannot be defined more than once",
     '[fruit]\napple = "red"\n\n[fruit]\norange = "orange"\n', source=TOML10 + "#table")
case("t_subtable_first", "toml", "[a.b] before [a]", "valid: defining a super-table after its sub-table is allowed",
     "[a.b]\nx = 1\n\n[a]\ny = 2\n", source=TOML10 + "#table")
case("t_dotted_over_header", "toml", "Dotted key into a [table]-defined table", "invalid: dotted keys may not redefine tables defined by a header",
     '[fruit.apple]\ncolor = "red"\n\n[fruit]\napple.taste = "sweet"\n', source=TOML10 + "#table")
case("t_header_over_dotted", "toml", "[table] header over a dotted-key table", "invalid: spec example '# [fruit.apple]  # INVALID'",
     '[fruit]\napple.color = "red"\napple.taste.sweet = true\n\n[fruit.apple]\n', source=TOML10 + "#table")
case("t_inline_extend", "toml", "Extending an inline table later", "invalid: inline tables are self-contained",
     '[product]\ntype = { name = "Nail" }\ntype.edible = false\n', source=TOML10 + "#inline-table")
case("t_inline_multiline", "toml", "Multi-line inline table with trailing comma", "TOML 1.1 only",
     'tbl = {\n  key = "a string",\n  nested = { x = 1, },\n}\n', source=TOML11 + "#inline-table")
case("t_escape_e", "toml", "\\e escape", "TOML 1.1 only", 'csi = "\\e[31m"\n', source=TOML11 + "#string")
case("t_escape_x", "toml", "\\x41 escape", "TOML 1.1 only", 'a = "\\x41"\n', source=TOML11 + "#string")
case("t_time_no_seconds", "toml", "Time without seconds", "TOML 1.1 only", "t = 07:32\n", source=TOML11 + "#local-time")
case("t_octal_leading_zero", "toml", "0755", "invalid: leading zeros are not allowed", "mode = 0755\n", source=TOML10 + "#integer")
case("t_octal_ok", "toml", "0o755", "valid octal, 493", "mode = 0o755\n", source=TOML10 + "#integer")
case("t_int64_max", "toml", "i64 max", "9223372036854775807 must be accepted", "max = 9223372036854775807\n", source=TOML10 + "#integer")
case("t_int64_overflow", "toml", "i64 max + 1", "must be an error, not a silent float", "big = 9223372036854775808\n", source=TOML10 + "#integer")
case("t_js_unsafe_int", "toml", "2^53 + 1", "valid TOML; JS numbers cannot hold it", "id = 9007199254740993\n", source=TOML10 + "#integer")
case("t_float_specials", "toml", "inf, nan, -0.0", "valid special floats", "a = inf\nb = -inf\nc = nan\nd = -0.0\n", source=TOML10 + "#float")
case("t_hetero_array", "toml", "Mixed-type array", "valid since 1.0 (invalid in 0.5)", 'a = [1, "a"]\n', source=TOML10 + "#array")
case("t_datetimes", "toml", "Four date-time types", "offset vs local datetime, local date, local time: what native type?",
     "odt = 1979-05-27T07:32:00-07:00\nldt = 1979-05-27T07:32:00\nld = 1979-05-27\nlt = 07:32:00\n", source=TOML10 + "#offset-date-time")
case("t_bool_case", "toml", "True", "invalid: booleans are lowercase", "enabled = True\n", source=TOML10 + "#boolean")
case("t_no_null", "toml", "Empty value", "invalid: TOML has no null, a key needs a value", "x = \n", source=TOML10 + "#keyvalue-pair")
case("t_dup_key", "toml", "Duplicate key", "invalid", "a = 1\na = 2\n", source=TOML10 + "#keys")
case("t_crlf_multiline", "toml", "CRLF inside a multi-line string", "the spec lets parsers normalise newlines; they split",
     b's = """\r\nline1\r\nline2"""\r\n', source=TOML10 + "#string ('TOML parsers should feel free to normalize newline')")
case("t_depth", "toml", "Nesting depth limit (arrays)", "how deep a = [[[...]]] can go", b"", mode="depth")

# --- the realistic cross-format config (also run through every parser as a case) ---
AGENT_TOML = '''# review-bot: agent service configuration
# Owner: platform team. Reload with SIGHUP.

schema_version = 3
service = "review-bot"
environment = "production"
deployed_at = 2026-10-08T09:30:00Z
regions = ["eu-west-1", "us-east-1"]

[model]
provider = "example-ai"
name = "large-2026-09"
max_tokens = 8192  # hard cap per response
temperature = 0.2
fallbacks = ["medium-2026-09", "small-2026-06"]

[timeouts]
connect_ms = 2500
request_s = 120.0
idle_s = 900  # close idle MCP sessions after 15 min

[retry]
attempts = 4
backoff = "exponential"
jitter = true
retry_on = [429, 500, 502, 503]

[routing]
allowed_countries = ["GB", "IE", "FR", "DE", "NO", "SE"]

[prompt]
system = """
You are a careful code reviewer.
Explain each finding in one sentence — cite the file and line.
Never approve a change you have not read.
"""

[logging]
level = "info"
format = "json"
redact = ["GITHUB_TOKEN", "SLACK_BOT_TOKEN"]

[budget]
max_usd_per_day = 250.0
alert_at = [0.5, 0.8, 0.95]

# MCP servers, started in this order
[[mcp_servers]]
name = "github"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
enabled = true
env = { GITHUB_TOKEN = "${GITHUB_TOKEN}", GITHUB_API_URL = "https://api.github.com" }

[[mcp_servers]]
name = "filesystem"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/srv/repos"]
enabled = true
env = {}

[[mcp_servers]]
name = "slack"
command = "uvx"
args = ["mcp-server-slack"]
enabled = false  # waiting on workspace approval
env = { SLACK_BOT_TOKEN = "${SLACK_BOT_TOKEN}", SLACK_TEAM_ID = "T0123456" }
'''

AGENT_YAML = '''# review-bot: agent service configuration
# Owner: platform team. Reload with SIGHUP.

schema_version: 3
service: review-bot
environment: production
deployed_at: 2026-10-08T09:30:00Z
regions: [eu-west-1, us-east-1]

model:
  provider: example-ai
  name: large-2026-09
  max_tokens: 8192  # hard cap per response
  temperature: 0.2
  fallbacks: [medium-2026-09, small-2026-06]

timeouts:
  connect_ms: 2500
  request_s: 120.0
  idle_s: 900  # close idle MCP sessions after 15 min

retry:
  attempts: 4
  backoff: exponential
  jitter: true
  retry_on: [429, 500, 502, 503]

routing:
  allowed_countries: [GB, IE, FR, DE, NO, SE]

prompt:
  system: |
    You are a careful code reviewer.
    Explain each finding in one sentence — cite the file and line.
    Never approve a change you have not read.

logging:
  level: info
  format: json
  redact: [GITHUB_TOKEN, SLACK_BOT_TOKEN]

budget:
  max_usd_per_day: 250.0
  alert_at: [0.5, 0.8, 0.95]

# MCP servers, started in this order
mcp_servers:
  - name: github
    command: npx
    args: [-y, "@modelcontextprotocol/server-github"]
    enabled: true
    env:
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_API_URL: https://api.github.com
  - name: filesystem
    command: npx
    args: [-y, "@modelcontextprotocol/server-filesystem", /srv/repos]
    enabled: true
    env: {}
  - name: slack
    command: uvx
    args: [mcp-server-slack]
    enabled: false  # waiting on workspace approval
    env:
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      SLACK_TEAM_ID: T0123456
'''

AGENT_JSON = '''{
  "schema_version": 3,
  "service": "review-bot",
  "environment": "production",
  "deployed_at": "2026-10-08T09:30:00Z",
  "regions": ["eu-west-1", "us-east-1"],
  "model": {
    "provider": "example-ai",
    "name": "large-2026-09",
    "max_tokens": 8192,
    "temperature": 0.2,
    "fallbacks": ["medium-2026-09", "small-2026-06"]
  },
  "timeouts": {
    "connect_ms": 2500,
    "request_s": 120.0,
    "idle_s": 900
  },
  "retry": {
    "attempts": 4,
    "backoff": "exponential",
    "jitter": true,
    "retry_on": [429, 500, 502, 503]
  },
  "routing": {
    "allowed_countries": ["GB", "IE", "FR", "DE", "NO", "SE"]
  },
  "prompt": {
    "system": "You are a careful code reviewer.\\nExplain each finding in one sentence — cite the file and line.\\nNever approve a change you have not read.\\n"
  },
  "logging": {
    "level": "info",
    "format": "json",
    "redact": ["GITHUB_TOKEN", "SLACK_BOT_TOKEN"]
  },
  "budget": {
    "max_usd_per_day": 250.0,
    "alert_at": [0.5, 0.8, 0.95]
  },
  "mcp_servers": [
    {
      "name": "github",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "enabled": true,
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}",
        "GITHUB_API_URL": "https://api.github.com"
      }
    },
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/srv/repos"],
      "enabled": true,
      "env": {}
    },
    {
      "name": "slack",
      "command": "uvx",
      "args": ["mcp-server-slack"],
      "enabled": false,
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "SLACK_TEAM_ID": "T0123456"
      }
    }
  ]
}
'''
CROSS = {"json": AGENT_JSON, "yaml": AGENT_YAML, "toml": AGENT_TOML}
CROSS_COMMENTS = ["review-bot: agent service configuration", "Owner: platform team. Reload with SIGHUP.",
                  "hard cap per response", "close idle MCP sessions after 15 min", "MCP servers, started in this order",
                  "waiting on workspace approval"]
EDIT = {"path": ["model", "max_tokens"], "value": 4096,
        "line": {"json": ('"max_tokens": 8192', '"max_tokens": 4096'), "yaml": ("max_tokens: 8192", "max_tokens: 4096"),
                 "toml": ("max_tokens = 8192", "max_tokens = 4096")}}
for _f, _t in CROSS.items():
    case(f"x_agent_{_f}", _f, f"Realistic agent config ({_f.upper()})", "the cross-format config: does every parser hear the same data?",
         _t, source="constructed for this post")
TRAP_STRINGS = ["NO", "no", "yes", "on", "off", "y", "n", "~", "null", "3.10", "1.20", "0755", "012", "22:22", "1:30:00",
                "1e3", "1_000", "0x1F", ".inf", "2001-12-14", "", "#x", "a: b", "- x", "@x", "!x", "*x", "true"]

# ----------------------------------------------------------------------------------------
# Configured defaults that explain the bomb and depth rows. Paths are inside the installed
# package (site-packages / node_modules / cargo registry / Go module cache / Go 1.27.2 source),
# line numbers as read on 2026-10-09. "none found" = no such limit located in the source.
# ----------------------------------------------------------------------------------------
LIMITS = {
    "py:pyyaml.safe_load": {"alias": "none found (aliases become shared references; yaml/composer.py has no counter)",
                            "depth": "Python recursion limit (sys.getrecursionlimit() = 1000)"},
    "py:pyyaml.CSafeLoader": {"alias": "none found (same composer contract)", "depth": "C stack (8 MiB RLIMIT_STACK) via CPython 3.14 stack protection"},
    "py:ruamel.safe": {"alias": "none found", "depth": "Python recursion limit"},
    "py:ruamel.rt": {"alias": "none found", "depth": "Python recursion limit"},
    "js:js-yaml@4": {"alias": "none found", "depth": "maxDepth 100: js-yaml4/lib/loader.js:154"},
    "js:js-yaml@5": {"alias": "maxAliases -1 (unlimited): js-yaml/dist/js-yaml.cjs.js:1567; maxTotalMergeKeys 1e4: :1566",
                     "depth": "maxDepth 100: js-yaml/dist/js-yaml.cjs.js:1830, check at :2474"},
    "js:yaml": {"alias": "maxAliasCount 100: yaml/dist/nodes/Node.js:28; check data.count * data.aliasCount > maxAliasCount: yaml/dist/nodes/Alias.js:61-66",
                "depth": "JS call stack (error code RESOURCE_EXHAUSTION)"},
    "go:yaml.v3": {"alias": "alias-ratio heuristic, >100 aliases and >1000 decodes, allowed ratio 0.99 falling to 0.10 between 400,000 and 4,000,000 decodes: gopkg.in/yaml.v3@v3.0.1/decode.go:458-491",
                   "depth": "10000 ('exceeded max depth of 10000')"},
    "go:sigs.k8s.io/yaml": {"alias": "same heuristic in go.yaml.in/yaml/v2@v2.4.2/decode.go:324-357", "depth": "10000"},
    "go:goccy/go-yaml": {"alias": "none found in decode.go", "depth": "ErrExceededMaxDepth: github.com/goccy/go-yaml@v1.19.2/error.go:18, decode.go:81"},
    "rs:serde_yaml": {"alias": "jumpcount > events.len() * 100 -> 'repetition limit exceeded': serde_yaml-0.9.34+deprecated/src/de.rs:478-481",
                      "depth": "remaining_depth 128: src/de.rs:112"},
    "rs:serde-saphyr": {"alias": "Budget defaults max_aliases 50,000, max_nodes 250,000: serde-saphyr-1.3.0/src/de/budget.rs:148-228",
                        "depth": "Budget max_depth 64: src/de/budget.rs:206-213"},
    "py:json": {"depth": "C stack (8 MiB RLIMIT_STACK) via CPython 3.14 stack protection"},
    "py:json5": {"depth": "Python recursion limit 1000 (recursive-descent parser)"},
    "js:JSON.parse": {"depth": "none found up to 100,000"}, "js:json5": {"depth": "none found up to 100,000"},
    "js:jsonc-parser": {"depth": "JS call stack (V8 default)"},
    "rs:serde_json": {"depth": "remaining_depth 128: serde_json-1.0.151/src/de.rs:63"},
    "rs:serde_json[arbitrary_precision]": {"depth": "remaining_depth 128: serde_json-1.0.151/src/de.rs:63"},
    "go:encoding/json": {"depth": "maxNestingDepth 10000: go1.27.2 src/encoding/json/scanner.go:148, jsontext/state.go:53"},
    "go:encoding/json/v2": {"depth": "maxNestingDepth 10000: go1.27.2 src/encoding/json/jsontext/state.go:53"},
    "jq": {"depth": "10000 ('Exceeds depth limit for parsing'; MAX_PARSING_DEPTH in jq's src/jv_parse.c, see json dossier)"},
    "py:tomllib": {"depth": "Python recursion limit"}, "py315:tomllib": {"depth": "Python recursion limit"},
    "py:tomli": {"depth": "MAX_INLINE_NESTING 400: tomli/_parser.py:43 (comment lines 36-42)"},
    "py:tomlkit": {"depth": "MAX_NESTING_DEPTH 100: tomlkit/parser.py:101"},
    "js:smol-toml": {"depth": "maxDepth option, default 1000: smol-toml/dist/parse.js:108"},
    "js:@iarna/toml": {"depth": "none found up to 100,000"},
    "rs:toml": {"depth": "const LIMIT: u32 = 80: toml-1.1.7+spec-1.1.0/src/de/parser/mod.rs:71"},
    "rs:toml_edit": {"depth": "const LIMIT: u32 = 80: toml_edit-0.25.16+spec-1.1.0/src/parser/mod.rs:142"},
    "go:BurntSushi/toml": {"depth": "none found up to 100,000"},
    "go:go-toml/v2": {"depth": "maxValueNesting 10000: github.com/pelletier/go-toml/v2@v2.4.3/unstable/parser.go:71"},
}

# ----------------------------------------------------------------------------------------
# Python value encoding
# ----------------------------------------------------------------------------------------
_SURR = re.compile("[\ud800-\udfff]")
_ADDR = re.compile(r"0x[0-9a-f]{6,}")


def qs(s: str) -> str:
    return _SURR.sub(lambda m: "\\u%04x" % ord(m.group()), json.dumps(s, ensure_ascii=False))


def clean_err(e: BaseException) -> str:
    return _ADDR.sub("0x…", f"{type(e).__name__}: {e}")[:MAXERR]


def ptag(v, depth=0):
    if depth > 3000:
        return "TRUNCATED:depth"
    t = type(v).__name__
    if v is None:
        return "NoneType:None"
    if isinstance(v, bool) or t == "ScalarBoolean":
        return f"{t}:{bool(v)}"
    if isinstance(v, int):
        return f"{t}:{int(v)}"
    if isinstance(v, float):
        return f"{t}:{float.__repr__(float(v))}"
    if isinstance(v, str):
        return f"{t}:{qs(str(v))}"
    if isinstance(v, dt.datetime):
        return f"{t}:{dt.datetime.isoformat(v)}"
    if isinstance(v, dt.date):
        return f"{t}:{dt.date.isoformat(v)}"
    if isinstance(v, dt.time):
        return f"{t}:{dt.time.isoformat(v)}"
    if isinstance(v, (bytes, bytearray)):
        return f"{t}:{bytes(v)!r}"
    if isinstance(v, Mapping):
        if all(isinstance(k, str) for k in v):
            return {str(k): ptag(x, depth + 1) for k, x in v.items()}
        return {"__pairs__": [[ptag(k, depth + 1), ptag(x, depth + 1)] for k, x in v.items()]}
    if isinstance(v, (list, tuple)):
        return [ptag(x, depth + 1) for x in v]
    if hasattr(v, "tag") and hasattr(v, "value"):   # ruamel TaggedScalar
        return f"{t}:{qs(str(getattr(v.tag, 'value', v.tag)))}={qs(str(v.value))}"
    return f"{t}:{_ADDR.sub('0x…', repr(v))[:300]}"


def ruamel(typ):
    """One YAML() instance per parser, reused across calls, as an application would."""
    from ruamel.yaml import YAML
    y = YAML(typ=typ)
    def load(s):
        return y.load(s)
    def load_all(s):
        return list(y.load_all(s))
    return load, load_all


def py_parsers():
    """id -> dict(format, version, call, parse, parse_all, extra). Third-party imports live here so the
    3.15 child (stdlib only) can import this file."""
    import importlib.metadata as md
    import json5
    import tomli
    import tomlkit
    import tomllib
    import yaml
    from ruamel.yaml import YAML
    pyv = platform.python_version()
    try:
        from yaml import _yaml as _libyaml
        libv = _libyaml.get_version_string()
    except Exception:  # noqa: BLE001
        libv = None
    yv = md.version("PyYAML") + (f" (bundled libyaml {libv})" if libv else " (no libyaml)")
    ry = YAML(typ="safe")
    ruamel_safe_impl = f"{type(ry.parser).__module__}.{type(ry.parser).__name__}" if hasattr(ry, "parser") else "?"
    rv = md.version("ruamel.yaml")
    P = {
        "py:json": dict(format="json", version=f"stdlib (Python {pyv})", call="json.loads(text)", parse=json.loads),
        "py:json5": dict(format="json", version=md.version("json5"), call="json5.loads(text)", parse=json5.loads),
        "py:tomllib": dict(format="toml", version=f"stdlib (Python {pyv})", call="tomllib.loads(text)", parse=tomllib.loads),
        "py:tomli": dict(format="toml", version=md.version("tomli"), call="tomli.loads(text)", parse=tomli.loads),
        "py:tomlkit": dict(format="toml", version=md.version("tomlkit"), call="tomlkit.parse(text) (values shown via .unwrap())",
                           parse=lambda s: tomlkit.parse(s), post=lambda d: d.unwrap()),
        "py:pyyaml.safe_load": dict(format="yaml", version=yv, call="yaml.safe_load(text)  [pure-Python SafeLoader]",
                                    parse=yaml.safe_load, parse_all=lambda s: list(yaml.safe_load_all(s))),
        "py:pyyaml.CSafeLoader": dict(format="yaml", version=yv, call="yaml.load(text, Loader=yaml.CSafeLoader)  [libyaml]",
                                      parse=lambda s: yaml.load(s, Loader=yaml.CSafeLoader),
                                      parse_all=lambda s: list(yaml.load_all(s, Loader=yaml.CSafeLoader))),
        "py:ruamel.safe": dict(format="yaml", version=rv, call=f"YAML(typ='safe').load(text)  [parser {ruamel_safe_impl}]",
                               parse=ruamel("safe")[0], parse_all=ruamel("safe")[1]),
        "py:ruamel.rt": dict(format="yaml", version=rv, call="YAML().load(text)  [default typ='rt', round-trip]",
                             parse=ruamel("rt")[0], parse_all=ruamel("rt")[1]),
        "py:pyyaml.full_load": dict(format="yaml", version=yv, call="yaml.full_load(text)", parse=yaml.full_load, extra=True),
        "py:pyyaml.unsafe_load": dict(format="yaml", version=yv, call="yaml.unsafe_load(text)", parse=yaml.unsafe_load, extra=True),
    }
    return P


def decode_text(b: bytes) -> str:
    # what open(path, encoding="utf-8").read() gives: a BOM survives as U+FEFF
    return b.decode("utf-8", errors="surrogateescape")


def run_py_case(p, c):
    text = decode_text(c["input"])
    stream = c["mode"] == "stream"
    if stream and "parse_all" not in p:
        return {"ok": False, "error": "n/a: no multi-document API"}
    fn = p["parse_all"] if stream else p["parse"]
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            raw = fn(text)
            v = p["post"](raw) if "post" in p else raw
        r = {"ok": True, "type": type(raw).__name__ if not stream else "list", "value": ptag(v)}
        if w:
            r["warnings"] = [_ADDR.sub("0x…", f"{x.category.__name__}: {x.message}")[:300] for x in w]
        return r
    except RecursionError as e:
        return {"ok": False, "error": "RecursionError: " + str(e)[:200]}
    except Exception as e:  # noqa: BLE001  (we record the exact exception)
        return {"ok": False, "error": clean_err(e)}


# ----------------------------------------------------------------------------------------
# children (run in a subprocess so a blow-up cannot take the harness down)
# ----------------------------------------------------------------------------------------
def nested(fmt, d):
    return ("a = " if fmt == "toml" else "") + "[" * d + "]" * d + "\n"


def py_graph_stats(root):
    memo, distinct, shared = {}, 0, False
    def count(v):
        nonlocal distinct, shared
        if isinstance(v, (Mapping, list, tuple)):
            if id(v) in memo:
                shared = True
                return memo[id(v)]
            distinct += 1
            memo[id(v)] = 0
            kids = v.values() if isinstance(v, Mapping) else v
            n = sum(count(k) for k in kids)
            memo[id(v)] = n
            return n
        return 1
    leaves = count(root)
    return dict(distinct_containers=distinct, expanded_leaf_count=leaves, shared_references=shared)


def child_main(argv):
    kind = argv[0]
    if kind == "depth":
        pid, fmt, d = argv[1], argv[2], int(argv[3])
        if pid == "py315:tomllib":
            import tomllib
            fn = tomllib.loads
        else:
            fn = py_parsers()[pid]["parse"]
        sys.setrecursionlimit(sys.getrecursionlimit())  # default, stated in _numbers.json
        try:
            fn(nested(fmt, d))
            print(json.dumps({"ok": True}))
        except RecursionError as e:
            print(json.dumps({"ok": False, "error": "RecursionError: " + str(e)[:200]}))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": clean_err(e)}))
    elif kind == "bomb":
        pid, path = argv[1], argv[2]
        text = Path(path).read_text("utf-8")
        p = py_parsers()[pid]
        t0 = time.perf_counter_ns()
        try:
            v = p["parse"](text)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": clean_err(e), "load_ms": round((time.perf_counter_ns() - t0) / 1e6, 2)}))
            return
        ms = (time.perf_counter_ns() - t0) / 1e6
        r = {"ok": True, "load_ms": round(ms, 2), **py_graph_stats(v)}
        if r["expanded_leaf_count"] <= 2_000_000:
            t1 = time.perf_counter_ns()
            s = json.dumps(v)
            r["materialized_json_bytes"] = len(s)
            r["materialize_ms"] = round((time.perf_counter_ns() - t1) / 1e6, 2)
        print(json.dumps(r))
    elif kind == "cases315":
        import tomllib
        req = json.loads(Path(argv[1]).read_text())
        out = {}
        for c in req["cases"]:
            if c["format"] != "toml" or c["mode"] != "doc":
                continue
            text = base64.b64decode(c["input_b64"]).decode("utf-8", "surrogateescape")
            try:
                v = tomllib.loads(text)
                out[c["id"]] = {"ok": True, "type": type(v).__name__, "value": ptag(v)}
            except Exception as e:  # noqa: BLE001
                out[c["id"]] = {"ok": False, "error": clean_err(e)}
        print(json.dumps({"version": platform.python_version(), "results": out}))


# ----------------------------------------------------------------------------------------
# subprocess plumbing
# ----------------------------------------------------------------------------------------
def _limit_mem():
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_MEM_BYTES, CHILD_MEM_BYTES))


def run_cmd(cmd, cwd=None, timeout=CHILD_TIMEOUT_S, limit_mem=True, inp=None, env=None):
    t0 = time.monotonic()
    try:
        cp = subprocess.run(cmd, cwd=cwd, input=inp, capture_output=True, timeout=timeout,
                            preexec_fn=_limit_mem if limit_mem else None, env=env)
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s", time.monotonic() - t0
    if cp.returncode != 0:
        tail = cp.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        sig = f"killed by signal {-cp.returncode}" if cp.returncode < 0 else f"exit {cp.returncode}"
        return None, f"{sig}: {' | '.join(tail)[:400]}", time.monotonic() - t0
    return cp.stdout, None, time.monotonic() - t0


def go_env():
    e = dict(os.environ)
    e.update(GOCACHE=str(GO_CACHE), GOTOOLCHAIN="local", GOFLAGS="-mod=mod")
    e["PATH"] = f"{GO_BIN.parent}:{e.get('PATH', '')}"
    return e


class Probe:
    """An external runtime probe: node / rust / rust-ap / go."""

    def __init__(self, name, argv_prefix, build=None, cwd=None, mem=True, env=None):
        self.name, self.argv_prefix, self.build_cmd, self.cwd, self.mem, self.env = name, argv_prefix, build, cwd, mem, env
        self.status = "unknown"

    def ensure(self):
        if self.build_cmd:
            for cmd, check in self.build_cmd:
                if check():
                    continue
                if shutil.which(cmd[0]) is None and not Path(cmd[0]).exists():
                    self.status = f"skipped: {cmd[0]} not found"
                    return False
                out, err, secs = run_cmd(cmd, cwd=self.cwd, timeout=1800, limit_mem=False, env=self.env)
                if err:
                    self.status = f"skipped: build failed ({' '.join(cmd)}): {err}"
                    return False
        exe = self.argv_prefix[0]
        if shutil.which(exe) is None and not Path(exe).exists():
            self.status = f"skipped: {exe} not found"
            return False
        self.status = "ok"
        return True

    def call(self, req_path, mode, *extra, timeout=CHILD_TIMEOUT_S):
        out, err, secs = run_cmd([*self.argv_prefix, str(req_path), mode, *map(str, extra)], cwd=self.cwd,
                                 timeout=timeout, limit_mem=self.mem, env=self.env)
        if err:
            return None, err
        return json.loads(out), None


def make_probes():
    node = shutil.which("node") or "node"
    probes = {
        "node": Probe("node", [node, "--max-old-space-size=3072", str(NODE_DIR / "probe.mjs")],
                      build=[(["npm", "ci", "--no-audit", "--no-fund"], lambda: (NODE_DIR / "node_modules").exists())],
                      cwd=NODE_DIR, mem=False),
        "rust": Probe("rust", [str(RUST_DIR / "target" / "release" / "hears_rs")],
                      build=[(["cargo", "build", "--release", "--locked"], lambda: (RUST_DIR / "target/release/hears_rs").exists())],
                      cwd=RUST_DIR),
        "rust-ap": Probe("rust-ap", [str(RUST_DIR / "target-ap" / "release" / "hears_rs")],
                         build=[(["cargo", "build", "--release", "--locked", "--features", "ap", "--target-dir", "target-ap"],
                                 lambda: (RUST_DIR / "target-ap/release/hears_rs").exists())],
                         cwd=RUST_DIR),
        "go": Probe("go", [str(GO_DIR / "hears_go")],
                    build=[([str(GO_BIN), "build", "-o", "hears_go", "."], lambda: (GO_DIR / "hears_go").exists())],
                    cwd=GO_DIR, env=go_env()),
    }
    return probes


# ----------------------------------------------------------------------------------------
# jq
# ----------------------------------------------------------------------------------------
def jq_tag(out_text):
    def conv(v):
        if isinstance(v, tuple):
            return f"jq-number:{v[1]}"
        if v is None:
            return "jq-null:null"
        if isinstance(v, bool):
            return f"jq-boolean:{str(v).lower()}"
        if isinstance(v, str):
            return f"jq-string:{qs(v)}"
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return f"jq-other:{v!r}"
    num = lambda s: ("n", s)  # noqa: E731
    return conv(json.loads(out_text, parse_int=num, parse_float=num, parse_constant=num))


def jq_case(b: bytes):
    jq = shutil.which("jq")
    cp = subprocess.run([jq, "-c", "."], input=b, capture_output=True, timeout=60)
    if cp.returncode != 0:
        return {"ok": False, "error": cp.stderr.decode("utf-8", "replace").strip()[:MAXERR]}
    out = cp.stdout.decode("utf-8", "replace").strip()
    r = {"ok": True, "type": "jq output text", "output": out}
    try:
        r["value"] = jq_tag(out)
    except Exception as e:  # noqa: BLE001
        r["value"] = f"jq-text:{qs(out)}"
        r["note"] = "output is not JSON: " + clean_err(e)
    return r


def jq_version():
    cp = subprocess.run(["jq", "--version"], capture_output=True, text=True)
    return cp.stdout.strip()


# ----------------------------------------------------------------------------------------
# normalisation: what did the parser hear, ignoring how its runtime spells types
# ----------------------------------------------------------------------------------------
STR_T = {"str", "string", "String", "jq-string", "LiteralScalarString", "FoldedScalarString", "PlainScalarString",
         "SingleQuotedScalarString", "DoubleQuotedScalarString", "ScalarString", "jq-text"}
BOOL_T = {"bool", "boolean", "Bool", "Boolean", "ScalarBoolean", "jq-boolean"}
NULL_T = {"NoneType", "null", "Null", "nil", "undefined", "jq-null", "None"}
NUM_RE = re.compile(r"^(int|float|ScalarInt|ScalarFloat|HexInt|HexCapsInt|OctalInt|BinaryInt|DecimalInt|ExponentialFloat|"
                    r"ExponentialCapsFloat|Integer\(i64\)|Float\(f64\)|Number\(.*\)|number|bigint|int64|uint64|int32|uint32|"
                    r"float64|float32|json\.Number|jq-number|Integer|Float)$")
DT_RE = re.compile(r"(date|time|Date|Time|Datetime|TimeStamp|TomlDate|LocalDate|LocalTime)", re.I)
# Leaf types that hold an IEEE-754 binary64 double. Runtimes print the same double differently (JS prints
# 12345678901234567000, Go 1.2345678901234567e+19, both for the double 12345678901234567168), so an
# integral double is rendered as the exact integer it holds. Integer types (int, int64, bigint, Number(u64),
# jq's preserved literal, ...) keep their own digits.
DOUBLE_T = {"float", "ScalarFloat", "ExponentialFloat", "ExponentialCapsFloat", "number", "float64", "float32",
            "Float(f64)", "Number(f64)"}


def split_leaf(s: str):
    # "<type>:<repr>"; type names may contain ':'? no -- but Rust 'Datetime(x)' and Go 'time.Time' do not.
    i = s.find(":")
    return (s[:i], s[i + 1:]) if i >= 0 else (s, "")


def canon_num(text: str, is_double: bool = False) -> str:
    t = text.strip()
    tl = t.lower().lstrip("+")
    if tl in ("nan", "-nan"):
        return "NaN"
    if tl in ("inf", "infinity"):
        return "Infinity"
    if tl in ("-inf", "-infinity"):
        return "-Infinity"
    if t.endswith("n") and t[:-1].lstrip("-").isdigit():   # JS bigint repr guard
        t = t[:-1]
    if t.startswith("-") and re.fullmatch(r"-0+(\.0*)?([eE][-+]?\d+)?", t):
        return "-0"   # a negative zero that survived parsing (Python int has no -0, so it never reaches here)
    if is_double:
        try:
            f = float(t)
        except ValueError:
            return t
        if math.isfinite(f) and f.is_integer():
            return str(int(f))   # exact value of the double, whatever digits the runtime printed
        return repr(f) if math.isfinite(f) else t
    try:
        return str(int(t))
    except ValueError:
        pass
    try:
        f = float(t)
    except ValueError:
        return t
    if math.isinf(f):
        return t   # an overflowing literal kept verbatim (jq, arbitrary_precision)
    if f == 0 and math.copysign(1, f) < 0:
        return "-0"
    if f.is_integer() and abs(f) < 1e16:
        return str(int(f))
    return repr(f)


def kind_of(t):
    if t in STR_T:
        return "str"
    if t in BOOL_T:
        return "bool"
    if t in NULL_T:
        return "null"
    if NUM_RE.match(t):
        return "num"
    if DT_RE.search(t):
        return "dt"
    return "other"


def norm(v, order=False, dt_mode="keep"):
    """Compact JSON-like rendering of a tagged value tree. dt_mode='instant' maps date-times (typed or string)
    to a UTC instant for the cross-format equivalence check."""
    if isinstance(v, list):
        return "[" + ",".join(norm(x, order, dt_mode) for x in v) + "]"
    if isinstance(v, dict):
        if "__pairs__" in v and len(v) == 1:
            items = [(norm(k, order, dt_mode), norm(x, order, dt_mode)) for k, x in v["__pairs__"]]
        elif "__set__" in v and len(v) == 1:
            return "set" + norm(v["__set__"], order, dt_mode)
        else:
            items = [(qs(k), norm(x, order, dt_mode)) for k, x in v.items()]
        if not order:
            items.sort()
        return "{" + ",".join(f"{k}:{x}" for k, x in items) + "}"
    if not isinstance(v, str):
        return f"<?{v!r}>"
    t, r = split_leaf(v)
    k = kind_of(t)
    if k == "str":
        try:
            s = json.loads(r)
        except json.JSONDecodeError:
            s = r
        if dt_mode == "instant":
            inst = as_instant(s)
            if inst:
                return f"<instant {inst}>"
        return qs(s) if isinstance(s, str) else r
    if k == "bool":
        return "true" if r.strip().lower() in ("true", "1") else "false"
    if k == "null":
        return "null"
    if k == "num":
        return canon_num(r, t in DOUBLE_T)
    if k == "dt":
        if dt_mode == "instant":
            inst = as_instant(r.split(" (loc=")[0].split(" {")[0])
            if inst:
                return f"<instant {inst}>"
        return f"<{t} {r}>"
    return f"<{t} {r}>"


def as_instant(s):
    if not isinstance(s, str) or not re.match(r"^\d{4}-\d\d-\d\d[T ]\d\d:\d\d", s):
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0").rstrip(".") + "Z"


def result_heard(r, order=False, dt_mode="keep"):
    if not r.get("ok"):
        e = r.get("error", "")
        if e.startswith("n/a"):
            return "n/a"
        return "ERROR"
    return norm(r["value"], order, dt_mode)


# ----------------------------------------------------------------------------------------
# round-trip analysis
# ----------------------------------------------------------------------------------------
def key_paths(v, prefix=()):
    out = []
    if isinstance(v, Mapping):
        for k, x in v.items():
            out.append(prefix + (str(k),))
            out += key_paths(x, prefix + (str(k),))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            out += key_paths(x, prefix + (str(i),))
    return out


def readers_for(rid, fmt):
    """The readers a round-trip output is checked with."""
    import json5
    import tomllib
    import yaml
    if fmt == "json":
        return [("json5", json5.loads)] if "json5" in rid else [("json", json.loads)]
    if fmt == "toml":
        return [("tomllib", tomllib.loads)]
    return [("yaml1.2", ruamel("safe")[0]), ("yaml1.1", yaml.safe_load)]


def intended():
    d = json.loads(AGENT_JSON)
    d[EDIT["path"][0]][EDIT["path"][1]] = EDIT["value"]
    return d


def analyse_roundtrip(rid, fmt, output, core=None):
    orig = CROSS[fmt]
    old, new = EDIT["line"][fmt]
    expected = orig.replace(old, new, 1)
    exp_lines, out_lines = expected.splitlines(keepends=True), output.splitlines(keepends=True)
    diff = [ln for ln in difflib.unified_diff(exp_lines, out_lines, n=0) if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    want = norm(ptag(intended()), dt_mode="instant")
    a = {"bytes": len(output.encode("utf-8")), "lines": output.count("\n"), "byte_identical_to_hand_edit": output == expected,
         "diff_lines_vs_hand_edit": len(diff), "hears_as_intended": {}, "same_as_hand_edit_for_reader": {}}
    first = None
    for name, fn in readers_for(rid, fmt):
        try:
            got = fn(output)
            first = got if first is None else first
            a["hears_as_intended"][name] = norm(ptag(got), dt_mode="instant") == want
            a["same_as_hand_edit_for_reader"][name] = norm(ptag(got), dt_mode="instant") == norm(ptag(fn(expected)), dt_mode="instant")
        except Exception as e:  # noqa: BLE001
            a["hears_as_intended"][name] = False
            a.setdefault("reread_errors", {})[name] = clean_err(e)
    if fmt == "yaml" and core is not None:
        if core.get("ok"):
            a["hears_as_intended"]["yaml1.2core"] = norm(core["value"], dt_mode="instant") == want
        else:
            a["hears_as_intended"]["yaml1.2core"] = False
            a.setdefault("reread_errors", {})["yaml1.2core"] = core.get("error")
    if first is not None:
        ref_paths = key_paths(intended())
        a["key_order_preserved"] = key_paths(first) == ref_paths
        top_out, top_in = [p[0] for p in key_paths(first) if len(p) == 1], [p[0] for p in ref_paths if len(p) == 1]
        a["top_level_keys_sorted"] = top_out == sorted(top_out) and top_in != sorted(top_in)
    if fmt in ("yaml", "toml"):
        a["comments_kept"] = f"{sum(c in output for c in CROSS_COMMENTS)}/{len(CROSS_COMMENTS)}"
        a["comments_lost"] = [c for c in CROSS_COMMENTS if c not in output]
    a["em_dash_escaped"] = "\u2014" not in output and ("\\u2014" in output or "\\u2014".upper() in output)
    a["diff_vs_hand_edit"] = "".join(diff)[:4000]
    return a


def py_roundtrips():
    import json5
    import tomlkit
    import yaml
    from ruamel.yaml import YAML
    path, val = EDIT["path"], EDIT["value"]
    R = {}

    def put(rid, fmt, how, fn):
        try:
            R[rid] = {"format": fmt, "how": how, "ok": True, "output": fn()}
        except Exception as e:  # noqa: BLE001
            R[rid] = {"format": fmt, "how": how, "ok": False, "error": clean_err(e)}

    def edited(d):
        d[path[0]][path[1]] = val
        return d

    put("py:json.dumps", "json", "json.dumps(edit(json.loads(t)), indent=2) + '\\n'",
        lambda: json.dumps(edited(json.loads(AGENT_JSON)), indent=2) + "\n")
    put("py:json.dumps(ensure_ascii=False)", "json", "json.dumps(edit(json.loads(t)), indent=2, ensure_ascii=False) + '\\n'",
        lambda: json.dumps(edited(json.loads(AGENT_JSON)), indent=2, ensure_ascii=False) + "\n")
    put("py:json5.dumps", "json", "json5.dumps(edit(json5.loads(t)), indent=2) + '\\n'",
        lambda: json5.dumps(edited(json5.loads(AGENT_JSON)), indent=2) + "\n")
    put("py:pyyaml.safe_dump", "yaml", "yaml.safe_dump(edit(yaml.safe_load(t)))  [defaults]",
        lambda: yaml.safe_dump(edited(yaml.safe_load(AGENT_YAML))))
    put("py:pyyaml.safe_dump(sort_keys=False)", "yaml", "yaml.safe_dump(edit(yaml.safe_load(t)), sort_keys=False, allow_unicode=True)",
        lambda: yaml.safe_dump(edited(yaml.safe_load(AGENT_YAML)), sort_keys=False, allow_unicode=True))

    def ruamel_rt(configure):
        y = YAML()
        if configure:
            y.indent(mapping=2, sequence=4, offset=2)
            y.width = 4096
        d = y.load(AGENT_YAML)
        edited(d)
        buf = io.StringIO()
        y.dump(d, buf)
        return buf.getvalue()
    put("py:ruamel.rt", "yaml", "YAML().load -> edit -> YAML().dump  [defaults]", lambda: ruamel_rt(False))
    put("py:ruamel.rt(indent 2/4/2)", "yaml", "same, with y.indent(mapping=2, sequence=4, offset=2); y.width=4096", lambda: ruamel_rt(True))

    def ruamel_safe():
        y = YAML(typ="safe")
        d = edited(y.load(AGENT_YAML))
        buf = io.StringIO()
        y.dump(d, buf)
        return buf.getvalue()
    put("py:ruamel.safe", "yaml", "YAML(typ='safe').load -> edit -> dump", ruamel_safe)

    def tk():
        d = tomlkit.parse(AGENT_TOML)
        d[path[0]][path[1]] = val
        return tomlkit.dumps(d)
    put("py:tomlkit", "toml", "tomlkit.parse -> doc[a][b] = v -> tomlkit.dumps", tk)

    E = {}
    for s in TRAP_STRINGS:
        def em(eid, fn):
            try:
                E.setdefault(eid, {})[s] = {"ok": True, "output": fn()}
            except Exception as e:  # noqa: BLE001
                E.setdefault(eid, {})[s] = {"ok": False, "error": clean_err(e)}
        em("py:pyyaml.safe_dump", lambda: yaml.safe_dump({"v": s}))

        def rdump(typ):
            y = YAML(typ=typ)
            buf = io.StringIO()
            y.dump({"v": s}, buf)
            return buf.getvalue()
        em("py:ruamel.rt.dump", lambda: rdump("rt"))
        em("py:ruamel.safe.dump", lambda: rdump("safe"))
    return R, E


def analyse_emitters(E, core=None):
    """For each YAML emitter and trap string: does the written text read back as the same string
    under a YAML 1.1 reader (PyYAML safe_load) and a YAML 1.2 reader (ruamel safe)?"""
    import tomllib
    import yaml
    out = {}
    for eid, rows in sorted(E.items()):
        is_toml = "toml" in eid
        res = {}
        for s, r in rows.items():
            if not r.get("ok"):
                res[s] = {"error": r["error"]}
                continue
            o = r["output"]
            row = {"output": o}
            if is_toml:
                try:
                    row["reads_back_as_string"] = tomllib.loads(o).get("v") == s
                except Exception as e:  # noqa: BLE001
                    row["reread_error"] = clean_err(e)
            else:
                c = (core or {}).get(f"emit|{eid}|{s}")
                if c is not None:
                    want = norm({"v": f"str:{qs(s)}"})
                    row["yaml1.2core_reads"] = norm(c["value"]["v"]) if c.get("ok") and isinstance(c["value"], dict) and "v" in c["value"] else ("ERROR: " + str(c.get("error"))[:120] if not c.get("ok") else norm(c["value"]))
                    row["yaml1.2core_same_string"] = bool(c.get("ok")) and isinstance(c["value"], dict) and norm(c["value"]) == want
                for rname, fn in (("yaml1.1", yaml.safe_load), ("yaml1.2", ruamel("safe")[0])):
                    try:
                        got = fn(o)
                        gv = got.get("v") if isinstance(got, Mapping) else got
                        row[f"{rname}_reads"] = norm(ptag(gv))
                        row[f"{rname}_same_string"] = gv == s and isinstance(gv, str)
                    except Exception as e:  # noqa: BLE001
                        row[f"{rname}_reads"] = "ERROR: " + clean_err(e)[:120]
                        row[f"{rname}_same_string"] = False
            res[s] = row
        summary = {}
        if not is_toml:
            summary["retyped_by_yaml1.1_reader"] = [s for s, x in res.items() if x.get("yaml1.1_same_string") is False]
            summary["retyped_by_yaml1.2_reader"] = [s for s, x in res.items() if x.get("yaml1.2_same_string") is False]
            summary["retyped_by_yaml1.2core_reader"] = [s for s, x in res.items() if x.get("yaml1.2core_same_string") is False]
        out[eid] = {"summary": summary, "strings": res}
    return out


# ----------------------------------------------------------------------------------------
# timing (Python side)
# ----------------------------------------------------------------------------------------
def time_py(P):
    out = {}
    for pid, p in sorted(P.items()):
        if p.get("extra"):
            continue
        text = CROSS[p["format"]]
        fn = p["parse"]
        for _ in range(TIMING_WARMUP):
            fn(text)
        ts = []
        for _ in range(TIMING_REPEATS):
            t0 = time.perf_counter_ns()
            fn(text)
            ts.append(time.perf_counter_ns() - t0)
        ts.sort()
        q = lambda f: ts[min(len(ts) - 1, int(f * (len(ts) - 1) + 0.5))]  # noqa: E731
        out[pid] = {"format": p["format"], "n": TIMING_REPEATS, "warmup": TIMING_WARMUP, "median_ns": q(0.5),
                    "p10_ns": q(0.1), "p90_ns": q(0.9), "min_ns": ts[0]}
    return out


def contention_snapshot():
    """cgroup v2 cpu.stat counters + load average. The parsers are timed one at a time on one thread (Go and V8
    GC helper threads add a little), so the timing phase alone uses about one CPU of the 2-CPU quota: a large
    throttled fraction, or CPU use well above the wall time, means other processes in the same cgroup were
    competing for the CPU and the medians from that run carry their noise."""
    s = {"t": time.monotonic()}
    try:
        for ln in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines():
            k, v = ln.split()
            if k in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec"):
                s[k] = int(v)
    except (OSError, ValueError):
        pass
    try:
        s["loadavg_1m"] = float(Path("/proc/loadavg").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return s


def contention_delta(a, b):
    wall = b["t"] - a["t"]
    out = {"timing_phase_wall_s": round(wall, 1), "loadavg_1m_before": a.get("loadavg_1m"),
           "loadavg_1m_after": b.get("loadavg_1m")}
    if "nr_periods" in a and "nr_periods" in b:
        periods = b["nr_periods"] - a["nr_periods"]
        throttled = b["nr_throttled"] - a["nr_throttled"]
        out.update({"cgroup_periods": periods, "cgroup_throttled_periods": throttled,
                    "cgroup_throttled_fraction": round(throttled / periods, 3) if periods else None,
                    "cgroup_cpu_used_s": round((b["usage_usec"] - a["usage_usec"]) / 1e6, 1),
                    "note": "the parsers are timed one at a time on one thread (about 1 CPU of the cgroup's "
                            "2-CPU quota, plus GC helper threads in Go and V8); cgroup_cpu_used_s well above "
                            "timing_phase_wall_s, or a large throttled fraction, means other processes in the "
                            "cgroup shared the CPU while the medians were taken"})
    return out


def sig3(x):
    if not x:
        return x
    return float(f"{x:.3g}") if not float(f"{x:.3g}").is_integer() else int(float(f"{x:.3g}"))


# ----------------------------------------------------------------------------------------
# machine
# ----------------------------------------------------------------------------------------
def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=go_env()).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def machine_info():
    cpu = None
    try:
        for ln in Path("/proc/cpuinfo").read_text().splitlines():
            if ln.startswith("model name"):
                cpu = ln.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem = None
    try:
        mem = Path("/proc/meminfo").read_text().splitlines()[0].split(":")[1].strip()
    except OSError:
        pass
    return {
        "date_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "os": f"{platform.system()} {platform.release()}", "arch": platform.machine(), "cpu": cpu,
        "cpus_host": os.cpu_count(), "cpus_affinity": len(os.sched_getaffinity(0)),
        "cgroup_cpu_max": (Path("/sys/fs/cgroup/cpu.max").read_text().strip() if Path("/sys/fs/cgroup/cpu.max").exists() else None),
        "mem_total": mem,
        "python": platform.python_version(), "python_impl": platform.python_implementation(),
        "node": sh(["node", "--version"]), "rustc": sh(["rustc", "--version"]), "cargo": sh(["cargo", "--version"]),
        "go": sh([str(GO_BIN), "version"]), "jq": jq_version(), "uv": sh(["uv", "--version"]),
        "py315": sh([str(PY315), "--version"]) if PY315.exists() else None,
        "python_recursion_limit": sys.getrecursionlimit(),
        "stack_rlimit_kib": (lambda r: r if r < 0 else r // 1024)(resource.getrlimit(resource.RLIMIT_STACK)[0]),
    }


# ----------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------
def depth_search(test, cap=DEPTH_CAP):
    ok, err = test(cap)
    if ok:
        return {"max_ok_depth": cap, "limit": f"none found up to the cap of {cap}"}
    ok1, err1 = test(1)
    if not ok1:
        return {"max_ok_depth": 0, "error_at_depth_1": err1}
    lo, hi, hi_err = 1, cap, err
    while hi - lo > 1:
        mid = (lo + hi) // 2
        ok, e = test(mid)
        if ok:
            lo = mid
        else:
            hi, hi_err = mid, e
    return {"max_ok_depth": lo, "first_failing_depth": hi, "error_at_first_failing_depth": hi_err}


def write_cases_mirror():
    ext = {"yaml": "yaml", "json": "json", "toml": "toml"}
    if CASES_DIR.exists():
        shutil.rmtree(CASES_DIR)
    for c in CASES:
        if c["mode"] == "depth":
            continue
        sub = "cross" if c["id"].startswith("x_") else c["format"]
        d = CASES_DIR / sub
        d.mkdir(parents=True, exist_ok=True)
        name = c["id"][2:] if not c["id"].startswith("x_") else c["id"][2:].rsplit("_", 1)[0]
        (d / f"{name}.{ext[c['format']]}").write_bytes(c["input"])


def main():
    t_start = time.monotonic()
    P = py_parsers()
    probes = make_probes()
    req = {
        "cases": [{"id": c["id"], "format": c["format"], "mode": c["mode"], "input_b64": base64.b64encode(c["input"]).decode()}
                  for c in CASES],
        "cross": {"repeats": TIMING_REPEATS, "warmup": TIMING_WARMUP,
                  "files": {k: base64.b64encode(v.encode()).decode() for k, v in CROSS.items()}},
        "roundtrip": {"files": {k: base64.b64encode(v.encode()).decode() for k, v in CROSS.items()},
                      "edit": {"path": EDIT["path"], "value": EDIT["value"]}, "trap_strings": TRAP_STRINGS},
    }
    tmpdir = Path(tempfile.mkdtemp(prefix="hears-"))
    req_path = tmpdir / "request.json"
    req_path.write_text(json.dumps(req))

    parsers_meta, versions, results, skipped = {}, {}, {}, {}
    for pid, p in P.items():
        parsers_meta[pid] = {"runtime": f"python {platform.python_version()}", "format": p["format"], "version": p["version"],
                             "call": p["call"], **({"runs_only_on": "cases that list it"} if p.get("extra") else {})}
        versions[pid] = p["version"]

    # --- Python, in process
    log("python cases")
    for pid, p in P.items():
        results[pid] = {}
        for c in CASES:
            if c["format"] != p["format"] or c["mode"] in ("bomb", "depth"):
                continue
            if p.get("extra") and pid not in c["extra"]:
                continue
            results[pid][c["id"]] = run_py_case(p, c)

    # --- Python 3.15 tomllib (release candidate)
    if PY315.exists():
        out, err, _ = run_cmd([str(PY315), str(Path(__file__).resolve()), "--child", "cases315", str(req_path)])
        if err:
            skipped["py315:tomllib"] = err
        else:
            o = json.loads(out)
            pid = "py315:tomllib"
            results[pid] = o["results"]
            versions[pid] = f"stdlib (Python {o['version']}, release candidate)"
            parsers_meta[pid] = {"runtime": f"python {o['version']}", "format": "toml", "version": versions[pid],
                                 "call": "tomllib.loads(text)"}
    else:
        skipped["py315:tomllib"] = f"skipped: {PY315} not found"

    # --- jq
    if shutil.which("jq"):
        pid = "jq"
        versions[pid] = jq_version()
        parsers_meta[pid] = {"runtime": "jq", "format": "json", "version": versions[pid], "call": "jq -c . < input (bytes on stdin)"}
        results[pid] = {c["id"]: jq_case(c["input"]) for c in CASES if c["format"] == "json" and c["mode"] == "doc"}
    else:
        skipped["jq"] = "skipped: jq not found"

    # --- external probes
    live = {}
    for name, pr in probes.items():
        log(f"probe {name}")
        if not pr.ensure():
            skipped[name] = pr.status
            continue
        o, err = pr.call(req_path, "cases")
        if err:
            skipped[name] = f"skipped: cases run failed: {err}"
            continue
        live[name] = pr
        for pid, meta in o["parsers"].items():
            parsers_meta[pid] = {"runtime": o.get("runtime"), **meta}
            versions[pid] = meta["version"]
        for pid, rs in o["results"].items():
            if pid == "go:encoding/json/v2":
                # Go 1.27's json/v2 picks "cannot" or "unable to" at random once per process, on purpose
                # (src/encoding/json/v2/errors.go:322-333). Mark the token so reruns diff cleanly.
                for r in rs.values():
                    if "error" in r:
                        r["error"] = re.sub(r"\b(cannot|unable to)\b", "{cannot|unable to}", r["error"], count=1)
            results[pid] = rs

    # --- bomb
    log("bomb")
    bomb = {}
    for c in [c for c in CASES if c["mode"] == "bomb"]:
        bpath = tmpdir / f"{c['id']}.yaml"
        bpath.write_bytes(c["input"])
        row = {}
        for pid, p in P.items():
            if p["format"] != "yaml" or p.get("extra"):
                continue
            out, err, secs = run_cmd([sys.executable, str(Path(__file__).resolve()), "--child", "bomb", pid, str(bpath)])
            row[pid] = json.loads(out) if not err else {"ok": False, "error": f"child process: {err}", "wall_s": round(secs, 1)}
        for name in ("node", "rust", "go"):
            if name not in live:
                continue
            o, err = live[name].call(req_path, "bomb", c["id"])
            if err:
                for pid, meta in parsers_meta.items():
                    if meta.get("runtime", "").startswith(name) and meta["format"] == "yaml":
                        row[pid] = {"ok": False, "error": f"probe process: {err}"}
                continue
            row.update(o["bomb"].get(c["id"], {}))
        bomb[c["id"]] = dict(sorted(row.items()))

    # --- depth
    log("depth")
    depth = {}
    for c in [c for c in CASES if c["mode"] == "depth"]:
        fmt = c["format"]
        row = {}
        pids = [pid for pid, p in P.items() if p["format"] == fmt and not p.get("extra")]
        if fmt == "toml" and PY315.exists():
            pids.append("py315:tomllib")
        for pid in pids:
            exe = str(PY315) if pid.startswith("py315") else sys.executable

            def test(d, pid=pid, exe=exe):
                out, err, _ = run_cmd([exe, str(Path(__file__).resolve()), "--child", "depth", pid, fmt, str(d)], timeout=120)
                if err:
                    return False, "child process: " + err
                r = json.loads(out)
                return r["ok"], r.get("error")
            row[pid] = depth_search(test)
        for name, pr in live.items():
            pids_ext = [pid for pid, m in parsers_meta.items() if m.get("format") == fmt and
                        pid.startswith({"node": "js:", "rust": "rs:", "rust-ap": "rs:", "go": "go:"}[name])]
            for pid in pids_ext:
                if name == "rust" and "arbitrary" in pid or name == "rust-ap" and "arbitrary" not in pid:
                    continue

                def test(d, pr=pr, pid=pid):
                    o, err = pr.call(req_path, "depth1", pid, fmt, d, timeout=120)
                    if err:
                        return False, "probe process: " + err
                    return o["depth1"]["ok"], o["depth1"].get("error")
                row[pid] = depth_search(test)
        if fmt == "json" and shutil.which("jq"):
            def test(d):
                cp = subprocess.run(["jq", "-c", "length"], input=nested("json", d).encode(), capture_output=True, timeout=120)
                return cp.returncode == 0, cp.stderr.decode("utf-8", "replace").strip()[:MAXERR] or None
            row["jq"] = depth_search(test)
        depth[c["id"]] = dict(sorted(row.items()))

    # --- timing
    log("timing")
    contention_before = contention_snapshot()
    timing = time_py(P)
    for name, pr in live.items():
        o, err = pr.call(req_path, "timing", timeout=900)
        if err:
            skipped[f"{name}:timing"] = err
            continue
        timing.update(o["timing"])
    timing_contention = contention_delta(contention_before, contention_snapshot())
    for t in timing.values():
        for k in ("median_ns", "p10_ns", "p90_ns", "min_ns"):
            t[k] = sig3(t[k])
        t["median_us"] = sig3(t["median_ns"] / 1000)

    # --- round trip + emitters
    log("roundtrip")
    rt, emit = py_roundtrips()
    for name, pr in live.items():
        o, err = pr.call(req_path, "roundtrip")
        if err:
            skipped[f"{name}:roundtrip"] = err
            continue
        rt.update(o.get("roundtrip", {}))
        for eid, rows in o.get("emit", {}).items():
            emit.setdefault(eid, {}).update(rows)
    # re-read every YAML output with eemeli yaml (strict YAML 1.2 core schema) in the Node probe
    core = {}
    if "node" in live:
        rr = [{"id": f"rt|{rid}", "text_b64": base64.b64encode(r["output"].encode()).decode()}
              for rid, r in rt.items() if r["ok"] and r["format"] == "yaml"]
        rr += [{"id": f"emit|{eid}|{s}", "text_b64": base64.b64encode(x["output"].encode()).decode()}
               for eid, rows in emit.items() if "toml" not in eid for s, x in rows.items() if x.get("ok")]
        rr_path = tmpdir / "reread.json"
        rr_path.write_text(json.dumps({"cases": [], "reread": rr}))
        o, err = live["node"].call(rr_path, "reread")
        if err:
            skipped["node:reread"] = err
        else:
            core = o["reread"]
    rt_out = {}
    for rid, r in sorted(rt.items()):
        row = {k: r[k] for k in ("format", "how", "ok")}
        if r["ok"]:
            row.update(analyse_roundtrip(rid, r["format"], r["output"], core.get(f"rt|{rid}") if core else None))
            row["output_sha256"] = hashlib.sha256(r["output"].encode()).hexdigest()[:16]
        else:
            row["error"] = r["error"]
        rt_out[rid] = row
    emit_out = analyse_emitters(emit, core)

    # --- assemble cases
    case_rows = []
    for c in CASES:
        row = {"id": c["id"], "format": c["format"], "title": c["title"], "trap": c["trap"], "source": c["source"],
               "mode": c["mode"]}
        if c["mode"] == "depth":
            row["input"] = None
            row["generator"] = ("'a = ' + " if c["format"] == "toml" else "") + "'[' * d + ']' * d + '\\n', d searched by bisection in [1, %d]" % DEPTH_CAP
            row["results"] = depth[c["id"]]
        else:
            row["input"] = decode_text(c["input"])
            row["input_bytes"] = len(c["input"])
            row["input_sha256"] = hashlib.sha256(c["input"]).hexdigest()[:16]
            if c["mode"] == "bomb":
                row["results"] = bomb[c["id"]]
            else:
                rs = {pid: results[pid][c["id"]] for pid in sorted(results) if c["id"] in results[pid]}
                row["results"] = rs
                groups = {}
                for pid, r in rs.items():
                    groups.setdefault(result_heard(r, c["order_matters"]), []).append(pid)
                row["heard"] = [{"repr": k, "parsers": v} for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
        case_rows.append(row)

    # --- cross-format equivalence (every parser vs the JSON reference read by py:json)
    ref = norm(results["py:json"]["x_agent_json"]["value"], dt_mode="instant")
    equiv = {}
    for fmt in ("json", "yaml", "toml"):
        for pid in sorted(results):
            r = results[pid].get(f"x_agent_{fmt}")
            if r is None:
                continue
            if not r.get("ok"):
                equiv[pid] = {"format": fmt, "equivalent": False, "error": r.get("error", "")[:200]}
                continue
            got = norm(r["value"], dt_mode="instant")
            e = {"format": fmt, "equivalent": got == ref}
            if got != ref:
                e["differs"] = first_diffs(ref, got)
            equiv[pid] = e

    numbers = {
        "about": {"title": "What the Parser Hears — measured pitfall matrix",
                  "harness": "_compute.py (uv run _compute.py)", "probes": str(HEARS),
                  "as_of": "2026-10-08 (package versions pinned to what was current on that date)",
                  "value_encoding": __doc__.split("Value encoding in results:")[1].strip(),
                  "heard": "per case, parsers grouped by what they heard: types normalised (str/bool/num/null), numbers canonical "
                           "(1000.0 == 1000; an integral IEEE double is shown as the exact integer it holds, so JS's "
                           "12345678901234567000 and Go's 1.2345678901234567e+19 are both 12345678901234567168), map keys "
                           "sorted unless order is the point of the case; date-times keep their native type",
                  "text_decoding": "Python: bytes.decode('utf-8') (keeps a BOM); Node: Buffer.toString('utf8') == readFileSync(p,'utf8') "
                                   "(keeps a BOM); Rust: String::from_utf8 (keeps a BOM); Go and jq: raw bytes",
                  "nondeterminism": "timings, bomb load_ms and the C-stack-bound depth limits (py:json, py:pyyaml.CSafeLoader) "
                                    "vary between runs; go:encoding/json/v2 error text picks 'cannot' or 'unable to' at random "
                                    "per process by design (Go 1.27.2 src/encoding/json/v2/errors.go:322-333) and is recorded "
                                    "as '{cannot|unable to}'",
                  "skipped": skipped},
        "machine": machine_info(),
        "versions": dict(sorted(versions.items())),
        "parsers": dict(sorted(parsers_meta.items())),
        "cases": case_rows,
        "limits": LIMITS,
        "cross_format": {
            "files": {f: {"bytes": len(t.encode()), "lines": t.count("\n"), "path": f"_cases/cross/agent.{f}"} for f, t in CROSS.items()},
            "timing_method": f"median of {TIMING_REPEATS} parses after {TIMING_WARMUP} warm-up parses, in process, monotonic clock "
                             "(Python perf_counter_ns, Node hrtime.bigint, Rust Instant, Go time.Now); parse only, default "
                             "options, untyped target; 3 significant digits; GC left on; jq not timed (process start dominates)",
            "timing": dict(sorted(timing.items())),
            "timing_contention": timing_contention,
            "equivalence_reference": "py:json reading agent.json; date-times compared as UTC instants, numbers canonically",
            "equivalence": equiv,
        },
        "roundtrip": {
            "edit": {"path": EDIT["path"], "from": 8192, "to": EDIT["value"]},
            "method": "load -> set model.max_tokens = 4096 -> dump, compared with the original file edited by hand on that one "
                      "line (diff_lines counts +/- lines of a unified diff against that hand edit). The output is re-read: "
                      "json -> py json (json5 output -> json5), toml -> tomllib, yaml -> 'yaml1.2' = ruamel.yaml safe (1.2 "
                      "resolver; note it still resolves timestamps and 1_000), 'yaml1.2core' = eemeli yaml 2.9.1 parse "
                      "(YAML 1.2 core schema, run in the Node probe) and 'yaml1.1' = PyYAML safe_load. "
                      "hears_as_intended: the re-read data equals agent.json with the edit (what the author meant; "
                      "date-times compared as instants). same_as_hand_edit_for_reader: the reader hears the same thing in "
                      "the output as in the hand-edited original. key_order_preserved compares every key path in order.",
            "results": rt_out,
            "emitters": {"method": "dump {v: s} for each trap string with default options; re-read with PyYAML 6.0.3 safe_load "
                                    "('yaml1.1'), ruamel.yaml 0.19.1 YAML(typ='safe') ('yaml1.2'; resolves timestamps and "
                                    "1_000 too) and eemeli yaml 2.9.1 parse ('yaml1.2core', strict core schema); a string "
                                    "'retyped' by a reader comes back as something other than the same string",
                         "results": emit_out},
        },
        "runtime_seconds": None,
    }
    numbers["runtime_seconds"] = round(time.monotonic() - t_start)
    OUT_JSON.write_text(json.dumps(numbers, indent=1, ensure_ascii=True) + "\n")
    write_cases_mirror()
    shutil.rmtree(tmpdir, ignore_errors=True)
    log(f"wrote {OUT_JSON} in {numbers['runtime_seconds']} s")


def first_diffs(a: str, b: str, ctx=60):
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return {"at_char": i, "reference": a[max(0, i - ctx): i + ctx], "parser": b[max(0, i - ctx): i + ctx]}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child_main(sys.argv[2:])
    else:
        main()
