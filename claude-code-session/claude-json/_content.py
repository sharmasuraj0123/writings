"""Content for the ~/.claude.json explorer. Rendered by
tools/build-claude-json-explorer.py into one index.html per folder.

Rules this file follows:
- Structure (key names, types, presence counts) was measured on one real
  ~/.claude.json on 28 September 2026. No value from that file appears here.
- Keys that are data (paths, UUIDs, skill, plugin, tool, model, flag and
  server names) never appear; a map gets one placeholder folder instead,
  written <like-this>.
- Meanings come from the Claude Code 2.1.280 binary and Anthropic's docs.
  Badges: "docs", "binary", "inferred".
- No em or en dashes anywhere.
"""

import re

POST_TITLE = "Anatomy of a Claude Code session"
KICKER = "Claude Code 2.1.280 · ~/.claude.json"
SAMPLE = "one real <code>~/.claude.json</code>, read on 28 September 2026"
FOOTNOTE = (
    "Key names, types and presence counts were measured on one real "
    "<code>~/.claude.json</code> (82 top-level keys, 72 project entries) on 28 "
    "September 2026; no value from that file is published here, and keys that "
    "are data (paths, UUIDs, names) are replaced by placeholders. Meanings are "
    "read from the Claude Code 2.1.280 binary <span class=\"src\">binary</span>, "
    "from Anthropic's documentation <span class=\"src\">docs</span>, or inferred "
    "from names and nearby code <span class=\"recon\">inferred</span>. Undocumented "
    "keys can change in any release."
)


def L(key, type, meaning, notes="", badge="binary", presence="", placeholder=False):
    """A leaf row: explained on its parent's page."""
    return dict(key=key, type=type, meaning=meaning, notes=notes, badge=badge,
                presence=presence, placeholder=placeholder)


def N(key, type, summary, *, folder=None, lede="", groups=(), chips=(), before=(),
      after=(), badge="binary", presence="", placeholder=False, notes="",
      tree_label="", **kw):
    """A folder row: an object entry that gets its own page."""
    if not folder:
        folder = "each-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") if placeholder else key
    d = dict(key=key, type=type, summary=summary, folder=folder,
             lede=lede, groups=list(groups), chips=list(chips), before=list(before),
             after=list(after), badge=badge, presence=presence, placeholder=placeholder,
             notes=notes, tree_label=tree_label, node=True)
    d.update(kw)
    return d


def G(title, rows, intro="", id=None, key_col="Key", count=True):
    return dict(title=title, rows=list(rows), intro=intro, id=id, key_col=key_col, count=count)


def P(title, html, id=None, tree=False):
    """A prose block."""
    return dict(title=title, html=html, id=id, tree=tree)


def path_label(trail, node):
    """projects[<project path>].lastModelUsage[<model id>] style path."""
    parts = list(trail[1:]) + ([node] if trail else [])
    if not parts:
        return "~/.claude.json"
    out = ""
    for p in parts:
        if p.get("placeholder"):
            out += f"[<{p['key']}>]"
        else:
            out += ("." if out else "") + p["key"]
    return out


ROOT = None  # filled in below


# ---------------------------------------------------------------------------
# projects[<project path>]
# ---------------------------------------------------------------------------

MCP_SERVER_ROWS = None  # filled in by the mcpServers section below

STAT_WRITTEN = (
    "Written when an interactive session ends (or synchronously at exit), when "
    "another conversation is resumed or forked in the session, and when "
    "<code>/clear</code> resets it; each write replaces the last."
)

LAST_MODEL_USAGE = N(
    "lastModelUsage", "object · map",
    "Tokens and estimated cost of the last session, per model.",
    presence="in 11 of 72",
    chips=["object", "map keyed by model id", "11 of 72 project entries"],
    lede=(
        "One entry per model the last session called, keyed by the model id. "
        "Written with the other <code>last*</code> stats and, like them, read "
        "only by the next startup's analytics event: the flat totals and the "
        "cost of each model go into it, nothing else reads this map."
    ),
    groups=[G("Entries", [
        N("model id", "object", "Token counts and estimated cost for one model in the last session.",
          folder="each-model", placeholder=True,
          chips=["object", "6 fields in the sample; 2.1.280 writes 7"],
          lede=(
              "The per-model usage record. The sample's records have six fields; "
              "2.1.280 also writes <code>thinkingTokens</code> when the model "
              "produced any, and no sampled record has it, which dates them to "
              "earlier releases."
          ),
          groups=[G("Fields", [
              L("inputTokens", "int", "Uncached input tokens."),
              L("outputTokens", "int", "Output tokens, thinking included."),
              L("cacheReadInputTokens", "int", "Input tokens read from the prompt cache."),
              L("cacheCreationInputTokens", "int", "Input tokens written to the prompt cache."),
              L("webSearchRequests", "int", "Server-side web search requests."),
              L("costUSD", "float", "Estimated cost for this model, in US dollars, from token counts and the price table in the binary."),
              L("thinkingTokens", "int", "Thinking tokens, already counted in <code>outputTokens</code>; absent when there were none.",
                presence="absent here"),
          ])],
        ),
    ], key_col="Key")],
)

STAT_MEANING = [
    ("min", "Shortest {x}, in ms."),
    ("max", "Longest {x}, in ms."),
    ("avg", "Mean {x}, in ms (sum over count)."),
    ("p50", "Median {x}, in ms."),
    ("p95", "95th percentile {x}, in ms."),
    ("p99", "99th percentile {x}, in ms."),
]
FAMILIES = [
    ("frame_duration_ms", "Terminal frame render time", "time to render one terminal UI frame",
     "Number of frames rendered.", "in 8 of 8"),
    ("hook_duration_ms", "Hook event run time", "run time of one hook event (all matching hooks together)",
     "Number of hook event runs.", "in 5 of 8"),
    ("pre_tool_hook_duration_ms", "PreToolUse hook time", "time spent in <code>PreToolUse</code> hooks before one tool call",
     "Number of tool calls that ran <code>PreToolUse</code> hooks.", "in 4 of 8"),
]

LAST_SESSION_METRICS = N(
    "lastSessionMetrics", "object",
    "Latency histograms of the last interactive session: UI frames, hook runs, PreToolUse hooks.",
    presence="in 8 of 72",
    chips=["object", "21 number fields", "8 of 72 project entries"],
    lede=(
        "A flat summary of the in-process stats store at the end of the last "
        "interactive session. Three duration histograms feed it in 2.1.280, "
        "each summarised by seven statistics, so every key is "
        "<code>&lt;metric&gt;_&lt;stat&gt;</code>. Percentiles are interpolated "
        "over a reservoir of at most 1,024 samples."
    ),
    before=[P(None, (
        "<p>It is written at session end only when the store recorded "
        "something, so an older value can outlive a session that recorded "
        "nothing. The next startup in the same project spreads it into the "
        "<code>tengu_exit</code> analytics event; nothing else reads it. No "
        "<code>-p</code> or SDK path writes it.</p>"
    ))],
    groups=[
        G(title, [L(f"{fam}_count", "int", count_text)] + [
            L(f"{fam}_{st}", "int or float", text.format(x=x)) for st, text in STAT_MEANING
        ], intro=f"Present {pres} sampled <code>lastSessionMetrics</code> objects.")
        for fam, title, x, count_text, pres in FAMILIES
    ],
)

REACT_VULN = N(
    "reactVulnerabilityCache", "object",
    "Legacy. A cached per-project dependency-scan result that no installed Claude Code reads.",
    presence="in 7 of 72",
    badge="inferred",
    chips=["object", "5 fields", "not referenced by 2.1.280"],
    lede=(
        "The name and shape read like a cached result of a one-time scan for a "
        "vulnerable React package in the project. The key occurs in no "
        "Claude Code build installed on this machine (2.1.183, 2.1.195, "
        "2.1.260, 2.1.280, 2.1.281) nor in the desktop app, so an older release "
        "wrote it, and because saves keep unknown keys, it stays."
    ),
    groups=[G("Fields", [
        L("detected", "bool", "Presumably whether a vulnerable package was found.", badge="inferred"),
        L("package", "null", "Unknown. Null wherever it appears in the sample.", badge="inferred"),
        L("packageManager", "null", "Presumably the package manager that installed the package, when one was found.", badge="inferred"),
        L("packageName", "null", "Presumably the vulnerable package's name, when one was found.", badge="inferred"),
        L("version", "null", "Presumably the installed version, when one was found.", badge="inferred"),
    ])],
)


def MCP_SERVER_NODE(local):
    """One server entry: the same shape at user and local scope."""
    return N(
        "server name", "object",
        "One MCP server's connection config: a transport type plus its launch or connection fields.",
        folder="each-server", placeholder=True,
        chips=["object", "sample entries: type and url", "may hold credentials"],
        lede=(
            "The config <code>claude mcp add</code> or <code>add-json</code> "
            "stores for one server. The key is the name you gave it. The sampled "
            "entries are remote servers with only <code>type</code> and "
            "<code>url</code>; the other fields below appear when a server needs "
            "them. Any of <code>url</code>, <code>headers</code> and "
            "<code>env</code> can carry a secret, so this map is sensitive."
        ),
        badge="docs",
        groups=[
            G("Fields in the sample", [
                L("type", "string",
                  "Transport: <code>stdio</code> (a local command), <code>http</code> "
                  "(streamable HTTP), <code>sse</code>, or <code>ws</code>. An entry with a "
                  "<code>url</code> but no <code>type</code> is read as stdio and skipped as "
                  "misconfigured.", badge="docs"),
                L("url", "string",
                  "Endpoint of a remote server. Query strings with tokens end up here in "
                  "plain text when a provider hands out tokenized URLs.", badge="docs"),
            ]),
            G("Other fields a server entry can have", [
                L("command", "string", "Executable of a stdio server.", badge="docs", presence="absent here"),
                L("args", "array of string", "Arguments of a stdio server.", badge="docs", presence="absent here"),
                L("env", "object", "Environment for a stdio server's process, name to value.", badge="docs", presence="absent here"),
                L("headers", "object", "Static request headers of a remote server, such as <code>Authorization</code>.", badge="docs", presence="absent here"),
                L("headersHelper", "string",
                  "A shell command whose JSON output is merged into the headers at connect time. "
                  "For a local-scope server it runs only after the folder is trusted.",
                  badge="docs", presence="absent here"),
                L("oauth", "object",
                  "OAuth client options: <code>clientId</code>, <code>callbackPort</code>, "
                  "<code>authServerMetadataUrl</code>, <code>scopes</code>. Tokens themselves "
                  "are kept in the credential store, not here.", badge="docs", presence="absent here"),
                L("timeout", "int", "Per-server tool execution timeout in ms; overrides <code>MCP_TOOL_TIMEOUT</code>.",
                  badge="docs", presence="absent here"),
                L("alwaysLoad", "bool", "Load every tool of this server into context at session start instead of through tool search.",
                  badge="docs", presence="absent here"),
            ], intro="Documented fields that no sampled entry uses. Objects among them get no folder here because no entry in the sample holds one."),
        ],
    )


def mcp_servers_node(scope):
    """The mcpServers map, at user scope (top level) or local scope (per project).
    Rows are filled in by MCP_SERVER_FIELDS, defined in the MCP section."""
    local = scope == "local"
    return N(
        "mcpServers", "object · map",
        ("Local-scope MCP servers: yours, for this project only." if local
         else "User-scope MCP servers: yours, in every project."),
        presence=("in 18 of 72 (non-empty in 1)" if local else ""),
        chips=["object", "map keyed by server name",
               ("local scope" if local else "user scope"),
               ("18 of 72 project entries, 1 non-empty" if local else "1 entry in the sample")],
        lede=(
            ("The servers <code>claude mcp add</code> writes by default: local "
             "scope, private to you and loaded only when Claude Code runs in this "
             "project. Because the entry is keyed by the repository root, a server "
             "added from a subdirectory or a linked worktree applies to the whole "
             "repository. Team servers belong in <code>.mcp.json</code> instead, and "
             "the per-server on/off toggles of <code>/mcp</code> live in "
             "<code>disabledMcpServers</code> and <code>enabledMcpServers</code>.")
            if local else
            ("The servers <code>claude mcp add --scope user</code> writes: private "
             "to you and loaded in every project. Local-scope servers live in each "
             "project entry, and team servers in the repository's <code>.mcp.json</code>.")
        ),
        badge="docs",
        groups=[G("Entries", [MCP_SERVER_NODE(local)])],
    )


LAST_STATS_NOTE = (
    "Read by nothing but the next startup in the same project, which sends it "
    "once in the <code>tengu_exit</code> analytics event. Not used by "
    "<code>/cost</code> or by <code>--resume</code>, which restores cost from the "
    "transcript."
)


def stat(key, type, meaning, presence="in 11 of 72"):
    return L(key, type, meaning, presence=presence)


EACH_PROJECT = N(
    "project path", "object",
    "Everything Claude Code keeps about one project root.",
    folder="each-project", placeholder=True,
    chips=["object", "8 keys always, up to 35 in the sample", "72 entries"],
    lede=(
        "One project's state: its trust decision, its local MCP servers and "
        "their toggles, whether its <code>CLAUDE.md</code> may import files from "
        "outside it, a few prompt-box and tip caches, and a snapshot of the last "
        "session's cost and latency. The eight keys of the default project "
        "object appear in every entry because any write copies them in; the "
        "rest appear once the feature that writes them has run."
    ),
    before=[P(None, (
        "<p>Most of this entry is bookkeeping. Three keys change behaviour: "
        "<code>hasTrustDialogAccepted</code>, <code>mcpServers</code>, and "
        "<code>hasClaudeMdExternalIncludesApproved</code>. The <code>last*</code> "
        "block looks like a resume cache and is not one: 2.1.280 writes it at "
        "the end of an interactive session and reads it only to send one "
        "analytics event at the next startup.</p>"
    ))],
    groups=[
        G("Trust and consent", [
            L("hasTrustDialogAccepted", "bool",
              "You accepted the workspace trust dialog for this key. <code>false</code> is "
              "the default copied into every new entry and means never accepted, not "
              "declined: declining exits without writing. Checked two ways, described on "
              "the <a href=\"../#trust\">projects page</a>.",
              presence="in 72 of 72 (true in 62)", badge="docs"),
            L("hasClaudeMdExternalIncludesApproved", "bool",
              "You approved <code>@path</code> imports in <code>CLAUDE.md</code> (and symlinked "
              "rules) that resolve outside the project. The memory loader includes those "
              "files only when this is true.", presence="in 72 of 72"),
            L("hasClaudeMdExternalIncludesWarningShown", "bool",
              "The external-imports dialog was answered here, so it is not shown again "
              "whatever the answer.", presence="in 72 of 72"),
        ]),
        G("MCP servers and toggles", [
            mcp_servers_node("local"),
            L("disabledMcpServers", "array of string",
              "Servers switched off in <code>/mcp</code> for this project: configured "
              "servers of any scope, plugin servers, claude.ai connectors (by display "
              "name) and built-ins that default to on.", presence="in 1 of 72", badge="docs"),
            L("enabledMcpjsonServers", "array of string",
              "Legacy home of the approved <code>.mcp.json</code> servers. Approvals now "
              "live in <code>.claude/settings.local.json</code>; a startup step moves a "
              "non-empty list there and deletes it, so only the empty default survives.",
              presence="in 72 of 72 (all empty)"),
            L("disabledMcpjsonServers", "array of string",
              "Legacy home of the rejected <code>.mcp.json</code> servers; moved the same way.",
              presence="in 72 of 72 (all empty)"),
            L("mcpContextUris", "array",
              "Vestigial: seeded as <code>[]</code> by the project defaults and never read "
              "or written again in 2.1.280.", presence="in 72 of 72 (all empty)"),
        ]),
        G("Prompt box and tips", [
            L("exampleFiles", "array of string",
              "Five file names this repository changes most (from <code>git log</code>, "
              "filtered to your commits when there are enough), used in the empty prompt's "
              "placeholder: Try \"how does &lt;file&gt; work?\". Regenerated after 7 days.",
              presence="in 16 of 72"),
            L("exampleFilesGeneratedAt", "int",
              "When <code>exampleFiles</code> was generated, epoch ms.", presence="in 14 of 72"),
            L("hasUnseenTeamArtifacts", "bool",
              "A teammate added a project skill or command in the last 7 days that you "
              "have not been shown; drives the \"New from your team\" tip. Needs trust, "
              "since it runs <code>git log</code>.", presence="in 24 of 72"),
        ]),
        G("The last session, for one analytics event", [
            stat("lastSessionId", "string", "Session id (UUID) of the session these stats describe."),
            stat("lastCost", "float", "Estimated cost of the session in US dollars, including cost restored on resume."),
            stat("lastDuration", "int", "Wall-clock length of the session, ms."),
            stat("lastAPIDuration", "int", "Summed API request time including retries, ms."),
            stat("lastAPIDurationWithoutRetries", "int", "Summed API request time counting only each request's final attempt, ms."),
            stat("lastToolDuration", "int", "Summed tool execution time, ms."),
            stat("lastLinesAdded", "int", "Lines added by file edits."),
            stat("lastLinesRemoved", "int", "Lines removed by file edits."),
            stat("lastTotalInputTokens", "int", "Uncached input tokens over all models."),
            stat("lastTotalOutputTokens", "int", "Output tokens over all models, thinking included."),
            stat("lastTotalCacheCreationInputTokens", "int", "Prompt-cache write tokens over all models."),
            stat("lastTotalCacheReadInputTokens", "int", "Prompt-cache read tokens over all models."),
            stat("lastTotalWebSearchRequests", "int", "Server-side web searches."),
            LAST_MODEL_USAGE,
            stat("lastFpsAverage", "float", "Average terminal frame rate of the session, frames per second.", "in 9 of 72"),
            stat("lastFpsLow1Pct", "float", "The \"1% low\" frame rate: 1000 over the slowest 1% frame time, fps.", "in 9 of 72"),
            LAST_SESSION_METRICS,
            stat("lastGracefulShutdown", "bool",
                 "Crash marker: set false when an interactive session mounts and true by a "
                 "clean exit, so a false at the next start means the last session died.", "in 6 of 72"),
            stat("lastVersionBase", "string", "Claude Code version of that session, as major.minor.patch.", "in 6 of 72"),
        ], intro=LAST_STATS_NOTE + " Each write replaces the previous values. The sampled entries lack "
           "<code>lastStartTime</code>, which 2.1.280 always writes, so they were last written by earlier releases."),
        G("Legacy keys no installed release reads", [
            L("allowedTools", "array",
              "Old per-project list of pre-approved tools. Seeded as <code>[]</code> by the "
              "defaults; no 2.1.280 permission code reads it. Approvals you give in a session "
              "go to <code>.claude/settings.local.json</code>.", presence="in 72 of 72 (all empty)", badge="docs"),
            L("lastHintSessionId", "string",
              "Unknown. Probably the session a resume hint was last shown for. No installed "
              "build references the key.", presence="in 2 of 72", badge="inferred"),
            L("lastSessionFirstPrompt", "string",
              "Unknown to 2.1.280. The name says it holds the first prompt of the last "
              "session, which would be user content in plain text. No installed build "
              "references the key; an older release wrote it and nothing removes it.",
              presence="in 2 of 72", badge="inferred"),
            L("lastSessionModified", "int",
              "Unknown. By its magnitude an epoch-ms timestamp of the last session. No "
              "installed build references the key.", presence="in 2 of 72", badge="inferred"),
            REACT_VULN,
        ], intro="Keys that 2.1.280, 2.1.260, 2.1.195, 2.1.183 and 2.1.281 on this machine never mention. "
           "Saves keep unknown keys, so they stay until the entry is purged."),
        G("Keys 2.1.280 can write that this sample lacks", [
            L("lastStartTime", "int", "Start of the last session, epoch ms (the logical start of a resumed conversation if earlier).", presence="absent here"),
            L("enabledMcpServers", "array of string", "Opt-in list for built-in servers that default to off; in 2.1.280 only <code>computer-use</code>.", presence="absent here", badge="docs"),
            L("enableAllProjectMcpServers", "bool", "Legacy approve-all flag for <code>.mcp.json</code>; moved to <code>.claude/settings.local.json</code> at startup and deleted.", presence="absent here"),
            L("seenTeamArtifactPaths", "array of string", "Teammate skills and commands already shown in the team tip; last 100 kept.", presence="absent here"),
            L("loggedAuthoredArtifactPaths", "array of string", "Skills and commands you authored that were already reported once in analytics; last 100 kept.", presence="absent here"),
            L("devIntentsDetected", "object", "When this project last showed signs of iOS or Android app work (map of intent to epoch ms); drives a desktop simulator tip.", presence="absent here"),
            L("localSettingsSeenGitTracked", "bool", "<code>.claude/settings.local.json</code> was once tracked by git here, so it is treated as repository-supplied from then on.", presence="absent here"),
            L("remoteFileMode", "string", "Answer to \"Sync this project directory to the cloud?\": <code>container_sync</code> or <code>device_tools</code>.", presence="absent here"),
            L("hasUsedRemoteSession", "bool", "A cloud session was created or linked from this project.", presence="absent here"),
            L("remoteControlSpawnMode", "string", "Saved spawn mode for <code>claude remote-control</code>: <code>same-dir</code> or <code>worktree</code>.", presence="absent here"),
            L("activeWorktreeSession", "object", "Snapshot of an active <code>--worktree</code> session (paths, branch, head commit, session id); cleared at exit. Write-only in 2.1.280.", presence="absent here"),
            L("diffSidebarBaseMode", "string", "What the diff sidebar compares against: <code>session</code>, <code>uncommitted</code> or <code>branch</code>.", presence="absent here"),
            L("webSetupPushOfferShown", "bool", "The post-push \"Connect GitHub to claude.ai\" offer was shown for this project.", presence="absent here"),
            L("orgMemoryRead", "bool", "<code>/config</code>: whether this directory reads synced project memory; unset means on.", presence="absent here"),
            L("orgMemoryWrites", "bool", "Consent-gated <code>/config</code> toggle to write synced project memory.", presence="absent here"),
            L("orgMemoryWritesAccount", "string", "The account and organization that granted <code>orgMemoryWrites</code>.", presence="absent here"),
            L("orgMemorySelection", "string", "Which synced memory store this directory uses.", presence="absent here"),
            L("orgMemorySelectionAccount", "string", "The account and organization that made that selection.", presence="absent here"),
            L("history, projectOnboardingSeenCount, hasCompletedProjectOnboarding", "various",
              "Retired: stripped from every entry on each save without being read. Prompt "
              "history now lives in <code>~/.claude/history.jsonl</code>.", presence="removed on save"),
        ], intro="Written only when the feature behind them runs, so a given file may never hold them."),
    ],
)

PROJECTS = N(
    "projects", "object · map",
    "One entry per project root: trust, local MCP servers and toggles, import consent, and the last session's stats.",
    presence="72 entries",
    chips=["object", "map keyed by absolute path", "72 entries in the sample", "never pruned"],
    lede=(
        "The per-project half of the file. Each key is the absolute path Claude "
        "Code treats as a project's identity, and each value holds what Claude "
        "Code remembers about it. Nothing prunes the map: entries accumulate for "
        "every root a session ever saved state in."
    ),
    before=[
        P("How the key is chosen", (
            "<p>The key is computed once per process "
            "(<code>getProjectPathForConfig</code>) and recomputed when the working "
            "directory moves, as with <code>/cd</code>:</p>"
            "<ol>"
            "<li>Take the launch directory with symlinks resolved, Unicode NFC-normalized.</li>"
            "<li>Walk up to the first directory holding a <code>.git</code> entry, file or directory.</li>"
            "<li>If that is a linked worktree, use the main checkout's root instead. A "
            "submodule or nested clone keeps its own root.</li>"
            "<li>Outside git, use the launch directory itself.</li>"
            "<li>Normalize: no trailing slash, no case folding; on Windows every "
            "backslash becomes <code>/</code>.</li>"
            "</ol>"
            "<p>So every subdirectory and every linked worktree of a repository shares "
            "one entry: one trust decision, one set of local MCP servers, one "
            "last-session snapshot.</p>"
        ), id="key"),
        P("Trust: two checks", (
            "<p><code>hasTrustDialogAccepted</code> is read in two different ways "
            "<span class=\"src\">binary</span> <span class=\"src\">docs</span>:</p>"
            "<ul>"
            "<li><strong>Session trust</strong> decides whether the trust dialog appears "
            "and gates git status prefetch, plugin hooks, memory tools, "
            "<code>apiKeyHelper</code> and similar. It passes if "
            "<code>CLAUDE_CODE_SANDBOXED</code> is set, if the process is a "
            "<code>-p</code>, SDK or background session, if this entry is true, or if "
            "any directory between the launch directory and the repository root (the "
            "filesystem root outside git) has a true entry.</li>"
            "<li><strong>Exact trust</strong> gates what a repository grants itself: "
            "<code>permissions.allow</code> and <code>additionalDirectories</code> in "
            "<code>.claude/settings.json</code>, <code>.mcp.json</code> approvals it "
            "ships, <code>headersHelper</code> commands. It needs this exact key to be "
            "true; a trusted parent does not count. When session trust came from a "
            "parent or from <code>-p</code>, those grants are dropped with a warning "
            "that tells you to set <code>projects[&lt;key&gt;].hasTrustDialogAccepted</code>.</li>"
            "</ul>"
            "<p>Trust in the home directory is held for the session and never written. "
            "Anthropic's own self-hosted runner seeds this key for four spellings of "
            "each workspace path (as given, NFC, realpath, realpath NFC) in a "
            "per-session config file.</p>"
        ), id="trust"),
    ],
    groups=[G("Entries", [EACH_PROJECT], key_col="Key")],
    after=[P("What removes an entry", (
        "<p>Only <code>claude project purge &lt;path&gt;</code> (or "
        "<code>--all</code>), through a locked delete. It matches the path, its "
        "realpath and the canonical git root of each, so purging a subdirectory "
        "removes the whole repository's entry. Every normal save does the "
        "opposite: it puts back any entry an older writer left out. Backups under "
        "<code>~/.claude/backups/</code> keep copies of deleted entries until they "
        "rotate out.</p>"
    ), id="purge")],
)


# ---------------------------------------------------------------------------
# Top-level scalar keys present in the sample (55), keyed by name.
# ---------------------------------------------------------------------------

ORPHAN = ("No Claude Code build installed on this machine (2.1.183 through "
          "2.1.281) references this key: an older release wrote it, and saves "
          "keep keys they do not know.")

S = {}


def s(key, type, meaning, notes="", badge="binary", presence=""):
    S[key] = L(key, type, meaning, notes=notes, badge=badge, presence=presence)


# identity
s("userID", "string",
  "Random anonymous id of this install: 64 hex characters, generated when missing "
  "or malformed. It is the device id in telemetry and feature-flag targeting and "
  "the <code>user.id</code> attribute of OpenTelemetry metrics. Not derived from "
  "your account.", notes="Deleting it yields a new, unrelated id.", badge="docs")
s("machineID", "string",
  "Random per-install machine id, 64 hex characters. Error reports send its first "
  "12 characters in place of the host name.")
s("anonymousId", "string", "Legacy identifier. " + ORPHAN, badge="inferred")
s("firstStartTime", "string",
  "When Claude Code first started with this file, as an ISO 8601 UTC timestamp. "
  "Written once and never overwritten; its value is not otherwise read.")
s("claudeCodeFirstTokenDate", "string",
  "Your organization's first Claude Code usage date as the server reports it, "
  "fetched once after a claude.ai login and sent with analytics and flag "
  "targeting. A null answer is stored too, which stops further fetches.")

# account
s("cachedExtraUsageDisabledReason", "string",
  "Why usage credits (formerly extra usage) are unavailable for your account, "
  "cached from API response headers: one of about 14 reasons such as "
  "<code>out_of_credits</code> or <code>seat_tier_level_disabled</code>, or null "
  "when they are on. Drives upsells and the 429 messages.")
s("penguinModeOrgEnabled", "bool",
  "Whether your organization allows Fast mode (internally \"penguin mode\"), "
  "cached from <code>/api/claude_code_penguin_mode</code> and used until the "
  "server answers. Turning false also removes <code>fastMode</code> from your "
  "user settings.")
s("hasAvailableSubscription", "bool",
  "Legacy subscription flag. 2.1.280 never sets it true and never reads it; "
  "<code>/logout</code> writes false.", badge="inferred")

# models
s("orgModelDefaultCache", "null",
  "Your organization's default model from the bootstrap endpoint "
  "(<code>/api/claude_cli/bootstrap</code>), or null when it sets none. When "
  "populated it is an object: <code>name</code>, <code>updated_at</code>, "
  "<code>data_source</code>, <code>override_user_selection</code>, "
  "<code>default_effort_level</code>, <code>override_user_effort</code>, plus the "
  "<code>orgUuid</code> it was fetched for. With <code>override_user_selection</code> "
  "the org default beats your own model choice.",
  notes="Null in the sample, so it has no folder here.")
s("autoCompactWindowsCache", "null",
  "Per-model auto-compact windows from the bootstrap endpoint, or null when the "
  "server sends none. When populated it maps a model id to a token count or to "
  "<code>{default, &lt;plan&gt;, surfaces}</code>; values outside 100,000 to "
  "1,000,000 are ignored. The env var and the <code>autoCompactWindow</code> "
  "setting take precedence.", notes="Null in the sample, so it has no folder here.")
s("additionalModelOptionsAnsweredAt", "int",
  "When the bootstrap endpoint's extra <code>/model</code> options were last "
  "saved, epoch ms. Its presence marks an empty list as a real answer.")
for m, label in (("unpinOpus47LaunchEffort", "claude-opus-4-7"),
                 ("unpinOpus48LaunchEffort", "claude-opus-4-8"),
                 ("unpinFable5LaunchEffort", "claude-fable-5")):
    s(m, "bool",
      f"Opts <code>{label}</code> out of launch-effort pinning. On installs older "
      "than the <code>firstStartVersion</code> stamp that still carry a top-level "
      "<code>effortLevel</code> in user settings, pinned models ignore that old "
      "effort and use their own default; true lets the old effort apply again.",
      notes="Read-only in 2.1.280; an earlier release set it.")

# migrations
s("migrationVersion", "int",
  "Version of the startup migration set that last completed. 2.1.280's set is "
  "14; any other value runs its 13 migrations before every command, "
  "<code>-p</code> included, and 14 is written only if all of them persisted.")
s("sonnet1m45MigrationComplete", "bool",
  "Marker for the migration that rewrote a <code>sonnet[1m]</code> model setting "
  "to Sonnet 4.5 1M. Set whether or not anything changed.")
s("opusProMigrationComplete", "bool",
  "Marker for the \"reset Pro to Opus default\" migration. For first-party Pro "
  "accounts with no model set it also stamps a timestamp that makes that launch "
  "show \"(auto-updated)\" next to the model.")
s("hasResetAutoModeOptInForDefaultOffer", "bool",
  "Marker for the migration that removed <code>skipAutoPermissionPrompt</code> "
  "from user settings once, so the auto-mode default offer could be shown again.")
for m in ("sonnet45MigrationComplete", "opus45MigrationComplete", "thinkingMigrationComplete"):
    s(m, "bool", "Completion marker of a retired one-shot migration. " + ORPHAN, badge="inferred")

# install and updates
s("installMethod", "string",
  "How this copy was installed: <code>native</code>, <code>global</code> (npm or "
  "bun global), <code>local</code> (<code>~/.claude/local</code>) or "
  "<code>unknown</code>. Steers the updater and <code>claude doctor</code>.")
s("autoUpdates", "bool",
  "Legacy auto-update switch. <code>false</code> disables updates unless the "
  "native installer wrote it; a startup migration moves an unprotected false into "
  "<code>DISABLE_AUTOUPDATER</code> in user settings and deletes this key.")
s("autoUpdatesProtectedForNative", "bool",
  "Written by the native installer together with <code>autoUpdates: false</code> "
  "to retire the old npm updater without turning updates off.")
s("lastReleaseNotesSeen", "string",
  "Last version whose release notes you were shown. When the running version is "
  "newer, the header shows \"Updated to latest\" with a summary from the changelog "
  "built into the binary.")
s("changelogLastFetched", "int",
  "When <code>/release-notes</code> last downloaded a changed CHANGELOG.md into "
  "<code>~/.claude/cache/changelog.md</code>, epoch ms. Write-only in 2.1.280.")
s("closedIssuesLastChecked", "int",
  "When Claude Code last ran <code>gh issue list --author @me</code> against "
  "anthropics/claude-code to announce your issues that were closed as fixed; at "
  "most once a day, epoch ms.")

# onboarding, dialogs, notices
s("hasCompletedOnboarding", "bool",
  "First-run onboarding (theme, sign-in, security notes, terminal setup) is done. "
  "Interactive startup shows onboarding until it is true, even with valid "
  "credentials. It also marks the file as holding auth: a save that would lose it "
  "is refused.", notes="<code>/logout</code> sets it false.")
s("lastOnboardingVersion", "string",
  "Version that was running when onboarding or login last completed. Write-only in 2.1.280.")
s("remoteDialogSeen", "bool",
  "You accepted the Remote Control explainer, in <code>claude remote-control</code> "
  "or <code>/remote-control</code>; both show it until this is true.")
s("hasSeenTasksHint", "bool",
  "You once moved focus from the prompt into the background-tasks pill. The hint "
  "it used to hide is gone; only the write remains.")
s("effortCalloutV2Dismissed", "bool", "Dismissal of a retired effort callout. " + ORPHAN, badge="inferred")
s("lastShownEmergencyTip", "string",
  "Text of the last one-time tip Anthropic pushed through remote config (the "
  "\"top of feed\" tip), so the same tip is not shown twice.")
s("subscriptionNoticeCount", "int",
  "Legacy impression count of the \"use your existing Claude plan\" notice. "
  "Impressions now go to <code>seenNotifications</code>; a one-time migration "
  "copied this value there.")
s("passesUpsellSeenCount", "int",
  "Impressions of the guest-passes startup banner; it stops at 3.")
s("hasVisitedPasses", "bool", "You opened <code>/passes</code>; hides the banner and tip until new passes arrive.")
s("passesLastSeenRemaining", "int",
  "Remaining guest passes when you last looked; a higher cached count resets the banner.")
s("remoteControlUpsellSeenCount", "int",
  "Impressions of the idle \"control this session from your phone\" upsell; capped at 3.")
s("fullscreenUpsellSeenCount", "int",
  "Impressions of the fullscreen-renderer upsell, 0 to 3. Also part of the "
  "fresh-install default for that renderer.")

# tips and usage
s("numStartups", "int",
  "Interactive sessions started with this file; <code>-p</code> does not count. "
  "It is the clock tips, announcements and nudges count in.")
s("promptQueueUseCount", "int",
  "Times you queued a message while Claude was busy; the queueing tip shows while it is 3 or less.")
s("btwUseCount", "int", "Times you asked a <code>/btw</code> side question; the tip shows while it is 0.")
s("lastPlanModeUse", "int",
  "When you last entered Plan Mode with Shift+Tab, epoch ms, refreshed at most daily; used by plan-mode tips.")

# preferences and integrations
s("theme", "string",
  "Legacy home of the color theme. 2.1.280 writes the theme to "
  "<code>~/.claude/settings.json</code> and reads this only as a fallback when no "
  "settings file sets one and this differs from <code>dark</code>.", badge="docs")
s("showSpinnerTree", "bool",
  "Legacy UI toggle. The loader deletes it from memory; saves re-read the file, "
  "so it stays on disk. Its original meaning is not recoverable from 2.1.280.",
  badge="inferred")
s("claudeInChromeDefaultEnabled", "bool",
  "The \"Claude in Chrome enabled by default\" setting. Absent means no choice yet, "
  "which keeps the one-time auto-enable offer eligible.")
s("hasCompletedClaudeInChromeOnboarding", "bool", "The Claude in Chrome onboarding screen was shown.")
s("cachedChromeExtensionInstalled", "bool",
  "Cached result of scanning Chromium-family browser profiles for the Claude in "
  "Chrome extension. Only ever written true, so an uninstalled extension leaves it stale.")
s("officialMarketplaceAutoInstallAttempted", "bool",
  "Claude Code has tried to register the official plugin marketplace "
  "<code>claude-plugins-official</code>. Failures retry with backoff from 1 hour to 7 days, at most 10 times.")
s("officialMarketplaceAutoInstalled", "bool",
  "The official plugin marketplace is registered; stops further attempts.")

# terminal
s("deepLinkTerminal", "string",
  "The macOS terminal app to open for <code>claude-cli://</code> deep links, "
  "remembered from the one you run Claude Code in: iTerm, Ghostty, kitty, "
  "Alacritty, WezTerm or Terminal.")
s("optionAsMetaKeyInstalled", "bool",
  "<code>/terminal-setup</code> finished in Terminal.app (Option as Meta, so "
  "Option+Enter inserts a newline).")
s("appleTerminalSetupInProgress", "bool",
  "Crash guard for <code>/terminal-setup</code> in Terminal.app: true while it "
  "edits Terminal preferences, so an interrupted run is rolled back at the next start.")
s("appleTerminalBackupPath", "string",
  "Path of the Terminal.app preferences backup that <code>/terminal-setup</code> "
  "took, used for that rollback. Not cleared after success.")

s("cachedGrowthBookFeaturesAt", "int",
  "When the feature-flag and experiment caches were last written, epoch ms. Read "
  "only by a Remote Control diagnostics line.")


# ---------------------------------------------------------------------------
# Keys 2.1.280 knows that the sample lacks (generated from the research notes,
# then edited). Grouped for the root page.
# ---------------------------------------------------------------------------

ABSENT = {}
ABSENT['prefs'] = [
    L('preferredNotifChannel', 'string', 'How local notifications (task done, permission prompt waiting, idle prompt) are delivered.', notes='Set by: <code>/config</code> row "Local notifications" (row id notifChannel; labelled "Notifications" behind a feature gate); now written to user settings. Default: "auto".', badge='docs', presence='absent here'),
    L('verbose', 'bool', "Show every tool call's full input and output instead of collapsed summaries.", notes='Set by: <code>/config</code> row "Verbose output" (writes user settings); <code>--verbose</code> overrides per session; settings viewMode overrides it. Default: false.', badge='docs', presence='absent here'),
    L('editorMode', 'string', 'Key binding mode of the prompt input.', notes='Set by: <code>/config</code> row "Editor mode" (row id editor; writes user settings). Default: "normal".', badge='docs', presence='absent here'),
    L('autoCompactEnabled', 'bool', 'Compact the conversation automatically when context approaches the limit.', notes='Set by: <code>/config</code> row "Auto-compact" (writes user settings); DISABLE_AUTO_COMPACT / DISABLE_COMPACT turn it off per session. Default: true.', badge='docs', presence='absent here'),
    L('autoScrollEnabled', 'bool', 'In fullscreen rendering, keep the view pinned to new output at the bottom.', notes='Set by: <code>/config</code> row "Auto-scroll" (only listed while fullscreen rendering is on; writes user settings). Default: true.', badge='docs', presence='absent here'),
    L('showTurnDuration', 'bool', 'Show the per-turn duration line after each response ("Cooked for 1m 6s").', notes='Set by: <code>/config</code> row "Show turn duration" (row id turnDuration; writes user settings). Default: true.', badge='docs', presence='absent here'),
    L('externalEditorContext', 'bool', "When Ctrl+G opens the prompt in an external editor, prefill Claude's last response as # comment lines (stripped on save).", notes='Set by: <code>/config</code> row "Show last response in external editor" (writes <code>~/.claude.json</code>). Default: false.', badge='docs', presence='absent here'),
    L('showMessageTimestamps', 'bool', 'Stamp each transcript message with its arrival time.', notes='Set by: <code>/config</code> row "Show message timestamps" (row id timestamps, Experimental group; writes user settings). Default: false.', badge='binary', presence='absent here'),
    L('diffTool', 'string', 'Where proposed Edit/Write diffs are shown while a VS Code or JetBrains IDE is connected: the IDE diff viewer (auto) or the terminal.', notes='Set by: <code>/config</code> row "Diff tool" (only while connected to an IDE; writes <code>~/.claude.json</code>). Default: "auto".', badge='docs', presence='absent here'),
    L('autoConnectIde', 'bool', 'Connect to a running VS Code or JetBrains IDE automatically when started from an external terminal.', notes='Set by: <code>/config</code> row "Auto-connect to IDE (external terminal)"; the "Do you want to enable auto-connect to IDE?" dialog; CLAUDE_CODE_AUTO_CONNECT_IDE overrides per session. Default: false.', badge='docs', presence='absent here'),
    L('autoInstallIdeExtension', 'bool', 'Install the Claude Code IDE extension automatically when running inside a VS Code or JetBrains terminal.', notes='Set by: <code>/config</code> row "Auto-install IDE extension"; CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL skips per session. Default: true.', badge='docs', presence='absent here'),
    L('fileCheckpointingEnabled', 'bool', 'Snapshot files before each edit so <code>/rewind</code> can restore code.', notes='Set by: <code>/config</code> row "Rewind code (checkpoints)" (row id checkpoints; writes user settings); CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING turns it off. Default: true.', badge='docs', presence='absent here'),
    L('terminalProgressBarEnabled', 'bool', 'Report an in-progress state to terminals that support it (OSC 9;4 progress sequences).', notes='Set by: <code>/config</code> row "Terminal progress bar" (row id progressBar; writes user settings). Default: true.', badge='docs', presence='absent here'),
    L('respectGitignore', 'bool', 'Whether the @ file picker leaves out files that match .gitignore.', notes='Set by: <code>/config</code> row "Respect .gitignore in file picker" (row id gitignore; writes <code>~/.claude.json</code>); a settings-file respectGitignore takes precedence. Default: true.', badge='docs', presence='absent here'),
    L('copyFullResponse', 'bool', 'Make <code>/copy</code> copy the whole last response right away instead of opening the code-block picker.', notes='Set by: <code>/config</code> row "Skip the <code>/copy</code> picker"; or choosing "always" in the <code>/copy</code> picker ("Preference saved. Use <code>/config</code> to change copyFullResponse"). Default: false.', badge='binary', presence='absent here'),
    L('copyOnSelect', 'bool', 'Copy text to the clipboard when you finish a mouse selection in fullscreen rendering or agent view.', notes='Set by: <code>/config</code> row "Copy on select" (only while fullscreen rendering is on; writes <code>~/.claude.json</code>). Default: true (a code default, not in the defaults object).', badge='docs', presence='absent here'),
    L('leftArrowOpensAgents', 'bool', 'Pressing the left arrow on an empty prompt backgrounds the session and opens agent view.', notes='Set by: <code>/config</code> row "&lt;left arrow&gt; opens agents"; agent view settings. Default: true (code default).', badge='docs', presence='absent here'),
    L('defaultToAgentsView', 'bool', 'Start <code>claude</code> in agent view instead of a regular session.', notes='Set by: <code>/config</code> row "Open agents view by default"; agent view settings row "Start in agent view". Default: false (code default).', badge='binary', presence='absent here'),
    L('prStatusFooterEnabled', 'bool', 'Show the pull-request status footer.', notes='Set by: <code>/config</code> row "Show PR status footer" (row id prStatus; writes <code>~/.claude.json</code>). Default: true (code default).', badge='binary', presence='absent here'),
    L('remoteControlAtStartup', 'bool', 'Connect Remote Control automatically when each interactive session starts.', notes="Default: unset (then the org/admin default or Claude Code's current default applies).", badge='docs', presence='absent here'),
    L('workflowSizeGuideline', 'string', 'Agent-count guideline sent to Claude for dynamic workflows it writes (small &lt;5, medium &lt;10, large &lt;50 agents).', notes='Set by: <code>/config</code> row "Dynamic workflow size" (writes <code>~/.claude.json</code>); a settings-file workflowSizeGuideline overrides it and hides the row. Default: computed default ("medium", or "small" on Pro per docs); not in the defaults object.', badge='docs', presence='absent here'),
    L('showStatusInTerminalTab', 'bool', 'Show the session status in the terminal tab title.', notes='Set by: <code>/config</code> row "Show status in terminal tab" (Experimental group, only while a remote flag enables it; writes <code>~/.claude.json</code>). Default: false (code falls back to false).', badge='binary', presence='absent here'),
    L('inputNeededNotifEnabled', 'bool', 'Push a notification to your phone when a permission prompt or question waits for you (while Remote Control is connected).', notes='Set by: <code>/config</code> row "Push when actions required" (writes user settings); synced to the server notification preference code_requires_action and hydrated from it when unset. Default: false (code default).', badge='docs', presence='absent here'),
    L('agentPushNotifEnabled', 'bool', 'Allow Claude to send a push notification to your phone when it decides one is worth sending.', notes='Set by: <code>/config</code> row "Push when Claude decides" (writes user settings); synced to a server notification preference. Default: false (code default).', badge='docs', presence='absent here'),
    L('teammateMode', 'string', 'Where agent-team teammates run: in the main pane or in tmux / iTerm2 split panes.', notes='Set by: <code>/config</code> row "Teammate mode" (Experimental group; writes user settings); <code>--teammate-mode</code> per session. Default: "in-process" (a code default, not in the defaults object).', badge='docs', presence='absent here'),
    L('messageIdleNotifThresholdMs', 'int', 'How long Claude sits idle waiting for your input before it sends the "Claude is waiting for your input" notification (type idle_prompt).', notes='Set by: hand edit only (no writer). Default: 60000.', badge='binary', presence='absent here'),
    L('env', 'object', "Environment variables applied to process.env at startup, before every settings file's env, so any settings-file env value wins.", notes='Set by: hand edit only (no writer found in 2.1.280). Default: {}.', badge='docs', presence='absent here'),
    L('briefTranscript', 'bool', 'Sticky focus view: the transcript shows only your prompt, a summary and the response.', notes='Set by: <code>/focus</code> command ("Toggle focus view"); a settings viewMode value overrides it. Default: false.', badge='binary', presence='absent here'),
    L('showExpandedTodos', 'bool', 'Remembers whether the expanded task list view was open, so the next session starts with it open.', notes='Set by: automatic whenever the expanded view changes (app:toggleTodos, ctrl+t by default). Default: false.', badge='binary', presence='absent here'),
    L('diffSidebarOpen', 'bool', 'Remembers whether you last had the diff panel open. false stops it auto-opening; true lets it auto-open from 110 terminal columns instead of the unset threshold of 144.', notes='Set by: automatic when switching between the conversation and diff tabs.', badge='binary', presence='absent here'),
    L('remoteHomeSettingsMode', 'string', 'Whether this machine\'s settings are sent into cloud sessions ("Use this machine\'s settings in cloud sessions").', notes="Set by: <code>/config</code> panel (turning it on needs the panel's consent view; key=value can only turn it off).", badge='binary', presence='absent here'),
    L('fleetViewGroupMode', 'string', 'How agent view groups sessions; cycled by a key in agent view.', notes='Set by: agent view. Default: "state" (code default).', badge='binary', presence='absent here'),
    L('preferTmuxOverIterm2', 'bool', 'For agent-team split panes inside iTerm2, use tmux instead of iTerm2 native panes.', notes='Set by: teammate backend setup choice.', badge='binary', presence='absent here'),
    L('codeReviewLastEffort', 'string', 'Effort level you last typed for <code>/code-review</code>; reused when none is given.', notes='Set by: <code>/code-review</code>.', badge='binary', presence='absent here'),
    L('favoritePlugins', 'array of string', 'Plugins you starred in the <code>/plugin</code> manager list.', notes='Set by: <code>/plugin</code> manager (favorite toggle).', badge='binary', presence='absent here'),
    L('lspRecommendationDisabled', 'bool', 'Turns off LSP plugin recommendations entirely (the "disable" choice in the recommendation prompt).', notes='Set by: LSP plugin recommendation prompt.', badge='binary', presence='absent here'),
    L('lspRecommendationNeverPlugins', 'array of string', 'Plugins you chose "never" for in the LSP recommendation prompt; they are skipped when matching a file extension.', notes='Set by: LSP plugin recommendation prompt ("never"). Default: unset (empty).', badge='binary', presence='absent here'),
]
ABSENT['secrets'] = [
    L('primaryApiKey', 'string', 'API key saved by <code>/login</code> (source "/login managed key") when it is kept in the config file instead of the OS keychain.', notes='', badge='binary', presence='absent here'),
    L('customApiKeyResponses', 'object', 'Your answers to "Do you want to use this API key?" for ANTHROPIC_API_KEY values. Each entry is the last 20 characters of the trimmed key, not the whole key.', notes='Default: {approved: [], rejected: []}.', badge='binary', presence='absent here'),
    L('bypassPermissionsModeAccepted', 'bool', 'Legacy record that you accepted the bypass-permissions (<code>--dangerously-skip-permissions</code>) disclaimer.', notes='Set by: older versions; the migrationVersion 14 startup migration writes skipDangerousModePermissionPrompt: true to user settings and deletes this key (still honored if present).', badge='binary', presence='absent here'),
    L('fableOverageConsentV2', 'object', 'Consent, per organization or account, to use the Fable model on usage credits (overage billing).', notes='Set by: the usage-credits consent flow in <code>/model</code> (<code>/config</code> refuses with "needs usage-credits consent, run <code>/model</code> first").', badge='binary', presence='absent here'),
    L('hasAcknowledgedCostThreshold', 'bool', 'You acknowledged the cost-threshold dialog, shown once session spend reaches $5 to users allowed to see costs.', notes='Set by: cost threshold dialog.', badge='binary', presence='absent here'),
    L('summonSidKey', 'string', 'Random per-machine secret, created on first use, used as an HMAC-SHA256 key to derive stable 16-hex-character status ids per artifact for artifact-comment auto-replies.', notes='Set by: automatic (getOrCreateSummonSidKey). Default: unset (generated).', badge='binary', presence='absent here'),
    L('remoteControlMachineId', 'string', 'Stable id for this machine in Remote Control, created on first use.', notes='Set by: automatic (getOrCreateRemoteControlMachineId). Default: unset (generated).', badge='binary', presence='absent here'),
    L('chromeExtension', 'object', 'The Claude in Chrome browser extension this machine is paired with.', notes='Set by: automatic on extension pairing.', badge='binary', presence='absent here'),
]
ABSENT['dialogs'] = [
    L('hasUsedStash', 'bool', 'Set the first time you stash the prompt (chat:stash, Ctrl+S by default); after that the "Tip: ctrl+s stash" hint is no longer shown.', notes='Set by: automatic, on first prompt stash. Default: false.', badge='binary', presence='absent here'),
    L('hasUsedBackgroundTask', 'bool', 'Set the first time you send running foreground work to the background with the task:background shortcut (ctrl+b by default).', notes='Set by: automatic, on first use of the background shortcut. Default: false.', badge='binary', presence='absent here'),
    L('hasUsedBackslashReturn', 'bool', 'Set the first time you insert a newline with backslash then Return; the newline hint then shortens to the compact form.', notes='Set by: automatic. Default: unset (false).', badge='binary', presence='absent here'),
    L('shiftEnterKeyBindingInstalled', 'bool', 'Set by <code>/terminal-setup</code> after it installs a Shift+Enter newline binding for VS Code, Cursor, Windsurf, Alacritty or Zed; used by newline hints and tips.', notes='Set by: <code>/terminal-setup</code>. Default: unset (treated as false).', badge='binary', presence='absent here'),
    L('hasIdeOnboardingBeenShown', 'object', 'The IDE onboarding dialog was already shown in this terminal/IDE type.', notes='Set by: automatic when the dialog is shown.', badge='binary', presence='absent here'),
    L('hasIdeAutoConnectDialogBeenShown', 'bool', 'The "Do you want to enable auto-connect to IDE?" dialog was answered (it also writes autoConnectIde).', notes='Set by: the IDE auto-connect dialog.', badge='binary', presence='absent here'),
    L('hasSeenAutoDefaultNudge', 'bool', 'The one-time nudge offering to make auto mode the default permission mode was answered (accept writes permissions.defaultMode "auto" to user settings).', notes='Set by: the auto-default nudge (feature-gated).', badge='binary', presence='absent here'),
    L('hasSeenAutoModeEntryWarning', 'bool', 'The first-time notice when entering auto mode was shown (skipped when skipAutoPermissionPrompt is set).', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('hasSeenAutoModeOutsideReadPrompt', 'bool', 'The one-time auto-mode prompt, shown when a read outside the working directories needs approval, offering to block such reads (permissions.blockReadsOutsideWorkingDirectories) was shown.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('hasSeenUltraplanTerms', 'bool', 'The terms screen on the first <code>/ultraplan</code> launch was shown.', notes='Set by: first <code>/ultraplan</code> run.', badge='binary', presence='absent here'),
    L('hasUsedRemoteControl', 'bool', 'Remote Control has been used on this machine; hides Remote Control upsell tips.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('hasOpenedAgentsView', 'bool', 'Agent view was opened at least once; hides the tip that advertises it.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('hasRunUltrareview', 'bool', '<code>/ultrareview</code> has been run; stops ultrareview awareness tips.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('resumeReturnDismissed', 'bool', 'You chose "never" on the prompt shown when returning to a long idle session (defaults 70 minutes and 100k tokens), so it is not offered again.', notes='Set by: the resume-return prompt.', badge='binary', presence='absent here'),
    L('transcriptShareDismissed', 'bool', 'You chose "don\'t ask again" on the prompt to share a transcript after a feedback survey.', notes='Set by: feedback survey transcript-share prompt.', badge='binary', presence='absent here'),
    L('iterm2It2SetupComplete', 'bool', 'The iTerm2 <code>it2</code> CLI and Python API setup (used for native iTerm2 split panes for agent teammates) was verified.', notes='Set by: automatic after it2 setup verification.', badge='binary', presence='absent here'),
    L('iterm2SetupInProgress', 'bool', 'Crash-recovery flag for iTerm2 preference changes: if set at startup, Claude Code restores the iTerm2 plist from iterm2BackupPath. In 2.1.280 nothing sets it to true; it is only read and cleared.', notes='Set by: only cleared in 2.1.280.', badge='binary', presence='absent here'),
    L('iterm2BackupPath', 'string', 'Backup of com.googlecode.iterm2.plist to restore after an interrupted iTerm2 setup; read-only in 2.1.280.', notes='Set by: no writer in 2.1.280.', badge='binary', presence='absent here'),
]
ABSENT['retired'] = [
    L('opus1mMergeNoticeSeenCount', 'int', 'Counter for a past notice, apparently about merging the Opus and Opus 1M model options.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('voiceNoticeSeenCount', 'int', 'Counter for a past voice-mode notice.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('opus47LaunchSeenCount', 'int', 'Counter for the Opus 4.7 launch announcement.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('opus48LaunchSeenCount', 'int', 'Counter for the Opus 4.8 launch announcement.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('speculationEnabled', 'bool', 'Toggle for a removed "speculation" feature; what it did is not recoverable from this binary.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('fleetViewPeakConcurrent', 'int', 'Peak number of concurrent sessions seen in fleet view (agent view).', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('pluginUsageLspGraceApplied', 'bool', 'One-shot flag for the LSP plugin usage grace refresh, replaced by the per-plugin list pluginUsageLspGraceAppliedIds.', notes='Set by: none (removed).', badge='binary', presence='absent here'),
    L('autoModeOptInDismissed', 'bool', 'Dismissal flag for an earlier auto-mode opt-in prompt.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('prideFlag', 'unknown', 'Seasonal Pride-themed UI flag.', notes='Set by: none (removed).', badge='inferred', presence='absent here'),
    L('routineFiredWatermark', 'unknown', 'Watermark for the removed startup notice that told you a one-off scheduled routine had run since your last session.', notes='Set by: none (removed).', badge='binary', presence='absent here'),
    L('autoUpdaterStatus', 'string', 'Pre-installMethod updater state. On load, migrated maps to installMethod "local", enabled to installMethod "global", disabled to autoUpdates false, anything else to installMethod "unknown"; applies only when installMethod is unset.', notes='Set by: none (legacy).', badge='binary', presence='absent here'),
    L('replBridgeEnabled', 'bool', 'Legacy top-level switch for the Remote Control bridge; the startup migration copies it into remoteControlAtStartup (unless that is already set) and deletes it.', notes='Set by: none (legacy; migrated away).', badge='binary', presence='absent here'),
    L('taskCompleteNotifEnabled', 'unknown', 'Name suggests a toggle for task-complete notifications; in 2.1.280 it appears only in GLOBAL_CONFIG_KEYS and nothing reads or writes it.', notes='Set by: none in 2.1.280.', badge='inferred', presence='absent here'),
    L('autoAddRemoteControlDaemonWorker', 'unknown', 'Internal-only <code>/config</code> id; in this build nothing reads or writes it beyond GLOBAL_CONFIG_KEYS.', notes='Set by: none in this build.', badge='inferred', presence='absent here'),
    L('cachedDynamicConfigs', 'object', 'Legacy cache slot, probably for remote "dynamic configs" of an older feature-flag client (inferred from the name). No reader or writer in 2.1.280.', notes='Set by: none in 2.1.280. Default: {}.', badge='inferred', presence='absent here'),
    L('subscriptionUpsellShownCount', 'int', 'Legacy counter; listed only among the counter keys; nothing reads or writes it in 2.1.280.', notes='Set by: none in 2.1.280.', badge='inferred', presence='absent here'),
    L('experimentNoticesSeenCount', 'int', 'Legacy counter; listed only among the counter keys; nothing reads or writes it in 2.1.280.', notes='Set by: none in 2.1.280.', badge='inferred', presence='absent here'),
    L('todoFeatureEnabled', 'bool', 'Settings-schema text: "Enable the todo / task tracking panel". In 2.1.280 it is only merged into the <code>/config</code> state; no feature reads it.', notes='Set by: no <code>/config</code> row; hand edit or settings.json. Default: true.', badge='binary', presence='absent here'),
    L('autoUploadSessions', 'bool', 'Settings-schema text: "Mirror local sessions to claude.ai as view-only (no remote control)". In this external build only the <code>/config</code> state merge and telemetry touch it.', notes='Set by: no <code>/config</code> row in this build (its id sits in an "Internal" category list). Default: unset (an invalid legacy value counts as off).', badge='binary', presence='absent here'),
    L('apiKeyHelper', 'string', 'Listed in GLOBAL_CONFIG_KEYS, but 2.1.280 reads apiKeyHelper only from settings files (merged settings, or only <code>--settings</code> flag settings under <code>--bare</code> / CLAUDE_CODE_SIMPLE); a value in <code>~/.claude.json</code> has no effect.', notes='Set by: not applicable in <code>~/.claude.json</code>; set it in settings.json.', badge='docs', presence='absent here'),
]
ABSENT['counters'] = [
    L('queuedCommandUpHintCount', 'int', 'Counter meant to limit the "Press up to edit queued messages" hint, which shows while the count is below 3.', notes='Set by: nothing in 2.1.280 increments it (read-only here). Default: 0.', badge='binary', presence='absent here'),
    L('memoryUsageCount', 'int', 'Counter of <code>/memory</code> use; the tip "Use <code>/memory</code> to view and manage Claude memory" is relevant only while it is 0 or less.', notes='Set by: nothing in 2.1.280 increments it (read-only here). Default: 0.', badge='binary', presence='absent here'),
    L('lspRecommendationIgnoredCount', 'int', 'How many LSP plugin recommendations were ignored; at 5 the recommendations stop.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('tipsHistoryByCommand', 'object', 'For each slash command a tip advertised, the tip id and startup number when it was shown; used to attribute a later use of that command to the tip (within 100 launches).', notes='Set by: automatic when a tip with an advertised command is shown.', badge='binary', presence='absent here'),
    L('announcementImpressions', 'object', 'How many times each startup announcement was shown; each announcement stops after its maxImpressions.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('promoStartupSeenCount', 'int', 'Times the startup "claim credit" promo banner was shown; it shows while the count is below 3.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('fullscreenDownsellSeenCount', 'int', 'Times the "fullscreen downsell" notice was shown to users in the downsell_on experiment arm; shown while below 5.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('voiceLangHintShownCount', 'int', 'Times the dictation-language hint was shown when enabling voice mode; resets when the language changes; shown while below 2.', notes='Set by: automatic (voice mode enable).', badge='binary', presence='absent here'),
    L('voiceFooterHintSeenCount', 'int', 'Times the voice push-to-talk footer hint was shown; shown while below 3.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('artifactRosterDenied', 'object', 'Records that the artifact roster fetch was refused with HTTP 401/403 for the current token; cleared on a successful fetch and on logout.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('promoStartupStatusCache', 'object', 'Cached eligibility and claimed state of the startup promo for the signed-in account.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('startupPrefetchedAt', 'int', 'When background startup prefetches last ran; with a remote nap interval set, later launches skip prefetching until it elapses. Cleared on logout.', notes='Set by: automatic, only when the remote nap interval is above 0.', badge='binary', presence='absent here'),
    L('claudeCodeHints', 'object', 'Bookkeeping for &lt;claude-code-hint&gt; plugin suggestions that CLI tools print: plugin ids already suggested (capped at 100) and a switch that turns the hints off.', notes="Set by: automatic when a hint is shown; the hint prompt's disable choice.", badge='binary', presence='absent here'),
    L('autoModeClassifierBillingNoticeAcknowledgedAt', 'int', 'When you chose Continue on the auto-mode server-fallback notice while using a third-party LLM gateway; the notice is suppressed for 24 hours after.', notes='Set by: auto mode server-fallback notice (Continue, gateway host present).', badge='binary', presence='absent here'),
    L('autoModeEnvSetup', 'object', 'Counts auto-mode denials to decide when to offer auto-mode environment onboarding (at least 5 denials and 5 startups); Later snoozes 7 days, Dismiss is permanent, Accept clears the object.', notes='Set by: automatic (denial counter) and the onboarding prompt.', badge='binary', presence='absent here'),
    L('bedrockDeclinedUpgrades', 'object', 'Amazon Bedrock model-upgrade offers you declined, per tier, so the same offer is not shown again.', notes='Set by: third-party model upgrade dialog (decline).', badge='binary', presence='absent here'),
    L('vertexDeclinedUpgrades', 'object', 'Google Vertex AI model-upgrade offers you declined, per tier.', notes='Set by: third-party model upgrade dialog (decline).', badge='binary', presence='absent here'),
    L('cachedUsageUtilization', 'object', 'Account-scoped cache of plan usage utilization, so windows and sessions can share a recent read; cleared on logout or account mismatch.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('fable5ToFableAliasMigrationTimestamp', 'int', 'Set when the startup migration rewrote a user-settings model of claude-fable-5 to the "fable" alias; that launch\'s model notice then says "(auto-updated)".', notes='Set by: startup migration (only when numStartups &gt; 1).', badge='binary', presence='absent here'),
    L('feedbackDraftsTurnOffPromptDeclines', 'int', 'Times you declined the prompt offering to turn off Claude-drafted feedback; the prompt stops after 2.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('githubActionSetupCount', 'int', 'Completed <code>/install-github-app</code> runs; any value hides the related tip.', notes='Set by: <code>/install-github-app</code>.', badge='binary', presence='absent here'),
    L('slackAppInstallCount', 'int', 'Times <code>/install-slack-app</code> opened the Slack app page; any value hides the tip.', notes='Set by: <code>/install-slack-app</code>.', badge='binary', presence='absent here'),
    L('hasRemoteEnvironment', 'bool', 'Your account has at least one cloud (remote) environment; updated when environments are fetched or a cloud session is created. Sent with telemetry and used as a feature condition.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('legacyOpusMigrationTimestamp', 'int', 'Set when the startup migration rewrote a legacy Opus 4 / 4.1 model id in user settings to "opus"; drives the "(auto-updated)" model notice for that launch.', notes='Set by: startup migration.', badge='binary', presence='absent here'),
    L('opusProMigrationTimestamp', 'int', 'Set by the "reset Pro to Opus default" migration for first-party Pro users with no custom model; drives the "(auto-updated)" notice.', notes='Set by: startup migration.', badge='binary', presence='absent here'),
    L('sonnet45To46MigrationTimestamp', 'int', 'Set when the startup migration rewrote a Sonnet 4.5 model id in user settings to the "sonnet" alias (only when numStartups &gt; 1).', notes='Set by: startup migration.', badge='binary', presence='absent here'),
    L('officialMarketplaceAutoInstallFailReason', 'string', 'Why the last official-marketplace auto-install attempt failed; policy_blocked stops retries.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('officialMarketplaceAutoInstallLastAttemptTime', 'int', 'Time of the last failed official-marketplace auto-install attempt.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('officialMarketplaceAutoInstallNextRetryTime', 'int', 'Earliest time of the next official-marketplace auto-install attempt.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('officialMarketplaceAutoInstallRetryCount', 'int', 'Failed official-marketplace auto-install attempts so far (stops at 10).', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('pluginPanes', 'object', 'Plugin pane layout (dock width, inline rows) and which plugin pane offers were already asked.', notes='Set by: automatic (layout changes are saved durably).', badge='binary', presence='absent here'),
    L('pluginSuggestionDiscoverShownCounts', 'object', 'Plugin suggestions shown in the <code>/plugin</code> list; a plugin already shown is not suggested there again.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('pluginSuggestionShownCounts', 'object', 'Per-plugin suggestion count consulted when choosing marketplace plugin tips (skipped once it reaches the tip cap). Nothing writes it in 2.1.280.', notes='Set by: none in 2.1.280 (legacy value still honored).', badge='binary', presence='absent here'),
    L('pluginSurveyState', 'object', 'Scheduling state for plugin feedback surveys.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('pluginUsageLspGraceAppliedIds', 'array of string', 'LSP plugins whose pluginUsage lastUsedAt got a one-time refresh (a grace period so unused-plugin review does not flag them); replaces the removed boolean pluginUsageLspGraceApplied.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('fullscreenAutoDisabled', 'object', 'Fullscreen rendering was auto-disabled for this Claude Code version after failed starts.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('fullscreenBootStrikes', 'object', 'Count of fullscreen starts that did not finish, for the current version.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('fullscreenBootPending', 'object', 'Boot canaries of fullscreen starts still in progress.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('agentLastUsed', 'object', 'When each agent template was last used; sorts agent lists by recency.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('closedIssuesAcknowledged', 'array of number', 'anthropics/claude-code issues you authored that were closed as completed and already announced to you; checked through <code>gh issue list --author @me</code> at most daily (closedIssuesLastChecked).', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('mcpNeedsAuthNoticed', 'array of string', 'MCP servers whose "needs auth" notice was already shown; names drop out once the server connects.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('lastSeenOrgDefaultUpdatedAt', 'string', 'updated_at of the organization default-model config last applied; when the org default changes, Claude Code clears the model in user settings so the new default takes effect. Cleared on logout.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('gzipRequestBodiesLatchedOff', 'object', 'After the API rejected a gzip-compressed request body, compression of request bodies stays off for 7 days.', notes='Set by: automatic.', badge='binary', presence='absent here'),
    L('webSetupPushOffer', 'object', 'Rate limit for the offer shown after a git push when GitHub is not connected to claude.ai ("Pushed to GitHub. Connect GitHub to claude.ai so you can work on this repo even when this machine is offline?"): at most once a day, 3 times in total, never after "don\'t ask again".', notes='Set by: automatic, plus the offer\'s "don\'t ask again" choice.', badge='binary', presence='absent here'),
    L('voiceLangHintLastLanguage', 'string', 'Dictation language the voice hint was last shown for; a change resets voiceLangHintShownCount.', notes='Set by: automatic (voice mode enable).', badge='binary', presence='absent here'),
]
ABSENT["counters"].insert(0, L("firstStartVersion", "string",
    "Version that was running at first start, stamped with <code>firstStartTime</code>. Its presence marks installs newer than the stamp: launch-effort pins apply only when it is absent.",
    notes="Never written when <code>firstStartTime</code> already exists, so older files never get it.", presence="absent here"))


# ---------------------------------------------------------------------------
# Root page prose
# ---------------------------------------------------------------------------

ROOT_WHAT = P("What this file is", (
    "<p>Anthropic's settings documentation calls <code>~/.claude.json</code> a "
    "fifth file that Claude Code \"writes for itself\": your sign-in, your MCP "
    "servers, per-project state such as trust decisions, and the few global "
    "keys that <code>/config</code> writes "
    "[<a href=\"https://code.claude.com/docs/en/settings\">docs: settings</a>] "
    "<span class=\"src\">docs</span>. Only five of its keys are documented as "
    "yours to edit: <code>autoConnectIde</code>, <code>autoInstallIdeExtension</code>, "
    "<code>copyOnSelect</code>, <code>diffTool</code> and <code>externalEditorContext</code> "
    "[<a href=\"https://code.claude.com/docs/en/settings-reference#global-config-settings\">docs: settings reference § Global config settings</a>].</p>"
    "<p>Everything else is the program's own state, and it is of three kinds. "
    "Some keys are <strong>decisions</strong> that change behaviour: trust per "
    "project, MCP servers, onboarding, dialogs you answered. Some are "
    "<strong>caches of server data</strong>: your account profile, about 700 "
    "feature flags, experiment assignments, model lists, eligibility answers. The "
    "rest are <strong>bookkeeping</strong>: counters that pace tips and upsells, "
    "one-shot migration markers, the last session's stats per project. A host "
    "that provisions Claude Code must get the first kind right and can ignore "
    "most of the rest.</p>"
    "<p>When Claude Code reads the file it spreads it over a built-in defaults "
    "object, and when it saves it drops every top-level key that equals its "
    "default <span class=\"src\">binary</span>. A missing key therefore usually "
    "means \"at its default\", not \"never set\". Unknown keys are kept on every "
    "save, which is why keys that no current release reads are still here.</p>"
), id="what")

ROOT_READING = P("How to read this explorer", (
    "<ul>"
    "<li><strong>Every object gets a folder</strong> named after its key, with "
    "its own page. Its scalar fields are explained on that page, and objects "
    "inside it get folders of their own, down to the last level.</li>"
    "<li><strong>A map whose keys are data</strong>, such as <code>projects</code> "
    "(keyed by path) or <code>skillUsage</code> (keyed by skill name), gets one "
    "placeholder folder that describes every entry, shown as "
    "<code class=\"ph\">&lt;project path&gt;</code> and named "
    "<code>each-project/</code>. Real paths, names and ids from the sampled file "
    "are never published.</li>"
    "<li><strong>An array is a leaf</strong> explained on its parent's page, "
    "unless its items are objects: then the array gets a folder that explains "
    "the item fields.</li>"
    "<li><strong>Types and presence</strong> are measured on one real file: "
    "<em>in 11 of 72</em> means the key appears in 11 of the 72 entries of the "
    "map it sits in.</li>"
    "<li><strong>Badges</strong>: <span class=\"src\">docs</span> from "
    "Anthropic's documentation, <span class=\"src\">binary</span> read from the "
    "2.1.280 program, <span class=\"recon\">inferred</span> from a key's name, "
    "shape and surrounding code when the program no longer uses it.</li>"
    "</ul>"
), id="reading")

ROOT_WHERE = P("Where the file lives", (
    "<p>The path is resolved once per process and then fixed "
    "<span class=\"src\">binary</span>:</p>"
    "<ul>"
    "<li>By default <code>~/.claude.json</code>, next to <code>~/.claude/</code> and "
    "not inside it.</li>"
    "<li>With <code>CLAUDE_CONFIG_DIR=/x</code>, it is <code>/x/.claude.json</code>. "
    "Even <code>CLAUDE_CONFIG_DIR=~/.claude</code> moves it, to "
    "<code>~/.claude/.claude.json</code>.</li>"
    "<li>A legacy <code>.config.json</code> in the config home "
    "(<code>$CLAUDE_CONFIG_DIR</code>, else <code>~/.claude</code>) wins if it exists.</li>"
    "<li><code>CLAUDE_CODE_CUSTOM_OAUTH_URL</code> switches the name to "
    "<code>.claude-custom-oauth.json</code>.</li>"
    "</ul>"
    "<p>Because the path is fixed at startup, set <code>CLAUDE_CONFIG_DIR</code> in "
    "the environment that launches Claude Code, not in a settings file's "
    "<code>env</code> block. Backups go to <code>backups/</code> in the config home.</p>"
), id="where")

ROOT_WRITES = P("How Claude Code writes it", (
    "<p>Each process reads the file once at startup and keeps it in memory. A "
    "one-second <code>fs.watchFile</code> poll reloads it when another process "
    "changes it, unless this process has a write pending <span class=\"src\">binary</span>.</p>"
    "<p>Every change is a function applied to the current state, queued per file "
    "and run under a lock: the directory <code>~/.claude.json.lock</code> "
    "(proper-lockfile), stale after 10 seconds and refreshed every 5. A busy lock "
    "is retried at 200 ms, doubling to 4 s, with jitter: 10 to 20 seconds in all, "
    "or 1.5 seconds during the first 30 seconds of startup. Under the lock the "
    "save:</p>"
    "<ol>"
    "<li>re-reads the file and applies the change to what it finds, so processes "
    "changing different keys do not clobber each other;</li>"
    "<li>puts back any <code>projects</code> entry the change left out, so no "
    "normal save deletes a project;</li>"
    "<li>strips ten retired keys and drops keys equal to their defaults;</li>"
    "<li>copies the current file to <code>backups/.claude.json.backup.&lt;ms&gt;</code> "
    "if the newest backup is at least a minute old, keeping five;</li>"
    "<li>writes two-space JSON to a temp file, fsyncs it and renames it over the "
    "original. A new file gets mode 0600.</li>"
    "</ol>"
    "<p>If the lock cannot be had, the save falls back to an unlocked "
    "read-modify-write, in which the last writer wins for the whole file. It "
    "skips that fallback when the lock is merely busy and the change touches only "
    "counters, caches or per-project session stats, and it refuses outright when "
    "the fresh read is unreadable or has lost the login "
    "(<code>oauthAccount</code>, <code>hasCompletedOnboarding</code>) that memory "
    "still has. At exit, per-project stats and plugin usage are written "
    "synchronously, without the lock or a backup.</p>"
    "<p>The file must be strict JSON. If it is not, <code>-p</code> and SDK runs "
    "exit with code 1; an interactive start shows a \"Configuration error\" dialog "
    "offering to exit or reset to defaults. A <code>.corrupted.&lt;ms&gt;</code> "
    "copy is kept, and restoring a backup is a manual <code>cp</code>. If the file "
    "breaks while a session runs, that session's next locked save rewrites it "
    "from memory.</p>"
), id="writes")

ROOT_MIGRATIONS = P("Migrations that run before every command", (
    "<p>Before any command runs, <code>-p</code> and SDK processes included, "
    "Claude Code checks <code>migrationVersion</code>. If it is not 14, it runs "
    "the thirteen migrations below and writes 14 only if every migration that "
    "writes settings succeeded; otherwise the set runs again at the next start "
    "<span class=\"src\">binary</span>. Several of them edit "
    "<code>~/.claude/settings.json</code>, not just this file, so a host that "
    "generates the user settings file should expect Claude Code to change it the "
    "first time a new version runs.</p>"
    "<ol>"
    "<li>An unprotected <code>autoUpdates: false</code> becomes "
    "<code>env.DISABLE_AUTOUPDATER=\"1\"</code> in user settings; both update keys are deleted here.</li>"
    "<li><code>bypassPermissionsModeAccepted</code> becomes "
    "<code>skipDangerousModePermissionPrompt: true</code> in user settings and is deleted here.</li>"
    "<li>The Pro-to-Opus default reset stamps <code>opusProMigrationComplete</code>.</li>"
    "<li>A <code>sonnet[1m]</code> model setting is pinned to Sonnet 4.5 1M; stamps <code>sonnet1m45MigrationComplete</code>.</li>"
    "<li>Opus 4 and 4.1 model ids in settings become <code>opus</code>.</li>"
    "<li>Sonnet 4.5 ids become <code>sonnet</code> or <code>sonnet[1m]</code>.</li>"
    "<li><code>opus</code> becomes <code>opus[1m]</code> where the account is eligible.</li>"
    "<li>An alias-table migration whose table is empty in this build.</li>"
    "<li><code>claude-fable-5</code> ids become <code>fable</code> or <code>fable[1m]</code>.</li>"
    "<li><code>replBridgeEnabled</code> becomes <code>remoteControlAtStartup</code>.</li>"
    "<li>The sixteen keys that moved to settings are copied into user settings "
    "when valid, not default, and not already set there. The copies here stay.</li>"
    "<li><code>seenNotifications</code> is built from legacy impression counters.</li>"
    "<li><code>skipAutoPermissionPrompt</code> is cleared once so the auto-mode "
    "default offer can show; stamps <code>hasResetAutoModeOptInForDefaultOffer</code>.</li>"
    "</ol>"
    "<p>Two steps run at every start regardless of the version: a project's "
    "legacy <code>.mcp.json</code> approval lists move from its entry here into "
    "its <code>.claude/settings.local.json</code>, and a legacy "
    "<code>cachedChangelog</code> key moves into "
    "<code>~/.claude/cache/changelog.md</code>.</p>"
), id="migrations")

ROOT_HOST = P("What a host should do with it", (
    "<ol>"
    "<li><strong>Give each workspace its own <code>CLAUDE_CONFIG_DIR</code>.</strong> "
    "Identity (<code>userID</code>, <code>machineID</code>), trust and the "
    "<code>projects</code> map then stay per workspace, and no process re-parses "
    "a file that dozens of others rewrite. Anthropic's own self-hosted runner "
    "gives every session its own config directory <span class=\"src\">binary</span>, "
    "and the SDK hosting guide recommends one per tenant "
    "[<a href=\"https://code.claude.com/docs/en/agent-sdk/hosting\">docs: hosting</a>].</li>"
    "<li><strong>Seed decisions before the first process starts.</strong> "
    "<code>hasCompletedOnboarding: true</code> skips first-run onboarding, which "
    "otherwise runs even with valid credentials; "
    "<code>projects[&lt;repo root&gt;].hasTrustDialogAccepted: true</code> with the "
    "exact key trusts the workspace, including for the grants a repository makes "
    "itself; <code>remoteDialogSeen: true</code> skips the Remote Control "
    "explainer. Theme and <code>skipDangerousModePermissionPrompt</code> belong in "
    "<code>settings.json</code> now, not here.</li>"
    "<li><strong>Do not template identity or account keys.</strong> Leave out "
    "<code>userID</code>, <code>machineID</code>, <code>remoteControlMachineId</code>, "
    "<code>summonSidKey</code> and <code>oauthAccount</code>; Claude Code generates "
    "or fetches them.</li>"
    "<li><strong>Edit a live file under the same lock.</strong> Create the "
    "<code>~/.claude.json.lock</code> directory, re-read, change, write a temp "
    "file and rename it, then remove the directory. An atomic rename without the "
    "lock can still lose a concurrent save, or be lost to one.</li>"
    "<li><strong>Pre-create the file.</strong> The lock needs the file to exist, so "
    "the very first save into an empty config home is unlocked; a file holding "
    "<code>{}</code> avoids that <span class=\"recon\">inferred</span>.</li>"
    "<li><strong>Treat it as a secret.</strong> It can hold your email, name and "
    "organization, MCP URLs and headers with tokens in them, the last 20 "
    "characters of approved API keys, and, from older releases, the first prompt "
    "of a project's last session.</li>"
    "</ol>"
), id="host")


# ---------------------------------------------------------------------------
# Top-level object nodes (filled in below; stubs are replaced as research lands)
# ---------------------------------------------------------------------------

O = {}


def o(node):
    O[node["key"]] = node
    return node


def stub(key, type, summary):
    return o(N(key, type, summary, lede=summary))


o(PROJECTS)
o(mcp_servers_node("user"))


# ---------------------------------------------------------------------------
# Root assembly
# ---------------------------------------------------------------------------

PRESENT_GROUPS = [
    ("Projects and trust", "projects",
     "Decisions that change behaviour, per project root.",
     ["projects", "githubRepoPaths"]),
    ("MCP servers", "mcp",
     "Your own MCP servers and which claude.ai connectors ever connected.",
     ["mcpServers", "claudeAiMcpEverConnected"]),
    ("Onboarding and answered dialogs", "onboarding",
     "One-time flows that stay done once these are set. A host seeds the first two.",
     ["hasCompletedOnboarding", "lastOnboardingVersion", "remoteDialogSeen",
      "hasCompletedClaudeInChromeOnboarding", "hasSeenTasksHint"]),
    ("Preferences", "preferences",
     "Choices you made, or that Claude Code remembered for you.",
     ["theme", "claudeInChromeDefaultEnabled", "deepLinkTerminal",
      "unpinOpus47LaunchEffort", "unpinOpus48LaunchEffort", "unpinFable5LaunchEffort"]),
    ("Account and organization", "account",
     "Caches of what Anthropic's servers said about your account and organization.",
     ["oauthAccount", "cachedArtifactRoster", "claudeCodeFirstTokenDate",
      "cachedExtraUsageDisabledReason", "penguinModeOrgEnabled",
      "groveConfigCache", "passesEligibilityCache"]),
    ("Flags and experiments", "flags",
     "Remote configuration: feature flags, gates, experiment assignments and client data.",
     ["cachedGrowthBookFeatures", "cachedGrowthBookFeaturesAt",
      "cachedExperimentFeatures", "cachedExperimentData", "clientDataCacheSlots"]),
    ("Models", "models",
     "What the servers said about models: extra options, costs, access, defaults.",
     ["additionalModelOptionsCache", "additionalModelOptionsAnsweredAt",
      "additionalModelCostsCache", "modelAccessCache", "orgModelDefaultCache",
      "autoCompactWindowsCache"]),
    ("Identity", "identity",
     "Random ids generated on this machine, and when it first ran.",
     ["userID", "machineID", "firstStartTime"]),
    ("Tips, notices and upsells", "tips",
     "Counters and timestamps that pace what Claude Code shows you.",
     ["numStartups", "tipsHistory", "tipLifetimeShownCounts", "lastShownEmergencyTip",
      "seenNotifications", "feedbackSurveyState", "subscriptionNoticeCount",
      "passesUpsellSeenCount", "hasVisitedPasses", "passesLastSeenRemaining",
      "remoteControlUpsellSeenCount", "fullscreenUpsellSeenCount",
      "promptQueueUseCount", "btwUseCount", "lastPlanModeUse"]),
    ("Usage and session bookkeeping", "usage",
     "Per-name usage counts that drive skill ranking and plugin review, and the Remote Control sessions this machine opened.",
     ["skillUsage", "pluginUsage", "replBridgePlaceholders"]),
    ("Install, updates and migrations", "install",
     "How this copy was installed, what it has already migrated, and one-time setup.",
     ["installMethod", "autoUpdates", "autoUpdatesProtectedForNative",
      "lastReleaseNotesSeen", "changelogLastFetched", "closedIssuesLastChecked",
      "migrationVersion", "sonnet1m45MigrationComplete", "opusProMigrationComplete",
      "hasResetAutoModeOptInForDefaultOffer", "officialMarketplaceAutoInstallAttempted",
      "officialMarketplaceAutoInstalled", "cachedChromeExtensionInstalled",
      "appleTerminalSetupInProgress", "appleTerminalBackupPath", "optionAsMetaKeyInstalled"]),
    ("Unread", "unread",
     "Keys no installed build reads: ten that none of 2.1.183 through 2.1.281 mentions, and two that 2.1.280 only deletes or resets.",
     ["anonymousId", "sonnet45MigrationComplete", "opus45MigrationComplete",
      "thinkingMigrationComplete", "effortCalloutV2Dismissed", "cachedStatsigGates",
      "s1mAccessCache", "hasShownOpus45Notice", "overageCreditGrantCache", "toolUsage",
      "showSpinnerTree", "hasAvailableSubscription"]),
]

ABSENT_GROUPS = [
    ("Absent here: preferences", "absent-prefs",
     "Keys with a <code>/config</code> row or a documented meaning. Most are absent because they hold their default; "
     "sixteen of them now live in <code>settings.json</code> and are read here only as a fallback.", "prefs"),
    ("Absent here: credentials, consent and machine ids", "absent-secrets",
     "Keys that hold a secret, an id or a consent. A template must not carry them.", "secrets"),
    ("Absent here: one-time hints and dialogs", "absent-dialogs",
     "Flags that stop a hint or dialog from coming back.", "dialogs"),
    ("Absent here: bookkeeping, caches and counters", "absent-counters",
     "Written automatically when the feature behind them runs.", "counters"),
    ("Absent here: retired and inert keys", "absent-retired",
     "Keys 2.1.280 strips on save, migrates away, or never reads.", "retired"),
]


def build_root():
    rows_for = {}
    rows_for.update(S)
    rows_for.update(O)
    groups = []
    seen = set()
    for title, gid, intro, keys in PRESENT_GROUPS:
        rows = []
        for k in keys:
            if k not in rows_for:
                raise KeyError(f"no row for top-level key {k}")
            rows.append(rows_for[k])
            seen.add(k)
        groups.append(G(title, rows, intro=intro, id=gid))
    missing = set(rows_for) - seen
    if missing:
        raise KeyError(f"top-level rows not placed in a group: {sorted(missing)}")
    for title, gid, intro, cat in ABSENT_GROUPS:
        groups.append(G(title, ABSENT[cat], intro=intro, id=gid))
    return N(
        "~/.claude.json", "object",
        "Claude Code's global state file, key by key.",
        folder="",
        title="~/.claude.json, key by key",
        h1="~/.claude.json, key by key",
        description=(
            "Every key of Claude Code's global state file ~/.claude.json, measured on one real file and "
            "read from the Claude Code 2.1.280 binary: one page per object, recursively, with what each "
            "key holds, who writes it, and what reads it."
        ),
        chips=["82 top-level keys in the sample", "24 folders at the top level",
               "129 more keys the binary knows", "Claude Code 2.1.280"],
        lede=(
            "Claude Code keeps one JSON file of its own state next to "
            "<code>~/.claude/</code>. This explorer takes a real one apart: every "
            "top-level key it held on 28 September 2026, every object inside them "
            "down to the last level, and the keys the 2.1.280 binary can add that "
            "this file did not have. It is the reference for the section "
            "<a href=\"../#global-state\">The state file</a> of "
            "<a href=\"../\">Anatomy of a Claude Code session</a>."
        ),
        before=[ROOT_WHAT, ROOT_READING, ROOT_WHERE, ROOT_WRITES, ROOT_MIGRATIONS, ROOT_HOST],
        groups=groups,
        after=[P("Folder map", "", id="map", tree=True)],
        toc=True,
        filter=True,
    )


# ---------------------------------------------------------------------------
# Top-level objects: the real pages
# ---------------------------------------------------------------------------

LOGOUT = "Deleted by <code>/logout</code>, which also runs before a login writes a different account."
BOOTSTRAP = ("Filled from <code>GET /api/claude_cli/bootstrap</code>, which runs in the "
             "background at startup, after <code>/login</code>, and when the model changes.")
LEGACY_OBJ = ("No Claude Code build installed on this machine references this key, so "
              "its meaning is inferred from its name and shape. An older release wrote "
              "it; saves keep keys they do not know, so it stays.")

# --- projects and trust -----------------------------------------------------

o(N("githubRepoPaths", "object · map",
    "Where your local checkouts of each GitHub repository live, most recent first.",
    presence="8 entries",
    chips=["object", "map keyed by owner/repo", "8 entries in the sample", "paths are personal"],
    lede=(
        "An index of your local clones. When an interactive session starts in a "
        "repository whose git remote is on github.com, Claude Code records the "
        "repository's root under its lowercased <code>owner/repo</code>, moving it to "
        "the front. Other hosts, GitHub Enterprise included, are not tracked. No TTL, "
        "no size cap."
    ),
    groups=[G("Entries", [
        L("owner/repo", "array of string",
          "Absolute paths (realpath of the git root) holding a clone of that repository, "
          "most recently used first. Read by <code>--teleport</code>, which offers these "
          "checkouts when you resume a cloud session outside its repository and drops "
          "paths that no longer hold it, and by deep-link launches that name a repository, "
          "which open in the first existing checkout.",
          placeholder=True),
    ])],
))

# --- MCP --------------------------------------------------------------------

S["claudeAiMcpEverConnected"] = L(
    "claudeAiMcpEverConnected", "array of string",
    "Names of claude.ai connectors (MCP servers configured in your claude.ai account, "
    "shown as \"claude.ai &lt;name&gt;\") that ever connected successfully from Claude "
    "Code. Append-only. <code>/mcp</code> folds connectors that were never connected "
    "under \"Show unused connectors\" instead of listing them as failures.",
    notes="The names reveal which services you connected, but carry no credentials.", badge="docs")

o(N("replBridgePlaceholders", "object · map",
    "Remote Control sessions this machine created, kept so a later run can archive the ones a crash orphaned.",
    presence="empty",
    chips=["object", "map keyed by remote session id", "empty in the sample"],
    lede=(
        "Bookkeeping for Remote Control, whose internal name was \"REPL bridge\". Each "
        "claude.ai session that a local interactive session opens is recorded with the "
        "process that owns it. Fifteen seconds after Remote Control starts, a sweep "
        "looks at records whose process is gone: a remote session that was never used "
        "is archived, and the record is dropped either way. At most 20 records are "
        "kept; records older than 30 days are dropped. Empty is the normal state."
    ),
    groups=[G("Entries", [
        N("session id", "object", "The process that created one remote session.",
          folder="each-session", placeholder=True,
          chips=["object", "3 fields"],
          lede=("One record per open Remote Control session. The key is the claude.ai "
                "session id (<code>session_…</code> or <code>cse_…</code>), an identifier "
                "but not a credential."),
          groups=[G("Fields", [
              L("pid", "int", "Process id that created the remote session."),
              L("procStart", "string", "Start-time token of that process, used to tell a reused pid from the original. Optional."),
              L("createdAt", "int", "When the record was written, epoch ms."),
          ])]),
    ])],
))

# --- account and organization -------------------------------------------------

o(N("oauthAccount", "object",
    "The profile of the Claude account you signed in with: identity, organization, billing, roles, trial.",
    chips=["object", "20 fields", "personal data", "refreshed daily"],
    lede=(
        "The account half of your login, fetched from Anthropic after "
        "<code>/login</code>. The tokens are not here: on macOS they sit in the "
        "Keychain, elsewhere in <code>~/.claude/.credentials.json</code>. Most readers "
        "see this object only while Anthropic OAuth is the active auth, so it goes "
        "quiet under <code>ANTHROPIC_API_KEY</code> or a third-party provider. " + LOGOUT
    ),
    before=[P(None, (
        "<p>Three sources fill it: <code>/api/oauth/profile</code> (identity, names, "
        "billing, trial), <code>/api/oauth/claude_cli/roles</code> (roles, organization "
        "name) and the bootstrap endpoint (organization type, rate-limit tiers). The "
        "profile is refetched at startup when it is older than 24 hours or missing "
        "fields. The email address is also placed in Claude's context every session, "
        "in a <code>userEmail</code> block <span class=\"src\">binary</span>. A save "
        "that would lose this object while memory still holds it is refused or "
        "repaired from memory.</p>"
    ))],
    groups=[
        G("Identity", [
            L("accountUuid", "string", "Your Anthropic account id. Keys <code>groveConfigCache</code> and other per-account caches."),
            L("emailAddress", "string", "Your account email. Shown in <code>/status</code> and \"Logged in as\", and placed in Claude's context each session."),
            L("displayName", "string", "Profile display name."),
            L("fullName", "string", "Profile full name."),
            L("accountCreatedAt", "string", "When the account was created, ISO 8601."),
            L("profileFetchedAt", "int", "When the profile was last fetched, epoch ms; drives the 24-hour refresh."),
        ]),
        G("Organization and roles", [
            L("organizationUuid", "string", "The active organization's id. Keys the per-organization caches; Remote Control needs it."),
            L("organizationName", "string", "The organization's name. For a personal plan it is often built from your own name."),
            L("organizationType", "string", "Plan family from bootstrap: <code>claude_pro</code>, <code>claude_max</code>, <code>claude_team</code>, <code>claude_enterprise</code>. Not read elsewhere in 2.1.280."),
            L("organizationRole", "string", "Your role in the organization; code compares <code>admin</code>, <code>billing</code>, <code>owner</code>, <code>primary_owner</code>."),
            L("workspaceRole", "null", "Console workspace role when there is one; code compares <code>workspace_admin</code> and <code>workspace_billing</code>."),
            L("organizationRateLimitTier", "string", "The organization's rate-limit tier from bootstrap. Not read elsewhere in 2.1.280."),
            L("userRateLimitTier", "null", "Per-user rate-limit tier, when the server sets one. Not read elsewhere in 2.1.280."),
            L("seatTier", "null", "Organization seat tier, when set; code compares <code>enterprise_usage_based</code>."),
        ]),
        G("Billing and trial", [
            L("billingType", "string", "How the organization pays: usage-based, a Stripe or cloud-marketplace subscription, or an app-store subscription. Decides whether usage credits can be provisioned."),
            L("subscriptionCreatedAt", "string", "When the subscription started, ISO 8601. Sent as a feature-flag targeting attribute."),
            L("hasExtraUsageEnabled", "bool", "The organization has usage credits (paid usage beyond the plan) turned on; changes rate-limit messages."),
            L("claudeCodeTrialEndsAt", "null", "End of a Claude Code Pro trial, ISO 8601, when one is running."),
            L("claudeCodeTrialDurationDays", "null", "Trial length the server grants, in days."),
            N("ccOnboardingFlags", "object",
              "Organization-level Claude Code onboarding flags from the profile.",
              presence="empty in the sample",
              chips=["object", "empty in the sample"],
              lede=("A map of flag name to value that the profile endpoint returns for "
                    "the organization. Empty here."),
              groups=[G("Entries", [
                  L("e10", "bool",
                    "The one flag 2.1.280 reads: whether the organization is eligible for a "
                    "Claude Code Pro trial.", presence="absent here"),
                  L("flag name", "any",
                    "Any other flag the server sends; 2.1.280 does not read them.", placeholder=True),
              ])]),
        ]),
    ],
))

o(N("cachedArtifactRoster", "object",
    "Which Artifact runtime version and capabilities your account can use, cached for 24 hours.",
    chips=["object", "5 fields", "account-scoped"],
    lede=(
        "A cache of the artifacts service's contract for the signed-in account "
        "(<code>GET /api/frame/contract/latest</code>): the runtime version and the "
        "capability names it offers, such as <code>assets</code>. It is used until the "
        "live roster is fetched in the current process, and ignored unless its account "
        "and organization match the current login. A 401 or 403 writes "
        "<code>artifactRosterDenied</code> instead. " + LOGOUT
    ),
    groups=[G("Fields", [
        L("accountUuid", "string", "Account the roster was fetched for (lowercased)."),
        L("organizationUuid", "string", "Organization it was fetched for, or null."),
        L("version", "string", "Artifact runtime contract version."),
        L("capabilities", "array of string", "Capability names the contract offers; <code>assets</code> allows artifact asset uploads. At most 256."),
        L("fetchedAt", "int", "Fetch time, epoch ms; fresh for 24 hours."),
    ])],
))

o(N("s1mAccessCache", "object · map",
    "Legacy. By its name, whether the account could use a Sonnet 1M model option.",
    presence="2 entries", badge="inferred",
    chips=["object", "map, 2 entries", "not referenced by 2.1.280"],
    lede=(LEGACY_OBJ + " A migration in 2.1.280 rewrites an old <code>sonnet[1m]</code> "
          "model setting, which confirms such an option existed."),
    groups=[G("Entries", [
        N("account or organization id", "object",
          "One cached access answer, keyed by an id the code no longer shows.",
          folder="each-entry", placeholder=True, badge="inferred",
          chips=["object", "3 fields"],
          lede="The key is probably an account or organization id, like the other per-account caches here; unverified.",
          groups=[G("Fields", [
              L("hasAccess", "bool", "Presumably: the account had access to the Sonnet 1M option.", badge="inferred"),
              L("hasAccessNotAsDefault", "bool", "Presumably: access existed but not as the default model.", badge="inferred"),
              L("timestamp", "int", "When the entry was cached, epoch ms by analogy with the other caches.", badge="inferred"),
          ])]),
    ])],
))

o(N("groveConfigCache", "object · map",
    "Per account: whether the consumer-terms update flow (\"Help improve our AI models\") applies.",
    presence="3 entries",
    chips=["object", "map keyed by account id", "24-hour TTL"],
    lede=(
        "\"Grove\" is the internal name of the consumer terms and privacy update that "
        "asks Pro and Max users whether their chats may be used to improve models. This "
        "cache holds only whether the flow is on for an account "
        "(<code>/api/claude_code_grove</code>); your actual choice is fetched separately "
        "and not stored here. When true, interactive startup may show the \"Updates to "
        "Consumer Terms and Policies\" dialog, and <code>-p</code> may print a notice "
        "and exit if action is required."
    ),
    groups=[G("Entries", [
        N("account id", "object", "The cached answer for one account.",
          folder="each-account", placeholder=True,
          chips=["object", "2 fields"],
          lede=("Keyed by <code>oauthAccount.accountUuid</code>. Missing: the dialog is "
                "skipped this session and a fetch runs in the background. Older than 24 "
                "hours: used, and refreshed in the background."),
          groups=[G("Fields", [
              L("grove_enabled", "bool", "Whether the policy-update flow is on for this account."),
              L("timestamp", "int", "When the entry was written, epoch ms."),
          ])]),
    ])],
))

REFERRAL = N("referral_code_details", "object or null",
             "Your guest-pass referral code and link, or null.",
             presence="object in 2 of 3, null in 1",
             chips=["object or null", "3 fields", "personal"],
             lede=("The referral code the <code>/passes</code> screen shows. The code and "
                   "link identify you to whoever redeems them."),
             groups=[G("Fields", [
                 L("campaign", "string", "Campaign id, such as <code>claude_code_guest_pass</code>."),
                 L("code", "string", "Your referral code."),
                 L("referral_link", "string", "The shareable link for that code."),
             ])])
REWARD = N("referrer_reward", "object or null",
           "The usage credit you earn per redeemed pass, or null.",
           presence="object in 2 of 3, null in 1",
           chips=["object or null", "2 fields"],
           lede="When present, <code>/passes</code> adds \"and earn usage credits\" to its description.",
           groups=[G("Fields", [
               L("amount_minor_units", "int", "Reward amount in minor currency units, such as cents."),
               L("currency", "string", "ISO 4217 currency code."),
           ])])

o(N("passesEligibilityCache", "object · map",
    "Per organization: whether you can share Claude Code guest passes, and your referral details.",
    presence="3 entries",
    chips=["object", "map keyed by organization id", "24-hour TTL", "personal"],
    lede=(
        "The response of the guest-pass eligibility endpoint for the "
        "<code>claude_code_guest_pass</code> campaign, stored verbatim with a timestamp. "
        "It decides whether <code>/passes</code> is visible, what its screen shows, and "
        "whether the startup banner appears (see <code>passesUpsellSeenCount</code>). "
        "Fetched in the background for Pro and Max subscribers."
    ),
    groups=[G("Entries", [
        N("organization id", "object", "One organization's eligibility answer.",
          folder="each-organization", placeholder=True,
          chips=["object", "up to 8 fields"],
          lede="Keyed by <code>oauthAccount.organizationUuid</code>. A stale entry is used while a refresh runs.",
          groups=[G("Fields", [
              L("eligible", "bool", "The account can share guest passes."),
              L("remaining_passes", "int or null", "Passes left to share; compared with <code>passesLastSeenRemaining</code>."),
              REFERRAL,
              REWARD,
              L("limit", "int", "Pass limit from this endpoint; not read by 2.1.280, which takes the limit from the redemptions endpoint.", presence="in 1 of 3"),
              L("share_link", "string", "Stored from the response; not read by 2.1.280.", presence="in 1 of 3"),
              L("terms_url", "string", "Stored from the response; not read by 2.1.280.", presence="in 1 of 3"),
              L("timestamp", "int", "When the response was cached, epoch ms."),
          ])]),
    ])],
))

o(N("overageCreditGrantCache", "object · map",
    "Legacy. A per-organization cache of usage-credit grant eligibility, since renamed.",
    presence="2 entries", badge="inferred",
    chips=["object", "map, 2 entries", "not referenced by 2.1.280"],
    lede=(LEGACY_OBJ + " Its inner <code>info</code> object has exactly the fields 2.1.280 "
          "now caches from <code>/api/oauth/organizations/:orgUUID/overage_credit_grant</code> "
          "under another key, <code>fotwEligibilityCache</code>, for a \"feature of the week\" "
          "promotion that grants usage credits."),
    groups=[G("Entries", [
        N("organization id", "object", "One organization's grant answer.",
          folder="each-organization", placeholder=True, badge="inferred",
          chips=["object", "2 fields"],
          lede="Probably keyed by organization id, as its successor is.",
          groups=[G("Fields", [
              N("info", "object", "The eligibility answer.",
                chips=["object", "5 fields"],
                lede="The same five fields the successor cache stores.",
                badge="inferred",
                groups=[G("Fields", [
                    L("eligible", "bool", "The organization is eligible for a grant."),
                    L("available", "bool", "A grant is available now."),
                    L("granted", "bool", "A grant was already given."),
                    L("amount_minor_units", "int or null", "Credit amount in minor currency units."),
                    L("currency", "string or null", "ISO 4217 code of that amount."),
                ])]),
              L("timestamp", "int", "When cached, epoch ms."),
          ])]),
    ])],
))

# --- flags and experiments ---------------------------------------------------

def NESTED(owner, levels=1):
    """A nested object inside remote configuration: one generic folder per level
    of nesting observed in the sample."""
    rows = [L("field", "any", f"A field of that nested object, defined by the {owner}.", placeholder=True)]
    if levels > 1:
        rows.append(NESTED(owner, levels - 1))
    return N("field", "object",
             "A field whose value is itself an object, such as the settings of one surface or the copy of one screen.",
             folder="each-nested-object", placeholder=True,
             chips=["object", f"fields defined by the {owner}"],
             lede=(f"Configuration nests further in some {owner}s: a group of numbers per "
                   "surface, or the labels of one screen. Its fields are defined by the "
                   f"{owner}, like the level above, and are not enumerated here."),
             groups=[G("Fields", rows)])



o(N("cachedGrowthBookFeatures", "object · map",
    "The disk copy of every feature flag Anthropic's flag service evaluated for you: 724 here.",
    presence="724 entries",
    chips=["object", "map keyed by flag name", "724 flags in the sample", "refreshed every 6 h"],
    lede=(
        "Claude Code's feature flags come from GrowthBook, evaluated on Anthropic's "
        "servers for your device, account and organization. The last answer is kept "
        "here, and every flag read is served from this map until the current process "
        "has fetched a fresh one, which is how flags work at startup, offline and before "
        "login. The whole map is replaced on each successful fetch, together with "
        "<code>cachedExperimentFeatures</code>, <code>cachedExperimentData</code> and "
        "<code>cachedGrowthBookFeaturesAt</code>."
    ),
    before=[P(None, (
        "<ul>"
        "<li><strong>When it refreshes.</strong> At startup (a fetch needs credentials, "
        "and in an interactive session, trust), every 6 hours by default, and after a "
        "login, logout or account switch. There is no expiry: stale values are used "
        "until replaced.</li>"
        "<li><strong>When it is ignored.</strong> <code>DISABLE_GROWTHBOOK</code>, and "
        "anything that turns off first-party telemetry "
        "(<code>DISABLE_TELEMETRY</code>, <code>DO_NOT_TRACK</code>, "
        "<code>CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC</code>, a third-party provider), "
        "make every flag fall back to the default written in the code. The undocumented "
        "<code>CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF</code> keeps reading this "
        "cache, without refreshing it, when telemetry is off.</li>"
        "<li><strong>Not keyed by account.</strong> After an account switch the map holds "
        "the previous account's values until the refetch lands.</li>"
        "</ul>"
        "<p>The flag names are Anthropic's internal codenames and are not listed here. "
        "In the sample, 567 values are booleans, 49 strings, 28 numbers, 12 arrays, 1 "
        "null and 67 objects.</p>"
    ))],
    groups=[G("Entries", [
        L("flag name", "bool, number, string, array or null",
          "The value the server evaluated for that flag: an on/off switch, a threshold, a "
          "list or a label. 655 of the 724.", placeholder=True),
        N("flag name", "array of object",
          "A flag whose value is a list of configuration objects; 2 of the 724.",
          folder="each-list-flag", placeholder=True,
          chips=["array of object", "items defined by each flag"],
          lede=("Two flags carry a list of small objects, such as a set of rules. The "
                "items' fields are defined by the flag and are not enumerated here."),
          groups=[G("Fields of each item", [
              L("field", "any", "A field of one item, defined by the flag.", placeholder=True),
          ])]),
        N("flag name", "object",
          "A flag whose value is a configuration object; 67 of the 724.",
          folder="each-object-flag", placeholder=True,
          chips=["object", "fields defined by each flag"],
          lede=(
              "Some flags carry a small configuration object instead of a switch: "
              "timeouts, retry counts, rollout thresholds, version gates, or the copy of "
              "an upsell. Each flag defines its own fields and the code that reads it "
              "supplies defaults, so there is no shared shape to document. The most "
              "common field is <code>enabled</code>, in 14 of the 67 objects."
          ),
          groups=[G("Fields", [
              L("field", "any",
                "A field of that flag's configuration, read only by the code behind that "
                "flag. Not enumerated here: the fields differ per flag and are Anthropic's "
                "remote configuration, not Claude Code's schema.", placeholder=True),
              NESTED("flag", levels=2),
          ])]),
    ])],
))

o(N("cachedStatsigGates", "object · map",
    "Legacy. Cached gate booleans from the feature-flag client Claude Code used before GrowthBook.",
    presence="2 entries", badge="inferred",
    chips=["object", "map, 2 entries", "not referenced by 2.1.280"],
    lede=(LEGACY_OBJ + " 2.1.280 contains no Statsig client at all; the only remnant is "
          "the old <code>~/.claude/statsig/</code> directory, which the cleanup sweep deletes."),
    groups=[G("Entries", [
        L("gate name", "bool", "A gate's cached state from the old client.", placeholder=True, badge="inferred"),
    ])],
))

S["cachedExperimentFeatures"] = L(
    "cachedExperimentFeatures", "array of string",
    "Sorted names of the flags whose value came from an A/B experiment at the last "
    "fetch; the same names as the keys of <code>cachedExperimentData</code>. Its only "
    "reader has no callers in 2.1.280, so the list is effectively write-only.")

o(N("cachedExperimentData", "object · map",
    "For each flag assigned by an experiment: the experiment, the variation and the value.",
    presence="11 entries",
    chips=["object", "map keyed by flag name", "11 entries in the sample"],
    lede=(
        "Written with <code>cachedGrowthBookFeatures</code>. It lets Claude Code log a "
        "correct experiment exposure when a flag is served from this disk cache before "
        "the fresh answer arrives: once the fresh answer confirms the same experiment "
        "and variation, the exposure is sent to Anthropic's event logging."
    ),
    groups=[G("Entries", [
        N("flag name", "object", "One flag's experiment assignment.",
          folder="each-flag", placeholder=True,
          chips=["object", "3 fields"],
          lede="The key is a flag name, also listed in <code>cachedExperimentFeatures</code>.",
          groups=[G("Fields", [
              L("experimentId", "string", "The experiment's key."),
              L("variationId", "int", "Index of the assigned variation, from 0."),
              N("value", "bool, string or object",
                "The value this variation assigns to the flag.",
                chips=["bool in 7 of 11", "object in 2", "string in 2"],
                lede=(
                    "Whatever the assigned variation sets the flag to. Booleans and "
                    "strings are the whole answer. The two object values in the sample "
                    "are configuration for upsell and onboarding experiments; like "
                    "object-valued flags, their fields are defined per experiment and "
                    "are not enumerated here."
                ),
                groups=[G("Fields", [
                    L("field", "any", "A field of that experiment's configuration.", placeholder=True),
                    NESTED("experiment"),
                ])]),
          ])]),
    ])],
))

CEDAR = N("cedar_lagoon", "object · map",
          "A server-sent map of model family to boolean.",
          chips=["object", "map keyed by model family", "in 12 of 12 slots"],
          lede=("A per-model-family switch the server sends. No code in 2.1.280 reads it "
                "by name, so what the booleans turn on is not recoverable from the binary."),
          badge="inferred",
          groups=[G("Entries", [
              L("model family", "bool", "The switch for one model family.", placeholder=True, badge="inferred"),
          ])])

o(N("clientDataCacheSlots", "object · map",
    "Server-sent client configuration, one slot per surface, model, version and organization.",
    presence="12 entries",
    chips=["object", "map keyed by slot hash", "at most 12 slots"],
    lede=(
        "The bootstrap endpoint returns an opaque <code>client_data</code> map: a "
        "per-model configuration channel alongside the feature flags, whose keys are "
        "internal codenames. Claude Code keeps the answer per slot. The slot key is "
        "<code>bi1-</code> plus the first 16 hex characters of a SHA-256 over the "
        "entrypoint, model, Claude Code version and organization id, so an upgrade "
        "starts new slots. " + BOOTSTRAP + " " + LOGOUT
    ),
    before=[P(None, (
        "<p>At most 12 slots are kept, newest first. A slot older than 24 hours is "
        "rewritten on the next bootstrap. When the exact slot is missing, a slot for the "
        "same entrypoint, model and organization written within 7 days is used "
        "instead.</p>"
    ))],
    groups=[G("Entries", [
        N("slot key", "object", "One cached client_data answer and what it was fetched for.",
          folder="each-slot", placeholder=True,
          chips=["object", "5 fields"],
          lede="The slot's payload and the four inputs its key was hashed from, minus the version.",
          groups=[G("Fields", [
              L("at", "int", "When the slot was written, epoch ms."),
              L("entrypoint", "string", "Surface it was fetched for, such as <code>cli</code>, <code>sdk-ts</code> or <code>claude-vscode</code>."),
              L("model", "string", "Canonical model id it was fetched for."),
              L("org", "string", "Organization id it was fetched for, or null."),
              N("data", "object", "The client_data map itself.",
                chips=["object", "codename keys", "2 to 5 keys in the sample"],
                lede=(
                    "Keys are internal codenames, and most are opaque to the client. Two "
                    "have a visible use in 2.1.280."
                ),
                groups=[G("Fields", [
                    L("atis", "string",
                      "An opaque assignment token sent back as the <code>x-cc-atis</code> "
                      "header on API requests; a different <code>x-cc-atis-current</code> in "
                      "a response triggers a refetch.", presence="in 1 of 12"),
                    L("convolute_arcades", "bool",
                      "When true for a model, arms an automatic fallback that retries on "
                      "another model after certain refusals. The exact routing is not fully "
                      "clear from the code.", presence="in 1 of 12", badge="inferred"),
                    L("cedar_basin", "string", "An opaque server value; nothing in 2.1.280 reads it by name.", presence="in 12 of 12", badge="inferred"),
                    CEDAR,
                    L("experimentKey", "string", "An opaque server value; nothing in 2.1.280 reads it by name.", presence="in 1 of 12", badge="inferred"),
                ])]),
          ])]),
    ])],
))

# --- models -------------------------------------------------------------------

o(N("additionalModelOptionsCache", "array of object",
    "Extra choices the server adds to the /model picker for your account.",
    presence="1 item",
    chips=["array of object", "1 item in the sample"],
    lede=(
        "Model options the server offers this account or organization beyond the "
        "built-in list. They are appended to the <code>/model</code> picker and make "
        "those model ids count as valid. " + BOOTSTRAP + " A response that omits the "
        "field keeps the previous list. " + LOGOUT
    ),
    groups=[G("Fields of each item", [
        L("value", "string", "The model id to select, or null."),
        L("label", "string", "The picker label; \" (disabled)\" is appended when the option cannot be chosen."),
        L("description", "string", "The picker description, sometimes prefixed with pricing and followed by the reason an option is disabled."),
        L("disabled", "bool", "Shown but not selectable. Present only when true.", presence="absent here"),
        L("promoListPrice", "string", "A struck-through list price during a launch promotion. Accepted by the reader; the bootstrap transform does not produce it.", presence="absent here"),
    ])],
))

o(N("additionalModelCostsCache", "object · map",
    "Server-provided prices for models the built-in price table does not know.",
    presence="empty",
    chips=["object", "map keyed by model id", "empty in the sample"],
    lede=(
        "Used to estimate session cost: the built-in price table first, then this map. "
        "A model in neither falls back to default pricing. Empty means every model in "
        "use is in the built-in table. " + BOOTSTRAP + " " + LOGOUT
    ),
    groups=[G("Entries", [
        N("model id", "object", "One model's prices.",
          folder="each-model", placeholder=True,
          chips=["object", "6 fields", "USD"],
          lede="Converted from the server's snake_case field names.",
          groups=[G("Fields", [
              L("inputTokens", "number", "Input price, USD per million tokens."),
              L("outputTokens", "number", "Output price, USD per million tokens."),
              L("promptCacheWriteTokens", "number", "Five-minute cache write price, USD per million tokens."),
              L("promptCacheWrite1hTokens", "number", "One-hour cache write price, USD per million tokens. Optional."),
              L("promptCacheReadTokens", "number", "Cache read price, USD per million tokens."),
              L("webSearchRequests", "number", "Price per web search request, USD; 0.01 when the server omits it."),
          ])]),
    ])],
))

S["modelAccessCache"] = L(
    "modelAccessCache", "array",
    "Per-model entitlements from the bootstrap endpoint. When populated, each item is "
    "<code>{apiName, entitled, maxEffortLevel}</code>: <code>entitled: false</code> makes "
    "that model unavailable, and <code>maxEffortLevel</code> caps the effort offered for "
    "it. Empty means no model is restricted.",
    notes="Empty in the sample, so it has no folder here.")

o(N("hasShownOpus45Notice", "object · map",
    "Legacy. By its name, which accounts were already shown the Opus 4.5 launch notice.",
    presence="3 entries", badge="inferred",
    chips=["object", "map, 3 entries", "not referenced by 2.1.280"],
    lede=(LEGACY_OBJ + " 2.1.280 strips several retired launch-notice counters on every "
          "save, but not this one."),
    groups=[G("Entries", [
        L("account or organization id", "bool", "Notice already shown for this key.", placeholder=True, badge="inferred"),
    ])],
))

# --- tips, notices and usage ---------------------------------------------------

o(N("tipsHistory", "object · map",
    "For each tip shown: the startup count when it was last shown, so cooldowns can be enforced.",
    presence="41 entries",
    chips=["object", "map keyed by tip id", "41 entries in the sample"],
    lede=(
        "Tips are the one-line hints under the spinner and at startup. Each tip has a "
        "cooldown measured in sessions: it is eligible again only when "
        "<code>numStartups</code> minus its entry here reaches that cooldown. Entries are "
        "overwritten, never pruned. <code>spinnerTipsEnabled: false</code> stops tips "
        "and with them this key."
    ),
    groups=[G("Entries", [
        L("tip id", "int",
          "The <code>numStartups</code> value when the tip was last shown: a launch count, "
          "not a timestamp. Ids are built-in tip names, <code>custom-tip-N</code> for "
          "<code>spinnerTipsOverride</code> tips, or <code>org-tip:…</code>.", placeholder=True),
    ])],
))

o(N("tipLifetimeShownCounts", "object · map",
    "How many launches each tip has been shown in, ever; enforces per-tip lifetime caps.",
    presence="15 entries",
    chips=["object", "map keyed by tip id", "15 entries in the sample"],
    lede=(
        "Incremented in the same update as <code>tipsHistory</code>, at most once per "
        "tip per launch. A tip with a lifetime cap stops once its count reaches it; some "
        "campaign tips rotate their wording by this count."
    ),
    groups=[G("Entries", [
        L("tip id", "int", "Launches in which this tip was shown.", placeholder=True),
    ])],
))

o(N("seenNotifications", "object · map",
    "Impression counts of one-off startup notices, each capped.",
    presence="empty",
    chips=["object", "map keyed by notice id", "empty in the sample"],
    lede=(
        "Each capped notice compares its count here with its cap. A one-time migration "
        "created the key, seeding it from the legacy <code>subscriptionNoticeCount</code>; "
        "an empty object is what it writes when there is nothing to carry over. Server "
        "announcements count separately, in <code>announcementImpressions</code>."
    ),
    groups=[G("Entries", [
        L("notice id", "int",
          "Times the notice was shown. Ids 2.1.280 writes: <code>subscription-switch</code> "
          "(max 3), <code>cc-ce-migrate</code> (max 3), <code>remote-control-auto-on</code> "
          "(max 3), <code>rc-active-badge</code> (max 5) and <code>sudo-npm-install</code> "
          "(max 1).", placeholder=True),
    ])],
))

o(N("feedbackSurveyState", "object",
    "When the \"How is Claude doing?\" survey was last shown, across sessions.",
    chips=["object", "1 field"],
    lede=(
        "Keeps the session-quality survey from reappearing too soon in another session "
        "or in the VS Code extension. Off with <code>CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY</code>, "
        "<code>feedbackSurveyRate: 0</code>, or the telemetry-off variables."
    ),
    groups=[G("Fields", [
        L("lastShownTime", "int",
          "When the survey was last shown or answered, epoch ms. The survey is blocked for "
          "about 28 hours after it by default."),
    ])],
))

o(N("skillUsage", "object · map",
    "How often each skill or prompt command was used, and when last.",
    presence="31 entries",
    chips=["object", "map keyed by skill name", "31 entries in the sample"],
    lede=(
        "Lifetime counts, never reset. When the skill list in Claude's context is over "
        "its character budget, skills are ranked by use, decayed by a 7-day half-life, "
        "and the least used lose their descriptions first "
        "[<a href=\"https://code.claude.com/docs/en/skills\">docs: skills</a>]. "
        "<code>/skill-doctor</code> and the <code>/plugin</code> stats tab show the "
        "same numbers."
    ),
    groups=[G("Entries", [
        N("skill name", "object", "Use count and last use of one skill.",
          folder="each-skill", placeholder=True,
          chips=["object", "2 fields"],
          lede=("The key is the skill or command name as dispatched: bare, "
                "plugin-qualified (<code>plugin:skill</code>) or nested. A second "
                "dispatch of the same skill within 60 seconds is not counted."),
          groups=[G("Fields", [
              L("usageCount", "int", "Counted dispatches since install."),
              L("lastUsedAt", "int", "Time of the last counted dispatch, epoch ms."),
          ])]),
    ])],
))

o(N("toolUsage", "object · map",
    "Legacy. Per-tool use counts from an older release.",
    presence="1 entry", badge="inferred",
    chips=["object", "map, 1 entry", "not referenced by 2.1.280"],
    lede=(LEGACY_OBJ + " Its value shape matches <code>skillUsage</code>, which suggests "
          "the same kind of lifetime counter."),
    groups=[G("Entries", [
        N("tool name", "object", "Presumably the use count and last use of one tool.",
          folder="each-tool", placeholder=True, badge="inferred",
          chips=["object", "2 fields"],
          lede="Read by no installed build.",
          groups=[G("Fields", [
              L("usageCount", "int", "Presumably lifetime uses of the tool.", badge="inferred"),
              L("lastUsedAt", "int", "Presumably the time of last use, epoch ms.", badge="inferred"),
          ])]),
    ])],
))

o(N("pluginUsage", "object · map",
    "How often each installed plugin was used, and when; drives the unused-plugin review.",
    presence="21 entries",
    chips=["object", "map keyed by plugin id", "21 entries in the sample"],
    lede=(
        "Any use of a plugin's parts counts: its skills and commands, its subagents, "
        "its MCP tools, its hooks, its LSP server. Uses are batched in memory and "
        "flushed after 60 seconds and at exit, where the write takes no lock. A "
        "user-installed marketplace plugin counts as unused after 14 days and 10 "
        "launches without use."
    ),
    groups=[G("Entries", [
        N("plugin id", "object", "Use count and last use of one plugin.",
          folder="each-plugin", placeholder=True,
          chips=["object", "3 fields"],
          lede=("The key is <code>&lt;plugin&gt;@&lt;marketplace&gt;</code>. Installing "
                "or enabling a plugin seeds its entry with a count of 0, so "
                "<code>lastUsedAt</code> proves use only when the count is above 0. "
                "Uninstalling deletes the entry."),
          groups=[G("Fields", [
              L("usageCount", "int", "Counted uses since install; 0 for a seeded entry."),
              L("lastUsedAt", "int", "Last use, or the install or re-enable time while the count is 0, epoch ms."),
              L("lastUsedNumStartups", "int", "The <code>numStartups</code> value at <code>lastUsedAt</code>."),
          ])]),
    ])],
))

ROOT = build_root()
