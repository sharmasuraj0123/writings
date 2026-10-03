#!/usr/bin/env python3
"""Benchmarks for "Where the JSON Lives". Stdlib only; writes _numbers.json.

Measures, on this machine, the cost of keeping a ~3 KB (2,879-byte) JSON state document
current under repeated small edits, five ways:
  file-rewrite (tmp + fsync + os.replace, the xo-space pattern) with and without fsync,
  JSONL append (fsync per line / per 100 lines),
  SQLite WAL: whole-document UPDATE, in-place json_set / jsonb_set, event INSERT,
  with synchronous=FULL and NORMAL, per-row and batched transactions.
Then reads: point lookup of one field, and a filter across 20,000 documents
with and without an expression index.
"""
import json, os, random, sqlite3, statistics, tempfile, time, platform, pathlib

random.seed(7)
HERE = pathlib.Path(__file__).resolve().parent
N = 1500

def doc(i=0):
    return {
        "id": f"sess-{i:06d}", "agent": random.choice(["claude_code", "codex", "hermes"]),
        "status": random.choice(["running", "idle", "done", "failed"]),
        "owner": f"user-{i % 50}", "updated_at": time.time(),
        "usage": {"input_tokens": random.randint(1, 10**6), "output_tokens": random.randint(1, 10**5),
                  "cost_usd": round(random.random() * 4, 4)},
        "todos": [{"id": k, "text": "step %d of the plan, written out at some length" % k,
                   "done": bool(k % 2)} for k in range(24)],
        "tags": ["xo", "space", "bench"], "notes": "x" * 600,
    }

BASE = doc()
SIZE = len(json.dumps(BASE).encode())

def timeit(fn, n):
    t = time.perf_counter(); fn(n); dt = time.perf_counter() - t
    return {"ops": n, "seconds": round(dt, 4), "ops_per_s": round(n / dt, 1), "us_per_op": round(dt / n * 1e6, 1)}

tmp = pathlib.Path(tempfile.mkdtemp(prefix="jsonbench-", dir=os.path.expanduser("~")))
R = {"machine": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                 "cpus": os.cpu_count(), "kernel": platform.release()},
     "doc_bytes": SIZE, "n": N, "write": {}, "read": {}}

# ---------- flat files ----------
def file_rewrite(fsync):
    path = tmp / "state.json"; d = dict(BASE)
    def run(n):
        for k in range(n):
            d["usage"]["input_tokens"] += 1; d["updated_at"] = time.time()
            fd, t = tempfile.mkstemp(dir=tmp, suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(d, f)
                if fsync: f.flush(); os.fsync(f.fileno())
            os.replace(t, path)
    return run
R["write"]["file_rewrite_fsync"] = timeit(file_rewrite(True), N)
R["write"]["file_rewrite_nofsync"] = timeit(file_rewrite(False), N)

def jsonl(batch):
    path = tmp / "timeline.jsonl"
    def run(n):
        with open(path, "a") as f:
            for k in range(n):
                f.write(json.dumps({"t": time.time(), "op": "usage", "delta": 1}) + "\n")
                if (k + 1) % batch == 0: f.flush(); os.fsync(f.fileno())
            f.flush(); os.fsync(f.fileno())
    return run
R["write"]["jsonl_append_fsync_each"] = timeit(jsonl(1), N)
R["write"]["jsonl_append_fsync_100"] = timeit(jsonl(100), N)

# ---------- SQLite ----------
def conn(sync):
    p = tmp / f"db-{sync}.sqlite"
    c = sqlite3.connect(p, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL"); c.execute(f"PRAGMA synchronous={sync}")
    c.execute("CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY, body BLOB NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, doc TEXT, body TEXT)")
    c.execute("INSERT OR REPLACE INTO docs VALUES('a', jsonb(?))", (json.dumps(BASE),))
    c.execute("INSERT OR REPLACE INTO docs VALUES('t', ?)", (json.dumps(BASE),))
    return c

for sync in ("FULL", "NORMAL"):
    c = conn(sync); d = dict(BASE)
    def whole(n):
        for k in range(n):
            d["usage"]["input_tokens"] += 1
            c.execute("UPDATE docs SET body=? WHERE id='t'", (json.dumps(d),))
    def patch_text(n):
        for k in range(n):
            c.execute("UPDATE docs SET body=json_set(body,'$.usage.input_tokens',"
                      "json_extract(body,'$.usage.input_tokens')+1) WHERE id='t'")
    def patch_jsonb(n):
        for k in range(n):
            c.execute("UPDATE docs SET body=jsonb_set(body,'$.usage.input_tokens',"
                      "body->>'$.usage.input_tokens'+1) WHERE id='a'")
    def event(n):
        for k in range(n):
            c.execute("INSERT INTO events(doc,body) VALUES('a',?)", (json.dumps({"op": "usage", "delta": 1}),))
    def event_batched(n):
        for k in range(0, n, 100):
            c.execute("BEGIN")
            for j in range(100):
                c.execute("INSERT INTO events(doc,body) VALUES('a',?)", (json.dumps({"op": "usage", "delta": 1}),))
            c.execute("COMMIT")
    for name, fn in [("whole_doc_update", whole), ("json_set_text", patch_text),
                     ("jsonb_set", patch_jsonb), ("event_insert", event), ("event_insert_batch100", event_batched)]:
        R["write"][f"sqlite_{sync.lower()}_{name}"] = timeit(fn, N)
    c.close()

# ---------- reads ----------
M = 20000
c = sqlite3.connect(tmp / "read.sqlite", isolation_level=None); c.execute("PRAGMA journal_mode=WAL")
c.execute("CREATE TABLE docs(id TEXT PRIMARY KEY, body BLOB NOT NULL)")
c.execute("BEGIN")
c.executemany("INSERT INTO docs VALUES(?, jsonb(?))", ((f"sess-{i:06d}", json.dumps(doc(i))) for i in range(M)))
c.execute("COMMIT")
files = tmp / "files"; files.mkdir()
for i in range(2000):
    (files / f"sess-{i:06d}.json").write_text(json.dumps(doc(i)))

def read_file(n):
    for k in range(n):
        json.loads((files / f"sess-{random.randrange(2000):06d}.json").read_text())["status"]
def read_sqlite(n):
    for k in range(n):
        c.execute("SELECT body->>'$.status' FROM docs WHERE id=?", (f"sess-{random.randrange(M):06d}",)).fetchone()
R["read"]["point_file_parse_whole"] = timeit(read_file, 5000)
R["read"]["point_sqlite_extract"] = timeit(read_sqlite, 5000)

Q = "SELECT count(*) FROM docs WHERE body->>'$.owner'=? AND body->>'$.status'='failed'"
def filt(n):
    for k in range(n): c.execute(Q, (f"user-{random.randrange(50)}",)).fetchone()
R["read"]["filter_20k_no_index"] = timeit(filt, 20)
c.execute("CREATE INDEX docs_owner_status ON docs(body->>'$.owner', body->>'$.status')")
R["read"]["filter_20k_expr_index"] = timeit(filt, 2000)
R["read"]["plan_with_index"] = " | ".join(r[-1] for r in c.execute("EXPLAIN QUERY PLAN " + Q, ("user-1",)))
R["sizes"] = {"sqlite_20k_docs_bytes": os.path.getsize(tmp / "read.sqlite"),
              "text_json_20k_bytes": sum(len(json.dumps(doc(i))) for i in range(200)) * 100}
c.close()

import shutil; shutil.rmtree(tmp)
(HERE / "_numbers.json").write_text(json.dumps(R, indent=2) + "\n")
print(json.dumps(R, indent=2))
