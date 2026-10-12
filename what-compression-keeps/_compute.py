# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = [
#   "brotli==1.2.0",
#   "lz4==4.4.5",
#   "cramjam==2.13.0",
# ]
# [tool.uv]
# exclude-newer = "2026-10-10T00:00:00Z"
# ///
"""What Compression Keeps: the measured numbers.

Run:   uv run /home/coder/xo-projects/writings/what-compression-keeps/_compute.py
       --only treatments,wire   recompute those keys and merge them into the existing _numbers.json
       --sample-only            skip the full-Silesia ratio pass (about 15 minutes on 2 vCPUs)
Needs: bash /home/coder/compression-ref/bench/setup.sh, run once, to fetch the Silesia corpus. Without it
       the Silesia rows are recorded as "skipped" with the reason.
Writes _numbers.json next to this file. Nothing heavy goes into the publication: the SQLite databases and
the git repository are built under BENCH/tmp and removed afterwards. No media is used.

Keys: treatments, entropy, random, lz_demo, window, frontier, wire, oracle, bombs, compaction, minify,
dct_demo; plus machine, corpora, method.

Exactness. Sizes, ratios, counts and entropies are exact and deterministic for the pinned versions:
generators are seeded, gzip headers carry mtime 0, git dates and identities are fixed and pack.threads is 1.
Timings are medians of repeated single-threaded runs after a warm-up, on a 2-CPU cgroup shared with other
tenants; they are reported as tiers, with cgroup throttling recorded before and after each timed phase.
MB = 10^6 bytes. ratio = original bytes / compressed bytes. bits/byte = 8 * compressed / original.
"""
from __future__ import annotations

import bz2
import concurrent.futures as cf
import ctypes
import datetime as dt
import gc
import gzip
import hashlib
import html
import itertools
import json
import lzma
import math
import multiprocessing as mp
import os
import platform
import random
import re
import shutil
import sqlite3
import statistics
import struct
import subprocess
import sys
import sysconfig
import time
import zlib
from collections import Counter
from pathlib import Path

from compression import zstd

import brotli
import cramjam
import lz4
import lz4.block
import lz4.frame

HERE = Path(__file__).resolve().parent
WRITINGS = HERE.parent
BENCH = Path("/home/coder/compression-ref/bench")            # heavy artefacts live outside the publication
CORPORA_DIR = BENCH / "corpora"
SILESIA_DIR = CORPORA_DIR / "silesia"
SILESIA_ZIP = CORPORA_DIR / "silesia.zip"
SILESIA_URL = "https://sun.aei.polsl.pl/~sdeor/corpus/silesia.zip"
SILESIA_ZIP_SHA256 = "0626e25f45c0ffb5dc801f13b7c82a3b75743ba07e3a71835a41e3d9f63c77af"  # recorded at first download
SILESIA_FILES = ["dickens", "mozilla", "mr", "nci", "ooffice", "osdb", "reymont", "samba", "sao", "webster",
                 "x-ray", "xml"]                                # sorted(); 211,938,580 bytes in total
SILESIA_BYTES = 211_938_580
TMP = BENCH / "tmp"
OUT_JSON = HERE / "_numbers.json"
STDLIB = Path(sysconfig.get_paths()["stdlib"])                 # /usr/lib/python3.14 under the system interpreter
PY_BINARY = Path(os.path.realpath(sys.executable))             # the ELF that runs this script
STDLIB_VERSIONS = [                                            # optional real corpus for the window sweep
    ("3.11.16", Path("/home/coder/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/lib/python3.11")),
    ("3.14.4", Path("/usr/lib/python3.14")),
    ("3.15.0rc1", Path("/home/coder/config-ref/bench/toml/.pythons/cpython-3.15.0rc1-linux-x86_64-gnu/lib/python3.15")),
]
PROSE_POSTS = ["what-the-parser-hears", "hardest-problems", "claude-code-session", "markov-processes",
               "where-the-json-lives"]
WIRE_PAGE = WRITINGS / "what-the-parser-hears" / "index.html"
WIRE_DICT = WRITINGS / "where-the-json-lives" / "index.html"
DELTA_PAIRS = [   # (path, previous commit, later commit) in the writings git repo: two published versions of one page
    ("xo-space-architecture/index.html", "40c1428", "3779b9e"),
    ("what-is-quirq/index.html", "a76229b", "107e64f"),
]
MINIFY_DOCS = [WRITINGS / "posts.json", WRITINGS / "what-the-parser-hears" / "_numbers.json", HERE / "_plan.json"]

ALL_KEYS = ["treatments", "entropy", "random", "lz_demo", "window", "wire", "oracle", "bombs", "compaction",
            "minify", "dct_demo", "frontier"]

CORPORA: dict[str, dict] = {}


# ----------------------------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------------------------
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def sha(b) -> str:
    return hashlib.sha256(b).hexdigest()


def ratio(n, c):
    return round(n / c, 4)


def bpb(c, n):
    return round(8 * c / n, 4)


def sig3(x):
    if x is None or x == 0:
        return x
    v = float(f"{x:.3g}")
    return int(v) if v.is_integer() else v


def register_corpus(name, data: bytes | None, source, licence, note=None, nbytes=None, digest=None):
    CORPORA[name] = {"bytes": len(data) if data is not None else nbytes,
                     "sha256": sha(data) if data is not None else digest,
                     "source": source, "licence": licence}
    if note:
        CORPORA[name]["note"] = note


def gz(d, level):                          # gzip member, mtime 0, so the bytes are reproducible
    return gzip.compress(d, compresslevel=level, mtime=0)


def tier(mbps):
    if mbps is None:
        return None
    for lo, label in ((500, ">=500 MB/s"), (100, "100-500 MB/s"), (10, "10-100 MB/s"), (1, "1-10 MB/s")):
        if mbps >= lo:
            return label
    return "<1 MB/s"


def contention_snapshot():
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


def contention_delta(a, b, note):
    wall = b["t"] - a["t"]
    out = {"phase_wall_s": round(wall, 1), "loadavg_1m_before": a.get("loadavg_1m"),
           "loadavg_1m_after": b.get("loadavg_1m")}
    if "nr_periods" in a and "nr_periods" in b:
        periods = b["nr_periods"] - a["nr_periods"]
        thr = b["nr_throttled"] - a["nr_throttled"]
        out.update({"cgroup_periods": periods, "cgroup_throttled_periods": thr,
                    "cgroup_throttled_fraction": round(thr / periods, 3) if periods else None,
                    "cgroup_throttled_s": round((b["throttled_usec"] - a["throttled_usec"]) / 1e6, 1),
                    "cgroup_cpu_used_s": round((b["usage_usec"] - a["usage_usec"]) / 1e6, 1)})
        raw_keys = ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec")
        out["cpu_stat_before"] = {k: a[k] for k in raw_keys if k in a}     # raw /sys/fs/cgroup/cpu.stat counters
        out["cpu_stat_after"] = {k: b[k] for k in raw_keys if k in b}
    out["note"] = note
    return out


def proc_io():
    """/proc/self/io counters. Reading the file is itself a read() that the next snapshot's rchar includes, and its
    length depends on how many digits the counters have, so the byte count of this read is returned as "_self_read"
    for the caller to subtract (otherwise a read delta wobbles by a few bytes from run to run)."""
    try:
        txt = Path("/proc/self/io").read_bytes()
        out = {k: int(v) for k, v in (ln.split(": ") for ln in txt.decode().splitlines())}
        out["_self_read"] = len(txt)
        return out
    except (OSError, ValueError):
        return {}


def zstd_window_bytes(frame: bytes):
    """Window_Size from a zstd frame header (RFC 8878 3.1.1.1); skips one leading skippable frame."""
    pos = 0
    magic = int.from_bytes(frame[0:4], "little")
    if magic & 0xFFFFFFF0 == 0x184D2A50:
        pos = 8 + int.from_bytes(frame[4:8], "little")
    if int.from_bytes(frame[pos:pos + 4], "little") != 0xFD2FB528:
        return None
    fhd = frame[pos + 4]
    fcs_flag, single, did_flag = fhd >> 6, (fhd >> 5) & 1, fhd & 3
    p = pos + 5
    if not single:
        wd = frame[p]
        wlog = 10 + (wd >> 3)
        base = 1 << wlog
        return base + (base // 8) * (wd & 7)
    p += (0, 1, 2, 4)[did_flag]
    n = (1, 2, 4, 8)[fcs_flag]
    v = int.from_bytes(frame[p:p + n], "little")
    return v + 256 if n == 2 else v


# ----------------------------------------------------------------------------------------------------------
# brotli with a raw (LZ77) dictionary, via the system libbrotli 1.2.0 (the brotli wheel has no dictionary API)
# ----------------------------------------------------------------------------------------------------------
class BrotliC:
    RAW = 0                                        # BROTLI_SHARED_DICTIONARY_RAW
    P_MODE, P_QUALITY, P_LGWIN, P_SIZE_HINT = 0, 1, 2, 5
    OP_FINISH = 2

    def __init__(self):
        from ctypes import POINTER, c_int, c_size_t, c_uint32, c_void_p
        self.enc = e = ctypes.CDLL("libbrotlienc.so.1")
        self.dec = d = ctypes.CDLL("libbrotlidec.so.1")
        e.BrotliEncoderCreateInstance.restype = c_void_p
        e.BrotliEncoderCreateInstance.argtypes = [c_void_p, c_void_p, c_void_p]
        e.BrotliEncoderSetParameter.argtypes = [c_void_p, c_int, c_uint32]
        e.BrotliEncoderSetParameter.restype = c_int
        e.BrotliEncoderPrepareDictionary.restype = c_void_p
        e.BrotliEncoderPrepareDictionary.argtypes = [c_int, c_size_t, c_void_p, c_int, c_void_p, c_void_p, c_void_p]
        e.BrotliEncoderAttachPreparedDictionary.argtypes = [c_void_p, c_void_p]
        e.BrotliEncoderAttachPreparedDictionary.restype = c_int
        e.BrotliEncoderCompressStream.argtypes = [c_void_p, c_int, POINTER(c_size_t), POINTER(c_void_p),
                                                  POINTER(c_size_t), POINTER(c_void_p), POINTER(c_size_t)]
        e.BrotliEncoderCompressStream.restype = c_int
        e.BrotliEncoderIsFinished.argtypes = [c_void_p]
        e.BrotliEncoderIsFinished.restype = c_int
        e.BrotliEncoderDestroyInstance.argtypes = [c_void_p]
        e.BrotliEncoderDestroyPreparedDictionary.argtypes = [c_void_p]
        e.BrotliEncoderVersion.restype = c_uint32
        d.BrotliDecoderCreateInstance.restype = c_void_p
        d.BrotliDecoderCreateInstance.argtypes = [c_void_p, c_void_p, c_void_p]
        d.BrotliDecoderAttachDictionary.argtypes = [c_void_p, c_int, c_size_t, c_void_p]
        d.BrotliDecoderAttachDictionary.restype = c_int
        d.BrotliDecoderDecompressStream.argtypes = [c_void_p, POINTER(c_size_t), POINTER(c_void_p),
                                                    POINTER(c_size_t), POINTER(c_void_p), POINTER(c_size_t)]
        d.BrotliDecoderDecompressStream.restype = c_int
        d.BrotliDecoderDestroyInstance.argtypes = [c_void_p]
        d.BrotliDecoderVersion.restype = c_uint32

    @staticmethod
    def _ver(v):
        return f"{v >> 24}.{(v >> 12) & 0xFFF}.{v & 0xFFF}"

    def versions(self):
        return {"encoder": self._ver(self.enc.BrotliEncoderVersion()), "decoder": self._ver(self.dec.BrotliDecoderVersion())}

    def compress(self, data: bytes, quality: int, lgwin: int = 22, dictionary: bytes | None = None) -> bytes:
        from ctypes import addressof, byref, c_size_t, c_void_p, create_string_buffer
        e = self.enc
        st = e.BrotliEncoderCreateInstance(None, None, None)
        pd = None
        try:
            e.BrotliEncoderSetParameter(st, self.P_MODE, 0)
            e.BrotliEncoderSetParameter(st, self.P_QUALITY, quality)
            e.BrotliEncoderSetParameter(st, self.P_LGWIN, lgwin)
            dbuf = None
            if dictionary is not None:
                dbuf = create_string_buffer(dictionary, len(dictionary))
                pd = e.BrotliEncoderPrepareDictionary(self.RAW, len(dictionary), addressof(dbuf), quality, None, None, None)
                if not pd or not e.BrotliEncoderAttachPreparedDictionary(st, pd):
                    raise RuntimeError("BrotliEncoderAttachPreparedDictionary failed")
            ibuf = create_string_buffer(data, len(data))
            cap = len(data) + (len(data) >> 2) + 65536
            obuf = create_string_buffer(cap)
            ain, nin = c_size_t(len(data)), c_void_p(addressof(ibuf))
            aout, nout, tot = c_size_t(cap), c_void_p(addressof(obuf)), c_size_t(0)
            if not e.BrotliEncoderCompressStream(st, self.OP_FINISH, byref(ain), byref(nin), byref(aout), byref(nout), byref(tot)):
                raise RuntimeError("BrotliEncoderCompressStream failed")
            if not e.BrotliEncoderIsFinished(st):
                raise RuntimeError("brotli output buffer too small")
            return obuf.raw[:cap - aout.value]
        finally:
            e.BrotliEncoderDestroyInstance(st)
            if pd:
                e.BrotliEncoderDestroyPreparedDictionary(pd)

    def decompress(self, comp: bytes, dictionary: bytes | None = None, expect: int = 1 << 20) -> bytes:
        from ctypes import addressof, byref, c_size_t, c_void_p, create_string_buffer
        d = self.dec
        st = d.BrotliDecoderCreateInstance(None, None, None)
        try:
            dbuf = None
            if dictionary is not None:
                dbuf = create_string_buffer(dictionary, len(dictionary))
                if not d.BrotliDecoderAttachDictionary(st, self.RAW, len(dictionary), addressof(dbuf)):
                    raise RuntimeError("BrotliDecoderAttachDictionary failed")
            ibuf = create_string_buffer(comp, len(comp))
            ain, nin = c_size_t(len(comp)), c_void_p(addressof(ibuf))
            out = bytearray()
            while True:
                cap = max(expect, 1 << 16)
                obuf = create_string_buffer(cap)
                aout, nout, tot = c_size_t(cap), c_void_p(addressof(obuf)), c_size_t(0)
                r = d.BrotliDecoderDecompressStream(st, byref(ain), byref(nin), byref(aout), byref(nout), byref(tot))
                out += obuf.raw[:cap - aout.value]
                if r == 1:
                    return bytes(out)
                if r != 3:
                    raise RuntimeError(f"brotli decode result {r}")
        finally:
            d.BrotliDecoderDestroyInstance(st)


# ----------------------------------------------------------------------------------------------------------
# codec registry for the frontier (module level so forked workers can look codecs up by id)
# ----------------------------------------------------------------------------------------------------------
CODECS: dict[str, dict] = {}


def _reg(cid, family, label, c, d, params):
    CODECS[cid] = {"family": family, "label": label, "c": c, "d": d, "params": params}


for _L in (1, 6, 9):
    _reg(f"zlib_{_L}", "DEFLATE (zlib)", f"zlib -{_L}", lambda x, L=_L: zlib.compress(x, L), zlib.decompress,
         {"api": "zlib.compress(data, level)", "level": _L, "window": "32 KiB",
          "framing": "zlib (RFC 1950), 6 bytes; a gzip member (RFC 1952) would add 12 more"})
for _L in (-5, 1, 3, 9, 19, 22):
    _reg(f"zstd_{_L}".replace("-", "m"), "Zstandard", f"zstd {_L}", lambda x, L=_L: zstd.compress(x, L),
         zstd.decompress, {"api": "compression.zstd.compress(data, level)", "level": _L,
                           "checksum_flag": 0, "content_size_flag": 1, "window": "level default for the input size",
                           "long_distance_matching": "auto (libzstd default)" + (
                               ": libzstd turns it on for the full corpus (level 22 uses window_log 27 and btultra2 "
                               "on inputs over 128 MiB) and off for the 12 MiB timed sample (window clamped to 2^24); "
                               "see frontier.zstd_22_ldm_check" if _L == 22 else ": off at this level")})
for _Q in (1, 5, 9, 11):
    _reg(f"brotli_{_Q}", "Brotli", f"brotli -q {_Q}", lambda x, Q=_Q: brotli.compress(x, quality=Q),
         brotli.decompress, {"api": "brotli.compress(data, quality=q)", "quality": _Q, "lgwin": 22, "mode": "generic"})
for _P in (0, 6, 9):
    _reg(f"xz_{_P}", "xz (LZMA2)", f"xz -{_P}", lambda x, P=_P: lzma.compress(x, preset=P), lzma.decompress,
         {"api": "lzma.compress(data, preset=p)", "preset": _P, "format": "xz", "check": "CRC64"})
_reg("bzip2_9", "bzip2 (BWT)", "bzip2 -9", lambda x: bz2.compress(x, 9), bz2.decompress,
     {"api": "bz2.compress(data, 9)", "block": "900 kB"})
_reg("lz4_default", "LZ4", "lz4 (default)", lambda x: lz4.frame.compress(x), lz4.frame.decompress,
     {"api": "lz4.frame.compress(data)", "compression_level": 0, "block_size": "64 KB (library default)",
      "block_linked": True, "content_checksum": False})
_reg("lz4_hc9", "LZ4", "lz4 -9 (HC)", lambda x: lz4.frame.compress(x, compression_level=9), lz4.frame.decompress,
     {"api": "lz4.frame.compress(data, compression_level=9)", "compression_level": 9, "block_size": "64 KB",
      "block_linked": True})
_reg("snappy", "Snappy", "snappy (raw)", lambda x: cramjam.snappy.compress_raw(x),
     lambda c: cramjam.snappy.decompress_raw(c),
     {"api": "cramjam.snappy.compress_raw(data)", "format": "raw Snappy block, no framing"})
FRONTIER_IDS = list(CODECS)
# full-corpus-only control: level 22 with long-distance matching forced off, to show what libzstd's auto-LDM adds
EXTRA_FULL = {"zstd_22_ldm_off": (lambda x: zstd.compress(x, options={zstd.CompressionParameter.compression_level: 22,
                                                                       zstd.CompressionParameter.enable_long_distance_matching: 2}),
                                  zstd.decompress)}


def silesia_present():
    return all((SILESIA_DIR / n).is_file() for n in SILESIA_FILES)


def silesia_concat() -> bytes:
    return b"".join((SILESIA_DIR / n).read_bytes() for n in SILESIA_FILES)


def silesia_sample() -> bytes:
    out = []
    for n in SILESIA_FILES:
        with open(SILESIA_DIR / n, "rb") as f:
            out.append(f.read(1 << 20))
    return b"".join(out)


def _full_ratio_job(cid):
    data = silesia_concat()
    c_fn, d_fn = (CODECS[cid]["c"], CODECS[cid]["d"]) if cid in CODECS else EXTRA_FULL[cid]
    cb = bytes(c_fn(data))
    ok = bytes(d_fn(cb)) == data
    return cid, len(cb), sha(cb), ok


# ----------------------------------------------------------------------------------------------------------
# treatments + compaction (2): a key-value update log
# ----------------------------------------------------------------------------------------------------------
KV = {"seed": 7, "updates": 200_000, "keys": 5_000, "deleted_keys": 250, "zipf_s": 0.9}
_KV_CACHE: dict = {}


def iso_ms(ms):
    return dt.datetime.fromtimestamp(ms // 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def make_kv_log():
    if _KV_CACHE:
        return _KV_CACHE["lines"]
    rng = random.Random(KV["seed"])
    n_keys, n = KV["keys"], KV["updates"]
    keys = [f"sku-{i:05d}" for i in range(n_keys)]
    warehouses = ["fra-1", "fra-2", "iad-1", "iad-3", "sin-1", "gru-1", "syd-2"]
    statuses = ["active", "active", "active", "backorder", "discontinued", "draft"]
    actors = ["svc-pricing", "svc-inventory", "svc-catalog", "ops-console"]
    t = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    lines: list[bytes] = []
    state: dict = {}

    def emit(key, value):
        nonlocal t
        t += rng.randint(1, 1200)
        rec = {"offset": len(lines), "ts": iso_ms(t), "key": key, "op": "put" if value is not None else "del",
               "value": value}
        lines.append(json.dumps(rec, separators=(",", ":")).encode() + b"\n")

    for k in keys:                                   # initial load: every key once
        v = {"price_cents": rng.randrange(199, 99_999), "stock": rng.randrange(0, 500),
             "status": rng.choice(statuses), "warehouse": rng.choice(warehouses), "updated_by": "svc-catalog", "rev": 1}
        state[k] = v
        emit(k, v)
    ranked = keys[:]
    rng.shuffle(ranked)
    cum = list(itertools.accumulate(1.0 / (r + 1) ** KV["zipf_s"] for r in range(n_keys)))
    doomed = rng.sample(keys, KV["deleted_keys"])
    del_at = dict(zip(rng.sample(range(n_keys + (n - n_keys) // 2, n), len(doomed)), doomed))
    gone = set()
    for i in range(n_keys, n):
        if i in del_at:
            k = del_at[i]
            gone.add(k)
            state.pop(k)
            emit(k, None)
            continue
        while True:
            k = rng.choices(ranked, cum_weights=cum)[0]
            if k not in gone:
                break
        v = dict(state[k])
        r = rng.random()
        if r < 0.55:
            v["stock"] = max(0, v["stock"] + rng.randint(-25, 40))
        elif r < 0.85:
            v["price_cents"] = max(99, int(v["price_cents"] * rng.uniform(0.9, 1.1)))
        elif r < 0.95:
            v["status"] = rng.choice(statuses)
        else:
            v["warehouse"] = rng.choice(warehouses)
        v["updated_by"] = rng.choice(actors)
        v["rev"] += 1
        state[k] = v
        emit(k, v)
    _KV_CACHE.update(lines=lines, state=state)
    return lines


def kv_parse(lines):
    out = []
    for ln in lines:
        r = json.loads(ln)
        out.append((r["key"], r["op"], len(ln)))
    return out


def kv_compact(lines, keep_tombstones=False):
    last = {}
    for i, (k, op, _) in enumerate(kv_parse(lines)):
        last[k] = (i, op)
    keep = sorted(i for i, op in last.values() if op == "put" or keep_tombstones)
    return [lines[i] for i in keep]


def kv_replay(blob: bytes):
    st = {}
    for ln in blob.splitlines():
        r = json.loads(ln)
        if r["op"] == "put":
            st[r["key"]] = r["value"]
        else:
            st.pop(r["key"], None)
    return st


def part_treatments():
    lines = make_kv_log()
    raw = b"".join(lines)
    parsed = kv_parse(lines)
    n_tomb = sum(1 for _, op, _ in parsed if op == "del")
    register_corpus("kv_update_log", raw, "generated by _compute.py make_kv_log() with seed 7",
                    "synthetic, no third-party content",
                    note=f"{KV['updates']:,} JSON Lines updates over {KV['keys']:,} keys (Zipf s={KV['zipf_s']}), "
                         f"{KV['deleted_keys']} keys deleted by a tombstone in the second half and never re-created")
    comp = b"".join(kv_compact(lines))
    comp_t = b"".join(kv_compact(lines, keep_tombstones=True))
    rows = []

    def row(rid, label, blob, replay, history_records, note=None):
        r = {"id": rid, "label": label, "bytes": len(blob), "ratio_vs_raw": ratio(len(raw), len(blob)),
             "pct_of_raw": round(100 * len(blob) / len(raw), 3), "can_replay_history": replay,
             "history_records_recoverable": history_records}
        if note:
            r["note"] = note
        rows.append(r)
        return r

    row("raw", "raw log (JSON Lines)", raw, True, len(lines))
    z3, z19 = zstd.compress(raw, 3), zstd.compress(raw, 19)
    assert zstd.decompress(z19) == raw and zstd.decompress(z3) == raw
    row("zstd_3", "raw log, zstd -3", z3, True, len(lines))
    row("zstd_19", "raw log, zstd -19", z19, True, len(lines))
    row("compacted", "compacted: last value per key, tombstoned keys dropped", comp, False,
        len(comp.splitlines()), "every superseded version and every tombstone is gone")
    row("compacted_keep_tombstones", "compacted, tombstones kept (as Kafka does until delete.retention.ms)",
        comp_t, False, len(comp_t.splitlines()))
    c3, c19 = zstd.compress(comp, 3), zstd.compress(comp, 19)
    row("compacted_zstd_3", "compacted, then zstd -3", c3, False, len(comp.splitlines()))
    row("compacted_zstd_19", "compacted, then zstd -19", c19, False, len(comp.splitlines()))
    g6 = gz(raw, 6)
    row("gzip_6", "raw log, gzip -6 (reference)", g6, True, len(lines))
    st_raw = kv_replay(raw)
    checks = {
        "final_state_equal_raw_vs_compacted": st_raw == kv_replay(comp),
        "final_state_equal_raw_vs_compacted_keep_tombstones": st_raw == kv_replay(comp_t),
        "final_state_equal_raw_vs_zstd19_roundtrip": st_raw == kv_replay(zstd.decompress(z19)),
        "final_state_equal_generator_state": st_raw == _KV_CACHE["state"],
        "zstd_roundtrip_byte_identical": True,
        "live_keys": len(st_raw),
    }
    return {
        "log": {"updates": len(lines), "keys": KV["keys"], "deleted_keys": KV["deleted_keys"], "tombstones": n_tomb,
                "puts": len(lines) - n_tomb, "bytes": len(raw), "mean_record_bytes": round(len(raw) / len(lines), 1),
                "sha256": sha(raw), "example_record": lines[KV["keys"] + 1].decode().strip(),
                "generator": "make_kv_log(): seed 7; first 5,000 records create every key; the remaining 195,000 "
                             "pick a key by Zipf(s=0.9) rank and change one field (stock 55%, price 30%, status 10%, "
                             "warehouse 5%) plus updated_by and rev; 250 keys get a tombstone at a random offset in "
                             "the second half and are never written again"},
        "rows": rows,
        "zstd_then_compact": {
            "possible": False,
            "why": "A zstd frame is one opaque stream: the keys, offsets and record boundaries that compaction "
                   "reads exist only after decompression. 'Compacting the compressed log' therefore means "
                   f"decompressing all {len(raw):,} bytes, compacting, and compressing again, which is "
                   "compact-then-compress with an extra decode. Compression has no notion of a superseded record; "
                   "it can only encode the whole history more cheaply. Systems that do both (Kafka batches, RocksDB "
                   "blocks) compress small units the compactor can open one at a time.",
            "bytes_that_must_be_decompressed_first": len(raw)},
        "order_matters": {"compact_then_zstd19_bytes": len(c19), "zstd19_only_bytes": len(z19),
                          "compact_then_zstd19_vs_zstd19_only": ratio(len(z19), len(c19))},
        "checks": checks,
    }


def kafka_style_cleaner(lines, seg_bytes=1 << 20, min_dirty_ratio=0.5):
    """A log-compaction simulation in the spirit of Kafka's cleaner: append-only segments of seg_bytes; the active
    segment is never cleaned; when dirty/(clean+dirty) over closed segments reaches min_dirty_ratio, all closed
    segments are rewritten keeping the latest record per key; a tombstone survives one cleaning (a stand-in for
    delete.retention.ms) and is dropped at the next."""
    recs = kv_parse(lines)
    segs: list[list[int]] = []
    seg_sizes: list[int] = []
    clean_upto = 0
    active, active_b = [], 0
    appended = written = read = cleanings = 0
    peak = 0
    tomb_seen: set[int] = set()
    series = []
    for i, (_, _, n) in enumerate(recs):
        active.append(i)
        active_b += n
        appended += n
        if active_b < seg_bytes:
            continue
        segs.append(active)
        seg_sizes.append(active_b)
        active, active_b = [], 0
        clean_b = sum(seg_sizes[:clean_upto])
        dirty_b = sum(seg_sizes[clean_upto:])
        before = clean_b + dirty_b
        peak = max(peak, before)
        if dirty_b / before >= min_dirty_ratio:
            idxs = [j for s in segs for j in s]
            read += before
            last = {}
            for j in idxs:
                last[recs[j][0]] = j
            out = []
            for j in idxs:
                if last[recs[j][0]] != j:
                    continue
                if recs[j][1] == "del":
                    if j in tomb_seen:
                        continue
                    tomb_seen.add(j)
                out.append(j)
            new_segs, new_sizes, cur, cb = [], [], [], 0
            for j in out:
                cur.append(j)
                cb += recs[j][2]
                if cb >= seg_bytes:
                    new_segs.append(cur)
                    new_sizes.append(cb)
                    cur, cb = [], 0
            if cur:
                new_segs.append(cur)
                new_sizes.append(cb)
            w = sum(new_sizes)
            written += w
            cleanings += 1
            series.append({"appended_bytes": appended, "log_bytes_before_clean": before, "log_bytes_after_clean": w,
                           "dirty_ratio": round(dirty_b / before, 3)})
            segs, seg_sizes, clean_upto = new_segs, new_sizes, len(new_segs)
    final_log = sum(seg_sizes) + active_b
    peak = max(peak, final_log)
    live = len(b"".join(kv_compact(lines)))
    return {
        "params": {"segment_bytes": seg_bytes, "min_cleanable_dirty_ratio": min_dirty_ratio,
                   "tombstone_retention": "one cleaning cycle",
                   "model": kafka_style_cleaner.__doc__.strip().replace("\n    ", " ")},
        "appended_bytes": appended, "cleanings": cleanings, "cleaner_bytes_read": read, "cleaner_bytes_written": written,
        "write_amplification": round((appended + written) / appended, 4),
        "peak_log_bytes": peak, "final_log_bytes": final_log, "live_bytes": live,
        "final_space_amplification": round(final_log / live, 4),
        "peak_space_amplification": round(peak / live, 4),
        "cleanings_series": series,
        "reading": "write_amplification = (bytes appended + bytes the cleaner rewrote) / bytes appended; "
                   "space amplification = log bytes on disk / bytes of the live (latest-per-key, no tombstone) state",
    }


# ----------------------------------------------------------------------------------------------------------
# entropy
# ----------------------------------------------------------------------------------------------------------
def entropy_orders(b: bytes):
    n = len(b)
    c0 = Counter(b)
    h0 = -sum(v / n * math.log2(v / n) for v in c0.values())
    res = {"order0": round(h0, 4)}
    for k in (1, 2):
        grams = Counter(b[i:i + k + 1] for i in range(n - k))
        pref = Counter()
        for g, c in grams.items():
            pref[g[:-1]] += c
        N = n - k
        res[f"order{k}"] = round(sum(c * math.log2(pref[g[:-1]] / c) for g, c in grams.items()) / N, 4)
        res[f"order{k}_contexts_seen"] = len(pref)
        res[f"order{k}_samples_per_context"] = round(N / len(pref), 1)
    return res


def article_text(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    m = re.search(r"<article[^>]*>(.*)</article>", s, re.S)
    a = m.group(1) if m else s
    a = re.sub(r"<(script|style|svg|pre|code|table|figure)\b.*?</\1>", " ", a, flags=re.S)
    a = re.sub(r"<[^>]+>", " ", a)
    a = html.unescape(a)
    a = re.sub(r"[ \t\r\f\v]+", " ", a)
    return re.sub(r"\s*\n\s*", "\n", a).strip() + "\n"


def prose_corpus() -> bytes:
    return "".join(article_text(WRITINGS / p / "index.html") for p in PROSE_POSTS).encode("utf-8")


def stdlib_toplevel(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(root.glob("*.py")))


def part_entropy():
    lines = make_kv_log()
    jsonl, acc = [], 0
    for ln in lines:
        if acc + len(ln) > 4 << 20:
            break
        jsonl.append(ln)
        acc += len(ln)
    items = [
        ("json", (WRITINGS / "what-the-parser-hears" / "_numbers.json").read_bytes(),
         "writings/what-the-parser-hears/_numbers.json", "first-party (this publication)", "JSON, indent=1"),
        ("jsonl_kv_log", b"".join(jsonl), "first 4 MiB (whole lines) of the treatments log",
         "synthetic, generated by this harness", "JSON Lines"),
        ("source_python", stdlib_toplevel(STDLIB), f"{STDLIB}/*.py (top level, sorted, concatenated)",
         "PSF License 2.0 (CPython standard library)", "Python source"),
        ("prose_writings", prose_corpus(),
         "visible <article> text of writings posts " + ", ".join(PROSE_POSTS) + " (tags, code, tables, figures, SVG stripped)",
         "first-party (this publication)", "English prose"),
        ("binary_elf", PY_BINARY.read_bytes(), str(PY_BINARY), "PSF License 2.0 (CPython), Ubuntu package build",
         "x86-64 ELF executable"),
        ("random", random.Random(7).randbytes(1 << 20), "random.Random(7).randbytes(1 MiB)", "synthetic",
         "pseudo-random bytes (Mersenne Twister, seed 7)"),
    ]
    if silesia_present():
        items.insert(4, ("prose_dickens", (SILESIA_DIR / "dickens").read_bytes(), "Silesia corpus: dickens",
                         "Silesia corpus (see corpora.silesia)", "English prose (Dickens novels)"))
    if SILESIA_ZIP.is_file():
        items.append(("already_compressed", SILESIA_ZIP.read_bytes()[: 4 << 20], "first 4 MiB of silesia.zip",
                      "Silesia corpus (see corpora.silesia)", "DEFLATE-compressed data"))
    rows = []
    for name, b, src, lic, kind in items:
        t0 = time.monotonic()
        register_corpus(f"entropy:{name}", b, src, lic)
        h = entropy_orders(b)
        sizes = {"gzip_9": len(gz(b, 9)), "zstd_19": len(zstd.compress(b, 19)),
                 "xz_9": len(lzma.compress(b, preset=9)), "bzip2_9": len(bz2.compress(b, 9))}
        bp = {k: bpb(v, len(b)) for k, v in sizes.items()}
        best = min(bp, key=bp.get)
        rows.append({"name": name, "kind": kind, "bytes": len(b), "entropy_bits_per_byte": h,
                     "compressed_bytes": sizes, "achieved_bits_per_byte": bp, "best": best,
                     "best_vs_order0": round(bp[best] - h["order0"], 4)})
        log(f"  entropy {name}: {len(b):,} B, H0={h['order0']} best {best} {bp[best]} ({time.monotonic() - t0:.0f} s)")
    missing = [n for n, ok in (("prose_dickens", silesia_present()), ("already_compressed", SILESIA_ZIP.is_file()))
               if not ok]
    skipped = None if not missing else \
        f"{' and '.join(missing)} need the Silesia corpus ({SILESIA_DIR}, {SILESIA_ZIP}); run {BENCH}/setup.sh"
    return {
        "rows": rows,
        "skipped": skipped,
        "method": "order-k entropy is the empirical (plug-in) conditional entropy H(X_i | previous k bytes) in bits "
                  "per byte, from overlapping (k+1)-gram counts of the file itself. It ignores the cost of describing "
                  "the model, so order 1 and order 2 understate what a real coder could reach when samples per "
                  "context are few: with 256 possible next bytes, an order-k estimate is only meaningful when "
                  "orderk_samples_per_context is well above 256 (order 2 on the 1 MiB random input reads about 4 "
                  "bits/byte for exactly this reason; the true value is 8). gzip_9 = gzip member at level 9 (mtime 0); zstd_19 = compression.zstd "
                  "level 19; xz_9 = lzma preset 9 (xz container, CRC64); bzip2_9 = bz2 level 9. Achieved bits/byte "
                  "include container overhead.",
        "reading": "achieved < order-0 means the compressor models context (repeats, previous bytes) that the "
                   "order-0 histogram cannot see; entropy is relative to a model",
    }


# ----------------------------------------------------------------------------------------------------------
# random input
# ----------------------------------------------------------------------------------------------------------
def part_random():
    data = random.Random(7).randbytes(1 << 20)
    n = len(data)

    def deflate_raw(x, level=9):
        o = zlib.compressobj(level, zlib.DEFLATED, -15)
        return o.compress(x) + o.flush()

    cases = [
        ("gzip_9", "gzip -9 (member, mtime 0)", lambda: gz(data, 9), gzip.decompress),
        ("gzip_6", "gzip -6", lambda: gz(data, 6), gzip.decompress),
        ("zlib_9", "zlib -9", lambda: zlib.compress(data, 9), zlib.decompress),
        ("deflate_raw_9", "raw DEFLATE -9 (no wrapper)", lambda: deflate_raw(data), lambda c: zlib.decompress(c, -15)),
        ("zstd_3", "zstd -3", lambda: zstd.compress(data, 3), zstd.decompress),
        ("zstd_19", "zstd -19", lambda: zstd.compress(data, 19), zstd.decompress),
        ("xz_6", "xz -6", lambda: lzma.compress(data, preset=6), lzma.decompress),
        ("xz_9", "xz -9", lambda: lzma.compress(data, preset=9), lzma.decompress),
        ("bzip2_9", "bzip2 -9", lambda: bz2.compress(data, 9), bz2.decompress),
        ("brotli_5", "brotli -q 5", lambda: brotli.compress(data, quality=5), brotli.decompress),
        ("brotli_11", "brotli -q 11", lambda: brotli.compress(data, quality=11), brotli.decompress),
        ("lz4_frame", "lz4 frame (default)", lambda: lz4.frame.compress(data), lz4.frame.decompress),
        ("lz4_hc9", "lz4 frame -9 (HC)", lambda: lz4.frame.compress(data, compression_level=9), lz4.frame.decompress),
        ("lz4_block", "lz4 block (4-byte size prefix)", lambda: lz4.block.compress(data), lz4.block.decompress),
        ("snappy_raw", "snappy raw", lambda: bytes(cramjam.snappy.compress_raw(data)),
         lambda c: bytes(cramjam.snappy.decompress_raw(c))),
        ("snappy_framed", "snappy framed", lambda: bytes(cramjam.snappy.compress(data)),
         lambda c: bytes(cramjam.snappy.decompress(c))),
    ]
    rows = []
    for cid, label, c, d in cases:
        out = c()
        assert d(out) == data, cid
        rows.append({"id": cid, "label": label, "bytes": len(out), "expansion_bytes": len(out) - n,
                     "expansion_pct": round(100 * (len(out) - n) / n, 4)})
    return {
        "input": {"bytes": n, "sha256": sha(data), "generator": "random.Random(7).randbytes(1 << 20)",
                  "order0_entropy_bits_per_byte": entropy_orders(data)["order0"]},
        "rows": rows,
        "counting_bound": {
            "statement": "of all n-byte inputs, the fraction that can map to an output at least one byte shorter is "
                         "at most (256^n - 1) / (255 * 256^n) < 1/255",
            "bound_fraction": round(1 / 255, 6), "bound_pct": round(100 / 255, 4)},
        "all_roundtrips_ok": True,
    }


# ----------------------------------------------------------------------------------------------------------
# LZ77 demo
# ----------------------------------------------------------------------------------------------------------
LZ_DEMOS = [
    ("shannon_1948",
     "reproducing at one point either exactly or approximately a message selected at another point",
     "Shannon 1948, 'A Mathematical Theory of Communication', Introduction: a fragment of the sentence 'The "
     "fundamental problem of communication is that of reproducing at one point ... at another point.' "
     "(theory.md section A quotes the full sentence)"),
    ("posts_json_line",
     '{"label":"Measured results (_numbers.json)","href":"what-the-parser-hears/_numbers.json"}',
     "writings/posts.json, entry 'what-the-parser-hears', attachments[1], minified with separators (',', ':')"),
]


def lz77_greedy(s: bytes, window=32768, min_match=3, max_match=258):
    """Greedy LZ77: at each position take the longest match (>= min_match) that starts in the previous `window`
    bytes, preferring the nearest on ties; matches may overlap the current position; else emit one literal."""
    n, i, toks = len(s), 0, []
    while i < n:
        best_len, best_d = 0, 0
        for j in range(i - 1, max(0, i - window) - 1, -1):
            L = 0
            while i + L < n and L < max_match and s[j + L] == s[i + L]:
                L += 1
            if L > best_len:
                best_len, best_d = L, i - j
        if best_len >= min_match:
            toks.append(("m", i, best_d, best_len))
            i += best_len
        else:
            toks.append(("l", i, s[i:i + 1]))
            i += 1
    return toks


def part_lz_demo():
    out = []
    for did, text, source in LZ_DEMOS:
        s = text.encode()
        assert len(s) <= 120
        toks = lz77_greedy(s)
        seq = []
        for t in toks:
            if t[0] == "l":
                if seq and seq[-1]["kind"] == "literal":
                    seq[-1]["text"] += t[2].decode()
                else:
                    seq.append({"kind": "literal", "pos": t[1], "text": t[2].decode()})
            else:
                _, pos, d, L = t
                seq.append({"kind": "match", "pos": pos, "distance": d, "length": L, "from_pos": pos - d,
                            "text": s[pos:pos + L].decode()})
        rebuilt = bytearray()
        for t in seq:
            if t["kind"] == "literal":
                rebuilt += t["text"].encode()
            else:
                for _ in range(t["length"]):
                    rebuilt.append(rebuilt[-t["distance"]])
        assert bytes(rebuilt) == s
        lit = sum(len(t["text"]) for t in seq if t["kind"] == "literal")
        matches = [t for t in seq if t["kind"] == "match"]
        o = zlib.compressobj(9, zlib.DEFLATED, -15)
        dfl = o.compress(s) + o.flush()
        out.append({"id": did, "text": text, "source": source, "bytes": len(s), "tokens": seq,
                    "counts": {"literal_bytes": lit, "matches": len(matches),
                               "matched_bytes": sum(t["length"] for t in matches),
                               "literal_runs": sum(1 for t in seq if t["kind"] == "literal"),
                               "tokens": len(seq)},
                    "raw_deflate_9_bytes": len(dfl), "zstd_19_bytes": len(zstd.compress(s, 19)),
                    "decoded_ok": True})
    return {"demos": out, "parser": lz77_greedy.__doc__.strip().replace("\n    ", " ") +
            " Window 32 KiB, minimum match 3, maximum 258 (DEFLATE's limits). This is not zlib's parse: zlib uses "
            "hash chains and lazy matching; raw_deflate_9_bytes is zlib's actual output for comparison."}


# ----------------------------------------------------------------------------------------------------------
# window reach
# ----------------------------------------------------------------------------------------------------------
TAGS = ["new", "sale", "eco", "bulk", "fragile", "imported", "limited", "refurb", "gift", "premium", "basic", "kids",
        "outdoor", "kitchen", "office", "garden", "audio", "video", "sport", "travel"]


def make_versions_corpus(seed=5, n_records=11_000, n_versions=12, edit_frac=0.02):
    rng = random.Random(seed)
    syll = ["ka", "lo", "mi", "re", "tu", "sa", "ne", "vo", "di", "pa", "ri", "zu", "fe", "go", "ba", "te", "lu",
            "mo", "shi", "qua", "en", "or", "an", "is"]
    vocab = ["".join(rng.choice(syll) for _ in range(rng.randint(1, 4))) for _ in range(4000)]
    cumw = list(itertools.accumulate(1.0 / (r + 1) for r in range(len(vocab))))
    cats = ["tools", "books", "garden", "audio", "kitchen", "toys", "office", "sport", "travel", "home"]

    def words(k):
        return " ".join(rng.choices(vocab, cum_weights=cumw, k=k))

    def new_rec(i):
        return {"id": i, "sku": f"SKU-{i:06d}", "name": words(3).title(), "category": rng.choice(cats),
                "price": round(rng.uniform(1, 500), 2), "stock": rng.randrange(0, 1000), "tags": rng.sample(TAGS, 3),
                "description": words(rng.randint(12, 30))}

    recs = [new_rec(i) for i in range(n_records)]
    next_id = n_records
    parts, sizes = [], []
    for v in range(n_versions):
        doc = {"version": v + 1, "generated": f"2026-10-{v + 1:02d}T00:00:00Z", "records": recs}
        b = json.dumps(doc, indent=1).encode() + b"\n"
        parts.append(b)
        sizes.append(len(b))
        for idx in rng.sample(range(len(recs)), int(len(recs) * edit_frac)):
            r = dict(recs[idx])
            r["price"] = round(r["price"] * rng.uniform(0.8, 1.2), 2)
            r["stock"] = rng.randrange(0, 1000)
            if rng.random() < 0.3:
                r["description"] = words(rng.randint(12, 30))
            recs[idx] = r
        for idx in sorted(rng.sample(range(len(recs)), len(recs) // 200), reverse=True):
            del recs[idx]
        for _ in range(n_records // 200):
            recs.append(new_rec(next_id))
            next_id += 1
    return b"".join(parts), sizes


def stdlib_versions_corpus():
    parts, info = [], []
    for ver, root in STDLIB_VERSIONS:
        if not root.is_dir():
            return None, f"missing {root}"
        files = sorted(p for p in root.rglob("*.py")
                       if not ({"site-packages", "test", "tests", "idlelib", "__pycache__"} & set(p.relative_to(root).parts)))
        b = b"".join(p.read_bytes() for p in files)
        parts.append(b)
        info.append({"version": ver, "root": str(root), "files": len(files), "bytes": len(b), "sha256": sha(b)})
    return b"".join(parts), info


LDM_ENABLE, LDM_DISABLE = 1, 2      # ZSTD_paramSwitch_e: 0 = auto (libzstd decides), 1 = enable, 2 = disable


def zstd_opts(level, wlog=None, ldm=None):
    o = {zstd.CompressionParameter.compression_level: level}
    if wlog is not None:
        o[zstd.CompressionParameter.window_log] = wlog
    if ldm is not None:                # explicit on/off; 0 = "auto": on for btopt+ (level 16+) with window >= 2^27
        o[zstd.CompressionParameter.enable_long_distance_matching] = LDM_ENABLE if ldm else LDM_DISABLE
    return o


def window_sweep(data, level=3, wlogs=range(10, 28)):
    rows = []
    for w in wlogs:
        for ldm in (0, 1):
            c = zstd.compress(data, options=zstd_opts(level, w, ldm))
            rows.append({"window_log": w, "window_bytes": 1 << w, "ldm": bool(ldm), "bytes": len(c),
                         "ratio": ratio(len(data), len(c))})
    d = zstd.compress(data, options=zstd_opts(level))
    default = {"bytes": len(d), "ratio": ratio(len(data), len(d)), "window_bytes_in_header": zstd_window_bytes(d)}
    for w, ldm in ((27, 1), (27, 0)):
        c = zstd.compress(data, options=zstd_opts(level, w, ldm))
        assert zstd.decompress(c) == data
    return rows, default


def part_window():
    data, sizes = make_versions_corpus()
    register_corpus("window:json_versions", data, "generated by _compute.py make_versions_corpus() with seed 5",
                    "synthetic, no third-party content",
                    note=f"{len(sizes)} successive versions of one JSON catalogue (indent=1), each a copy of the "
                         "previous with 2% of records edited, 0.5% deleted, 0.5% added")
    t0 = time.monotonic()
    rows, default = window_sweep(data)
    log(f"  window synthetic sweep {time.monotonic() - t0:.0f} s")
    refs = []
    for label, opts in (("zstd -19, default parameters", zstd_opts(19)),
                        ("zstd -19, window_log 27 + long-distance matching", zstd_opts(19, 27, 1))):
        c = zstd.compress(data, options=opts)
        refs.append({"label": label, "bytes": len(c), "ratio": ratio(len(data), len(c)),
                     "window_bytes_in_header": zstd_window_bytes(c)})
    out = {"level": 3, "synthetic": {
        "corpus": {"bytes": len(data), "versions": len(sizes), "version_bytes": sizes,
                   "mean_version_bytes": round(statistics.mean(sizes)),
                   "repeat_distance_note": "each version repeats about 98% of the previous one, one version-length "
                                           f"(~{statistics.mean(sizes) / 2**20:.2f} MiB) back, so a window of 2^22 "
                                           "(4 MiB) is the first that can reach it"},
        "rows": rows, "level3_default_parameters": default, "level19_reference": refs}}
    real, info = stdlib_versions_corpus()
    if real is None:
        out["stdlib_versions"] = {"skipped": info}
    else:
        register_corpus("window:cpython_stdlib_3_versions", real,
                        "; ".join(f"{i['version']}: {i['root']}" for i in info) + " (all *.py except site-packages, "
                        "test, tests, idlelib; sorted relative paths)", "PSF License 2.0 (CPython standard library)")
        t0 = time.monotonic()
        rrows, rdefault = window_sweep(real)
        log(f"  window stdlib sweep {time.monotonic() - t0:.0f} s")
        out["stdlib_versions"] = {"corpus": {"bytes": len(real), "parts": info,
                                             "repeat_distance_note": "the same module in the next version sits one "
                                             "stdlib (~11 MB) later, so 2^24 (16 MiB) is the first window that reaches it"},
                                  "rows": rrows, "level3_default_parameters": rdefault}
    out["method"] = ("compression.zstd one-shot compress with options {compression_level: 3, window_log: w, "
                     "enable_long_distance_matching: 2 (disable) or 1 (enable)}; every other parameter is the level's "
                     "default as adjusted by libzstd (a window larger than the input is clamped to it, so window_log "
                     "26 and 27 coincide on both corpora, 45.6 MB and 33.7 MB); round trip checked at window_log 27 with "
                     "and without LDM. level19_reference 'default parameters' leaves LDM on auto, which libzstd "
                     "resolves to off here because the level-19 window is 2^23")
    return out


# ----------------------------------------------------------------------------------------------------------
# frontier
# ----------------------------------------------------------------------------------------------------------
def pareto(points):
    keep = []
    for pid, x, y in points:
        if not any((qx >= x and qy >= y) and (qx > x or qy > y) for _, qx, qy in points):
            keep.append(pid)
    return keep


def part_frontier(sample_only=False):
    if not silesia_present():
        return {"skipped": f"Silesia corpus not found in {SILESIA_DIR}; run {BENCH}/setup.sh"}
    zsha = sha(SILESIA_ZIP.read_bytes()) if SILESIA_ZIP.exists() else None
    full = silesia_concat()
    full_sha = sha(full)
    files = [{"name": n, "bytes": (SILESIA_DIR / n).stat().st_size, "sha256": sha((SILESIA_DIR / n).read_bytes())}
             for n in SILESIA_FILES]
    register_corpus("silesia", full, f"{SILESIA_URL} -> {SILESIA_DIR} (12 files concatenated in sorted() order)",
                    "no licence stated by the publisher; distributed by its author (S. Deorowicz) as a compression "
                    "benchmark; files of mixed origin; used here for measurement only and not redistributed",
                    note=f"silesia.zip sha256 {zsha} (publisher gives no checksum; recorded at first download "
                         "2026-10-09); lzbench's silesia.tar is the same 12 files plus tar headers (211,947,520 B)")
    sample = silesia_sample()
    register_corpus("silesia_sample_12x1MiB", sample, "first 1 MiB of each of the 12 Silesia files, sorted() order",
                    "as corpora.silesia")
    del full
    rows = {cid: {"id": cid, "family": CODECS[cid]["family"], "label": CODECS[cid]["label"],
                  "params": CODECS[cid]["params"]} for cid in FRONTIER_IDS}
    # 1) exact ratios on the full corpus, two worker processes, not timed
    if not sample_only:
        expected_cost = {"brotli_11": 45, "zstd_22": 11, "zstd_22_ldm_off": 11, "xz_9": 11, "xz_6": 10,
                         "zstd_19": 9.3, "brotli_9": 7.3, "bzip2_9": 2, "xz_0": 1.7, "zlib_9": 1.6}
        order = sorted(FRONTIER_IDS + list(EXTRA_FULL), key=lambda c: -expected_cost.get(c, 0.5))
        extra_full = {}
        t0 = time.monotonic()
        with cf.ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("fork")) as ex:
            for cid, clen, csha, ok in ex.map(_full_ratio_job, order):
                if cid in EXTRA_FULL:
                    extra_full[cid] = {"bytes": clen, "ratio": ratio(SILESIA_BYTES, clen), "sha256": csha,
                                       "roundtrip_ok": ok}
                    log(f"  full {cid}: {clen:,} B ratio {SILESIA_BYTES / clen:.3f} ok={ok}")
                    continue
                rows[cid]["full"] = {"bytes": clen, "ratio": ratio(SILESIA_BYTES, clen),
                                     "pct_of_original": round(100 * clen / SILESIA_BYTES, 3), "sha256": csha,
                                     "roundtrip_ok": ok}
                log(f"  full {cid}: {clen:,} B ratio {SILESIA_BYTES / clen:.3f} ok={ok}")
        full_wall = round(time.monotonic() - t0)
    else:
        full_wall = None
        extra_full = {}
    # 2) timings on the 12 MiB stratified sample, one codec at a time, one thread
    warm = sample[: 256 << 10]
    snap_a = contention_snapshot()
    for cid in FRONTIER_IDS:
        co = CODECS[cid]
        co["c"](warm)
        gc.collect()
        gc.disable()
        try:
            t = time.perf_counter_ns()
            comp = co["c"](sample)
            cts = [time.perf_counter_ns() - t]
            n_c = 3 if cts[0] > 3e9 else 7
            for _ in range(n_c - 1):
                t = time.perf_counter_ns()
                co["c"](sample)
                cts.append(time.perf_counter_ns() - t)
            comp = bytes(comp)
            ok = bytes(co["d"](comp)) == sample
            dts = []
            for _ in range(7):
                t = time.perf_counter_ns()
                co["d"](comp)
                dts.append(time.perf_counter_ns() - t)
        finally:
            gc.enable()
        cmed, dmed = statistics.median(cts) / 1e9, statistics.median(dts) / 1e9
        cmb, dmb = len(sample) / cmed / 1e6, len(sample) / dmed / 1e6
        rows[cid]["sample"] = {"bytes": len(comp), "ratio": ratio(len(sample), len(comp)), "roundtrip_ok": ok}
        rows[cid]["timing"] = {"compress_MBps": sig3(cmb), "decompress_MBps": sig3(dmb),
                               "compress_tier": tier(cmb), "decompress_tier": tier(dmb),
                               "compress_runs": n_c, "decompress_runs": 7,
                               "compress_s_median": sig3(cmed), "decompress_s_median": sig3(dmed),
                               "compress_s_min_max": [sig3(min(cts) / 1e9), sig3(max(cts) / 1e9)],
                               "decompress_over_compress_speed": sig3(dmb / cmb)}
        log(f"  timed {cid}: {cmb:.1f} MB/s comp, {dmb:.1f} MB/s decomp (n={n_c}/7) ratio {len(sample) / len(comp):.3f}")
    snap_b = contention_snapshot()
    pts_sample = [(cid, r["timing"]["compress_MBps"], r["sample"]["ratio"]) for cid, r in rows.items()]
    out = {
        "corpus_full": {"name": "silesia", "bytes": SILESIA_BYTES, "sha256": full_sha, "files": files,
                        "zip_sha256": zsha, "url": SILESIA_URL},
        "corpus_timed": {"name": "silesia_sample_12x1MiB", "bytes": len(sample), "sha256": sha(sample)},
        "rows": list(rows.values()),
        "pareto_compress_speed_vs_ratio_sample": pareto(pts_sample),
        "pareto_decompress_speed_vs_ratio_sample": pareto(
            [(cid, r["timing"]["decompress_MBps"], r["sample"]["ratio"]) for cid, r in rows.items()]),
        "full_pass_wall_s": full_wall,
        "zstd_22_ldm_check": ({"ldm_auto_default_bytes": rows["zstd_22"]["full"]["bytes"],
                               "ldm_forced_off_bytes": extra_full["zstd_22_ldm_off"]["bytes"],
                               "ldm_forced_off_roundtrip_ok": extra_full["zstd_22_ldm_off"]["roundtrip_ok"],
                               "bytes_saved_by_auto_ldm": extra_full["zstd_22_ldm_off"]["bytes"] - rows["zstd_22"]["full"]["bytes"],
                               "note": "enable_long_distance_matching is a ZSTD_paramSwitch_e (0 auto, 1 on, 2 off). "
                                       "On auto, libzstd enables LDM when the strategy is btopt or stronger and the "
                                       "window is 2^27 or more, which is level 22 on this 211.9 MB input; the "
                                       "frontier's zstd_22 row therefore includes LDM, as lzbench's does."}
                              if "zstd_22_ldm_off" in extra_full and "full" in rows["zstd_22"] else None),
        "timing_contention": contention_delta(snap_a, snap_b,
                                              "codecs timed one at a time on one thread (about 1 CPU of the cgroup's "
                                              "2-CPU quota); cgroup_cpu_used_s well above phase_wall_s, or a high "
                                              "throttled fraction, means other tenants shared the CPU"),
        "method": "Ratios: each codec/level compresses the full Silesia corpus (12 files concatenated, 211,938,580 B) "
                  "once, in two worker processes (not timed), and the output is decompressed and compared byte for "
                  "byte. Speeds: the 12 MiB stratified sample (first 1 MiB of each file), one codec at a time in the "
                  "main process on one thread, gc disabled while timing; warm-up = one compression of the first "
                  "256 KiB; compression median of 7 runs, or 3 when a run takes over 3 s; decompression median of 7 "
                  "runs after one untimed verifying run. MB/s = sample bytes / median seconds / 10^6, 3 significant "
                  "figures, reported with a tier because the machine is shared. ratio = original / compressed (the "
                  "zstd and LZ4 README convention); pct_of_original = compressed / original * 100 (lzbench's "
                  "convention). zstd_22_ldm_check is one extra untimed full-corpus job (level 22 with long-distance "
                  "matching forced off) that shows what libzstd's automatic LDM contributes to the zstd_22 row.",
    }
    return out


# ----------------------------------------------------------------------------------------------------------
# wire
# ----------------------------------------------------------------------------------------------------------
def part_wire():
    page = WIRE_PAGE.read_bytes()
    dct = WIRE_DICT.read_bytes()
    register_corpus("wire:page", page, str(WIRE_PAGE), "first-party (this publication)")
    register_corpus("wire:dictionary", dct, str(WIRE_DICT), "first-party (this publication)",
                    note="used as a raw-content (LZ77 prefix) dictionary, the way RFC 9842 dcb/dcz use a previously "
                         "fetched resource")
    dh = hashlib.sha256(dct).digest()
    rows = []

    def add(rid, label, body, header=b"", **extra):
        rows.append({"id": rid, "label": label, "bytes": len(header) + len(body), "header_bytes": len(header),
                     "pct_of_identity": round(100 * (len(header) + len(body)) / len(page), 3),
                     "ratio": ratio(len(page), len(header) + len(body)), **extra})

    add("identity", "identity (no Content-Encoding)", page)
    for L in (6, 9):
        c = gz(page, L)
        assert gzip.decompress(c) == page
        add(f"gzip_{L}", f"gzip -{L}", c)
    for Q in (5, 11):
        c = brotli.compress(page, quality=Q)
        assert brotli.decompress(c) == page
        add(f"br_{Q}", f"br (brotli -q {Q}, lgwin 22)", c)
    for L in (3, 19):
        c = zstd.compress(page, L)
        assert zstd.decompress(c) == page
        w = zstd_window_bytes(c)
        add(f"zstd_{L}", f"zstd -{L}", c, window_bytes=w, rfc9659_window_ok=w <= 8 << 20)
    zd = zstd.ZstdDict(dct, is_raw=True)
    dcz_header = struct.pack("<II", 0x184D2A5E, 32) + dh
    for L in (3, 19):
        c = zstd.compress(page, L, zstd_dict=zd.as_undigested_dict)
        full = dcz_header + c
        assert zstd.decompress(full, zstd_dict=zd) == page
        w = zstd_window_bytes(c)
        add(f"dcz_{L}", f"dcz (zstd -{L}, raw dictionary = where-the-json-lives/index.html)", c, dcz_header,
            window_bytes=w, dictionary_load="ZstdDict(is_raw=True).as_undigested_dict")
        cp = zstd.compress(page, L, zstd_dict=zd.as_prefix)
        assert zstd.decompress(dcz_header + cp, zstd_dict=zd.as_prefix) == page
        add(f"dcz_{L}_prefix", f"dcz variant (zstd -{L}, dictionary loaded as a prefix, like --patch-from)", cp,
            dcz_header, window_bytes=zstd_window_bytes(cp), dictionary_load="ZstdDict(is_raw=True).as_prefix")
    bc_info = {}
    try:
        bc = BrotliC()
        bc_info = {"library": "system libbrotlienc.so.1 / libbrotlidec.so.1 via ctypes", **bc.versions()}
        dcb_header = b"\xff\x44\x43\x42" + dh
        for Q in (5, 11):
            c = bc.compress(page, Q, 22, dct)
            assert bc.decompress(c, dct, len(page) + 1024) == page
            add(f"dcb_{Q}", f"dcb (brotli -q {Q}, lgwin 22, raw dictionary = where-the-json-lives/index.html)",
                c, dcb_header, dictionary_load="BrotliEncoderPrepareDictionary(BROTLI_SHARED_DICTIONARY_RAW)")
        same = bc.compress(page, 11, 22) == brotli.compress(page, quality=11)
        bc_info["ctypes_no_dict_q11_identical_to_wheel"] = same
    except (OSError, RuntimeError) as e:
        rows.append({"id": "dcb", "skipped": f"{type(e).__name__}: {e}"})
    first = {f"dictionary_{k}": v for k, v in
             (("identity_bytes", len(dct)), ("br_11_bytes", len(brotli.compress(dct, quality=11))),
              ("zstd_19_bytes", len(zstd.compress(dct, 19))))}
    # delta: the previous committed version of the same page as the dictionary (what dictionary transport is for)
    deltas = []
    for path, old_c, new_c in DELTA_PAIRS:
        try:
            old = subprocess.run(["git", "-C", str(WRITINGS), "show", f"{old_c}:{path}"], capture_output=True,
                                 check=True).stdout
            new = subprocess.run(["git", "-C", str(WRITINGS), "show", f"{new_c}:{path}"], capture_output=True,
                                 check=True).stdout
        except (subprocess.CalledProcessError, OSError) as e:
            deltas.append({"path": path, "skipped": f"{type(e).__name__}: {e}"})
            continue
        register_corpus(f"wire:delta:{path}@{old_c}", old, f"git show {old_c}:{path} (writings repo)",
                        "first-party (this publication)")
        register_corpus(f"wire:delta:{path}@{new_c}", new, f"git show {new_c}:{path} (writings repo)",
                        "first-party (this publication)")
        oh = hashlib.sha256(old).digest()
        zo = zstd.ZstdDict(old, is_raw=True)
        enc = {"identity": len(new), "gzip_6": len(gz(new, 6)), "br_11": len(brotli.compress(new, quality=11)),
               "zstd_19": len(zstd.compress(new, 19))}
        c = zstd.compress(new, 19, zstd_dict=zo.as_undigested_dict)
        assert zstd.decompress(struct.pack("<II", 0x184D2A5E, 32) + oh + c, zstd_dict=zo) == new
        enc["dcz_19"] = 40 + len(c)
        enc["dcz_19_window_bytes"] = zstd_window_bytes(c)
        if bc_info:
            cb = bc.compress(new, 11, 22, old)
            assert bc.decompress(cb, old, len(new) + 1024) == new
            enc["dcb_11"] = 36 + len(cb)
        deltas.append({"path": path, "dictionary_commit": old_c, "target_commit": new_c,
                       "dictionary_bytes": len(old), "target_bytes": len(new),
                       "dictionary_sha256": sha(old), "target_sha256": sha(new), "bytes": enc,
                       "pct_of_identity": {k: round(100 * v / len(new), 3) for k, v in enc.items()
                                           if not k.endswith("window_bytes")}})
    return {
        "page": {"path": str(WIRE_PAGE.relative_to(WRITINGS)), "bytes": len(page), "sha256": sha(page)},
        "dictionary": {"path": str(WIRE_DICT.relative_to(WRITINGS)), "bytes": len(dct), "sha256": sha(dct), **first},
        "rows": rows,
        "delta_previous_version": deltas,
        "brotli_dictionary_encoder": bc_info,
        "method": "gzip via gzip.compress(mtime=0); br via the brotli 1.2.0 wheel (quality q, lgwin 22, generic mode); "
                  "zstd via compression.zstd (window read back from the frame header: RFC 9659 requires <= 8 MB); "
                  "dcz = RFC 9842 40-byte header (zstd skippable frame 0x184D2A5E, length 32, SHA-256 of the "
                  "dictionary) + a zstd frame compressed with the dictionary as raw content; dcb = RFC 9842 36-byte "
                  "header (ff 44 43 42 + SHA-256) + a brotli stream compressed with the dictionary attached as a raw "
                  "LZ77 dictionary through libbrotlienc (the brotli wheel has no dictionary API). Every encoding was "
                  "decoded and compared with the page. Byte counts include the dcz/dcb headers.",
        "note": "rows: the dictionary is a different post from the same site (shared CSS, chrome and script), not "
                "an earlier version of the same page. delta_previous_version: the dictionary is the previous "
                "committed version of the same page on main's first-parent history (git show of the writings repo; "
                "for what-is-quirq, 107e64f is a merge whose first parent is a76229b), the case RFC 9842 is built for.",
    }


# ----------------------------------------------------------------------------------------------------------
# BREACH-style length oracle (synthetic)
# ----------------------------------------------------------------------------------------------------------
ORACLE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Inbox - Example Mail</title>
<link rel="stylesheet" href="/static/app.css"><script src="/static/app.js" defer></script></head>
<body>
<header class="top"><a class="brand" href="/">Example Mail</a>
<nav><a href="/inbox">Inbox</a> <a href="/sent">Sent</a> <a href="/drafts">Drafts</a> <a href="/settings">Settings</a>
<a class="signout" href="/logout?csrf_token={secret}">Sign out</a></nav></header>
<main>
<form class="search" action="/search" method="get"><input type="search" name="q" placeholder="Search mail"></form>
<p class="empty">No messages match <b>{reflected}</b>. Try a different search.</p>
<ul class="messages">
{messages}
</ul>
</main>
<footer><a href="/help">Help</a> <a href="/privacy">Privacy</a> <a href="/terms">Terms</a></footer>
</body></html>
"""


def part_oracle():
    rng = random.Random(2013)
    hexd = "0123456789abcdef"
    secret = "".join(rng.choice(hexd) for _ in range(32))
    filler = "".join(rng.choice("ghijklmnopqrstuvwxyz") for _ in range(32))  # never hex, so never part of the secret
    senders = ["Ada", "Grace", "Alan", "Edsger", "Barbara", "Donald", "Frances", "Ken"]
    subjects = ["Quarterly report", "Lunch on Friday?", "Re: build failures", "Invoice 2219", "Travel plans",
                "Re: Re: the migration", "Meeting notes", "Welcome aboard"]
    messages = "\n".join(f'<li class="msg"><a href="/m/{1000 + i}"><span class="from">{senders[i]}</span> '
                         f'<span class="subj">{subjects[i]}</span> <time>2026-10-0{1 + i % 9}</time></a></li>'
                         for i in range(8))

    def page(reflected, token):
        return ORACLE_PAGE.format(secret=token, reflected=reflected, messages=messages).encode()

    def deflate(b):
        o = zlib.compressobj(6, zlib.DEFLATED, -15)
        return len(o.compress(b) + o.flush())

    def lens(b):
        return {"deflate_6": deflate(b), "brotli_5": len(brotli.compress(b, quality=5)), "zstd_3": len(zstd.compress(b, 3))}

    prefix = "csrf_token="

    def guess(k):
        return secret[:k] + filler[k:]

    sweep = []
    for k in (0, 1, 2, 4, 8, 12, 16, 20, 24, 28, 32):
        g = prefix + guess(k)
        sweep.append({"correct_leading_chars": k, "reflected": g, "page_bytes": len(page(g, secret)),
                      "compressed_bytes": lens(page(g, secret))})
    # character-by-character: at each position, which of the 16 hex candidates gives the shortest output?
    per_pos = {"deflate_6": 0, "brotli_5": 0, "zstd_3": 0}
    ties = {"deflate_6": 0, "brotli_5": 0, "zstd_3": 0}
    lost = {"deflate_6": 0, "brotli_5": 0, "zstd_3": 0}
    example = None
    for k in range(32):
        cand = {c: lens(page(prefix + secret[:k] + c + filler[k + 1:], secret)) for c in hexd}
        for codec in per_pos:
            vals = {c: v[codec] for c, v in cand.items()}
            m = min(vals.values())
            winners = [c for c, v in vals.items() if v == m]
            if winners == [secret[k]]:
                per_pos[codec] += 1
            elif secret[k] in winners:
                ties[codec] += 1
            else:
                lost[codec] += 1
        if k == 4:
            example = {"position": k, "right_char": secret[k],
                       "deflate_6_by_candidate": {c: v["deflate_6"] for c, v in cand.items()}}
    masked = []
    mrng = random.Random(99)
    for k in (0, 8, 16, 24, 32):
        mask = mrng.randbytes(16)
        tok = mask.hex() + bytes(a ^ b for a, b in zip(bytes.fromhex(secret), mask)).hex()
        g = prefix + guess(k)
        masked.append({"correct_leading_chars": k, "compressed_bytes": lens(page(g, tok))})
    return {
        "secret": secret, "secret_note": "synthetic: random.Random(2013), 32 hex characters; not a real credential",
        "filler": filler, "reflected_prefix": prefix,
        "page_template_bytes": len(page(prefix + guess(0), secret)),
        "sweep": sweep,
        "per_character_oracle": {"positions": 32, "candidates_per_position": 16,
                                 "right_char_uniquely_shortest": per_pos, "right_char_tied_for_shortest": ties,
                                 "right_char_not_among_shortest": lost,
                                 "example": example},
        "masked_token_sweep": masked,
        "method": "One synthetic HTML response (an inbox page) holds the secret in a link (?csrf_token=SECRET) and "
                  "reflects attacker input in the text. The attacker's input is 'csrf_token=' + a 32-character guess "
                  "whose first k characters are right and the rest are non-hex filler, so every guess has the same "
                  "length. deflate_6 = raw DEFLATE at level 6 (what a gzip body holds; a gzip member adds a constant "
                  "18 bytes); brotli_5 = brotli quality 5; zstd_3 = zstd level 3. Masked: the token is sent as a fresh "
                  "16-byte mask plus (secret XOR mask) per response, the standard BREACH mitigation.",
    }


# ----------------------------------------------------------------------------------------------------------
# decompression bombs
# ----------------------------------------------------------------------------------------------------------
BOMB_TOTAL = 1 << 30
BOMB_CHUNK = 1 << 20
BOMB_CAP = 64 << 20


def part_bombs():
    zeros = bytes(BOMB_CHUNK)
    makers = {
        "gzip_9": (lambda: zlib.compressobj(9, zlib.DEFLATED, 31), lambda o, x: o.compress(x), lambda o: o.flush()),
        "zstd_3": (lambda: zstd.ZstdCompressor(level=3), lambda o, x: o.compress(x), lambda o: o.flush()),
        "zstd_19": (lambda: zstd.ZstdCompressor(level=19), lambda o, x: o.compress(x), lambda o: o.flush()),
        "bzip2_9": (lambda: bz2.BZ2Compressor(9), lambda o, x: o.compress(x), lambda o: o.flush()),
        "xz_6": (lambda: lzma.LZMACompressor(preset=6), lambda o, x: o.compress(x), lambda o: o.flush()),
        "brotli_5": (lambda: brotli.Compressor(quality=5), lambda o, x: o.process(x), lambda o: o.finish()),
    }
    rows = []
    for cid, (mk, feed, fin) in makers.items():
        t0 = time.perf_counter()
        o = mk()
        parts = [feed(o, zeros) for _ in range(BOMB_TOTAL // BOMB_CHUNK)]
        parts.append(fin(o))
        bomb = b"".join(parts)
        tc = time.perf_counter() - t0
        # bounded: ask for at most BOMB_CAP bytes and stop
        if cid.startswith("gzip"):
            d = zlib.decompressobj(31)
            first = d.decompress(bomb, BOMB_CAP)
            bounded = {"returned_bytes": len(first), "eof": d.eof, "input_left_unconsumed": len(d.unconsumed_tail)}
        elif cid.startswith("brotli"):
            d = brotli.Decompressor()
            first = d.process(bomb, output_buffer_limit=BOMB_CAP)
            bounded = {"returned_bytes": len(first), "is_finished": d.is_finished(),
                       "can_accept_more_data": d.can_accept_more_data()}
        else:
            d = {"zstd": zstd.ZstdDecompressor, "bzip2": bz2.BZ2Decompressor, "xz": lzma.LZMADecompressor}[cid.split("_")[0]]()
            first = d.decompress(bomb, max_length=BOMB_CAP)
            bounded = {"returned_bytes": len(first), "eof": d.eof, "needs_input": d.needs_input}
        bounded["stopped_at_cap"] = len(first) == BOMB_CAP
        bounded["overshoot_bytes"] = len(first) - BOMB_CAP
        del first
        # full drain in <= 1 MiB steps: memory stays bounded, total proves the expansion
        t0 = time.perf_counter()
        total, nonzero = 0, False
        if cid.startswith("gzip"):
            d = zlib.decompressobj(31)
            buf = bomb
            while not d.eof:
                out = d.decompress(buf, BOMB_CHUNK)
                buf = d.unconsumed_tail
                total += len(out)
                nonzero = nonzero or out.count(0) != len(out)
        elif cid.startswith("brotli"):
            d = brotli.Decompressor()
            out = d.process(bomb, output_buffer_limit=BOMB_CHUNK)
            total += len(out)
            nonzero = nonzero or out.count(0) != len(out)
            while not d.is_finished():
                out = d.process(b"", output_buffer_limit=BOMB_CHUNK)
                total += len(out)
                nonzero = nonzero or out.count(0) != len(out)
        else:
            d = {"zstd": zstd.ZstdDecompressor, "bzip2": bz2.BZ2Decompressor, "xz": lzma.LZMADecompressor}[cid.split("_")[0]]()
            out = d.decompress(bomb, max_length=BOMB_CHUNK)
            total += len(out)
            nonzero = nonzero or out.count(0) != len(out)
            while not d.eof:
                out = d.decompress(b"", max_length=BOMB_CHUNK)
                total += len(out)
                nonzero = nonzero or out.count(0) != len(out)
        td = time.perf_counter() - t0
        rows.append({"id": cid, "bomb_bytes": len(bomb), "expands_to": total, "ratio": round(total / len(bomb), 1),
                     "all_zero": not nonzero, "sha256": sha(bomb), "bounded_call": bounded,
                     "compress_s_single_run": sig3(tc), "full_streaming_decompress_s_single_run": sig3(td)})
        log(f"  bomb {cid}: {len(bomb):,} B -> {total:,} B (x{total / len(bomb):,.0f})")
    return {"payload": f"{BOMB_TOTAL:,} zero bytes, fed in {BOMB_CHUNK:,}-byte chunks (never held in memory)",
            "cap_bytes": BOMB_CAP, "rows": rows,
            "method": "Compression is streamed with each library's incremental compressor. 'bounded_call' is one "
                      "decompression call asked for at most cap_bytes (zlib max_length, ZstdDecompressor/"
                      "BZ2Decompressor/LZMADecompressor max_length, brotli Decompressor.process(output_buffer_limit)); "
                      "zlib, zstd, bzip2 and xz return exactly the cap with the stream unfinished, so the caller can "
                      "refuse; brotli's output_buffer_limit stops growing the buffer once it reaches the limit, so it "
                      "can return more than the limit (overshoot_bytes). The full drain "
                      "decodes in 1 MiB steps to prove the expansion. Times are single runs (tiers, shared machine)."}


# ----------------------------------------------------------------------------------------------------------
# compaction: SQLite, the key-value log, git
# ----------------------------------------------------------------------------------------------------------
WORDS = ("the of and to in is it that for on with as was by be this are or at from which an have not but they "
         "one all were there their can more has will would been when who other into time only new some could "
         "than these two may first then do any like my now over such our man me even most made after also did "
         "many before must through back years where much your way well down should because each just those "
         "people how too little state good very make world still own see men work long get here between both "
         "life being under never day same another know while last might us great old year off come since against "
         "go came right used take three").split()


def db_state(con, path):
    return {"file_bytes": path.stat().st_size, "page_size": con.execute("PRAGMA page_size").fetchone()[0],
            "page_count": con.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": con.execute("PRAGMA freelist_count").fetchone()[0],
            "rows": con.execute("SELECT count(*) FROM docs").fetchone()[0]}


def sqlite_docs(n=100_000, seed=11):
    rng = random.Random(seed)
    base = int(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    out = []
    for i in range(1, n + 1):
        out.append((i, json.dumps({
            "doc_id": f"d-{i:06d}", "agent": rng.choice(["claude_code", "codex", "hermes", "pi"]),
            "status": rng.choice(["running", "idle", "done", "failed"]), "owner": f"user-{rng.randrange(200):03d}",
            "created_at": iso_ms(base + i * 997), "usage": {"input_tokens": rng.randrange(1, 10**6),
                                                            "output_tokens": rng.randrange(1, 10**5)},
            "tags": rng.sample(TAGS, 3), "summary": " ".join(rng.choices(WORDS, k=rng.randint(30, 60)))},
            separators=(",", ":"))))
    return out


def remnants(raw: bytes, deleted: set, psz: int):
    """Deleted documents whose doc_id string is still in the file, by where the bytes sit: a freelist page, the
    unallocated gap of a live b-tree page (between the cell pointer array and the cell content area), or the
    content area (a freeblock)."""
    free, t = set(), struct.unpack(">I", raw[32:36])[0]
    while t:
        pg = raw[(t - 1) * psz: t * psz]
        nxt, n = struct.unpack(">II", pg[:8])
        free.add(t)
        free.update(struct.unpack(">I", pg[8 + 4 * k: 12 + 4 * k])[0] for k in range(n))
        t = nxt
    where = Counter()
    ids = set()
    for m in re.finditer(rb'"doc_id":"d-(\d{6})"', raw):
        i = int(m.group(1))
        if i not in deleted:
            continue
        ids.add(i)
        pgno, off = m.start() // psz + 1, m.start() % psz
        base = (pgno - 1) * psz + (100 if pgno == 1 else 0)
        if pgno in free:
            where["freelist_page"] += 1
        else:
            cstart = struct.unpack(">H", raw[base + 5: base + 7])[0] or 65536
            where["live_page_unallocated_gap" if off < cstart else "live_page_content_area"] += 1
    return {"documents": len(ids), "by_location": dict(where)}


def sqlite_run(tmp: Path, docs, mode: str, pattern: str):
    path = tmp / f"docs-{mode.lower()}-{pattern}.sqlite"
    for p in (path, Path(str(path) + "-journal")):
        p.unlink(missing_ok=True)
    con = sqlite3.connect(path, isolation_level=None)
    con.execute(f"PRAGMA auto_vacuum={mode}")
    con.execute("CREATE TABLE docs(id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
    con.execute("BEGIN")
    con.executemany("INSERT INTO docs VALUES(?, ?)", docs)
    con.execute("COMMIT")
    res = {"auto_vacuum": mode, "delete_pattern": pattern, "after_insert": db_state(con, path)}
    n = len(docs)
    if pattern == "oldest90":
        where, deleted = f"id <= {n * 9 // 10}", set(range(1, n * 9 // 10 + 1))
    else:
        where, deleted = "id % 10 != 0", {i for i in range(1, n + 1) if i % 10}
    before_sha = sha("\n".join(f"{i}\t{b}" for i, b in con.execute(f"SELECT id, body FROM docs WHERE NOT ({where}) ORDER BY id")).encode())
    con.execute("BEGIN")
    con.execute(f"DELETE FROM docs WHERE {where}")
    con.execute("COMMIT")
    st = db_state(con, path)
    raw = path.read_bytes()
    st["deleted_rows_still_present_in_file_bytes"] = remnants(raw, deleted, st["page_size"])
    st["zstd_3_of_file_bytes"] = len(zstd.compress(raw, 3))
    res["after_delete"] = st
    io0, t0 = proc_io(), time.perf_counter()
    if mode == "NONE":
        con.execute("VACUUM")
        step = "VACUUM"
    elif mode == "INCREMENTAL":
        # the pragma frees one page per sqlite3_step(); Python's execute() steps once, so drain it with fetchall()
        con.execute("PRAGMA incremental_vacuum").fetchall()
        step = "PRAGMA incremental_vacuum (stepped to completion)"
    else:
        step = None
    if step:
        io1 = proc_io()
        st = db_state(con, path)
        raw = path.read_bytes()
        st["deleted_rows_still_present_in_file_bytes"] = remnants(raw, deleted, st["page_size"])
        st["zstd_3_of_file_bytes"] = len(zstd.compress(raw, 3))
        st["bytes_written_by_step"] = io1.get("wchar", 0) - io0.get("wchar", 0)
        st["bytes_read_by_step"] = io1.get("rchar", 0) - io0.get("rchar", 0) - io0.get("_self_read", 0)
        st["step_s_single_run"] = sig3(time.perf_counter() - t0)
        res["step"] = step
        res["after_step"] = st
    after_sha = sha("\n".join(f"{i}\t{b}" for i, b in con.execute("SELECT id, body FROM docs ORDER BY id")).encode())
    res["logical_content_unchanged"] = before_sha == after_sha
    res["secure_delete"] = con.execute("PRAGMA secure_delete").fetchone()[0]
    con.close()
    path.unlink()
    return res


def sqlite_rowid_check(tmp: Path):
    path = tmp / "rowid.sqlite"
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("CREATE TABLE notes(body TEXT)")              # no INTEGER PRIMARY KEY: rowid is implicit
    con.execute("CREATE INDEX notes_body ON notes(body)")
    con.execute("BEGIN")
    con.executemany("INSERT INTO notes(body) VALUES(?)", ((f"note {i:06d} " + "x" * 200,) for i in range(20_000)))
    con.execute("COMMIT")
    con.execute("DELETE FROM notes WHERE rowid % 10 != 0")
    before = dict(con.execute("SELECT body, rowid FROM notes"))
    con.execute("VACUUM")
    after = dict(con.execute("SELECT body, rowid FROM notes"))
    con.close()
    path.unlink()
    changed = sum(1 for k, v in before.items() if after.get(k) != v)
    return {"table": "notes(body TEXT) + index, no INTEGER PRIMARY KEY; 20,000 rows, 90% deleted (scattered)",
            "rows": len(before), "rowids_changed_by_vacuum": changed,
            "max_rowid_before": max(before.values()), "max_rowid_after": max(after.values())}


def tree_bytes(root: Path):
    app = alloc = files = 0
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            st = p.stat()
            app += st.st_size
            alloc += st.st_blocks * 512
            files += 1
    return {"apparent_bytes": app, "allocated_bytes": alloc, "files": files}


def git_part(tmp: Path, n_commits=300, n_files=24, seed=3):
    repo = tmp / "repo"
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "LC_ALL": "C", "TZ": "UTC",
           "GIT_AUTHOR_NAME": "XO Bench", "GIT_AUTHOR_EMAIL": "bench@example.invalid",
           "GIT_COMMITTER_NAME": "XO Bench", "GIT_COMMITTER_EMAIL": "bench@example.invalid"}

    def git(*args, when=None):
        e = dict(env)
        if when is not None:
            e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = f"{when} +0000"
        return subprocess.run(["git", *args], cwd=repo, env=e, check=True, capture_output=True, text=True).stdout

    git("init", "-q", "-b", "main")
    for k, v in (("gc.auto", "0"), ("maintenance.auto", "false"), ("pack.threads", "1"), ("commit.gpgsign", "false"),
                 ("core.autocrlf", "false")):
        git("config", k, v)
    rng = random.Random(seed)
    files = {}
    for i in range(n_files):
        if i % 2 == 0:
            name = f"config/service_{i:02d}.json"
            cfg = {f"key_{j:03d}": (rng.randrange(10**6) if j % 3 else " ".join(rng.choices(WORDS, k=4)))
                   for j in range(rng.randint(60, 160))}
            lines = json.dumps(cfg, indent=2).splitlines()
        else:
            name = f"src/module_{i:02d}.py"
            lines = []
            for f in range(rng.randint(25, 60)):
                lines += [f"def step_{f:03d}(state, value):", f"    \"\"\"{' '.join(rng.choices(WORDS, k=8))}\"\"\"",
                          f"    total = state.get('{rng.choice(WORDS)}', 0) + value * {rng.randrange(1, 99)}",
                          f"    return total - {rng.randrange(1000)}", ""]
        files[name] = lines
    t = 1_790_000_000

    def write_all():
        for name, lines in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(lines) + "\n")

    write_all()
    git("add", "-A")
    git("commit", "-q", "-m", "initial import", when=t)
    for c in range(1, n_commits):
        for name in rng.sample(sorted(files), rng.randint(1, 3)):
            lines = files[name]
            for _ in range(rng.randint(1, 5)):
                op = rng.random()
                pos = rng.randrange(len(lines))
                if op < 0.6:
                    lines[pos] = re.sub(r"\d+", lambda m: str(rng.randrange(10**6)), lines[pos], count=1) \
                        if re.search(r"\d", lines[pos]) else lines[pos] + f"  # {rng.choice(WORDS)}"
                elif op < 0.85:
                    lines.insert(pos, f"    # note: {' '.join(rng.choices(WORDS, k=6))}")
                elif len(lines) > 20:
                    del lines[pos]
            p = repo / name
            p.write_text("\n".join(lines) + "\n")
        git("commit", "-q", "-a", "-m", f"change {c}", when=t + c * 3600)
    head_tree = sum(int(ln.split()[3]) for ln in git("ls-tree", "-r", "-l", "HEAD").splitlines())
    # unreachable history: a scratch branch with large files, then deleted and its reflog expired
    git("checkout", "-q", "-b", "scratch")
    for c in range(5):
        (repo / f"blob_{c}.dat").write_text(rng.randbytes(128 << 10).hex())
        git("add", "-A")
        git("commit", "-q", "-m", f"scratch {c}", when=t + (n_commits + c) * 3600)
    git("checkout", "-q", "main")
    git("branch", "-q", "-D", "scratch")
    git("reflog", "expire", "--expire=now", "--all")

    def count_objects():
        return {k: int(v) for k, v in (ln.split(": ") for ln in git("count-objects", "-v").splitlines())}

    def object_totals():
        tot = Counter()
        cnt = Counter()
        for ln in git("cat-file", "--batch-all-objects", "--batch-check=%(objecttype) %(objectsize)").splitlines():
            ty, sz = ln.split()
            tot[ty] += int(sz)
            cnt[ty] += 1
        return {"objects": sum(cnt.values()), "uncompressed_bytes": sum(tot.values()), "by_type_count": dict(cnt),
                "by_type_bytes": dict(tot)}

    reachable = len(git("rev-list", "--objects", "--all").splitlines())
    before = {"count_objects": count_objects(), "dot_git": tree_bytes(repo / ".git"),
              "dot_git_objects_dir": tree_bytes(repo / ".git" / "objects"), "objects": object_totals(),
              "reachable_objects": reachable}
    t0 = time.perf_counter()
    git("gc", "--prune=now", "-q")
    tgc = time.perf_counter() - t0
    vp = git("verify-pack", "-v", *[str(p) for p in (repo / ".git" / "objects" / "pack").glob("*.idx")])
    deltas = sum(int(m) for m in re.findall(r"chain length = \d+: (\d+) objects?", vp))
    nondelta = sum(int(m) for m in re.findall(r"non delta: (\d+) objects?", vp))
    after = {"count_objects": count_objects(), "dot_git": tree_bytes(repo / ".git"),
             "dot_git_objects_dir": tree_bytes(repo / ".git" / "objects"), "objects": object_totals(),
             "pack_objects_delta": deltas, "pack_objects_non_delta": nondelta,
             "pack_file_bytes": sum(q.stat().st_size for q in (repo / ".git" / "objects" / "pack").glob("*.pack")),
             "idx_file_bytes": sum(q.stat().st_size for q in (repo / ".git" / "objects" / "pack").glob("*.idx"))}
    out = {"commits_on_main": n_commits, "files": n_files, "head_tree_bytes": head_tree,
           "unreachable_setup": "branch 'scratch' with 5 commits each adding a 256 KiB hex file, deleted, reflog expired",
           "before_gc": before, "after_gc": after, "gc_s_single_run": sig3(tgc),
           "git_config": {"gc.auto": 0, "pack.threads": 1, "core.compression": "default", "core.loosecompression": "default"},
           "command": "git gc --prune=now",
           "note": "dot_git is every regular file under .git (objects plus hooks samples, index, logs, config); dot_git_objects_dir is .git/objects alone (loose objects before gc; after gc the .pack, .idx and .rev files plus info/packs and info/commit-graph). count_objects size-pack is in KiB and counts the .pack and .idx files together. allocated_bytes = st_blocks * 512 on this filesystem (4 KiB blocks)"}
    shutil.rmtree(repo, ignore_errors=True)
    return out


def part_compaction():
    tmp = TMP / "what-compression-keeps"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    os.environ["SQLITE_TMPDIR"] = str(tmp)                    # VACUUM's temporary database goes here
    docs = sqlite_docs()
    register_corpus("sqlite_docs", "\n".join(b for _, b in docs).encode(),
                    "generated by _compute.py sqlite_docs() with seed 11", "synthetic, no third-party content",
                    note="100,000 JSON documents (agent-session-like records), one per row")
    runs = []
    for mode, pattern in (("NONE", "oldest90"), ("NONE", "scattered90"), ("INCREMENTAL", "oldest90"),
                          ("INCREMENTAL", "scattered90"), ("FULL", "oldest90")):
        t0 = time.monotonic()
        runs.append(sqlite_run(tmp, docs, mode, pattern))
        log(f"  sqlite {mode} {pattern}: {time.monotonic() - t0:.0f} s")
    c = sqlite3.connect(":memory:")
    opts = [r[0] for r in c.execute("PRAGMA compile_options")]
    c.close()
    sq = {"sqlite_version": sqlite3.sqlite_version, "journal_mode": "delete (default)", "rows_inserted": len(docs),
          "compile_options_relevant": [o for o in opts if "SECURE_DELETE" in o or "AUTOVACUUM" in o or "PAGE_SIZE" in o],
          "doc_bytes_total": sum(len(b) for _, b in docs), "runs": runs, "rowid_check": sqlite_rowid_check(tmp),
          "method": "auto_vacuum set before CREATE TABLE; 100,000 rows inserted in one transaction; 90% deleted in one "
                    "transaction either as the oldest 90% (ids 1..90,000, whole pages free up) or scattered (every "
                    "row whose id is not a multiple of 10, so most pages keep a few rows); then VACUUM (NONE) or "
                    "PRAGMA incremental_vacuum (INCREMENTAL); FULL truncates at commit. bytes_written_by_step is the "
                    "process's /proc/self/io wchar delta (bytes passed to write(), including VACUUM's temporary "
                    "database and rollback journal). deleted_rows_still_present_in_file_bytes counts deleted "
                    "documents whose doc_id string can still be found in the raw database file, and where (this Ubuntu "
                    "build compiles in SECURE_DELETE, so freed cells and freelist pages are zeroed)."}
    lines = make_kv_log()
    raw_b = sum(len(x) for x in lines)
    live_b = len(b"".join(kv_compact(lines)))
    kv = {"one_shot": {"bytes_read": raw_b, "bytes_written": live_b, "live_bytes": live_b,
                       "space_reclaimed_bytes": raw_b - live_b,
                       "note": "a full compaction reads the whole log once and writes only the live state"},
          "online_cleaner": kafka_style_cleaner(lines)}
    t0 = time.monotonic()
    g = git_part(tmp)
    log(f"  git: {time.monotonic() - t0:.0f} s")
    shutil.rmtree(tmp, ignore_errors=True)
    return {"sqlite": sq, "kv_log": kv, "git": g}


# ----------------------------------------------------------------------------------------------------------
# minification
# ----------------------------------------------------------------------------------------------------------
def part_minify():
    rows = []
    for p in MINIFY_DOCS:
        orig = p.read_bytes()
        obj = json.loads(orig)
        forms = {"as_on_disk": orig,
                 "pretty_indent2": (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode(),
                 "minified": json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()}
        assert all(json.loads(v) == obj for v in forms.values())
        register_corpus(f"minify:{p.relative_to(WRITINGS)}", orig, str(p.relative_to(WRITINGS)),
                        "first-party (this publication)")
        r = {"doc": str(p.relative_to(WRITINGS)), "forms": {}}
        for fname, b in forms.items():
            r["forms"][fname] = {"raw": len(b), "gzip_6": len(gz(b, 6)), "brotli_11": len(brotli.compress(b, quality=11)),
                                 "zstd_3": len(zstd.compress(b, 3))}
        pr, mn = r["forms"]["pretty_indent2"], r["forms"]["minified"]
        r["minify_saving_pct"] = {k: round(100 * (pr[k] - mn[k]) / pr[k], 2) for k in pr}
        rows.append(r)
    return {"rows": rows,
            "method": "pretty_indent2 = json.dumps(indent=2, ensure_ascii=False) + newline; minified = json.dumps("
                      "separators=(',', ':'), ensure_ascii=False); both re-parse to the same value; gzip_6 mtime 0; "
                      "brotli_11 lgwin 22; zstd_3. minify_saving_pct compares minified with pretty_indent2 in each column."}


# ----------------------------------------------------------------------------------------------------------
# DCT demo (pure Python)
# ----------------------------------------------------------------------------------------------------------
Q50 = [[16, 11, 10, 16, 24, 40, 51, 61], [12, 12, 14, 19, 26, 58, 60, 55], [14, 13, 16, 24, 40, 57, 69, 56],
       [14, 17, 22, 29, 51, 87, 80, 62], [18, 22, 37, 56, 68, 109, 103, 77], [24, 35, 55, 64, 81, 104, 113, 92],
       [49, 64, 78, 87, 103, 121, 120, 101], [72, 92, 95, 98, 112, 100, 103, 99]]
ZIGZAG = sorted(((v, u) for v in range(8) for u in range(8)),
                key=lambda p: (p[0] + p[1], p[0] if (p[0] + p[1]) % 2 else p[1]))


def _c(k):
    return 1 / math.sqrt(2) if k == 0 else 1.0


def fdct(f):
    return [[0.25 * _c(u) * _c(v) * sum(f[y][x] * math.cos((2 * x + 1) * u * math.pi / 16) *
                                         math.cos((2 * y + 1) * v * math.pi / 16) for y in range(8) for x in range(8))
             for u in range(8)] for v in range(8)]


def idct(F):
    return [[0.25 * sum(_c(u) * _c(v) * F[v][u] * math.cos((2 * x + 1) * u * math.pi / 16) *
                        math.cos((2 * y + 1) * v * math.pi / 16) for v in range(8) for u in range(8))
             for x in range(8)] for y in range(8)]


def rnd_half_away(x):
    x = round(x, 9)                    # snap float noise first: an exact tie such as 56/16 = 3.5 must not round
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)   # by whether the DCT sum came out 3.4999999...


def part_dct_demo():
    blocks = {
        "smooth_gradient": [[100 + 6 * x + 4 * y for x in range(8)] for y in range(8)],
        "gradient_with_edge": [[90 + 4 * x + 3 * y + (70 if x >= 4 else 0) for x in range(8)] for y in range(8)],
    }
    out = []
    for name, px in blocks.items():
        F = fdct([[p - 128 for p in row] for row in px])
        Sq = [[rnd_half_away(F[v][u] / Q50[v][u]) for u in range(8)] for v in range(8)]
        zz = [Sq[v][u] for v, u in ZIGZAG]
        last_nz = max((i for i, c in enumerate(zz) if c), default=-1)
        R = idct([[Sq[v][u] * Q50[v][u] for u in range(8)] for v in range(8)])
        rec = [[max(0, min(255, rnd_half_away(R[y][x] + 128))) for x in range(8)] for y in range(8)]
        err = [rec[y][x] - px[y][x] for y in range(8) for x in range(8)]
        mse = sum(e * e for e in err) / 64
        out.append({"name": name, "pixels": px,
                    "dct_coefficients": [[round(c, 1) for c in row] for row in F],
                    "quantized": Sq, "zero_coefficients": sum(1 for c in zz if c == 0),
                    "nonzero_coefficients": sum(1 for c in zz if c), "zigzag": zz,
                    "last_nonzero_zigzag_index": last_nz, "reconstructed": rec,
                    "max_abs_error": max(abs(e) for e in err),
                    "psnr_db": round(10 * math.log10(255 ** 2 / mse), 2) if mse else None})
    return {"blocks": out, "quant_table": Q50,
            "method": "Synthetic 8x8 blocks (no image file). Level shift -128, the 2-D DCT of ITU-T T.81 A.3.3 "
                      "(F(v,u) = 1/4 C(u) C(v) sum f(y,x) cos((2x+1)u pi/16) cos((2y+1)v pi/16)), quantization "
                      "Sq = round(F/Q) with T.81 Annex K Table K.1 (luminance), which is the IJG 'quality 50' table "
                      "unscaled, rounding half away from zero after snapping to 9 decimals (the smooth block's DC "
                      "coefficient is exactly 56, and 56/16 = 3.5 is a tie that rounds to 4); reconstructed = "
                      "dequantize, inverse DCT, +128, round, clamp. zigzag is the T.81 Figure A.6 order; rows are v "
                      "(vertical frequency), columns u."}


# ----------------------------------------------------------------------------------------------------------
# machine
# ----------------------------------------------------------------------------------------------------------
def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def loaded_libraries():
    pats = {"zlib": "libz.so", "libzstd": "libzstd.so", "liblzma": "liblzma.so", "libbz2": "libbz2.so",
            "libsqlite3": "libsqlite3.so", "libbrotlienc": "libbrotlienc.so", "libbrotlidec": "libbrotlidec.so",
            "brotli_wheel": "_brotli", "lz4_wheel": "lz4/", "cramjam_wheel": "cramjam", "_zstd": "_zstd.",
            "_lzma": "_lzma.", "_bz2": "_bz2.", "zlib_module": "zlib.cpython", "_sqlite3": "_sqlite3."}
    found = {}
    try:
        for ln in Path("/proc/self/maps").read_text().splitlines():
            p = ln.split()[-1] if len(ln.split()) >= 6 else ""
            if not p.startswith("/"):
                continue
            for k, pat in pats.items():
                if pat in p and ".so" in p:
                    found.setdefault(k, set()).add(p)
    except OSError:
        pass
    out = {}
    for k, ps in sorted(found.items()):
        out[k] = [{"path": p, "sha256": sha(Path(p).read_bytes())} for p in sorted(ps) if Path(p).exists()]
    return out


def c_version(path, fn):
    try:
        lib = ctypes.CDLL(path)
        f = getattr(lib, fn)
        f.restype = ctypes.c_char_p
        return f().decode()
    except (OSError, AttributeError):
        return None


def machine_info():
    cpu = None
    for ln in Path("/proc/cpuinfo").read_text().splitlines():
        if ln.startswith("model name"):
            cpu = ln.split(":", 1)[1].strip()
            break
    libs = loaded_libraries()

    def first(k):
        return libs.get(k, [{}])[0].get("path")

    try:
        bver = BrotliC().versions()
    except OSError:
        bver = None
    return {
        "date_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "os": sh(["sh", "-c", ". /etc/os-release && echo $PRETTY_NAME"]), "kernel": platform.release(),
        "arch": platform.machine(), "cpu": cpu, "cpus_host": os.cpu_count(),
        "cpus_affinity": len(os.sched_getaffinity(0)),
        "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip() if Path("/sys/fs/cgroup/cpu.max").exists() else None,
        "mem_total": Path("/proc/meminfo").read_text().splitlines()[0].split(":")[1].strip(),
        "python": platform.python_version(), "python_executable": str(PY_BINARY), "uv": sh(["uv", "--version"]),
        "git": sh(["git", "--version"]),
        "versions": {
            "zlib_compiled": zlib.ZLIB_VERSION, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "libzstd": zstd.zstd_version, "liblzma": c_version(first("liblzma"), "lzma_version_string"),
            "libbz2": c_version(first("libbz2"), "BZ2_bzlibVersion"), "sqlite": sqlite3.sqlite_version,
            "brotli_wheel": brotli.__version__, "brotli_wheel_library": getattr(brotli, "version", None),
            "libbrotli_system_ctypes": bver, "lz4_wheel": lz4.__version__,
            "lz4_wheel_library": lz4.library_version_string(), "cramjam_wheel": cramjam.__version__,
            "snappy": "cramjam's Rust Snappy implementation (version not exposed)",
        },
        "libraries_loaded": libs,
        "downloads": {"silesia.zip": {"url": SILESIA_URL, "path": str(SILESIA_ZIP),
                                      "sha256": sha(SILESIA_ZIP.read_bytes()) if SILESIA_ZIP.exists() else None,
                                      "expected_sha256": SILESIA_ZIP_SHA256,
                                      "publisher_checksum": "none published; expected_sha256 recorded at first download"}},
        "binaries_downloaded": "none (all codecs are the stdlib, three pinned wheels and the system libbrotli)",
    }


# ----------------------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------------------
PARTS = {"treatments": part_treatments, "entropy": part_entropy, "random": part_random, "lz_demo": part_lz_demo,
         "window": part_window, "wire": part_wire, "oracle": part_oracle, "bombs": part_bombs,
         "compaction": part_compaction, "minify": part_minify, "dct_demo": part_dct_demo, "frontier": part_frontier}


def main(argv):
    only = None
    sample_only = "--sample-only" in argv
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
        bad = set(only) - set(PARTS)
        if bad:
            sys.exit(f"unknown keys: {sorted(bad)}")
    keys = [k for k in ALL_KEYS if only is None or k in only]
    numbers = {}
    if only and OUT_JSON.exists():
        numbers = json.loads(OUT_JSON.read_text())
        for name, c in numbers.get("corpora", {}).items():
            CORPORA[name] = c
    t_start = time.monotonic()
    snap0 = contention_snapshot()
    phase = numbers.get("phase_seconds", {})
    runs = numbers.get("key_runs", {})
    for k in keys:
        log(f"{k} ...")
        t0 = time.monotonic()
        try:
            numbers[k] = PARTS[k](sample_only) if k == "frontier" else PARTS[k]()
        except Exception as e:  # noqa: BLE001
            numbers[k] = {"error": f"{type(e).__name__}: {e}"}
            log(f"{k} FAILED: {type(e).__name__}: {e}")
            raise
        phase[k] = round(time.monotonic() - t0, 1)
        runs[k] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log(f"{k} done in {phase[k]:.0f} s")
    snap1 = contention_snapshot()
    numbers["machine"] = machine_info()
    numbers["machine"]["run_contention"] = contention_delta(
        snap0, snap1, "whole run; the frontier's full-corpus pass deliberately uses two worker processes" if only is None
        else f"partial invocation (--only {','.join(keys)}) only; other keys keep the numbers of the runs in key_runs")
    numbers["corpora"] = dict(sorted(CORPORA.items()))
    numbers["method"] = {
        "harness": "_compute.py (PEP 723; uv run); Python " + platform.python_version() + " with compression.zstd, "
                   "zlib, bz2, lzma, sqlite3 from the stdlib, and the pinned wheels brotli 1.2.0, lz4 4.4.5, "
                   "cramjam 2.13.0; libbrotli 1.2.0 (system) via ctypes for dictionary brotli; git CLI",
        "exactness": __doc__.split("Exactness.")[1].split("MB = ")[0].strip().replace("\n", " "),
        "units": "MB = 10^6 bytes; ratio = original / compressed; bits/byte = 8 * compressed / original",
        "private_data": "none used (no ~/.claude or ~/.quirq data is read)",
        "heavy_artefacts": f"{BENCH} (outside the publication); setup: {BENCH}/setup.sh",
    }
    numbers["phase_seconds"] = phase
    numbers["key_runs"] = runs
    numbers["runtime_seconds_this_invocation"] = round(time.monotonic() - t_start)
    ordered = {k: numbers[k] for k in ["method", "machine", "corpora", "key_runs", "phase_seconds",
                                       "runtime_seconds_this_invocation"] + ALL_KEYS if k in numbers}
    OUT_JSON.write_text(json.dumps(ordered, indent=1, ensure_ascii=True) + "\n")
    log(f"wrote {OUT_JSON} ({OUT_JSON.stat().st_size:,} B) in {ordered['runtime_seconds_this_invocation']} s")


if __name__ == "__main__":
    main(sys.argv[1:])
