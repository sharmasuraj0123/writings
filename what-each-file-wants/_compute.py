# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = [
#   "brotli==1.2.0",
#   "lz4==4.4.5",
#   "zlib-ng==1.0.0",
#   "deflate==0.9.0",
#   "pyarrow==26.0.0",
#   "cbor2==6.1.5",
#   "msgpack==1.2.3",
#   "pymongo==4.18.3",
#   "protobuf==7.36.2",
#   "fastavro==1.13.1",
#   "pillow==12.3.0",
# ]
# [tool.uv]
# exclude-newer = "2026-10-10T00:00:00Z"
# ///
"""What Each File Wants: the measured numbers.

Run:   uv run /home/coder/xo-projects/writings/what-each-file-wants/_compute.py
       --only json,small   recompute those keys and merge them into the existing _numbers.json
       --smoke             tiny inputs, every key, written to BENCH/tmp/what-each-file-wants/_numbers.smoke.json
Needs: bash /home/coder/compression-ref/bench/setup.sh, run once: the static FFmpeg (BtbN n9.0.2), the libjxl 0.12.0
       tools (cjxl, djxl, ssimulacra2), oxipng 10.2.1 and the licence-clean media. Anything missing is recorded as
       "skipped" with the reason. The text-data keys (json, small, binary, config, logs, tables) need nothing downloaded.
Writes _numbers.json next to this file. Media, encodes and scratch files live under BENCH, outside the publication.

Keys: versions, corpora, json, small, binary, config, logs, tables, images, audio, video, recompress, headline;
plus machine, method, key_runs, phase_seconds.

Exactness. Sizes, ratios and quality scores are exact and deterministic for the pinned versions and inputs:
generators are seeded, gzip members carry mtime 0, archives use fixed dates and owners, MP4/MKV are written with
-fflags +bitexact. Timings are medians of repeated runs after a warm-up (the count is stated next to each), on a
2-CPU cgroup shared with other tenants; they are reported as tiers, with cgroup throttling recorded before and after
each timed phase. Video encodes are timed once each, and three settings three times (median, determinism check).
MB = 10^6 bytes. ratio = original bytes / compressed bytes. saving_pct = 100 * (original - compressed) / original.

Private data. None is read: no ~/.claude or ~/.quirq file is opened. The doomfly audit log is read for sizes and
ratios only; none of its content is stored.
"""
from __future__ import annotations

import datetime as dt
import gc
import gzip
import hashlib
import io
import json
import lzma
import math
import os
import platform
import random
import re
import resource
import shutil
import statistics
import struct
import subprocess
import sys
import tarfile
import time
import traceback
import zipfile
import zlib
from pathlib import Path

from compression import zstd

import brotli
import deflate
import lz4
import lz4.frame
from zlib_ng import gzip_ng, zlib_ng

HERE = Path(__file__).resolve().parent
WRITINGS = HERE.parent
XO = Path("/home/coder/xo-projects")
BENCH = Path("/home/coder/compression-ref/bench")              # heavy artefacts live outside the publication
BIN = BENCH / "bin"
DL = BENCH / "dl"
MEDIA = BENCH / "media" / "what-each-file-wants"
WORK = BENCH / "tmp" / "what-each-file-wants"
OUT_JSON = HERE / "_numbers.json"
SETUP = BENCH / "setup.sh"

FF_NAME = "ffmpeg-n9.0.2-24-gfd5d616c29-linux64-gpl-9.0"
FFMPEG = BIN / FF_NAME / "bin" / "ffmpeg"
FFPROBE = BIN / FF_NAME / "bin" / "ffprobe"
JXL_DIR = BIN / "jxl-0.12.0" / "tools"
CJXL, DJXL, SSIMULACRA2 = JXL_DIR / "cjxl", JXL_DIR / "djxl", JXL_DIR / "ssimulacra2"
OXIPNG = BIN / "oxipng-10.2.1" / "oxipng"

DOWNLOADS = {   # name: url, local file, expected sha256, where the checksum comes from
    "ffmpeg": ("https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-09-14-16/"
               f"{FF_NAME}.tar.xz", DL / f"{FF_NAME}.tar.xz",
               "0f792547d955e8f13fd80dfafb41002236492ddc3961fbd0ec680c6a8609e868",
               "BtbN's checksums.sha256 in the same dated release (autobuild-2026-10-09-14-16)"),
    "libjxl": ("https://github.com/libjxl/libjxl/releases/download/v0.12.0/jxl-linux-x86_64-static.tar.lz",
               DL / "jxl-0.12.0-linux-x86_64-static.tar.lz",
               "5318a1ea40adad76d023e0c17a03d4627f8282f83cb2b575e69be8e74f1ff456",
               "SHA-256 digest GitHub lists for the release asset"),
    "oxipng": ("https://github.com/oxipng/oxipng/releases/download/v10.2.1/oxipng-10.2.1-x86_64-unknown-linux-musl.tar.gz",
               DL / "oxipng-10.2.1-x86_64-unknown-linux-musl.tar.gz",
               "1813750ef592c5350ca79c88f98b2c0876d05c826dc7156245256d4255c1ad17",
               "SHA-256 digest GitHub lists for the release asset"),
}

KODAK_LICENCE = ("Kodak Lossless True Color Image Suite; host r0k.us: \"It is my understanding they have been released by "
                 "the Eastman Kodak Company for unrestricted usage.\" No licence file; used for measurement only, not "
                 "stored in the publication")
SINTEL_LICENCE = ("CC BY 3.0, Sintel (Durian Open Movie Project): \"The results of the Durian Open Movie project are being "
                  "licensed under the Creative Commons Attribution 3.0 license. This includes all the data we've published "
                  "online\" (https://durian.blender.org/sharing/). Attribution: (c) copyright Blender Foundation | "
                  "durian.blender.org")
MEDIA_FILES = {
    "kodim05": dict(path=MEDIA / "kodim05.png", url="https://r0k.us/graphics/kodak/kodak/kodim05.png",
                    sha256="10349e963c5c813d327852f82c1795fa4148d69fedffc4c589bee458e3ac3d53", licence=KODAK_LICENCE,
                    kind="photo", desc="Kodak kodim05 (motorcycles; dense detail), 768x512 RGB PNG"),
    "kodim15": dict(path=MEDIA / "kodim15.png", url="https://r0k.us/graphics/kodak/kodak/kodim15.png",
                    sha256="7538cbb80cb9103606c48b806eae57d56c885c7f90b9b3be70a41160f9cbb683", licence=KODAK_LICENCE,
                    kind="photo", desc="Kodak kodim15 (portrait; smooth skin and background), 768x512 RGB PNG"),
    "kodim23": dict(path=MEDIA / "kodim23.png", url="https://r0k.us/graphics/kodak/kodak/kodim23.png",
                    sha256="e3111a2fd4da24af15d6459ef9eacfe54106b38e27b4a21821b75c3f5d2d5baf", licence=KODAK_LICENCE,
                    kind="photo", desc="Kodak kodim23 (parrots; saturated colour, soft background), 768x512 RGB PNG"),
    "sintel_audio": dict(path=MEDIA / "sintel_trailer-audio.flac",
                         url="https://media.xiph.org/video/derf/flac/Sintel/sintel_trailer-audio.flac",
                         sha256="171d95acdb59882b4b8fb39cc1463920a859a78d3772bca532059c9ee02d48a6", licence=SINTEL_LICENCE,
                         kind="audio", desc="Sintel trailer soundtrack, FLAC as distributed by Xiph derf, 52.0 s, "
                                            "48 kHz, stereo, 16-bit"),
    "sintel_video": dict(path=MEDIA / "sintel_trailer_1080p24_f480-719.y4m",
                         url="https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_1080p24.y4m",
                         sha256="7bd57f55d12002530a0c0db6ae5becf8a0968fe95b99b42c49fd897fa56bef66", licence=SINTEL_LICENCE,
                         kind="video", desc="frames 480-719 (20.0-30.0 s) of derf's sintel_trailer_2k_1080p24.y4m, cut "
                                            "by HTTP range requests (45-byte header + 240 frames): 1920x1080, 24 fps, "
                                            "8-bit 4:2:0 (C420jpeg), 2.35:1 picture letterboxed in 16:9. derf footnote 2: "
                                            "converted from 8-bit RGB to Y'CbCr with rgb2yuv, so a converted derivative, "
                                            "not a lossless master"),
}
FIRST_PARTY_IMAGES = {
    "xo_space_dashboard": dict(path=XO / "xo-space/brand/screenshots/dashboard-todos.png", kind="screenshot",
                               licence="MIT (Copyright (c) 2026 XO Labs, Inc.; xo-space/LICENSE); first-party",
                               desc="xo-space dashboard screenshot, 1440x860 RGB PNG: dark UI, text, thin lines"),
    "doomfly_pixel_fly": dict(path=XO / "doomfly/doomfly/doom-ui/public/pixel-fly.png", kind="graphic",
                              licence="MIT (Copyright (c) 2026 nftechie and DOOMFLY contributors; doomfly/doomfly/LICENSE)",
                              desc="doomfly pixel-art fly, 1536x1024 RGB PNG; the repo README calls it \"one generated "
                                   "pixel-art fly\""),
}
FIRST_PARTY_JPEGS = {n: WRITINGS / "assets" / n for n in ("og.jpg", "mobius.jpg", "quirq-mark.jpg")}
AUDIT_LOG = XO / "doomfly/doomfly/outputs/doom/local-training/audit.jsonl"
AUDIT_GZ = XO / "doomfly/doomfly/outputs/doom/local-training/archive/20260917T13-5a009119-f851-4006-8600-403a160c6a6d.jsonl.gz"

ALL_KEYS = ["json", "small", "binary", "config", "logs", "tables", "images", "audio", "video", "recompress", "headline"]
SMOKE = False
CORPORA: dict[str, dict] = {}
TOOLV: dict[str, object] = {}          # tool versions discovered while running (encoder banners, libvmaf version)


# ----------------------------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------------------------
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def sha(b) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ratio(n, c):
    return round(n / c, 4) if c else None


def saving(n, c):
    return round(100 * (n - c) / n, 3) if n else None


def sig3(x):
    if x is None or x == 0:
        return x
    v = float(f"{x:.3g}")
    return int(v) if v.is_integer() else v


def gz(d, level):                      # gzip member with mtime 0 and no file name: reproducible bytes
    return gzip.compress(d, compresslevel=level, mtime=0)


def tier_mbps(mbps):
    if mbps is None:
        return None
    for lo, label in ((500, ">=500 MB/s"), (100, "100-500 MB/s"), (10, "10-100 MB/s"), (1, "1-10 MB/s")):
        if mbps >= lo:
            return label
    return "<1 MB/s"


def tier_msgs(per_s):
    for lo, label in ((1e5, ">=100k msg/s"), (1e4, "10k-100k msg/s"), (1e3, "1k-10k msg/s")):
        if per_s >= lo:
            return label
    return "<1k msg/s"


def tier_mpix(mps):
    for lo, label in ((10, ">=10 MP/s"), (1, "1-10 MP/s"), (0.1, "0.1-1 MP/s")):
        if mps >= lo:
            return label
    return "<0.1 MP/s"


def tier_fps(fps):
    for lo, label in ((10, ">=10 fps"), (3, "3-10 fps"), (1, "1-3 fps")):
        if fps >= lo:
            return label
    return "<1 fps"


def register_corpus(name, data: bytes | None, source, licence, note=None, nbytes=None, digest=None, path=None):
    CORPORA[name] = {"bytes": len(data) if data is not None else nbytes,
                     "sha256": sha(data) if data is not None else digest, "source": source, "licence": licence}
    if path:
        CORPORA[name]["path"] = str(path)
    if note:
        CORPORA[name]["note"] = note


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
        keys = ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec")
        out["cpu_stat_before"] = {k: a[k] for k in keys if k in a}       # raw /sys/fs/cgroup/cpu.stat counters
        out["cpu_stat_after"] = {k: b[k] for k in keys if k in b}
    out["note"] = note
    return out


def run(cmd, check=True, stdout_bytes=False):
    """Run a child process; return (CompletedProcess, wall seconds, child CPU seconds (user+sys))."""
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=not stdout_bytes)
    wall = time.perf_counter() - t0
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
    if check and p.returncode != 0:
        err = p.stderr if isinstance(p.stderr, str) else p.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"{Path(str(cmd[0])).name} exited {p.returncode}: {err[-1200:]}")
    return p, wall, cpu


def missing_tools(*paths):
    return [str(p) for p in paths if not (Path(p).is_file() and os.access(p, os.X_OK))]


def fresh_dir(p: Path) -> Path:
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True)
    return p


def bench(c, d, data: bytes, slow_s=2.0, n_c_max=7, n_d=7):
    """Median timings: warm-up on the first 256 KiB, then compression n_c_max times (3 if one run takes > slow_s),
    one verifying decompression, then n_d timed decompressions; gc disabled while timing."""
    c(data[: 1 << 18])
    gc.collect()
    gc.disable()
    try:
        t = time.perf_counter_ns()
        comp = c(data)
        cts = [time.perf_counter_ns() - t]
        n_c = 3 if cts[0] > slow_s * 1e9 else n_c_max
        for _ in range(n_c - 1):
            t = time.perf_counter_ns()
            c(data)
            cts.append(time.perf_counter_ns() - t)
        comp = bytes(comp)
        ok = bytes(d(comp)) == data
        dts = []
        for _ in range(n_d):
            t = time.perf_counter_ns()
            d(comp)
            dts.append(time.perf_counter_ns() - t)
    finally:
        gc.enable()
    cmed, dmed = statistics.median(cts) / 1e9, statistics.median(dts) / 1e9
    cmb, dmb = len(data) / cmed / 1e6, len(data) / dmed / 1e6
    return comp, ok, {"compress_MBps": sig3(cmb), "decompress_MBps": sig3(dmb), "compress_tier": tier_mbps(cmb),
                      "decompress_tier": tier_mbps(dmb), "compress_runs": n_c, "decompress_runs": n_d,
                      "compress_s_median": sig3(cmed), "decompress_s_median": sig3(dmed)}


def median_time(fn, n=5, warm=1):
    for _ in range(warm):
        fn()
    ts = []
    gc.collect()
    for _ in range(n):
        t = time.perf_counter_ns()
        fn()
        ts.append(time.perf_counter_ns() - t)
    return statistics.median(ts) / 1e9


# ----------------------------------------------------------------------------------------------------------
# general-purpose codecs (one registry for json, binary, logs, config, recompress)
# ----------------------------------------------------------------------------------------------------------
CODECS: dict[str, dict] = {}


def _reg(cid, family, label, c, d, params, library):
    CODECS[cid] = {"family": family, "label": label, "c": c, "d": d, "params": params, "library": library}


for _L in (1, 6, 9):
    _reg(f"gzip_{_L}", "DEFLATE (gzip)", f"gzip -{_L}", lambda x, L=_L: gz(x, L), gzip.decompress,
         {"api": "gzip.compress(data, compresslevel, mtime=0)", "level": _L, "framing": "gzip member, 18 B"},
         "zlib (stdlib)")
for _L in (1, 6, 9):
    _reg(f"zlibng_gzip_{_L}", "DEFLATE (gzip)", f"zlib-ng gzip -{_L}",
         lambda x, L=_L: gzip_ng.compress(x, L, mtime=0), gzip_ng.decompress,
         {"api": "zlib_ng.gzip_ng.compress(data, level, mtime=0)", "level": _L, "framing": "gzip member, 18 B"},
         "zlib-ng (python-zlib-ng wheel)")
for _L in (1, 6, 9, 12):
    _reg(f"libdeflate_gzip_{_L}", "DEFLATE (gzip)", f"libdeflate gzip -{_L}",
         lambda x, L=_L: deflate.gzip_compress(x, L), deflate.gzip_decompress,
         {"api": "deflate.gzip_compress(data, level)", "level": _L, "framing": "gzip member, 18 B",
          "note": "libdeflate is whole-buffer only (no streaming); levels 10-12 are its slow optimal parsing"},
         "libdeflate (deflate wheel)")
for _Q in (1, 5, 9, 11):
    _reg(f"brotli_{_Q}", "Brotli", f"brotli -q {_Q}", lambda x, Q=_Q: brotli.compress(x, quality=Q),
         brotli.decompress, {"api": "brotli.compress(data, quality=q)", "quality": _Q, "lgwin": 22, "mode": "generic"},
         "brotli wheel")
for _L in (1, 3, 9, 19, 22):
    _reg(f"zstd_{_L}", "Zstandard", f"zstd {_L}", lambda x, L=_L: zstd.compress(x, L), zstd.decompress,
         {"api": "compression.zstd.compress(data, level)", "level": _L, "checksum_flag": 0, "content_size_flag": 1},
         "libzstd (stdlib compression.zstd)")
for _P in (6, 9):
    _reg(f"xz_{_P}", "xz (LZMA2)", f"xz -{_P}", lambda x, P=_P: lzma.compress(x, preset=P), lzma.decompress,
         {"api": "lzma.compress(data, preset=p)", "preset": _P, "format": "xz", "check": "CRC64",
          "cli_equivalent": f"xz -T1 -{_P} (byte-identical); xz 5.8's default multithreaded mode (-T0) also stores "
                            "block sizes in the block header, a few bytes more"}, "liblzma (stdlib)")
_reg("lz4", "LZ4", "lz4 (default)", lambda x: lz4.frame.compress(x), lz4.frame.decompress,
     {"api": "lz4.frame.compress(data)", "compression_level": 0, "block_size": "64 KB", "block_linked": True},
     "lz4 wheel")
_reg("lz4_hc9", "LZ4", "lz4 -9 (HC)", lambda x: lz4.frame.compress(x, compression_level=9), lz4.frame.decompress,
     {"api": "lz4.frame.compress(data, compression_level=9)", "compression_level": 9}, "lz4 wheel")
JSON_CODECS = list(CODECS)


# ----------------------------------------------------------------------------------------------------------
# seeded generators
# ----------------------------------------------------------------------------------------------------------
WORDS = ("the of and to in is for on that with as by from at this be are or was it an not which have has more can "
         "all will one new about also into time only its other some these than may out up use when what their there "
         "two most first data file line value error request response server client cache query index table record "
         "field event user session token model agent tool result build test deploy config update create delete read "
         "write open close start stop retry timeout limit batch stream frame block level window match buffer queue "
         "worker task job step stage phase report metric latency throughput memory disk network packet header payload "
         "schema version release commit branch merge patch review issue fix bug feature change note path module "
         "function method class object array string number boolean null true false key map list set item entry node "
         "edge graph tree root leaf parent child order sort filter group count sum mean median max min total rate "
         "ratio size length width height depth").split()
FIRST = ["Ada", "Alan", "Grace", "Linus", "Margaret", "Dennis", "Ken", "Barbara", "Edsger", "Donald", "Frances", "John",
         "Radia", "Tim", "Sophie", "Hedy", "Katherine", "Claude", "Niklaus", "Bjarne", "Guido", "Yukihiro", "Anders",
         "James", "Brendan", "Larry", "Rasmus", "Jean", "Annie", "Mary"]
LAST = ["Lovelace", "Turing", "Hopper", "Torvalds", "Hamilton", "Ritchie", "Thompson", "Liskov", "Dijkstra", "Knuth",
        "Allen", "McCarthy", "Perlman", "Berners-Lee", "Wilson", "Lamarr", "Johnson", "Shannon", "Wirth", "Stroustrup",
        "van Rossum", "Matsumoto", "Hejlsberg", "Gosling", "Eich", "Wall", "Lerdorf", "Sammet", "Easley", "Keller"]
CITIES = [("Berlin", "DE", "10115"), ("Paris", "FR", "75002"), ("London", "GB", "EC1A 1BB"), ("Madrid", "ES", "28013"),
          ("Amsterdam", "NL", "1012 JS"), ("Austin", "US", "78701"), ("Toronto", "CA", "M5H 2N2"),
          ("Tokyo", "JP", "100-0005"), ("Sydney", "AU", "2000"), ("Bengaluru", "IN", "560001"),
          ("São Paulo", "BR", "01310-100"), ("Dublin", "IE", "D02 X285")]
CURRENCY = {"DE": "eur", "FR": "eur", "ES": "eur", "NL": "eur", "IE": "eur", "GB": "gbp", "US": "usd", "CA": "cad",
            "JP": "jpy", "AU": "aud", "IN": "inr", "BR": "brl"}
STREETS = ["Main Street", "High Street", "Market Square", "Station Road", "Church Lane", "Park Avenue", "Mill Road",
           "King Street", "Queen Street", "Harbour Way"]
TAGS = ["new", "sale", "eco", "bundle", "limited", "refurbished", "gift", "bestseller", "clearance", "preorder"]
B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
START = int(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc).timestamp())
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def b62(r, n):
    return "".join(r.choice(B62) for _ in range(n))


def iso_ms(t: float) -> str:
    ms = int(round(t * 1000))
    s, ms = divmod(ms, 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(s)) + f".{ms:03d}Z"


def sentence(r, n):
    w = [r.choice(WORDS) for _ in range(n)]
    return (" ".join(w)).capitalize() + "."


def api_records(n, seed=20261010):
    """Stripe/GitHub-style 'order' objects: nested customer, line items, address, metadata, events. Amounts are integer
    minor units; weights and ratings are floats; nullable fields are present as null. Customers (1,500) and products
    (400) come from fixed pools chosen with a skew, so values repeat across records as they do in real API pages."""
    r = random.Random(seed)
    products = []
    for i in range(400):
        products.append({"sku": f"SKU-{10000 + 7 * i:05d}",
                         "name": " ".join(r.choice(WORDS).capitalize() for _ in range(r.randint(2, 4))),
                         "unit_amount": r.choice([499, 999, 1299, 1999, 2499, 4999, 7999, 12999]) + r.choice([0, 0, 50]),
                         "weight_kg": round(r.uniform(0.05, 12), 3), "tags": r.sample(TAGS, r.randint(0, 3))})
    customers = []
    for _ in range(1500):
        fn, ln, city = r.choice(FIRST), r.choice(LAST), r.choice(CITIES)
        customers.append({"id": "cus_" + b62(r, 14), "name": f"{fn} {ln}",
                          "email": f"{fn}.{ln}{r.randint(1, 99)}@example.com".lower().replace(" ", ""),
                          "country": city[1], "tier": r.choices(["free", "pro", "team", "enterprise"], [50, 30, 15, 5])[0],
                          "_city": city, "_street": f"{r.randint(1, 240)} {r.choice(STREETS)}"})
    recs, t = [], float(START)
    for _ in range(n):
        t += r.expovariate(1 / 420)
        c = customers[min(int(len(customers) * r.random() ** 2.2), len(customers) - 1)]
        items = []
        for _k in range(r.choices([1, 2, 3, 4, 5], [45, 25, 15, 10, 5])[0]):
            p = products[min(int(400 * r.random() ** 1.8), 399)]
            q = r.choices([1, 2, 3, 5], [70, 18, 8, 4])[0]
            items.append({"id": "li_" + b62(r, 10), "sku": p["sku"], "name": p["name"], "quantity": q,
                          "unit_amount": p["unit_amount"], "amount": p["unit_amount"] * q, "weight_kg": p["weight_kg"],
                          "tags": list(p["tags"])})
        sub = sum(it["amount"] for it in items)
        ship = 0 if sub > 5000 else r.choice([499, 699, 999])
        tax = round(sub * r.choice([0.07, 0.19, 0.2, 0.21]))
        status = r.choices(["paid", "fulfilled", "pending", "refunded", "canceled"], [50, 30, 10, 5, 5])[0]
        upd = t + r.expovariate(1 / 3600)
        events = [{"type": "order.created", "at": iso_ms(t)}]
        if status in ("paid", "fulfilled", "refunded"):
            events.append({"type": "charge.succeeded", "at": iso_ms(t + r.uniform(1, 30))})
        if status == "fulfilled":
            events.append({"type": "order.fulfilled", "at": iso_ms(upd)})
        if status in ("refunded", "canceled"):
            events.append({"type": f"order.{status}", "at": iso_ms(upd)})
        recs.append({
            "id": "ord_" + b62(r, 14), "object": "order", "created_at": iso_ms(t), "updated_at": iso_ms(upd),
            "status": status, "currency": CURRENCY[c["country"]], "amount_subtotal": sub, "amount_tax": tax,
            "amount_shipping": ship, "amount_total": sub + tax + ship,
            "customer": {k: c[k] for k in ("id", "name", "email", "country", "tier")},
            "line_items": items,
            "shipping": {"name": c["name"],
                         "address": {"line1": c["_street"],
                                     "line2": f"Apt {r.randint(1, 40)}" if r.random() < 0.25 else None,
                                     "city": c["_city"][0], "postal_code": c["_city"][2], "country": c["_city"][1]},
                         "carrier": r.choice(["dhl", "ups", "fedex", "royal_mail", "la_poste"]),
                         "tracking": ("1Z" + b62(r, 16).upper()) if status == "fulfilled" else None},
            "metadata": {"source": r.choices(["web", "ios", "android", "api"], [55, 20, 15, 10])[0],
                         "campaign": r.choice(["autumn-sale", "newsletter-41", "partner-xo", "retarget-7"])
                         if r.random() < 0.3 else None,
                         "ab_bucket": r.randrange(10), "client_version": r.choice(["3.12.1", "3.12.2", "3.13.0", "4.0.0-rc.2"])},
            "flags": {"gift": r.random() < 0.08, "priority": r.random() < 0.12, "test": False},
            "rating": round(r.uniform(1, 5), 1) if status == "fulfilled" and r.random() < 0.4 else None,
            "note": sentence(r, r.randint(4, 14)) if r.random() < 0.15 else None,
            "events": events})
    return recs


def dumps_pretty(o):
    return json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")


def dumps_min(o):
    return json.dumps(o, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def dumps_default(o):
    return json.dumps(o).encode("utf-8")           # Python's defaults: ", " and ": " separators, ensure_ascii=True


def agent_events(n, seed=20261011):
    """Agent-session events as standalone JSON messages, target sizes log-uniform on [100, 4096] bytes: heartbeats,
    token-usage records, tool calls, tool results and assistant messages. Free text is drawn from a 200-word vocabulary
    (plus paths and numbers), so it is less repetitive than real tool output."""
    r = random.Random(seed)
    sessions = ["ses_" + b62(r, 12) for _ in range(80)]
    projects = ["writings", "xo-space", "fly-lab", "mindwalk", "originkit", "quirq-calculator"]
    tools = ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "WebFetch", "TodoWrite"]
    exts = [".py", ".ts", ".md", ".json", ".toml", ".html"]
    models = ["model-large-2026-09", "model-medium-2026-08", "model-small-2026-06"]
    t = float(START + 30 * 86400)
    docs = []
    for i in range(n):
        target = int(round(math.exp(r.uniform(math.log(100), math.log(4096)))))
        t += r.expovariate(1 / 3.0)
        d = {"v": 1, "ts": iso_ms(t), "session": sessions[min(int(80 * r.random() ** 1.5), 79)], "seq": i,
             "project": r.choice(projects)}
        path = f"src/{r.choice(WORDS)}/{r.choice(WORDS)}_{r.choice(WORDS)}{r.choice(exts)}"
        if target < 170:
            d.update(type="heartbeat", state=r.choice(["idle", "busy", "waiting"]))
            field = None
        elif target < 330:
            d.update(type="usage", model=r.choice(models), input_tokens=r.randint(200, 180000),
                     output_tokens=r.randint(10, 8000), cache_read_tokens=r.randint(0, 150000))
            field = None
        elif target < 800:
            d.update(type="tool_use", tool=r.choice(tools), input={"path": path, "limit": r.choice([None, 200, 2000])})
            field = "description"
        elif target < 1800:
            d.update(type="tool_result", tool=r.choice(tools), ok=r.random() < 0.93, duration_ms=r.randint(3, 9000),
                     path=path)
            field = "output"
        else:
            d.update(type="message", role="assistant", model=r.choice(models))
            field = "text"
        if field:
            words, size = [], len(dumps_min(d)) + len(field) + 6
            while size < target:
                w = r.choice(WORDS) if r.random() < 0.9 else (path if r.random() < 0.5 else str(r.randint(0, 99999)))
                words.append(w)
                size += len(w) + 1
            d[field] = " ".join(words)
        b = dumps_min(d)
        if len(b) > 4096 and field:
            d[field] = d[field][: max(0, len(d[field]) - (len(b) - 4096))]
            b = dumps_min(d)
        docs.append(b)
    return docs


def access_log(target_bytes, seed=20261012):
    """nginx 'combined' lines plus request time: private-range client IPs (skewed), API, static and search paths,
    weighted status codes, lognormal response sizes, a referrer and user-agent pool."""
    r = random.Random(seed)
    ips = [f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}" for _ in range(3000)]
    uas = ["Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0",
           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
           "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",
           "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
           "curl/8.18.0", "python-requests/2.33.1", "Go-http-client/2.0", "okhttp/5.1.0",
           "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "kube-probe/1.34"]
    refs = ["-", "https://example.com/", "https://example.com/dashboard", "https://example.com/docs/getting-started",
            "https://www.google.com/", "https://news.ycombinator.com/"]
    out, size, t = [], 0, float(START + 38 * 86400)
    while size < target_bytes:
        t += r.expovariate(20)
        ip = ips[min(int(3000 * r.random() ** 2.5), 2999)]
        k = r.random()
        if k < 0.35:
            path = f"/api/v1/orders/ord_{b62(r, 14)}"
        elif k < 0.5:
            path = f"/api/v1/orders?limit={r.choice([20, 50, 100])}&cursor={b62(r, 10)}"
        elif k < 0.6:
            path = f"/api/v1/users/{r.randint(1000, 99999)}/sessions"
        elif k < 0.75:
            path = r.choice(["/static/js/app.3f9a1c.js", "/static/css/site.81bd02.css", "/static/js/vendor.c0ffee.js",
                             "/favicon.ico", "/"])
        elif k < 0.85:
            path = f"/api/v1/search?q={r.choice(WORDS)}+{r.choice(WORDS)}&page={r.randint(1, 5)}"
        elif k < 0.93:
            path = f"/images/{r.choice(WORDS)}-{r.randint(1, 400)}.webp"
        else:
            path = r.choice(["/healthz", "/metrics", "/readyz"])
        method = r.choices(["GET", "POST", "PUT", "DELETE"], [80, 15, 3, 2])[0]
        status = r.choices([200, 201, 304, 401, 404, 500, 503], [85, 1, 6, 2, 4, 1.5, 0.5])[0]
        nbytes = 0 if status == 304 else int(r.lognormvariate(7.5, 1.3))
        rt = r.lognormvariate(-4.2, 1.0)
        g = time.gmtime(int(t))
        stamp = f"{g.tm_mday:02d}/{MONTHS[g.tm_mon - 1]}/{g.tm_year}:{g.tm_hour:02d}:{g.tm_min:02d}:{g.tm_sec:02d} +0000"
        ln = (f'{ip} - - [{stamp}] "{method} {path} HTTP/1.1" {status} {nbytes} "{r.choice(refs)}" '
              f'"{uas[min(int(10 * r.random() ** 1.7), 9)]}" rt={rt:.3f} uct={rt * r.uniform(0.01, 0.2):.3f}\n')
        out.append(ln)
        size += len(ln)
    return "".join(out).encode("ascii")


# ----------------------------------------------------------------------------------------------------------
# json
# ----------------------------------------------------------------------------------------------------------
API_N = 4100


def json_main_corpora():
    out = []
    for name, p, licence in [("posts_json", WRITINGS / "posts.json", "XO Labs first-party (this site's post index)"),
                             ("parser_hears_numbers", WRITINGS / "what-the-parser-hears" / "_numbers.json",
                              "XO Labs first-party (the measured output of a sibling post's harness)")]:
        if not p.exists():
            continue
        raw = p.read_bytes()
        register_corpus(name, raw, str(p), licence)
        out.append((name, raw, json.loads(raw)))
    recs = api_records(API_N if not SMOKE else 400)
    mn = dumps_min(recs)
    register_corpus("api_records", mn, f"generated by api_records(n={len(recs)}, seed=20261010) in _compute.py",
                    "synthetic (this harness)", note="bytes/sha256 are of the minified form; pretty = indent 2")
    out.append(("api_records", None, recs))
    return out


def part_json():
    corpora = json_main_corpora()
    forms_out, ratios = [], {}
    for name, raw, obj in corpora:
        forms = {}
        if raw is not None:
            forms["on_disk"] = raw
        forms["pretty"] = dumps_pretty(obj)
        forms["default_dumps"] = dumps_default(obj)
        forms["minified"] = dumps_min(obj)
        ratios[name] = {}
        for form, data in forms.items():
            forms_out.append({"corpus": name, "form": form, "bytes": len(data), "sha256": sha(data)})
            row = {}
            for cid in JSON_CODECS:
                co = CODECS[cid]
                comp = co["c"](data)
                ok = bytes(co["d"](comp)) == data
                if cid.startswith(("zlibng", "libdeflate")):
                    ok = ok and gzip.decompress(comp) == data          # interop: stdlib zlib reads their gzip
                row[cid] = {"bytes": len(comp), "ratio": ratio(len(data), len(comp)),
                            "pct_of_original": round(100 * len(comp) / len(data), 3), "roundtrip_ok": ok}
            ratios[name][form] = row
            log(f"  json ratios {name}/{form}: {len(data):,} B; zstd3 {row['zstd_3']['ratio']}, br11 {row['brotli_11']['ratio']}")
    # timings on the main corpus, minified and pretty
    timing = {}
    snap_a = contention_snapshot()
    main = next(o for n, r_, o in corpora if n == "api_records")
    for form, data in (("minified", dumps_min(main)), ("pretty", dumps_pretty(main))):
        rows = {}
        for cid in JSON_CODECS:
            co = CODECS[cid]
            comp, ok, t = bench(co["c"], co["d"], data)
            rows[cid] = dict(bytes=len(comp), ratio=ratio(len(data), len(comp)), roundtrip_ok=ok, **t)
            log(f"  json timed {form} {cid}: {t['compress_MBps']} MB/s c, {t['decompress_MBps']} MB/s d, ratio {rows[cid]['ratio']}")
        timing[form] = {"bytes": len(data), "rows": rows}
    snap_b = contention_snapshot()
    # minify table: raw and compressed, pretty vs minified vs Python default separators
    minify = {}
    for name in ratios:
        m = {}
        for form, row in ratios[name].items():
            raw_b = next(f["bytes"] for f in forms_out if f["corpus"] == name and f["form"] == form)
            m[form] = {"raw": raw_b, "gzip_6": row["gzip_6"]["bytes"], "brotli_11": row["brotli_11"]["bytes"],
                       "zstd_3": row["zstd_3"]["bytes"], "zstd_19": row["zstd_19"]["bytes"]}
        p, mi = m["pretty"], m["minified"]
        m["minify_saving_pct"] = {k: saving(p[k], mi[k]) for k in ("raw", "gzip_6", "brotli_11", "zstd_3", "zstd_19")}
        minify[name] = m
    # frontier points and a knee for zstd and brotli levels (main corpus, minified)
    tm = timing["minified"]["rows"]
    points = [{"id": cid, "label": CODECS[cid]["label"], "family": CODECS[cid]["family"], "ratio": tm[cid]["ratio"],
               "compress_MBps": tm[cid]["compress_MBps"], "decompress_MBps": tm[cid]["decompress_MBps"]}
              for cid in JSON_CODECS]
    knee = {}
    for fam, ids in (("zstd", ["zstd_1", "zstd_3", "zstd_9", "zstd_19", "zstd_22"]),
                     ("brotli", ["brotli_1", "brotli_5", "brotli_9", "brotli_11"]),
                     ("gzip", ["gzip_1", "gzip_6", "gzip_9"])):
        steps = []
        for a, b in zip(ids, ids[1:]):
            steps.append({"from": a, "to": b, "ratio_gain_pct": round(100 * (tm[b]["ratio"] / tm[a]["ratio"] - 1), 2),
                          "compress_slowdown_x": sig3(tm[a]["compress_MBps"] / tm[b]["compress_MBps"])})
        knee[fam] = steps
    return {
        "corpora": forms_out,
        "codecs": {cid: {k: v for k, v in CODECS[cid].items() if k not in ("c", "d")} for cid in JSON_CODECS},
        "ratios": ratios,
        "timing": {"corpus": "api_records", **timing,
                   "contention": contention_delta(snap_a, snap_b, "codecs timed one at a time in one Python thread")},
        "frontier_points_minified": points,
        "knee_minified": knee,
        "minify": minify,
        "method": "Every codec/level compresses every form of every corpus once (exact bytes, verified by "
                  "decompression; zlib-ng and libdeflate gzip output is also decoded by the stdlib gzip module). "
                  "Forms: on_disk = the file's bytes; pretty = json.dumps(obj, indent=2, ensure_ascii=False); "
                  "default_dumps = json.dumps(obj) (Python's ', ' and ': ' separators, ensure_ascii=True); minified = "
                  "separators=(',', ':'), ensure_ascii=False. Timings: api_records minified and pretty, one codec at a "
                  "time on one thread, gc off; warm-up = one compression of the first 256 KiB; compression median of 7 "
                  "runs (3 when one run exceeds 2 s), decompression median of 7. Speeds are MB/s of the uncompressed "
                  "input, 3 significant figures, labelled with a tier because the CPU is shared. knee_minified: ratio "
                  "gained and compression speed lost from one level to the next.",
    }


# ----------------------------------------------------------------------------------------------------------
# small
# ----------------------------------------------------------------------------------------------------------
SMALL_N = 20000
DICT_SIZES = [4096, 16384, 65536, 112640]
BUCKETS = [(100, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 4097)]


def zstd_lean(level, zd=None):
    opts = {zstd.CompressionParameter.compression_level: level, zstd.CompressionParameter.content_size_flag: 0,
            zstd.CompressionParameter.checksum_flag: 0, zstd.CompressionParameter.dict_id_flag: 0}
    return lambda x: zstd.compress(x, options=opts, zstd_dict=zd)


def part_small():
    n = SMALL_N if not SMOKE else 2000
    docs = agent_events(n)
    blob = b"\n".join(docs) + b"\n"
    register_corpus("agent_events", blob, f"generated by agent_events(n={n}, seed=20261011) in _compute.py",
                    "synthetic (this harness)", note="bytes/sha256 are of the documents joined by newlines (JSONL)")
    idx = list(range(n))
    random.Random(7).shuffle(idx)
    train = [docs[i] for i in idx[: n // 2]]
    test = [docs[i] for i in idx[n // 2:]]
    # dictionaries, trained on the train split only
    dicts, dict_info = {}, {}
    for ds in DICT_SIZES:
        t0 = time.perf_counter()
        zd = zstd.train_dict(train, ds)
        tt = time.perf_counter() - t0
        zd2 = zstd.train_dict(train, ds)
        dicts[ds] = zd
        dict_info[str(ds)] = {"requested_bytes": ds, "bytes": len(zd.dict_content), "dict_id": zd.dict_id,
                              "sha256": sha(zd.dict_content), "train_s_single_run": sig3(tt),
                              "deterministic_retrain": zd2.dict_content == zd.dict_content}
        log(f"  small: dict {ds} -> {len(zd.dict_content)} B in {tt:.2f} s")
    methods = {
        "gzip_6": (lambda x: gz(x, 6), gzip.decompress),
        "deflate_raw_6": (lambda x: zlib.compress(x, 6, wbits=-15), lambda c: zlib.decompress(c, wbits=-15)),
        "brotli_5": (lambda x: brotli.compress(x, quality=5), brotli.decompress),
        "brotli_11": (lambda x: brotli.compress(x, quality=11), brotli.decompress),
        "zstd_3": (lambda x: zstd.compress(x, 3), zstd.decompress),
        "zstd_19": (lambda x: zstd.compress(x, 19), zstd.decompress),
        "zstd_3_lean": (zstd_lean(3), zstd.decompress),
    }
    for ds, zd in dicts.items():
        k = ds // 1024
        methods[f"zstd_3_dict{k}k"] = (lambda x, zd=zd: zstd.compress(x, 3, zstd_dict=zd),
                                       lambda c, zd=zd: zstd.decompress(c, zstd_dict=zd))
    zd110 = dicts[112640]
    methods["zstd_19_dict110k"] = (lambda x: zstd.compress(x, 19, zstd_dict=zd110),
                                   lambda c: zstd.decompress(c, zstd_dict=zd110))
    methods["zstd_3_dict110k_lean"] = (zstd_lean(3, zd110), lambda c: zstd.decompress(c, zstd_dict=zd110))
    methods["zstd_3_dict110k_digested"] = (lambda x: zstd.compress(x, 3, zstd_dict=zd110.as_digested_dict),
                                           lambda c: zstd.decompress(c, zstd_dict=zd110))
    per = {}
    raw_sizes = [len(d) for d in test]
    for m, (c, d) in methods.items():
        sizes, ok = [], True
        for doc in test:
            cb = c(doc)
            sizes.append(len(cb))
            if d(cb) != doc:
                ok = False
        per[m] = {"sizes": sizes, "ok": ok}
        log(f"  small per-doc {m}: total ratio {sum(raw_sizes) / sum(sizes):.3f}")
    def summarize(raw, comp):
        rr = [a / b for a, b in zip(raw, comp)]
        return {"docs": len(raw), "raw_bytes": sum(raw), "compressed_bytes": sum(comp),
                "ratio_total": ratio(sum(raw), sum(comp)), "ratio_median": round(statistics.median(rr), 4),
                "docs_grew": sum(1 for a, b in zip(raw, comp) if b > a),
                "docs_grew_pct": round(100 * sum(1 for a, b in zip(raw, comp) if b > a) / len(raw), 2)}
    overall = {m: dict(summarize(raw_sizes, v["sizes"]), roundtrip_ok=v["ok"]) for m, v in per.items()}
    by_bucket = {}
    for lo, hi in BUCKETS:
        sel = [i for i, s in enumerate(raw_sizes) if lo <= s < hi]
        if not sel:
            continue
        b = {"range": [lo, hi - 1 if hi == 4097 else hi], "docs": len(sel),
             "raw_mean": round(statistics.mean(raw_sizes[i] for i in sel), 1)}
        for m, v in per.items():
            b[m] = summarize([raw_sizes[i] for i in sel], [v["sizes"][i] for i in sel])
        # batches of 100 documents of this bucket per zstd 3 frame
        bdocs = [test[i] for i in sel]
        comp = sum(len(zstd.compress(b"\n".join(bdocs[j:j + 100]) + b"\n", 3)) for j in range(0, len(bdocs), 100))
        raw = sum(len(x) + 1 for x in bdocs)
        b["zstd_3_batch100"] = {"raw_bytes": raw, "compressed_bytes": comp, "ratio_total": ratio(raw, comp),
                                "note": "documents of this bucket, newline-joined, 100 per frame"}
        by_bucket[f"{lo}-{hi - 1 if hi == 4097 else hi}"] = b
    # batching: N consecutive test documents (JSONL) per frame
    batching = {}
    for name, c in (("zstd_3", lambda x: zstd.compress(x, 3)), ("gzip_6", lambda x: gz(x, 6)),
                    ("zstd_3_dict110k", lambda x: zstd.compress(x, 3, zstd_dict=zd110)),
                    ("brotli_5", lambda x: brotli.compress(x, quality=5))):
        rows = {}
        for N in (1, 10, 100, 1000, len(test)):
            comp = raw = 0
            for j in range(0, len(test), N):
                chunk = b"\n".join(test[j:j + N]) + b"\n"
                raw += len(chunk)
                comp += len(c(chunk))
            rows[str(N)] = {"frames": math.ceil(len(test) / N), "raw_bytes": raw, "compressed_bytes": comp,
                            "ratio": ratio(raw, comp)}
        batching[name] = rows
    # speed: messages per second, all test documents one at a time
    snap_a = contention_snapshot()
    speed = {}
    for m in ("zstd_3", "zstd_3_dict110k", "zstd_3_dict110k_digested", "gzip_6", "brotli_5"):
        c, d = methods[m]
        comps = [c(x) for x in test]
        tc = median_time(lambda: [c(x) for x in test], n=5)
        td = median_time(lambda: [d(x) for x in comps], n=5)
        speed[m] = {"compress_msgs_per_s": sig3(len(test) / tc), "decompress_msgs_per_s": sig3(len(test) / td),
                    "compress_tier": tier_msgs(len(test) / tc), "decompress_tier": tier_msgs(len(test) / td),
                    "runs": 5, "note": "one call per message, including per-call context setup"}
    snap_b = contention_snapshot()
    size_hist = {f"{lo}-{hi - 1 if hi == 4097 else hi}": sum(1 for s in [len(x) for x in docs] if lo <= s < hi)
                 for lo, hi in BUCKETS}
    return {
        "corpus": {"name": "agent_events", "docs": n, "bytes_total": sum(len(x) for x in docs),
                   "size_min": min(len(x) for x in docs), "size_median": statistics.median(len(x) for x in docs),
                   "size_max": max(len(x) for x in docs), "size_histogram": size_hist,
                   "split": {"train_docs": len(train), "test_docs": len(test), "train_bytes": sum(map(len, train)),
                             "test_bytes": sum(raw_sizes), "how": "random.Random(7).shuffle of the indices; first half "
                                                                  "train, second half test; disjoint"}},
        "dictionaries": dict_info,
        "per_document_test_split": overall,
        "by_size_bucket": by_bucket,
        "batching_test_split": batching,
        "speed": dict(speed, contention=contention_delta(snap_a, snap_b, "one Python thread")),
        "framing_bytes": {"gzip_member": 18, "zlib": 6, "zstd_frame_min": 6,
                          "zstd_frame_with_content_size_and_dict_id": "magic 4 + descriptor 1 + dict id 0-4 + content "
                                                                      "size 0-8 (+ 3-byte block header)"},
        "method": "Per-document: each test document compressed alone (gzip member mtime 0; raw DEFLATE with no framing; "
                  "brotli quality 5 and 11 with its built-in static dictionary; zstd frames with the default "
                  "content-size flag on; '_lean' = content_size_flag, checksum_flag and dict_id_flag all 0). "
                  "Dictionaries: compression.zstd.train_dict(train_docs, size) on the train split only, measured on the "
                  "disjoint test split. Passing a ZstdDict directly loads it undigested on every call (costly, about a "
                  "millisecond for 110 KB here); '_digested' passes zd.as_digested_dict, which the ZstdDict caches per "
                  "level (the speed table shows the difference). "
                  "Batching: N consecutive test documents joined by newlines per frame. ratio_total "
                  "= sum raw / sum compressed; docs_grew counts compressed > raw.",
    }


# ----------------------------------------------------------------------------------------------------------
# binary
# ----------------------------------------------------------------------------------------------------------
PB_SCHEMA = {
    "OrderList": [("orders", "Order*")],
    "Order": [("id", "string"), ("object", "string"), ("created_at", "string"), ("updated_at", "string"),
              ("status", "string"), ("currency", "string"), ("amount_subtotal", "int64"), ("amount_tax", "int64"),
              ("amount_shipping", "int64"), ("amount_total", "int64"), ("customer", "Customer"),
              ("line_items", "LineItem*"), ("shipping", "Shipping"), ("metadata", "Metadata"), ("flags", "Flags"),
              ("rating", "double?"), ("note", "string?"), ("events", "Event*")],
    "Customer": [("id", "string"), ("name", "string"), ("email", "string"), ("country", "string"), ("tier", "string")],
    "LineItem": [("id", "string"), ("sku", "string"), ("name", "string"), ("quantity", "int64"),
                 ("unit_amount", "int64"), ("amount", "int64"), ("weight_kg", "double"), ("tags", "string*")],
    "Shipping": [("name", "string"), ("address", "Address"), ("carrier", "string"), ("tracking", "string?")],
    "Address": [("line1", "string"), ("line2", "string?"), ("city", "string"), ("postal_code", "string"),
                ("country", "string")],
    "Metadata": [("source", "string"), ("campaign", "string?"), ("ab_bucket", "int64"), ("client_version", "string")],
    "Flags": [("gift", "bool"), ("priority", "bool"), ("test", "bool")],
    "Event": [("type", "string"), ("at", "string")],
}
SCALARS = {"string", "int64", "double", "bool"}


def pb_classes():
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
    F = descriptor_pb2.FieldDescriptorProto
    tmap = {"string": F.TYPE_STRING, "int64": F.TYPE_INT64, "double": F.TYPE_DOUBLE, "bool": F.TYPE_BOOL}
    fdp = descriptor_pb2.FileDescriptorProto(name="ewfw_orders.proto", package="ewfw", syntax="proto2")
    for mname, fields in PB_SCHEMA.items():
        mp = fdp.message_type.add(name=mname)
        for num, (fname, ftype) in enumerate(fields, 1):
            base = ftype.rstrip("*?")
            f = mp.field.add(name=fname, number=num,
                             label=F.LABEL_REPEATED if ftype.endswith("*") else F.LABEL_OPTIONAL)
            if base in SCALARS:
                f.type = tmap[base]
            else:
                f.type = F.TYPE_MESSAGE
                f.type_name = f".ewfw.{base}"
    pool = descriptor_pool.DescriptorPool()
    pool.Add(fdp)
    return {m: message_factory.GetMessageClass(pool.FindMessageTypeByName(f"ewfw.{m}")) for m in PB_SCHEMA}


def pb_fill(msg, d, mname):
    for fname, ftype in PB_SCHEMA[mname]:
        v = d.get(fname)
        if v is None:
            continue
        base = ftype.rstrip("*?")
        if ftype.endswith("*"):
            if base in SCALARS:
                getattr(msg, fname).extend(v)
            else:
                rep = getattr(msg, fname)
                for it in v:
                    pb_fill(rep.add(), it, base)
        elif base in SCALARS:
            setattr(msg, fname, v)
        else:
            pb_fill(getattr(msg, fname), v, base)


def pb_to_obj(msg, mname):
    """Rebuild the record dict from a parsed message (absent optional fields -> None), touching every field, so
    protobuf's decode yields the same Python objects as the other decoders (upb's parse alone is lazy)."""
    out = {}
    for fname, ftype in PB_SCHEMA[mname]:
        base = ftype.rstrip("*?")
        v = getattr(msg, fname)
        if ftype.endswith("*"):
            out[fname] = [x if base in SCALARS else pb_to_obj(x, base) for x in v]
        elif ftype.endswith("?") and not msg.HasField(fname):
            out[fname] = None
        else:
            out[fname] = v if base in SCALARS else pb_to_obj(v, base)
    return out


def avro_schema():
    amap = {"string": "string", "int64": "long", "double": "double", "bool": "boolean"}

    def rec(mname):
        fields = []
        for fname, ftype in PB_SCHEMA[mname]:
            base = ftype.rstrip("*?")
            t = amap[base] if base in SCALARS else rec(base)
            if ftype.endswith("*"):
                t = {"type": "array", "items": t}
            if ftype.endswith("?"):
                fields.append({"name": fname, "type": ["null", t], "default": None})
            else:
                fields.append({"name": fname, "type": t})
        return {"type": "record", "name": mname, "namespace": "ewfw", "fields": fields}
    return rec("Order")


def part_binary():
    import bson
    import cbor2
    import fastavro
    import msgpack
    recs = api_records(API_N if not SMOKE else 400)
    pbc = pb_classes()
    ol = pbc["OrderList"]()
    for rr in recs:
        pb_fill(ol.orders.add(), rr, "Order")
    sch = fastavro.parse_schema(avro_schema())

    def avro_stream(rs):
        buf = io.BytesIO()
        for x in rs:
            fastavro.schemaless_writer(buf, sch, x)
        return buf.getvalue()

    def avro_read(b):
        buf, out = io.BytesIO(b), []
        while buf.tell() < len(b):
            out.append(fastavro.schemaless_reader(buf, sch))
        return out

    def avro_ocf(rs):
        buf = io.BytesIO()
        fastavro.writer(buf, sch, rs, codec="null", sync_marker=b"\x00" * 16)
        return buf.getvalue()

    encoders = {
        "json_pretty": (lambda: dumps_pretty(recs), lambda b: json.loads(b)),
        "json_default_dumps": (lambda: dumps_default(recs), lambda b: json.loads(b)),
        "json_minified": (lambda: dumps_min(recs), lambda b: json.loads(b)),
        "cbor": (lambda: cbor2.dumps(recs), lambda b: cbor2.loads(b)),
        "msgpack": (lambda: msgpack.packb(recs), lambda b: msgpack.unpackb(b)),
        "bson": (lambda: b"".join(bson.encode(x) for x in recs), lambda b: bson.decode_all(b)),
        "protobuf": (lambda: ol.SerializeToString(),
                     lambda b: [pb_to_obj(o, "Order") for o in pbc["OrderList"].FromString(b).orders]),
        "avro_schemaless": (lambda: avro_stream(recs), avro_read),
        "avro_ocf_null": (lambda: avro_ocf(recs), lambda b: list(fastavro.reader(io.BytesIO(b)))),
    }
    notes = {
        "json_pretty": "json.dumps(records, indent=2, ensure_ascii=False)",
        "json_default_dumps": "json.dumps(records): ', ' and ': ' separators, ensure_ascii=True",
        "json_minified": "separators=(',', ':'), ensure_ascii=False",
        "cbor": "cbor2.dumps(records): one CBOR array of maps (RFC 8949); floats as float64",
        "msgpack": "msgpack.packb(records): one array of maps",
        "bson": "bson.encode(record) for each record, concatenated (mongodump-style document sequence; BSON's top level "
                "must be a document)",
        "protobuf": "one OrderList message (repeated Order), proto2 schema built at run time from PB_SCHEMA with "
                    "descriptor_pb2 (no protoc); field names are not on the wire",
        "avro_schemaless": "fastavro.schemaless_writer per record, concatenated; the schema travels out of band",
        "avro_ocf_null": "Avro object container file, codec null: schema JSON in the header, 16-byte sync markers",
    }
    snap_a = contention_snapshot()
    rows = {}
    for name, (enc, dec) in encoders.items():
        b = enc()
        back = dec(b)
        ok = back == recs
        if name == "protobuf":
            ok = ok and pbc["OrderList"].FromString(b).SerializeToString() == b
        enc_s = median_time(enc, n=5)
        dec_s = median_time(lambda: dec(b), n=5)
        comp = {k: len(CODECS[k]["c"](b)) for k in ("gzip_6", "zstd_3", "zstd_19")}
        rows[name] = {"raw": len(b), "sha256": sha(b), "gzip_6": comp["gzip_6"], "zstd_3": comp["zstd_3"],
                      "zstd_19": comp["zstd_19"], "roundtrip_ok": ok, "how": notes[name],
                      "encode_s_median": sig3(enc_s), "decode_s_median": sig3(dec_s),
                      "decode_records_per_s": sig3(len(recs) / dec_s), "timing_runs": 5}
        if name == "protobuf":
            rows[name]["parse_only_s_median"] = sig3(median_time(lambda: pbc["OrderList"].FromString(b), n=5))
            rows[name]["decode_note"] = ("decode_s_median = FromString plus building the record dicts (every field "
                                         "touched), comparable with the other decoders; parse_only_s_median = "
                                         "FromString alone, which upb makes lazy (Python objects are created on access)")
        log(f"  binary {name}: raw {len(b):,} gz6 {comp['gzip_6']:,} zstd3 {comp['zstd_3']:,} ok={ok}")
    snap_b = contention_snapshot()
    base = rows["json_minified"]
    for name, r_ in rows.items():
        r_["vs_json_minified_pct"] = {k: round(100 * (r_[k] / base[k] - 1), 2) for k in ("raw", "gzip_6", "zstd_3", "zstd_19")}
    return {"records": len(recs), "record_source": "api_records (the same generator and seed as json.api_records)",
            "rows": rows,
            "libraries": {"python_json": "stdlib json (C accelerator)", "cbor": "cbor2 6.1.5 (C extension _cbor2)",
                          "msgpack": "msgpack 1.2.3 (C extension)", "bson": "pymongo 4.18.3 bson (C extension)",
                          "protobuf": "protobuf 7.36.2 (upb backend)", "avro": "fastavro 1.13.1 (Cython)"},
            "timing_contention": contention_delta(snap_a, snap_b, "one Python thread; library speeds, not format speeds"),
            "method": "One record set, nine encodings; each raw and compressed with gzip -6 (mtime 0), zstd 3 and zstd 19. "
                      "roundtrip_ok: decoded value equals the records (protobuf: the dicts rebuilt from the parsed message "
                      "equal the records, and re-serialisation is byte-identical). vs_json_minified_pct = size relative to minified JSON under the same codec. "
                      "Encode/decode times are medians of 5 after 1 warm-up, for these Python libraries."}


# ----------------------------------------------------------------------------------------------------------
# config
# ----------------------------------------------------------------------------------------------------------
PRUNE = {"node_modules", ".git", "target", ".venv", "venv", "dist", "build", ".next", "__pycache__", ".pytest_cache",
         ".venv-neural", ".mypy_cache", ".ruff_cache", ".turbo", "coverage", "target-gpusim"}
CONFIG_ROOTS = [("xo-space", []), ("quirq-calculator", []), ("writings", ["what-the-parser-hears/_cases"]),
                ("fly-lab", []), ("originkit", []), ("laya", ["laya-src", "models/hub", "models/xet"]), ("mindwalk", []),
                ("makepad", ["experiments/makepad"]), ("sentrux", ["repo"]), ("doomfly", ["doomfly"]),
                ("fly-chess", ["fly-chess"]), ("flyjump", ["flyjump"]), ("default", []), ("site", []), (".xo", [])]
UPSTREAM = ["sentrux/repo", "makepad/experiments/makepad", "laya/laya-src", "doomfly/doomfly", "fly-chess/fly-chess",
            "flyjump/flyjump"]


def config_role(rel: str, fmt: str):
    n = rel.split("/")[-1]
    if fmt != "json":
        return fmt
    if rel.startswith(".xo/") or "/.xo/" in rel:
        return "json:state(.xo)"
    if n == "package-lock.json":
        return "json:lockfile"
    if n.endswith(".schema.json"):
        return "json:schema"
    data = {"_numbers.json", "vectors.json", "engine.json", "grupos.json", ".last-run.json", "browser-fixtures.json",
            "usage_sync_state.json", ".agent_harnesses.json", "run.json", "verdict.json"}
    if n in data or n.endswith(".checked.json") or (n == "manifest.json" and ("installed" in rel or "research" in rel)):
        return "json:data/artifact"
    return "json:config/manifest"


def walk(root: Path, skips):
    skip_paths = [root / s for s in skips]
    for dp, dns, fns in os.walk(root):
        dpp = Path(dp)
        dns[:] = sorted(d for d in dns if d not in PRUNE and not any(dpp / d == s for s in skip_paths))
        for f in sorted(fns):
            yield dpp / f


def part_config():
    files = []
    for proj, skips in CONFIG_ROOTS:
        root = XO / proj
        if not root.is_dir():
            continue
        for p in walk(root, skips):
            suf = p.suffix.lower()
            fmt = {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml"}.get(suf)
            if not fmt or not p.is_file() or p.is_symlink():
                continue
            rel = str(p.relative_to(XO))
            if p == OUT_JSON:
                continue                      # this harness's own output changes on every run
            files.append((rel, fmt, config_role(rel, fmt), p))
    locks = []
    for p in walk(XO, []):
        if p.name == "Cargo.lock" and p.is_file():
            rel = str(p.relative_to(XO))
            locks.append((rel, "toml", "cargo-lock", p))

    def measure(rel, fmt, role, p):
        b = p.read_bytes()
        n = len(b)
        g, br, z = len(gz(b, 9)), len(brotli.compress(b, quality=11)), len(zstd.compress(b, 19))
        return {"path": rel, "format": fmt, "role": role, "bytes": n, "gzip_9": g, "brotli_11": br, "zstd_19": z,
                "upstream": any(rel.startswith(u + "/") for u in UPSTREAM),
                "gzip_9_frac": round(g / n, 4) if n else None, "brotli_11_frac": round(br / n, 4) if n else None,
                "zstd_19_frac": round(z / n, 4) if n else None}
    rows = [measure(*f) for f in files]
    lock_rows = [measure(*f) for f in locks]
    cfg_files = sorted((rel, p) for rel, fmt, role, p in files
                       if role in ("json:config/manifest", "json:schema", "yaml", "toml") and p.stat().st_size > 0)
    register_corpus("xo_config_files", b"".join(p.read_bytes() for _, p in cfg_files),
                    f"{XO}: the {len(cfg_files)} files of config.summary.config (paths in config.files)",
                    "XO Labs first-party (XO-owned trees under ~/xo-projects; upstream clones skipped)",
                    note="bytes/sha256 are of the files concatenated in sorted path order; the other groups in "
                         "config.files (.xo watcher state, data artefacts) change between runs and are not hashed")
    lock_licence = {"sentrux/repo/": "MIT (Copyright (c) 2026 Sentrux; sentrux/repo/LICENSE); upstream clone",
                    "makepad/experiments/makepad/": "MIT (Copyright (c) 2023 Makepad B.V.; LICENSE); upstream clone",
                    "fly-chess/fly-chess/": "no licence file in the clone (github.com/tolatolatop/fly-chess); "
                                            "measured only, not redistributed"}
    for rel, _, _, p in locks:
        register_corpus("cargo_lock_" + rel.split("/")[0].replace("-", "_"), p.read_bytes(), str(p),
                        next((v for k, v in lock_licence.items() if rel.startswith(k)), "see the repository"))
    groups = {"config": ("json:config/manifest", "json:schema", "yaml", "toml"), "xo_state": ("json:state(.xo)",),
              "data_artifact": ("json:data/artifact",), "json_lockfile": ("json:lockfile",)}

    def stats(rs):
        rs = [r_ for r_ in rs if r_["bytes"] > 0]
        if not rs:
            return None
        out = {"files": len(rs), "bytes_total": sum(r_["bytes"] for r_ in rs),
               "bytes_median": statistics.median(r_["bytes"] for r_ in rs),
               "bytes_max": max(r_["bytes"] for r_ in rs), "empty_files_excluded": None}
        for k in ("gzip_9", "brotli_11", "zstd_19"):
            grew = [r_ for r_ in rs if r_[k] > r_["bytes"]]
            shrank = [r_ for r_ in rs if r_[k] < r_["bytes"]]
            out[k] = {"grew": len(grew), "grew_pct": round(100 * len(grew) / len(rs), 1),
                      "ratio_median": round(statistics.median(r_["bytes"] / r_[k] for r_ in rs), 4),
                      "ratio_total": ratio(sum(r_["bytes"] for r_ in rs), sum(r_[k] for r_ in rs)),
                      "largest_that_grew": max((r_["bytes"] for r_ in grew), default=None),
                      "smallest_that_shrank": min((r_["bytes"] for r_ in shrank), default=None)}
        return out
    by_group = {}
    for g, roles in groups.items():
        sel = [r_ for r_ in rows if r_["role"] in roles]
        by_group[g] = stats(sel)
        if by_group[g] is not None:
            by_group[g]["empty_files_excluded"] = sum(1 for r_ in sel if r_["bytes"] == 0)
            by_group[g]["by_format"] = {f: len([r_ for r_ in sel if r_["format"] == f]) for f in ("json", "yaml", "toml")}
    edges = [0, 128, 256, 512, 1024, 2048, 4096, 16384, 1 << 30]
    cfg = [r_ for r_ in rows if r_["role"] in groups["config"] and r_["bytes"] > 0]
    by_size = {}
    for lo, hi in zip(edges, edges[1:]):
        sel = [r_ for r_ in cfg if lo <= r_["bytes"] < hi]
        if sel:
            by_size[f"{lo}-{hi - 1}" if hi < 1 << 30 else f">={lo}"] = {
                "files": len(sel), **{f"{k}_grew": sum(1 for r_ in sel if r_[k] > r_["bytes"]) for k in ("gzip_9", "brotli_11", "zstd_19")},
                **{f"{k}_frac_median": round(statistics.median(r_[k] / r_["bytes"] for r_ in sel), 4) for k in ("gzip_9", "brotli_11", "zstd_19")}}
    return {"roots": [str(XO / p) for p, _ in CONFIG_ROOTS], "pruned_dirs": sorted(PRUNE),
            "skipped_subtrees": {p: s for p, s in CONFIG_ROOTS if s},
            "summary": by_group, "config_by_size": by_size, "cargo_lock": {"files": lock_rows, "summary": stats(lock_rows)},
            "files": rows,
            "method": "Every .json/.yaml/.yml/.toml file in the XO-owned trees under ~/xo-projects (the roots and skips of "
                      "~/config-ref/bench/tree/survey.py, minus ~/linear-app, which is outside ~/xo-projects; nested "
                      "upstream clones skipped; this post's fixtures under what-the-parser-hears/_cases excluded), each "
                      "compressed alone with gzip -9 (gzip member, mtime 0, no file name: 18 bytes of framing), brotli "
                      "quality 11 and zstd 19. Roles follow ~/config-ref/bench/tree/classify.py; 'config' = JSON "
                      "config/manifest + JSON Schema + YAML + TOML. Paths are relative to ~/xo-projects. Cargo.lock: every "
                      "Cargo.lock under ~/xo-projects (upstream clones included, flagged). frac = compressed / original."}


# ----------------------------------------------------------------------------------------------------------
# logs
# ----------------------------------------------------------------------------------------------------------
BLOCKS = [1024, 4096, 16384, 65536, 262144, 1 << 20, 4 << 20]
SEEKABLE_SKIPPABLE_MAGIC = 0x184D2A5E
SEEKABLE_MAGIC = 0x8F92EAB1


def seekable_compress(data, frame_size, level):
    """zstd seekable format (contrib/seekable_format): independent frames, then a skippable frame holding the seek
    table: per frame Compressed_Size u32 + Decompressed_Size u32, then Number_Of_Frames u32, descriptor u8 (no
    checksums), Seekable_Magic_Number u32."""
    frames, entries = [], []
    for off in range(0, len(data), frame_size):
        chunk = data[off:off + frame_size]
        c = zstd.compress(chunk, level)
        frames.append(c)
        entries.append(struct.pack("<II", len(c), len(chunk)))
    table = b"".join(entries) + struct.pack("<IBI", len(frames), 0, SEEKABLE_MAGIC)
    skippable = struct.pack("<II", SEEKABLE_SKIPPABLE_MAGIC, len(table)) + table
    return b"".join(frames) + skippable, len(skippable), len(frames)


def seekable_read(blob, offset, length):
    n, desc, magic = struct.unpack("<IBI", blob[-9:])
    assert magic == SEEKABLE_MAGIC
    esz = 12 if desc & 0x80 else 8
    tstart = len(blob) - 9 - n * esz
    coff = doff = 0
    out, frames_read = bytearray(), 0
    for i in range(n):
        csz, dsz = struct.unpack("<II", blob[tstart + i * esz: tstart + i * esz + 8])
        if doff + dsz > offset and doff < offset + length:
            plain = zstd.decompress(blob[coff:coff + csz])
            frames_read += 1
            lo = max(0, offset - doff)
            hi = min(dsz, offset + length - doff)
            out += plain[lo:hi]
        coff += csz
        doff += dsz
        if doff >= offset + length:
            break
    return bytes(out), frames_read


def block_sweep(data):
    out = {}
    codecs = {"gzip_6": lambda x: gz(x, 6), "zstd_3": lambda x: zstd.compress(x, 3),
              "zstd_19": lambda x: zstd.compress(x, 19), "xz_6": lambda x: lzma.compress(x, preset=6)}
    for cid, c in codecs.items():
        row = {}
        for bs in BLOCKS + [len(data)]:
            if bs > len(data) and bs != len(data):
                continue
            comp = sum(len(c(data[o:o + bs])) for o in range(0, len(data), bs))
            row["whole" if bs == len(data) else str(bs)] = {"blocks": math.ceil(len(data) / bs), "bytes": comp,
                                                             "ratio": ratio(len(data), comp)}
        out[cid] = row
        log(f"  logs blocks {cid}: " + ", ".join(f"{k}:{v['ratio']}" for k, v in row.items()))
    return out


def seekable_study(data):
    out = {}
    r = random.Random(99)
    whole = {lv: len(zstd.compress(data, lv)) for lv in (3, 19)}
    for lv in (3, 19):
        for fs in (65536, 1 << 20):
            blob, tbytes, nframes = seekable_compress(data, fs, lv)
            ok_stream = zstd.decompress(blob) == data             # standard decoders skip the skippable frame
            reads, ok_ra, fr = [], True, []
            for _ in range(200):
                off = r.randrange(0, max(1, len(data) - 1024))
                got, k = seekable_read(blob, off, 1024)
                ok_ra &= got == data[off:off + 1024]
                fr.append(k)
            t = median_time(lambda: seekable_read(blob, len(data) // 2, 1024), n=7)
            frames_bytes = len(blob) - tbytes
            out[f"zstd_{lv}_frame_{fs}"] = {
                "frame_size": fs, "frames": nframes, "frames_bytes": frames_bytes, "seek_table_bytes": tbytes,
                "total_bytes": len(blob), "single_frame_bytes": whole[lv],
                "overhead_vs_single_frame_pct": round(100 * (len(blob) / whole[lv] - 1), 3),
                "of_which_seek_table_pct": round(100 * tbytes / whole[lv], 4),
                "ratio": ratio(len(data), len(blob)), "stream_decode_ok": ok_stream, "random_reads_ok": ok_ra,
                "random_read_1KiB_frames_decompressed_mean": round(statistics.mean(fr), 3),
                "random_read_1KiB_s_median": sig3(t), "random_read_runs": 7}
    one = zstd.compress(data, 3)
    out["whole_file_single_frame_zstd_3_decompress_s_median"] = sig3(median_time(lambda: zstd.decompress(one), n=7))
    return out


def part_logs():
    corpora = {}
    if AUDIT_LOG.is_file():
        a = AUDIT_LOG.read_bytes()
        if SMOKE:
            a = a[: 600_000]
        register_corpus("doomfly_audit_jsonl", a, str(AUDIT_LOG),
                        "doomfly (MIT) run output on this machine; read for sizes and ratios only, content never stored",
                        note=f"{a.count(b'\n')} lines")
        corpora["doomfly_audit_jsonl"] = a
    synth = access_log(6_000_000 if not SMOKE else 600_000)
    register_corpus("access_log", synth, "generated by access_log(6_000_000, seed=20261012) in _compute.py",
                    "synthetic (this harness)", note=f"{synth.count(b'\n')} lines, nginx combined format + rt/uct")
    corpora["access_log"] = synth
    out = {"corpora": {k: {"bytes": len(v), "lines": v.count(b"\n")} for k, v in corpora.items()}, "blocks": {},
           "seekable": {}}
    snap_a = contention_snapshot()
    out["zstd_3_window_log_check"] = {}
    for name, data in corpora.items():
        out["blocks"][name] = block_sweep(data)
        out["seekable"][name] = seekable_study(data)
        out["zstd_3_window_log_check"][name] = {
            str(wl): len(zstd.compress(data, options={zstd.CompressionParameter.compression_level: 3,
                                                      zstd.CompressionParameter.window_log: wl}))
            for wl in (17, 18, 19, 20, 21, 22, 23)}
    snap_b = contention_snapshot()
    if AUDIT_GZ.is_file():
        gzraw = AUDIT_GZ.read_bytes()
        gzb = len(gzraw)
        register_corpus("doomfly_audit_archive_gz", gzraw, str(AUDIT_GZ),
                        "doomfly (MIT) run output on this machine; read for size and a decompression check only")
        out["tree_archive"] = {"path": str(AUDIT_GZ.relative_to(XO)), "bytes": gzb,
                               "decompresses_to_audit_log": (not SMOKE) and gzip.decompress(gzraw) == corpora.get("doomfly_audit_jsonl"),
                               "ratio": ratio(AUDIT_LOG.stat().st_size, gzb),
                               "gzip_header": {"xfl": gzraw[8], "os": gzraw[9], "fname_flag": bool(gzraw[3] & 0x08),
                                               "note": "XFL 2 = compressor used maximum compression (level 9); OS 255 "
                                                       "= unknown, which Python's gzip module writes"}}
    out["timing_contention"] = contention_delta(snap_a, snap_b, "random-read timings only")
    out["not_measured"] = {"private_session_logs": "not used by design: no ~/.claude or ~/.quirq file is opened; the brief allows aggregate ratios only, and the doomfly audit log stands in for agent JSONL"}
    out["method"] = ("Block sweep: the file is cut into fixed-size byte blocks (the last one shorter), each compressed as an "
                     "independent gzip member / zstd frame / xz stream with full headers; bytes = sum over blocks; "
                     "'whole' = the file as one block. Seekable: independent zstd frames of 64 KiB or 1 MiB plus a seek "
                     "table in the zstd contrib seekable format (skippable frame, magic 0x184D2A5E; 8 bytes per frame; "
                     "9-byte footer with magic 0x8F92EAB1), written by this harness; 200 random 1 KiB reads (seed 99) "
                     "are checked against the original; overhead is against one zstd frame of the whole file at the same "
                     "level. zstd_3_window_log_check: the whole file at level 3 with window_log forced to each value "
                     "(level 3's default for inputs over 256 KB is 21); it tests why 1 MiB blocks can beat one frame "
                     "at level 3. The audit log's content is never stored.")
    return out


# ----------------------------------------------------------------------------------------------------------
# tables
# ----------------------------------------------------------------------------------------------------------
TABLE_ROWS = 1_000_000


def make_table(n, seed=20261013):
    import pyarrow as pa
    r = random.Random(seed)
    events = ["page_view", "click", "search", "add_to_cart", "purchase", "login", "logout", "error"]
    ew = [46, 22, 10, 9, 4, 4, 3, 2]
    regions = ["eu-west-1", "eu-central-1", "us-east-1", "us-west-2", "ap-south-1", "ap-northeast-1"]
    countries = ["DE", "US", "GB", "FR", "IN", "JP", "BR", "CA", "ES", "NL", "AU", "IE", "IT", "SE", "PL", "MX", "KR",
                 "SG", "CH", "AT"]
    devices = ["desktop", "mobile", "tablet", "bot"]
    refs = ["", "", "", "https://www.google.com/", "https://news.ycombinator.com/", "https://example.com/newsletter",
            "https://t.co/", "https://www.bing.com/", "https://duckduckgo.com/", "https://github.com/"]
    cols = {k: [] for k in ("ts", "event", "region", "user_id", "session_id", "product_id", "price", "quantity",
                            "latency_ms", "status", "country", "device", "referrer", "query")}
    t = START * 1000
    sessions = {}
    for _ in range(n):
        t += int(r.expovariate(1 / 2600)) + 1
        ev = r.choices(events, ew)[0]
        uid = 1 + min(int(100000 * r.random() ** 2), 99999)
        s = sessions.get(uid)
        if s is None or s[1] < t:
            s = (b62(r, 16), t + 1_800_000)
            sessions[uid] = s
        cols["ts"].append(t)
        cols["event"].append(ev)
        cols["region"].append(regions[min(int(6 * r.random() ** 1.4), 5)])
        cols["user_id"].append(uid)
        cols["session_id"].append(s[0])
        has_p = ev in ("click", "add_to_cart", "purchase")
        cols["product_id"].append(1 + min(int(5000 * r.random() ** 2.5), 4999) if has_p else None)
        cols["price"].append(round(r.lognormvariate(3.2, 0.9), 2) if ev in ("add_to_cart", "purchase") else None)
        cols["quantity"].append(r.choices([1, 2, 3, 4], [80, 12, 5, 3])[0] if ev in ("add_to_cart", "purchase") else None)
        cols["latency_ms"].append(round(r.lognormvariate(3.0, 0.8), 3))
        cols["status"].append(r.choices([200, 304, 404, 500], [93, 4, 2.5, 0.5])[0] if ev != "error" else 500)
        cols["country"].append(countries[min(int(20 * r.random() ** 1.8), 19)])
        cols["device"].append(r.choices(devices, [52, 40, 6, 2])[0])
        cols["referrer"].append(r.choice(refs))
        cols["query"].append(f"{r.choice(WORDS)} {r.choice(WORDS)}" if ev == "search" else None)
    types = {"ts": pa.timestamp("ms", tz="UTC"), "event": pa.string(), "region": pa.string(), "user_id": pa.int64(),
             "session_id": pa.string(), "product_id": pa.int32(), "price": pa.float64(), "quantity": pa.int16(),
             "latency_ms": pa.float64(), "status": pa.int16(), "country": pa.string(), "device": pa.string(),
             "referrer": pa.string(), "query": pa.string()}
    return pa.table({k: pa.array(v, type=types[k]) for k, v in cols.items()})


def part_tables():
    import pyarrow as pa
    import pyarrow.csv as pacsv
    import pyarrow.feather as feather
    import pyarrow.parquet as pq
    W = fresh_dir(WORK / "tables")
    n = TABLE_ROWS if not SMOKE else 50_000
    tbl = make_table(n)
    files = {}
    csv_path = W / "events.csv"
    pacsv.write_csv(tbl, csv_path)
    csv = csv_path.read_bytes()
    register_corpus("events_table_csv", csv, f"generated by make_table(n={n}, seed=20261013) in _compute.py, written "
                    "with pyarrow.csv.write_csv (quoting 'needed')", "synthetic (this harness)",
                    note=f"{n} rows x {tbl.num_columns} columns")
    files["csv"] = csv_path
    for name, c in (("csv_gzip_6", lambda x: gz(x, 6)), ("csv_zstd_3", lambda x: zstd.compress(x, 3)),
                    ("csv_zstd_19", lambda x: zstd.compress(x, 19))):
        p = W / ("events.csv.gz" if "gzip" in name else f"events.{name}.csv.zst")
        p.write_bytes(c(csv))
        files[name] = p
    del csv
    variants = []
    for comp, lvl in (("none", None), ("snappy", None), ("zstd", 1), ("zstd", 3), ("zstd", 9), ("lz4_raw", None),
                      ("gzip", None)):
        for ud in (True, False):
            variants.append((f"parquet_{comp}{'' if lvl is None else lvl}_{'dict' if ud else 'nodict'}",
                             dict(compression=comp, compression_level=lvl, use_dictionary=ud)))
    floats = ["price", "latency_ms"]
    variants.append(("parquet_zstd3_dict_bss_floats", dict(compression="zstd", compression_level=3,
                                                           use_dictionary=[c for c in tbl.column_names if c not in floats],
                                                           column_encoding={c: "BYTE_STREAM_SPLIT" for c in floats})))
    variants.append(("parquet_zstd3_delta_ts_ids", dict(compression="zstd", compression_level=3,
                                                        use_dictionary=[c for c in tbl.column_names if c not in ("ts", "user_id")],
                                                        column_encoding={"ts": "DELTA_BINARY_PACKED",
                                                                         "user_id": "DELTA_BINARY_PACKED"})))
    for name, kw in variants:
        p = W / f"{name}.parquet"
        pq.write_table(tbl, p, **kw)
        files[name] = p
        log(f"  tables {name}: {p.stat().st_size:,} B")
    lowcard = ["event", "region", "country", "device", "referrer", "query", "status", "quantity", "product_id"]
    tuned = dict(compression="zstd", compression_level=3, use_dictionary=lowcard,
                 column_encoding={"ts": "DELTA_BINARY_PACKED", "user_id": "DELTA_BINARY_PACKED",
                                  "price": "BYTE_STREAM_SPLIT", "latency_ms": "BYTE_STREAM_SPLIT",
                                  "session_id": "DELTA_BYTE_ARRAY"})
    for name, kw in (("parquet_zstd3_tuned", tuned), ("parquet_zstd9_tuned", dict(tuned, compression_level=9))):
        p = W / f"{name}.parquet"
        pq.write_table(tbl, p, **kw)
        files[name] = p
        variants.append((name, kw))
        log(f"  tables {name}: {p.stat().st_size:,} B")
    for comp in ("uncompressed", "lz4", "zstd"):
        p = W / f"events.{comp}.arrow"
        feather.write_feather(tbl, p, compression=comp)
        files[f"arrow_ipc_{comp}"] = p
    p = W / "events.zstd3.arrow"                       # like-for-like with Parquet zstd 3 (Arrow's own default is 1)
    feather.write_feather(tbl, p, compression="zstd", compression_level=3)
    files["arrow_ipc_zstd3"] = p
    p1 = W / "events.zstd1.arrow"
    feather.write_feather(tbl, p1, compression="zstd", compression_level=1)
    arrow_zstd_default_is_level_1 = sha_file(p1) == sha_file(files["arrow_ipc_zstd"])
    p1.unlink()
    # determinism: write two variants twice
    det = {}
    for name in ("parquet_zstd3_dict", "parquet_snappy_dict"):
        kw = dict(variants)[name]
        p2 = W / f"{name}.again.parquet"
        pq.write_table(tbl, p2, **kw)
        det[name] = sha_file(p2) == sha_file(files[name])
        p2.unlink()
    # per-column chunk sizes for two variants
    columns = {}
    for name in ("parquet_zstd3_dict", "parquet_zstd3_nodict", "parquet_none_dict", "parquet_none_nodict",
                 "parquet_zstd3_tuned"):
        md = pq.ParquetFile(files[name]).metadata
        cc = {}
        for i in range(md.num_columns):
            ch = md.row_group(0).column(i)
            cc[ch.path_in_schema] = {"compressed": ch.total_compressed_size, "uncompressed": ch.total_uncompressed_size,
                                     "encodings": list(ch.encodings), "codec": ch.compression}
        columns[name] = {"row_groups": md.num_row_groups, "created_by": md.created_by, "columns": cc}
    # read times
    snap_a = contention_snapshot()
    rows = {}
    for name, p in files.items():
        if name.startswith("csv"):
            fn = lambda p=p: pacsv.read_csv(p)
        elif name.startswith("parquet"):
            fn = lambda p=p: pq.read_table(p)
        else:
            fn = lambda p=p: feather.read_table(p)
        back = fn()
        same = back.num_rows == n and (back.equals(tbl) if not name.startswith("csv") else True)
        tsec = median_time(fn, n=5, warm=1)
        rows[name] = {"bytes": p.stat().st_size, "sha256": sha_file(p), "read_s_median": sig3(tsec),
                      "read_Mrows_per_s": sig3(n / tsec / 1e6), "read_runs": 5, "read_back_equal": same}
        log(f"  tables read {name}: {tsec:.3f} s")
    snap_b = contention_snapshot()
    base = rows["csv"]["bytes"]
    gzb = rows["csv_gzip_6"]["bytes"]
    for r_ in rows.values():
        r_["vs_csv_pct"] = round(100 * r_["bytes"] / base, 2)
        r_["vs_csv_gzip_6_x"] = round(gzb / r_["bytes"], 3)
    out = {"rows": n, "columns": {f.name: str(f.type) for f in tbl.schema},
           "description": "Synthetic clickstream: ts (ms, increasing, exponential gaps, mean 2.6 s, from 2026-09-01), "
                          "event (8 values, skewed), region (6), user_id (1-100,000, skewed), session_id (16 base62 "
                          "chars, renewed after 30 min per user), product_id/price/quantity (only for product events, "
                          "else null), latency_ms (lognormal, 3 decimals), status (HTTP code), country (20, skewed), "
                          "device (4), referrer (10 incl. empty), query (2 words, only for search). Generated with "
                          "random.Random(20261013).",
           "files": rows, "parquet_columns": columns, "parquet_deterministic_rewrite": det,
           "writer_defaults": {"pyarrow.parquet.write_table": "compression='snappy', use_dictionary=True, version='2.6', "
                                                              "row_group_size = all rows up to 1Mi (here one row group)",
                               "pyarrow.feather.write_feather": "compression='lz4' when available",
                               "arrow_ipc_zstd_level": "arrow_ipc_zstd uses Arrow's default zstd level; identical bytes "
                                                       "to compression_level=1: " + str(arrow_zstd_default_is_level_1) +
                                                       "; arrow_ipc_zstd3 sets level 3 explicitly"},
           "not_measured": {"duckdb_native": "not run: DuckDB is not installed and not among the pinned wheels; its "
                                             "lightweight compression is a sourced claim (structured.md section 7)"},
           "timing_contention": contention_delta(snap_a, snap_b, "pyarrow reads use its own thread pool (2 CPUs)"),
           "method": "One table written as CSV (pyarrow, quoting 'needed'), CSV + gzip -6 / zstd 3 / zstd 19, Parquet "
                     "(pyarrow 26.0.0) with each codec with and without dictionary encoding, two encoding variants "
                     "(BYTE_STREAM_SPLIT on the two float columns; DELTA_BINARY_PACKED on ts and user_id), a 'tuned' "
                     "layout (dictionary only on the low-cardinality columns, DELTA_BINARY_PACKED on ts and user_id, "
                     "BYTE_STREAM_SPLIT on the floats, DELTA_BYTE_ARRAY on session_id) at zstd 3 and 9, and Arrow IPC "
                     "(Feather v2) uncompressed / lz4 / zstd (Arrow default level, 1) / zstd 3. Read time = median of 5 full reads into an Arrow table "
                     "after 1 warm-up (CSV via pyarrow.csv.read_csv, which decompresses .gz/.zst by extension). "
                     "read_back_equal: Parquet/Arrow read back Table.equals the original; CSV: row count."}
    if not SMOKE:
        shutil.rmtree(W)            # 100+ MB of scratch; the sizes and hashes are recorded above
    return out


# ----------------------------------------------------------------------------------------------------------
# images
# ----------------------------------------------------------------------------------------------------------
JPEG_Q = [20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 93, 95, 97]
WEBP_Q = [20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 93, 95, 97, 100]
AVIF_Q = [20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 93, 95, 97]
JXL_D = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 9.0]
SSIM2_TARGETS = [60, 70, 80, 85, 90]


def ssim2(orig: Path, dist: Path) -> float:
    p, _, _ = run([SSIMULACRA2, orig, dist])
    return float(p.stdout.strip().split()[-1])


def pil_bytes(im, **kw):
    buf = io.BytesIO()
    im.save(buf, **kw)
    return buf.getvalue()


def decode_to_png(data: bytes, out: Path):
    from PIL import Image
    Image.open(io.BytesIO(data)).convert("RGB").save(out, format="PNG", compress_level=1)


def interp_bytes(points, target):
    pts = sorted(points, key=lambda p: p["bytes"])
    for a, b in zip(pts, pts[1:]):
        sa, sb = a["ssimulacra2"], b["ssimulacra2"]
        if sa <= target <= sb and sb > sa:
            f = (target - sa) / (sb - sa)
            return round(math.exp(math.log(a["bytes"]) + f * (math.log(b["bytes"]) - math.log(a["bytes"])))), \
                [a["param"], b["param"]]
    return None, None


def part_images():
    miss = missing_tools(CJXL, DJXL, SSIMULACRA2, OXIPNG)
    if miss:
        return {"skipped": f"missing {miss}; run {SETUP} jxl oxipng"}
    from PIL import Image, features
    W = fresh_dir(WORK / "images")
    photos = {k: v for k, v in MEDIA_FILES.items() if v["kind"] == "photo" and v["path"].is_file()}
    if not photos:
        return {"skipped": f"no photographs in {MEDIA}; run {SETUP} images"}
    graphics = {k: v for k, v in FIRST_PARTY_IMAGES.items() if v["path"].is_file()}
    for k, v in photos.items():
        if sha_file(v["path"]) != v["sha256"]:
            return {"skipped": f"{v['path']} sha256 mismatch"}
        register_corpus(f"image_{k}", v["path"].read_bytes(), v["url"], v["licence"], note=v["desc"], path=v["path"])
    for k, v in graphics.items():
        register_corpus(f"image_{k}", v["path"].read_bytes(), str(v["path"]), v["licence"], note=v["desc"])
    allimgs = {**photos, **graphics}
    if SMOKE:
        allimgs = dict(list(photos.items())[:1] + list(graphics.items())[:1])
        photos = dict(list(photos.items())[:1])
    # ---- lossless
    lossless = {}
    for k, v in allimgs.items():
        src = v["path"]
        im = Image.open(src)
        im.load()
        mode = "RGBA" if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info else "RGB"
        ref = im.convert(mode)
        px = ref.tobytes()
        w, h = ref.size
        row = {"kind": v["kind"], "width": w, "height": h, "mode": mode, "png_as_is": src.stat().st_size}

        def same(data=None, path=None):
            imx = Image.open(io.BytesIO(data) if data is not None else path)
            return imx.convert(mode).tobytes() == px
        b = pil_bytes(ref, format="PNG", optimize=True)
        row["png_pillow_optimize"] = {"bytes": len(b), "lossless_ok": same(b)}
        tmp = W / f"{k}.src.png"
        shutil.copyfile(src, tmp)
        out = W / f"{k}.oxipng.png"
        _, wall, _ = run([OXIPNG, "-o", "4", "--strip", "safe", "--out", out, tmp])
        row["oxipng_o4"] = {"bytes": out.stat().st_size, "lossless_ok": same(path=out), "wall_s": sig3(wall)}
        for name, kw in (("webp_lossless_default", dict(lossless=True)),
                         ("webp_lossless_max", dict(lossless=True, quality=100, method=6))):
            t0 = time.perf_counter()
            b = pil_bytes(ref, format="WEBP", **kw)
            row[name] = {"bytes": len(b), "lossless_ok": same(b), "wall_s": sig3(time.perf_counter() - t0)}
        for e in (7, 9):
            out = W / f"{k}.e{e}.jxl"
            _, wall, _ = run([CJXL, tmp, out, "-d", "0", "-e", str(e), "--quiet"])
            dec = W / f"{k}.e{e}.dec.png"
            run([DJXL, out, dec, "--quiet"])
            row[f"jxl_lossless_e{e}"] = {"bytes": out.stat().st_size, "lossless_ok": same(path=dec), "wall_s": sig3(wall)}
        for f_ in ("png_pillow_optimize", "oxipng_o4", "webp_lossless_default", "webp_lossless_max", "jxl_lossless_e7",
                   "jxl_lossless_e9"):
            row[f_]["vs_png_as_is_pct"] = round(100 * (row[f_]["bytes"] / row["png_as_is"] - 1), 2)
        lossless[k] = row
        log(f"  images lossless {k}: png {row['png_as_is']:,} oxipng {row['oxipng_o4']['bytes']:,} "
            f"webp {row['webp_lossless_max']['bytes']:,} jxl {row['jxl_lossless_e9']['bytes']:,}")
    # ---- lossy sweeps on photographs, scored with SSIMULACRA 2
    jq, wq, aq, jd = (JPEG_Q, WEBP_Q, AVIF_Q, JXL_D) if not SMOKE else ([50, 75, 90], [50, 75, 90], [50, 75, 90], [1.0, 2.0, 4.0])
    sweeps = {}
    for k, v in photos.items():
        ref = Image.open(v["path"]).convert("RGB")
        w, h = ref.size
        refpng = W / f"{k}.ref.png"
        ref.save(refpng, format="PNG", compress_level=1)
        codecs = {}

        def score(data, tag, decoder="pillow"):
            dec = W / f"{k}.{tag}.dec.png"
            if decoder == "pillow":
                decode_to_png(data, dec)
            return round(ssim2(refpng, dec), 4)
        pts = []
        for q in jq:
            b = pil_bytes(ref, format="JPEG", quality=q, optimize=True, subsampling="4:2:0")
            pts.append({"param": q, "bytes": len(b), "bpp": round(8 * len(b) / (w * h), 4), "ssimulacra2": score(b, f"jpg{q}")})
        codecs["jpeg_420"] = pts
        pts = []
        for q in jq:
            b = pil_bytes(ref, format="JPEG", quality=q, optimize=True, subsampling="4:4:4")
            pts.append({"param": q, "bytes": len(b), "bpp": round(8 * len(b) / (w * h), 4), "ssimulacra2": score(b, f"jpg444{q}")})
        codecs["jpeg_444"] = pts
        pts = []
        for q in wq:
            b = pil_bytes(ref, format="WEBP", quality=q, method=4)
            pts.append({"param": q, "bytes": len(b), "bpp": round(8 * len(b) / (w * h), 4), "ssimulacra2": score(b, f"webp{q}")})
        codecs["webp"] = pts
        pts = []
        for q in aq:
            b = pil_bytes(ref, format="AVIF", quality=q, speed=6)
            pts.append({"param": q, "bytes": len(b), "bpp": round(8 * len(b) / (w * h), 4), "ssimulacra2": score(b, f"avif{q}")})
        codecs["avif"] = pts
        pts = []
        for d_ in jd:
            out = W / f"{k}.d{d_}.jxl"
            run([CJXL, refpng, out, "-d", str(d_), "-e", "7", "--quiet"])
            dec = W / f"{k}.d{d_}.dec.png"
            run([DJXL, out, dec, "--quiet"])
            n_ = out.stat().st_size
            pts.append({"param": d_, "bytes": n_, "bpp": round(8 * n_ / (w * h), 4), "ssimulacra2": round(ssim2(refpng, dec), 4)})
        codecs["jxl"] = pts
        matched = {}
        for tgt in SSIM2_TARGETS:
            mrow = {}
            for c, pts in codecs.items():
                bb, br = interp_bytes(pts, tgt)
                mrow[c] = {"bytes": bb, "between_params": br}
            jb = mrow["jpeg_420"]["bytes"]
            for c in mrow:
                if mrow[c]["bytes"] and jb:
                    mrow[c]["vs_jpeg_420_pct"] = round(100 * (mrow[c]["bytes"] / jb - 1), 1)
            matched[str(tgt)] = mrow
        sweeps[k] = {"width": w, "height": h, "codecs": codecs, "bytes_at_ssimulacra2": matched}
        log(f"  images lossy {k}: at 80 -> " + ", ".join(f"{c}:{matched['80'][c]['bytes']}" for c in codecs))
    # totals across the photographs at each target
    totals = {}
    for tgt in SSIM2_TARGETS:
        t_ = {}
        for c in ("jpeg_420", "jpeg_444", "webp", "avif", "jxl"):
            vals = [sweeps[k]["bytes_at_ssimulacra2"][str(tgt)][c]["bytes"] for k in sweeps]
            t_[c] = sum(vals) if all(vals) else None
        if t_["jpeg_420"]:
            t_["vs_jpeg_420_pct"] = {c: round(100 * (t_[c] / t_["jpeg_420"] - 1), 1) for c in t_ if t_[c]
                                     and c != "jpeg_420"}
        totals[str(tgt)] = t_
    # ---- encode speed tiers on the first photograph
    k0 = next(iter(photos))
    ref = Image.open(photos[k0]["path"]).convert("RGB")
    refpng = W / f"{k0}.ref.png"
    mp = ref.size[0] * ref.size[1] / 1e6
    snap_a = contention_snapshot()
    speed = {}
    for name, fn in (("jpeg_q85", lambda: pil_bytes(ref, format="JPEG", quality=85, optimize=True)),
                     ("webp_q85_m4", lambda: pil_bytes(ref, format="WEBP", quality=85, method=4)),
                     ("avif_q75_s6", lambda: pil_bytes(ref, format="AVIF", quality=75, speed=6)),
                     ("jxl_d1_e7_cli", lambda: run([CJXL, refpng, W / "speed.jxl", "-d", "1", "-e", "7", "--quiet"])),
                     ("webp_lossless_default", lambda: pil_bytes(ref, format="WEBP", lossless=True)),
                     ("jxl_lossless_e7_cli", lambda: run([CJXL, refpng, W / "speed0.jxl", "-d", "0", "-e", "7", "--quiet"]))):
        tsec = median_time(fn, n=5)
        speed[name] = {"s_median": sig3(tsec), "MP_per_s": sig3(mp / tsec), "tier": tier_mpix(mp / tsec), "runs": 5}
    snap_b = contention_snapshot()
    # ---- JPEG -> JPEG XL lossless recompression
    jpegs = {}
    srcs = {f"writings_{n.split('.')[0]}": p for n, p in FIRST_PARTY_JPEGS.items() if p.is_file()}
    for k, p in srcs.items():
        register_corpus(f"image_{k}", p.read_bytes(), str(p), "XO Labs first-party (this site's own image assets)",
                        note="JPEG as published on the site; used for JPEG -> JPEG XL transcoding and recompress")
    for k in photos:
        p = W / f"{k}_q90.jpg"
        p.write_bytes(pil_bytes(Image.open(photos[k]["path"]).convert("RGB"), format="JPEG", quality=90, optimize=True))
        srcs[f"{k}_pillow_q90"] = p
    for k, p in srcs.items():
        out = W / f"{k}.jpg.jxl"
        run([CJXL, p, out, "--lossless_jpeg=1", "-e", "7", "--quiet"])
        rec = W / f"{k}.rec.jpg"
        run([DJXL, out, rec, "--quiet"])
        a, b = p.stat().st_size, out.stat().st_size
        jpegs[k] = {"jpeg_bytes": a, "jxl_bytes": b, "saving_pct": saving(a, b),
                    "bit_exact_reconstruction": sha_file(rec) == sha_file(p),
                    "source": str(p.relative_to(WRITINGS)) if str(p).startswith(str(WRITINGS)) else f"Pillow q90 of {k.split('_')[0]}"}
    if jpegs:
        tot_a = sum(v["jpeg_bytes"] for v in jpegs.values())
        tot_b = sum(v["jxl_bytes"] for v in jpegs.values())
        jpegs["_total"] = {"jpeg_bytes": tot_a, "jxl_bytes": tot_b, "saving_pct": saving(tot_a, tot_b),
                           "mean_saving_pct": round(statistics.mean(v["saving_pct"] for k, v in jpegs.items()
                                                                    if not k.startswith("_")), 2)}
    # ---- SVG is text
    svgs = sorted(p for p in WRITINGS.rglob("*.svg") if "_cases" not in p.parts)
    sv = b"".join(p.read_bytes() for p in svgs)
    register_corpus("svg_site_set", sv, f"{WRITINGS}/**/*.svg ({len(svgs)} files; what-the-parser-hears/_cases excluded)",
                    "XO Labs first-party (this site's SVG assets)",
                    note="bytes/sha256 are of the files concatenated in sorted path order")
    svg = {"files": len(svgs), "bytes": sum(p.stat().st_size for p in svgs),
           "gzip_9_per_file": sum(len(gz(p.read_bytes(), 9)) for p in svgs),
           "brotli_11_per_file": sum(len(brotli.compress(p.read_bytes(), quality=11)) for p in svgs),
           "zstd_19_per_file": sum(len(zstd.compress(p.read_bytes(), 19)) for p in svgs), "sha256_concat": sha(sv)}
    for k_ in ("gzip_9_per_file", "brotli_11_per_file", "zstd_19_per_file"):
        svg[k_.replace("_per_file", "_ratio")] = ratio(svg["bytes"], svg[k_])
    from PIL import _avif
    TOOLV["pillow_codecs"] = {"libjpeg_turbo": features.version("libjpeg_turbo"), "libwebp": features.version("webp"),
                              "libavif": features.version("avif"), "avif_codecs": _avif.codec_versions(),
                              "zlib_in_pillow": features.version("zlib"), "zlib_ng_in_pillow": features.version("zlib_ng")}
    return {"inputs": {k: {"path": str(v["path"]), "kind": v["kind"], "licence": v["licence"], "desc": v["desc"]}
                       for k, v in allimgs.items()},
            "lossless": lossless, "lossy_photos": sweeps, "lossy_totals_at_ssimulacra2": totals,
            "encode_speed": dict(speed, image=k0, megapixels=round(mp, 4),
                                 contention=contention_delta(snap_a, snap_b, "Pillow encoders in-process; cjxl as a child "
                                                                            "process (includes process start and PNG decode)")),
            "jpeg_to_jxl_lossless": jpegs, "svg_text": svg,
            "not_measured": {"mozjpeg_jpegli": "not available as pinned wheels or static binaries here; JPEG is Pillow's libjpeg-turbo with optimised Huffman tables", "butteraugli": "not run; SSIMULACRA 2 is the one metric (butteraugli_main ships in the same libjxl tarball)"},
            "metric": {"name": "SSIMULACRA 2", "tool": str(SSIMULACRA2), "scale_from_tool_usage_text": [
                "70 = high quality (hard to notice artifacts without comparison to the original, average output of "
                "cjxl -d 2.5 / -q 73 or libjpeg-turbo quality 70)",
                "80 = very high quality (impossible to distinguish from the original in a side-by-side comparison at "
                "1:1, average output of cjxl -d 1.5 / -q 85 or libjpeg-turbo quality 85 (4:2:2))",
                "90 = visually lossless (impossible to distinguish from the original in a flicker test at 1:1, average "
                "output of cjxl -d 0.5 / -q 95 or libjpeg-turbo quality 95 (4:4:4)"]},
            "settings": {"jpeg": "Pillow (libjpeg-turbo) quality q, optimize=True (optimised Huffman), baseline, "
                                 "subsampling 4:2:0 or 4:4:4",
                         "webp": "Pillow (libwebp) quality q, method 4 (default), lossy",
                         "avif": "Pillow (libavif + libaom) quality q, speed 6 (default), 4:2:0 (default)",
                         "jxl": "cjxl -d distance -e 7 (default effort), from the PNG",
                         "lossless": "oxipng -o 4 --strip safe; Pillow PNG optimize=True; WebP lossless default "
                                     "(quality 80, method 4) and max (quality 100, method 6); cjxl -d 0 -e 7 and -e 9",
                         "jpeg_to_jxl": "cjxl in.jpg out.jxl --lossless_jpeg=1 -e 7; djxl out.jxl rec.jpg; "
                                        "bit_exact = SHA-256 of rec.jpg equals the input"},
            "method": "Lossless: every result is decoded and compared pixel for pixel with the source (lossless_ok). "
                      "Lossy: each photograph is encoded at every listed setting; the output is decoded (Pillow for "
                      "JPEG/WebP/AVIF, djxl for JPEG XL) to PNG and scored against the source PNG with ssimulacra2. "
                      "bytes_at_ssimulacra2: bytes at the target score, interpolated linearly in log(bytes) between the "
                      "two neighbouring settings that bracket it; null = the sweep never reached that score. Encode "
                      "speed: median of 5 after 1 warm-up on one 768x512 photograph."}


# ----------------------------------------------------------------------------------------------------------
# audio
# ----------------------------------------------------------------------------------------------------------
FLAC_BLOCKS = {0: "STREAMINFO", 1: "PADDING", 2: "APPLICATION", 3: "SEEKTABLE", 4: "VORBIS_COMMENT", 5: "CUESHEET",
               6: "PICTURE"}


def flac_layout(b: bytes):
    """Metadata blocks of a FLAC file (RFC 9639 sec. 8) and the offset where audio frames start."""
    assert b[:4] == b"fLaC"
    pos, blocks = 4, []
    while True:
        hdr = b[pos]
        n = int.from_bytes(b[pos + 1:pos + 4], "big")
        blocks.append({"type": FLAC_BLOCKS.get(hdr & 0x7F, hdr & 0x7F), "bytes": n})
        pos += 4 + n
        if hdr & 0x80:
            break
    return blocks, pos
AUDIO_ENCODES = [
    ("wav_pcm_s16le", ["-c:a", "pcm_s16le"], "wav", True),
    ("flac_0", ["-c:a", "flac", "-compression_level", "0"], "flac", True),
    ("flac_5", ["-c:a", "flac", "-compression_level", "5"], "flac", True),
    ("flac_8", ["-c:a", "flac", "-compression_level", "8"], "flac", True),
    ("alac", ["-c:a", "alac"], "m4a", True),
    ("opus_32k", ["-c:a", "libopus", "-b:a", "32k"], "opus", False),
    ("opus_64k", ["-c:a", "libopus", "-b:a", "64k"], "opus", False),
    ("opus_96k", ["-c:a", "libopus", "-b:a", "96k"], "opus", False),
    ("opus_128k", ["-c:a", "libopus", "-b:a", "128k"], "opus", False),
    ("aac_128k", ["-c:a", "aac", "-b:a", "128k"], "m4a", False),
    ("mp3_128k", ["-c:a", "libmp3lame", "-b:a", "128k"], "mp3", False),
]


def ffprobe_json(p: Path, *args):
    pr, _, _ = run([FFPROBE, "-v", "error", "-of", "json", *args, p])
    return json.loads(pr.stdout)


def part_audio():
    miss = missing_tools(FFMPEG, FFPROBE)
    if miss:
        return {"skipped": f"missing {miss}; run {SETUP} ffmpeg"}
    m = MEDIA_FILES["sintel_audio"]
    if not m["path"].is_file():
        return {"skipped": f"{m['path']} missing; run {SETUP} audio"}
    src = m["path"]
    if sha_file(src) != m["sha256"]:
        return {"skipped": f"{src} sha256 mismatch"}
    register_corpus("audio_sintel_trailer", src.read_bytes(), m["url"], m["licence"], note=m["desc"], path=src)
    W = fresh_dir(WORK / "audio")
    base = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src]
    if SMOKE:
        base += ["-t", "5"]
    pr, _, _ = run(base + ["-map", "0:a", "-f", "s16le", "-c:a", "pcm_s16le", "-"], stdout_bytes=True)
    pcm = pr.stdout
    info = ffprobe_json(src, "-show_entries", "stream=sample_rate,channels,bits_per_raw_sample:format=duration")
    dur = len(pcm) / (48000 * 2 * 2)
    rows = {"source_flac_as_distributed": {"bytes": src.stat().st_size, "kbps": round(src.stat().st_size * 8 / dur / 1000, 1),
                                           "lossless": True}}
    for name, args, ext, lossless in AUDIO_ENCODES:
        out = W / f"{name}.{ext}"
        cmd = base + ["-map", "0:a", "-map_metadata", "-1", "-fflags", "+bitexact", *args, out]
        walls = []
        for _ in range(3):
            _, wall, _ = run(cmd)
            walls.append(wall)
        n = out.stat().st_size
        row = {"bytes": n, "kbps": round(n * 8 / dur / 1000, 1), "ratio_vs_wav": None, "lossless": lossless,
               "encode_s_median": sig3(statistics.median(walls)), "encode_runs": 3,
               "encode_x_realtime": sig3(dur / statistics.median(walls)), "args": " ".join(map(str, args))}
        if lossless:
            pr2, _, _ = run([FFMPEG, "-nostdin", "-v", "error", "-i", out, "-f", "s16le", "-c:a", "pcm_s16le", "-"],
                            stdout_bytes=True)
            row["pcm_identical"] = pr2.stdout == pcm
        rows[name] = row
    wav = rows["wav_pcm_s16le"]["bytes"]
    for r_ in rows.values():
        r_["ratio_vs_wav"] = ratio(wav, r_["bytes"])
        r_["pct_of_wav"] = round(100 * r_["bytes"] / wav, 2)
    # where a general-purpose codec still finds something in FLAC: the metadata padding vs the audio frames
    flac = {}
    for name, path in (("flac_8", W / "flac_8.flac"), ("source_flac_as_distributed", src)):
        b = path.read_bytes()
        blocks, start = flac_layout(b)
        frames = b[start:]
        flac[name] = {"bytes": len(b), "metadata_blocks": blocks, "audio_frames_bytes": len(frames),
                      "padding_bytes": sum(x["bytes"] for x in blocks if x["type"] == "PADDING"),
                      **{f"{cid}_whole_saving_pct": saving(len(b), len(CODECS[cid]["c"](b))) for cid in ("gzip_9", "zstd_19")},
                      **{f"{cid}_frames_only_saving_pct": saving(len(frames), len(CODECS[cid]["c"](frames)))
                         for cid in ("gzip_9", "zstd_19")}}
    return {"source": {"path": str(src), "url": m["url"], "licence": m["licence"], "duration_s": round(dur, 3),
                       "pcm_bytes": len(pcm), "pcm_sha256": sha(pcm), "probe": info.get("streams", [{}])[0]},
            "rows": rows, "flac_structure": flac, "quality_metric": None,
            "quality_metric_note": "No perceptual audio metric is available here (ViSQOL/PEAQ not installed); bytes only. "
                                   "Lossless rows are verified: decoded PCM is byte-identical to the source's.",
            "encoders": {"flac": "FFmpeg's native FLAC encoder (not libFLAC); -compression_level 0/5/8; FFmpeg's FLAC "
                                  "muxer writes an 8,192-byte PADDING metadata block (see flac_structure)",
                         "alac": "FFmpeg's native ALAC encoder", "opus": "libopus via FFmpeg (VBR, application audio, "
                         "20 ms frames: FFmpeg defaults) in Ogg", "aac": "FFmpeg's native AAC encoder (LC) in MP4",
                         "mp3": "libmp3lame CBR"},
            "method": "Source FLAC decoded to 16-bit PCM by FFmpeg; each row encodes that clip with the FFmpeg command "
                      "base + args (stream 0:a, metadata stripped, -fflags +bitexact). kbps = file bytes * 8 / duration. "
                      "Encode time: median of 3 single-process runs (FFmpeg's own threading), including FLAC decode."}


# ----------------------------------------------------------------------------------------------------------
# video
# ----------------------------------------------------------------------------------------------------------
VIDEO_ENCODES = [
    ("x264_crf18", "libx264", ["-preset", "medium", "-crf", "18"], True),
    ("x264_crf23", "libx264", ["-preset", "medium", "-crf", "23"], True),
    ("x264_crf28", "libx264", ["-preset", "medium", "-crf", "28"], True),
    ("x264_crf33", "libx264", ["-preset", "medium", "-crf", "33"], False),
    ("x265_crf23", "libx265", ["-preset", "medium", "-crf", "23", "-tag:v", "hvc1", "-x265-params", "log-level=error"], True),
    ("x265_crf28", "libx265", ["-preset", "medium", "-crf", "28", "-tag:v", "hvc1", "-x265-params", "log-level=error"], True),
    ("x265_crf32", "libx265", ["-preset", "medium", "-crf", "32", "-tag:v", "hvc1", "-x265-params", "log-level=error"], True),
    ("x265_crf36", "libx265", ["-preset", "medium", "-crf", "36", "-tag:v", "hvc1", "-x265-params", "log-level=error"], False),
    ("svtav1_p8_crf25", "libsvtav1", ["-preset", "8", "-crf", "25"], True),
    ("svtav1_p8_crf35", "libsvtav1", ["-preset", "8", "-crf", "35"], True),
    ("svtav1_p8_crf45", "libsvtav1", ["-preset", "8", "-crf", "45"], True),
    ("svtav1_p8_crf55", "libsvtav1", ["-preset", "8", "-crf", "55"], False),
    ("svtav1_p4_crf35", "libsvtav1", ["-preset", "4", "-crf", "35"], False),
    ("svtav1_p10_crf35", "libsvtav1", ["-preset", "10", "-crf", "35"], False),
]
VIDEO_TIMED_REPEATS = {"x264_crf23", "x265_crf28", "svtav1_p8_crf35"}
VMAF_MODEL = "vmaf_v0.6.1"


def polyfit3(xs, ys):
    """Least-squares cubic y = c0 + c1 u + c2 u^2 + c3 u^3 with u = (x - m) / s; returns (coeffs, m, s)."""
    m = statistics.mean(xs)
    s = statistics.pstdev(xs) or 1.0
    us = [(x - m) / s for x in xs]
    A = [[sum(u ** (i + j) for u in us) for j in range(4)] for i in range(4)]
    b = [sum(y * u ** i for u, y in zip(us, ys)) for i in range(4)]
    for i in range(4):                                   # Gaussian elimination with partial pivoting
        piv = max(range(i, 4), key=lambda r: abs(A[r][i]))
        A[i], A[piv], b[i], b[piv] = A[piv], A[i], b[piv], b[i]
        for r in range(i + 1, 4):
            f = A[r][i] / A[i][i]
            for c in range(i, 4):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    c = [0.0] * 4
    for i in range(3, -1, -1):
        c[i] = (b[i] - sum(A[i][j] * c[j] for j in range(i + 1, 4))) / A[i][i]
    return c, m, s


def poly_mean(fit, lo, hi):
    c, m, s = fit
    a, b = (lo - m) / s, (hi - m) / s
    F = lambda u: sum(c[i] * u ** (i + 1) / (i + 1) for i in range(4))
    return (F(b) - F(a)) / (b - a)


def poly_monotonic(fit, lo, hi, n=400):
    """True if the fitted cubic is non-decreasing on [lo, hi] (rate must not fall as quality rises)."""
    c, m, s = fit
    ys = [sum(c[i] * ((lo + (hi - lo) * j / (n - 1) - m) / s) ** i for i in range(4)) for j in range(n)]
    return all(b >= a - 1e-12 for a, b in zip(ys, ys[1:]))


def pchip_slopes(xs, ys):
    """Node derivatives of the shape-preserving piecewise cubic Hermite interpolant (Fritsch-Carlson with the
    Fritsch-Butland weighted harmonic mean inside and the one-sided three-point rule at the ends), the same rules as
    scipy.interpolate.PchipInterpolator."""
    sgn = lambda v: (v > 0) - (v < 0)
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    m = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [m[0], m[0]]
    d = [0.0] * n
    for k in range(1, n - 1):
        if sgn(m[k - 1]) != sgn(m[k]) or m[k - 1] == 0 or m[k] == 0:
            d[k] = 0.0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            d[k] = (w1 + w2) / (w1 / m[k - 1] + w2 / m[k])

    def edge(h0, h1, m0, m1):
        e = ((2 * h0 + h1) * m0 - h0 * m1) / (h0 + h1)
        if sgn(e) != sgn(m0):
            return 0.0
        if sgn(m0) != sgn(m1) and abs(e) > 3 * abs(m0):
            return 3 * m0
        return e
    d[0] = edge(h[0], h[1], m[0], m[1])
    d[-1] = edge(h[-1], h[-2], m[-1], m[-2])
    return d


def pchip_eval(xs, ys, ds, x):
    k = max(0, min(len(xs) - 2, next((i for i in range(len(xs) - 1) if x <= xs[i + 1]), len(xs) - 2)))
    h = xs[k + 1] - xs[k]
    t = (x - xs[k]) / h
    return ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[k] + (t ** 3 - 2 * t ** 2 + t) * h * ds[k]
            + (-2 * t ** 3 + 3 * t ** 2) * ys[k + 1] + (t ** 3 - t ** 2) * h * ds[k + 1])


def pchip_mean(pts, lo, hi, samples=1000):
    """Mean of the PCHIP of log10(kbps) over [lo, hi]: trapezoidal integration over `samples` evenly spaced points."""
    xs = [v for v, _ in pts]
    ys = [math.log10(k) for _, k in pts]
    ds = pchip_slopes(xs, ys)
    step = (hi - lo) / (samples - 1)
    vals = [pchip_eval(xs, ys, ds, lo + step * i) for i in range(samples)]
    return step * (sum(vals) - (vals[0] + vals[-1]) / 2) / (hi - lo)


def bd_rate(ref, test):
    """Bjontegaard delta rate as draft-ietf-netvc-testing-09 sec. 4.2 specifies it: log10(kbps) as a function of VMAF,
    a piecewise cubic Hermite interpolating polynomial through each codec's points, integrated over the overlapping VMAF
    interval with 1,000 samples and the trapezoidal rule; returns the % rate change of test vs ref at equal VMAF.
    The classic VCEG-M33 single cubic (least squares) is recorded beside it for comparison, with a flag saying whether
    each fitted cubic is monotonic over the interval (a cubic through 4 uneven points can bend backwards)."""
    ref, test = sorted(ref), sorted(test)
    lo = max(min(v for v, _ in ref), min(v for v, _ in test))
    hi = min(max(v for v, _ in ref), max(v for v, _ in test))
    n_ref = sum(1 for v, _ in ref if lo <= v <= hi)
    n_test = sum(1 for v, _ in test if lo <= v <= hi)
    info = {"vmaf_interval": [round(lo, 3), round(hi, 3)], "points_in_interval": {"ref": n_ref, "test": n_test},
            "points_in_fit": {"ref": len(ref), "test": len(test)},
            "method": "PCHIP of log10(kbps) on VMAF, trapezoidal integration over 1,000 samples of the overlap "
                      "(draft-ietf-netvc-testing-09 sec. 4.2)"}
    if hi <= lo or n_ref < 3 or n_test < 3:
        return dict(info, bd_rate_pct=None, skipped="fewer than 3 points of each codec inside the overlapping VMAF range")
    d = pchip_mean(test, lo, hi) - pchip_mean(ref, lo, hi)
    fr = polyfit3([v for v, _ in ref], [math.log10(k) for _, k in ref])
    ft = polyfit3([v for v, _ in test], [math.log10(k) for _, k in test])
    dp = poly_mean(ft, lo, hi) - poly_mean(fr, lo, hi)
    return dict(info, bd_rate_pct=round(100 * (10 ** d - 1), 2),
                comparison_vceg_m33_cubic={"bd_rate_pct": round(100 * (10 ** dp - 1), 2),
                                           "cubic_monotonic": {"ref": poly_monotonic(fr, lo, hi),
                                                               "test": poly_monotonic(ft, lo, hi)},
                                           "note": "single least-squares cubic per codec (VCEG-M33 style); not used "
                                                   "for the headline when a fit is non-monotonic"})


def rate_at_vmaf(pts, target):
    pts = sorted(pts)
    for (v1, k1), (v2, k2) in zip(pts, pts[1:]):
        if v1 <= target <= v2 and v2 > v1:
            f = (target - v1) / (v2 - v1)
            return round(10 ** (math.log10(k1) + f * (math.log10(k2) - math.log10(k1))), 1)
    return None


def vmaf(enc: Path, src: Path, logp: Path, nframes: int):
    lav = (f"[0:v]setpts=PTS-STARTPTS[d];[1:v]setpts=PTS-STARTPTS[r];[d][r]libvmaf=model=version={VMAF_MODEL}:"
           f"feature=name=psnr:n_threads=2:shortest=1:log_fmt=json:log_path={logp}")
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", enc, "-i", src]
    _, wall, _ = run(cmd + ["-lavfi", lav, "-frames:v", str(nframes), "-f", "null", "-"])
    d = json.loads(logp.read_text())
    pm = d["pooled_metrics"]
    TOOLV["libvmaf"] = d.get("version")
    return {"vmaf_mean": round(pm["vmaf"]["mean"], 4), "vmaf_harmonic_mean": round(pm["vmaf"]["harmonic_mean"], 4),
            "vmaf_min": round(pm["vmaf"]["min"], 4), "psnr_y_mean": round(pm["psnr_y"]["mean"], 4),
            "frames_scored": len(d.get("frames", [])), "vmaf_wall_s": sig3(wall)}


def part_video():
    miss = missing_tools(FFMPEG, FFPROBE)
    if miss:
        return {"skipped": f"missing {miss}; run {SETUP} ffmpeg"}
    m = MEDIA_FILES["sintel_video"]
    src = m["path"]
    if not src.is_file():
        return {"skipped": f"{src} missing; run {SETUP} video"}
    if sha_file(src) != m["sha256"]:
        return {"skipped": f"{src} sha256 mismatch"}
    register_corpus("video_sintel_trailer_1080p_10s", None, m["url"], m["licence"], note=m["desc"],
                    nbytes=src.stat().st_size, digest=m["sha256"], path=src)
    W = fresh_dir(WORK / "video")
    nframes = 240 if not SMOKE else 24
    dur = nframes / 24
    encs = VIDEO_ENCODES if not SMOKE else [e for e in VIDEO_ENCODES if e[0] in ("x264_crf23", "x265_crf28",
                                                                                   "svtav1_p8_crf35")]
    rows = {}
    snap_a = contention_snapshot()
    for name, lib, args, core in encs:
        out = W / f"{name}.mp4"
        cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "info", "-y", "-i", src, "-frames:v", str(nframes),
               "-an", "-map_metadata", "-1", "-fflags", "+bitexact", "-c:v", lib, *args, "-pix_fmt", "yuv420p", out]
        p, wall, cpu = run(cmd)
        walls, cpus, shas = [wall], [cpu], [sha_file(out)]
        if name in VIDEO_TIMED_REPEATS and not SMOKE:
            for _ in range(2):
                _, w2, c2 = run(cmd)
                walls.append(w2)
                cpus.append(c2)
                shas.append(sha_file(out))
        blob = out.read_bytes()
        settings = {}
        if lib in ("libx264", "libx265"):
            if lib == "libx264":
                mm = re.search(rb"x264 - core (\d+)[^\x00]{0,20}", blob)
                TOOLV["x264"] = mm.group(0).decode("ascii", "replace").split(" - H.264")[0] if mm else None
            else:
                mm = re.search(rb"x265 \(build \d+\) - [^:]+", blob)
                TOOLV["x265"] = mm.group(0).decode("ascii", "replace") if mm else None
            so = re.search(rb"options: ([^\x00]+)", blob)          # the encoder's own settings string (version SEI)
            opts = dict(t.split("=", 1) for t in so.group(1).decode("ascii", "replace").split() if "=" in t) if so else {}
            settings = {k: opts.get(k) for k in ("crf", "rc", "keyint", "min-keyint", "bframes", "ref", "me", "subme",
                                                 "rd", "threads", "frame-threads", "input-csp") if k in opts}
            settings["source"] = "options string in the encoder's version SEI"
        else:
            mm = re.search(r"SVT-AV1 Encoder Lib (\S+)", p.stderr)
            TOOLV["svt_av1"] = mm.group(1) if mm else None
            for ln in p.stderr.splitlines():                    # "SVT [config]: a / b / c : x / y / z"
                if "SVT [config]:" in ln and ":" in ln.split("SVT [config]:", 1)[1]:
                    ks, vs = ln.split("SVT [config]:", 1)[1].rsplit(":", 1)
                    for k_, v_ in zip(ks.split("/"), vs.split("/")):
                        if k_.strip() in ("bit-depth", "color format", "preset", "tune", "pred struct", "gop size",
                                          "mini-gop size", "BRC mode", "rate factor"):
                            settings[k_.strip()] = v_.strip()
            settings["source"] = "SVT-AV1 '[config]' banner on stderr"
        pk = ffprobe_json(out, "-select_streams", "v:0", "-show_entries", "packet=size,flags")
        vbytes = sum(int(x["size"]) for x in pk["packets"])
        keyframes = sum(1 for x in pk["packets"] if "K" in x.get("flags", ""))
        st = ffprobe_json(out, "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=codec_name,profile,pix_fmt,width,height,nb_read_frames")["streams"][0]
        q = vmaf(out, src, W / f"{name}.vmaf.json", nframes)
        wmed = statistics.median(walls)
        rows[name] = {"encoder": lib, "args": " ".join(args), "core_crf_grid": core, "file_bytes": out.stat().st_size,
                      "video_stream_bytes": vbytes, "kbps": round(vbytes * 8 / dur / 1000, 1),
                      "container_overhead_bytes": out.stat().st_size - vbytes, "keyframes": keyframes, **q,
                      "encode_wall_s_median": sig3(wmed), "encode_cpu_s_median": sig3(statistics.median(cpus)),
                      "encode_fps": sig3(nframes / wmed), "encode_tier": tier_fps(nframes / wmed),
                      "encode_runs": len(walls), "deterministic_across_runs": len(set(shas)) == 1 if len(shas) > 1 else None,
                      "sha256": shas[0], "stream": st, "encoder_settings_reported": settings}
        log(f"  video {name}: {rows[name]['kbps']} kbps VMAF {q['vmaf_mean']} {nframes / wmed:.1f} fps")
    snap_b = contention_snapshot()
    # rate-quality curves; BD-rate, kbps_at_vmaf and single_points_vs_curves are derived from them in derive()
    curves = {}
    for fam, pref in (("x264", "x264_crf"), ("x265", "x265_crf"), ("svtav1_p8", "svtav1_p8_crf")):
        curves[fam] = sorted((rows[k]["vmaf_mean"], rows[k]["kbps"]) for k in rows if k.startswith(pref))
    # remux MP4 -> MKV: only the container changes
    remux = None
    x = W / "x264_crf23.mp4"
    if x.is_file():
        mkv = W / "x264_crf23.mkv"
        run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", x, "-map", "0", "-c", "copy", "-fflags", "+bitexact", mkv])

        def annexb(p):
            pr, _, _ = run([FFMPEG, "-nostdin", "-v", "error", "-i", p, "-map", "0:v", "-c", "copy", "-bsf:v",
                            "h264_mp4toannexb", "-f", "h264", "-"], stdout_bytes=True)
            return sha(pr.stdout), len(pr.stdout)
        a, b = annexb(x), annexb(mkv)
        mp4b = x.read_bytes()
        remux = {"mp4_bytes": len(mp4b), "mkv_bytes": mkv.stat().st_size,
                 "difference_bytes": mkv.stat().st_size - len(mp4b),
                 "h264_annexb_identical": a == b, "h264_annexb_bytes": a[1],
                 "general_purpose_on_mp4": {cid: {"bytes": len(CODECS[cid]["c"](mp4b)),
                                                  "saving_pct": saving(len(mp4b), len(CODECS[cid]["c"](mp4b)))}
                                            for cid in ("gzip_9", "zstd_19")}}
    return {"source": {"path": str(src), "url": m["url"], "licence": m["licence"], "desc": m["desc"],
                       "frames": nframes, "duration_s": dur, "width": 1920, "height": 1080, "pix_fmt": "yuv420p",
                       "fps": 24, "resolution_note": "1080p (no downscale); VMAF computed at 1080p against the same Y4M"},
            "encodes": rows, "curves_vmaf_kbps": curves, "remux": remux,
            "vmaf": {"model": VMAF_MODEL, "n_threads": 2, "pooling": "mean (harmonic mean and min also recorded)",
                     "filter": "FFmpeg libvmaf, distorted first, reference second, setpts aligned, shortest=1"},
            "timing_contention": contention_delta(snap_a, snap_b, "encoders use FFmpeg/encoder default threading on the "
                                                                  "2-CPU cgroup; wall time tiers, CPU seconds recorded"),
            "method": "Each encode: FFmpeg reads the 240-frame Y4M and writes MP4 (-an, -map_metadata -1, -fflags "
                      "+bitexact, -pix_fmt yuv420p), encoder defaults otherwise (GOP, threads, tune). kbps = video packet "
                      "bytes * 8 / 10 s. core_crf_grid marks the settings named in the brief; the others (x264 CRF 33, "
                      "x265 CRF 36, SVT-AV1 CRF 55) were added so each curve has 4 points. BD-rate (derived from "
                      "curves_vmaf_kbps): draft-ietf-netvc-testing-09 sec. 4.2 -- log10(kbps) against VMAF (mean), a "
                      "piecewise cubic Hermite interpolating polynomial through each codec's 4 points, integrated over "
                      "the overlapping VMAF interval with 1,000 samples and the trapezoidal rule; reported only when at "
                      "least 3 points of each codec lie inside that interval. The classic VCEG-M33 single cubic is "
                      "recorded beside it (comparison_vceg_m33_cubic) with a monotonicity flag: on this clip the x264 "
                      "cubic bends backwards between VMAF 87 and 93 and overstates the savings. kbps_at_vmaf: log-linear "
                      "interpolation between neighbouring points. encoder_settings_reported: what each encoder says it "
                      "used (x264/x265 SEI options; SVT-AV1 banner). GOPs are encoder defaults and differ: x264/x265 "
                      "keyint 250 (one GOP plus scene cuts in 240 frames), SVT-AV1 gop size 161 (a second keyframe). "
                      "Encode time: one run each; x264 CRF 23, x265 CRF 28 and SVT-AV1 P8 CRF 35 three runs (median) "
                      "with a byte-identity check across runs.",
            "not_measured": {"vp9_libvpx": "not run (time budget on 2 shared CPUs; the brief says 'if time allows')",
                             "libaom_rav1e_vvenc": "not run (one AV1 encoder, SVT-AV1, covers AV1)",
                             "10bit_encodes": "not run; the 10-bit cost for 8-bit sources is a sourced claim (SVT-AV1 docs)",
                             "vmaf_v1_or_neg_models": f"not run; only {VMAF_MODEL}, FFmpeg's libvmaf default"}}


# ----------------------------------------------------------------------------------------------------------
# recompress
# ----------------------------------------------------------------------------------------------------------
RECOMP_CODECS = ["gzip_9", "zstd_19", "xz_9", "brotli_11"]
STD_DHT_LENGTHS = {29, 179}       # ITU T.81 Annex K example tables: DC 12 symbols (29 B), AC 162 symbols (179 B)


def jpeg_info(b: bytes):
    """Marker walk up to the first SOS: SOF type, Huffman tables (standard Annex K or custom), restart interval and
    APPn bytes. Explains why a general-purpose codec can still shrink some JPEGs."""
    i, out = 2, {"sof": None, "dht_tables": 0, "dht_all_annex_k_sizes": True, "restart_interval": 0, "app_bytes": 0}
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xDA:
            out["entropy_coded_bytes_from_sos"] = len(b) - i
            break
        n = int.from_bytes(b[i + 2:i + 4], "big")
        seg = b[i + 4:i + 2 + n]
        if m in (0xC0, 0xC1, 0xC2):
            out["sof"] = {0xC0: "baseline", 0xC1: "extended", 0xC2: "progressive"}[m]
        elif m == 0xC4:
            j = 0
            while j < len(seg):
                cnt = sum(seg[j + 1:j + 17])
                out["dht_tables"] += 1
                out["dht_all_annex_k_sizes"] &= (17 + cnt) in STD_DHT_LENGTHS
                j += 17 + cnt
        elif m == 0xDD:
            out["restart_interval"] = int.from_bytes(seg[:2], "big")
        elif 0xE0 <= m <= 0xEF:
            out["app_bytes"] += n + 2
        i += 2 + n
    return out


def det_tar(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0, 0o644, 0, 0, "", ""
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def det_zip(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data, compresslevel=6)
    return buf.getvalue()


def part_recompress(numbers):
    from PIL import Image
    inputs = {}
    imgw, audw, vidw = WORK / "images", WORK / "audio", WORK / "video"
    k5 = MEDIA_FILES["kodim05"]["path"]
    if k5.is_file():
        p = imgw / "kodim05_q90.jpg"
        inputs["jpeg_pillow_q90_kodim05"] = p.read_bytes() if p.is_file() else \
            pil_bytes(Image.open(k5).convert("RGB"), format="JPEG", quality=90, optimize=True)
        inputs["png_kodim05_as_distributed"] = k5.read_bytes()
    if FIRST_PARTY_JPEGS["og.jpg"].is_file():
        inputs["jpeg_writings_og"] = FIRST_PARTY_JPEGS["og.jpg"].read_bytes()
    if FIRST_PARTY_IMAGES["xo_space_dashboard"]["path"].is_file():
        inputs["png_xo_space_screenshot"] = FIRST_PARTY_IMAGES["xo_space_dashboard"]["path"].read_bytes()
    for k, p in (("mp4_h264_x264_crf23", vidw / "x264_crf23.mp4"), ("mp4_av1_svtav1_p8_crf35", vidw / "svtav1_p8_crf35.mp4"),
                 ("opus_96k", audw / "opus_96k.opus"), ("flac_8", audw / "flac_8.flac"),
                 ("aac_128k_m4a", audw / "aac_128k.m4a")):
        if p.is_file():
            inputs[k] = p.read_bytes()
    text_members = []
    for name, p in (("posts.json", WRITINGS / "posts.json"),
                    ("parser_hears_numbers.json", WRITINGS / "what-the-parser-hears" / "_numbers.json")):
        if p.is_file():
            text_members.append((name, p.read_bytes()))
    text_members.append(("api_records.min.json", dumps_min(api_records(API_N if not SMOKE else 400))))
    acc2 = access_log(2_000_000 if not SMOKE else 200_000, seed=20261014)
    register_corpus("access_log_archive_member", acc2, "generated by access_log(2_000_000, seed=20261014) in _compute.py",
                    "synthetic (this harness)", note="the access.log member of recompress's .zip and .tar.gz")
    text_members.append(("access.log", acc2))
    raw_tar = det_tar(text_members)
    inputs["zip_deflate6_text"] = det_zip(text_members)
    inputs["tar_gz6_text"] = gz(raw_tar, 6)
    rows = {}
    for k, data in inputs.items():
        r_ = {"bytes": len(data)}
        if k.startswith("jpeg"):
            r_["jpeg_structure"] = jpeg_info(data)
        for cid in RECOMP_CODECS:
            cb = CODECS[cid]["c"](data)
            r_[cid] = {"bytes": len(cb), "saving_pct": saving(len(data), len(cb)), "delta_bytes": len(cb) - len(data)}
        rows[k] = r_
        log(f"  recompress {k}: " + ", ".join(f"{c} {r_[c]['saving_pct']}%" for c in RECOMP_CODECS))
    mixed_names = [k for k in ("jpeg_pillow_q90_kodim05", "png_kodim05_as_distributed", "mp4_h264_x264_crf23",
                               "opus_96k", "flac_8") if k in inputs]
    mixed = det_tar([(k, inputs[k]) for k in mixed_names])
    mixed_row = {"members": mixed_names, "tar_bytes": len(mixed)}
    for cid in ("zstd_19", "xz_9"):
        cb = CODECS[cid]["c"](mixed)
        mixed_row[cid] = {"bytes": len(cb), "saving_pct": saving(len(mixed), len(cb))}
    # exceptions: re-doing the entropy coding
    exc = {}
    imgs = numbers.get("images") or {}
    if "lossless" in imgs:
        for k in ("kodim05", "xo_space_dashboard"):
            if k in imgs["lossless"]:
                L = imgs["lossless"][k]
                exc[f"oxipng_o4_{k}"] = {"png_bytes": L["png_as_is"], "after": L["oxipng_o4"]["bytes"],
                                         "saving_pct": saving(L["png_as_is"], L["oxipng_o4"]["bytes"]),
                                         "from": f"images.lossless.{k}.oxipng_o4"}
                exc[f"jxl_lossless_e9_{k}"] = {"png_bytes": L["png_as_is"], "after": L["jxl_lossless_e9"]["bytes"],
                                               "saving_pct": saving(L["png_as_is"], L["jxl_lossless_e9"]["bytes"]),
                                               "from": f"images.lossless.{k}.jxl_lossless_e9"}
    if "jpeg_to_jxl_lossless" in imgs:
        for k, v in imgs["jpeg_to_jxl_lossless"].items():
            if k in ("writings_og", "kodim05_pillow_q90"):
                exc[f"jpeg_to_jxl_{k}"] = {"jpeg_bytes": v["jpeg_bytes"], "after": v["jxl_bytes"],
                                           "saving_pct": v["saving_pct"], "bit_exact": v["bit_exact_reconstruction"],
                                           "from": f"images.jpeg_to_jxl_lossless.{k}"}
    zb = inputs["zip_deflate6_text"]
    with zipfile.ZipFile(io.BytesIO(zb)) as zf:
        members = [(n, zf.read(n)) for n in zf.namelist()]
    t = det_tar(members)
    for cid in ("zstd_19", "xz_9"):
        cb = CODECS[cid]["c"](t)
        exc[f"zip_repacked_tar_{cid}"] = {"zip_bytes": len(zb), "after": len(cb), "saving_pct": saving(len(zb), len(cb))}
    tg = inputs["tar_gz6_text"]
    for cid in ("zstd_19", "xz_9"):
        cb = CODECS[cid]["c"](gzip.decompress(tg))
        exc[f"tar_gz_to_tar_{cid}"] = {"tar_gz_bytes": len(tg), "after": len(cb), "saving_pct": saving(len(tg), len(cb))}
    media_keys = [k for k in rows if not k.startswith(("zip_", "tar_"))]
    worst = {cid: [min(rows[k][cid]["saving_pct"] for k in media_keys), max(rows[k][cid]["saving_pct"] for k in media_keys)]
             for cid in RECOMP_CODECS} if media_keys else {}
    return {"rows": rows, "media_saving_pct_range": worst, "mixed_media_tar": mixed_row, "exceptions": exc,
            "text_archive_members": [{"name": n, "bytes": len(b), "sha256": sha(b)} for n, b in text_members],
            "method": "Each file (from the images/audio/video keys' outputs, or the inputs named) is compressed whole with "
                      "gzip -9 (mtime 0), zstd 19, xz -9 and brotli 11; saving_pct = 100*(original-compressed)/original "
                      "(negative = it grew). The .zip (DEFLATE level 6, fixed dates) and .tar.gz (USTAR, mtime 0, "
                      "gzip -6) hold the same text files. Exceptions re-do the entropy coding instead of wrapping it: "
                      "oxipng and JPEG XL lossless on PNG, JPEG XL lossless transcoding of JPEG, ZIP and tar.gz repacked "
                      "with a stronger codec."}


# ----------------------------------------------------------------------------------------------------------
# derived views (pure functions of the stored numbers; recomputed on every invocation)
# ----------------------------------------------------------------------------------------------------------
def derive(N):
    v = N.get("video")
    if isinstance(v, dict) and "encodes" in v:
        curves = {f: sorted(tuple(x) for x in pts) for f, pts in v["curves_vmaf_kbps"].items()}
        bd = {}
        if all(len(curves.get(f, [])) >= 3 for f in ("x264", "x265", "svtav1_p8")):
            bd = {"x265_vs_x264": bd_rate(curves["x264"], curves["x265"]),
                  "svtav1_p8_vs_x264": bd_rate(curves["x264"], curves["svtav1_p8"]),
                  "svtav1_p8_vs_x265": bd_rate(curves["x265"], curves["svtav1_p8"])}
        v["bd_rate"] = bd
        matched = {}
        for tgt in (90, 93, 95):
            row = {f: rate_at_vmaf(curves[f], tgt) for f in curves}
            if row.get("x264"):
                row["vs_x264_pct"] = {f: round(100 * (row[f] / row["x264"] - 1), 1) for f in curves if row.get(f)}
            matched[str(tgt)] = row
        v["kbps_at_vmaf"] = matched
        single = {}
        for name in ("svtav1_p4_crf35", "svtav1_p10_crf35"):
            e = v["encodes"].get(name)
            if not e:
                continue
            row = {"vmaf_mean": e["vmaf_mean"], "kbps": e["kbps"], "encode_fps": e["encode_fps"]}
            for f in curves:
                k = rate_at_vmaf(curves[f], e["vmaf_mean"])
                row[f"{f}_kbps_at_same_vmaf"] = k
                row[f"vs_{f}_pct"] = round(100 * (e["kbps"] / k - 1), 1) if k else None
            single[name] = row
        v["single_points_vs_curves"] = dict(single, method="the point's kbps against each preset-curve's kbps at "
                                                           "the same VMAF (log-linear interpolation between its "
                                                           "neighbouring CRF points)")
    im = N.get("images")
    if isinstance(im, dict) and "lossy_photos" in im:
        im["max_ssimulacra2_reached"] = {k: {c: max(p["ssimulacra2"] for p in pts) for c, pts in s_["codecs"].items()}
                                         for k, s_ in im["lossy_photos"].items()}


# ----------------------------------------------------------------------------------------------------------
# headline
# ----------------------------------------------------------------------------------------------------------
def part_headline(N):
    tiles = []

    def ok(k):
        return isinstance(N.get(k), dict) and "skipped" not in N[k] and "error" not in N[k]
    if ok("json"):
        rr = N["json"]["ratios"]["api_records"]["minified"]
        best = max(rr, key=lambda c: rr[c]["ratio"])
        tiles.append({"type": "JSON at rest", "value": rr["zstd_3"]["ratio"], "unit": "x", "codec": "zstd 3",
                      "detail": f"best measured {rr[best]['ratio']}x ({CODECS[best]['label']}); gzip -6 "
                                f"{rr['gzip_6']['ratio']}x; brotli 11 {rr['brotli_11']['ratio']}x",
                      "path": "json.ratios.api_records.minified"})
    if ok("small"):
        s = N["small"]["per_document_test_split"]
        tiles.append({"type": "Small JSON messages", "value": s["zstd_3_dict110k"]["ratio_total"], "unit": "x",
                      "codec": "zstd 3 + 110 KB trained dictionary",
                      "detail": f"vs {s['zstd_3']['ratio_total']}x without a dictionary; gzip -6 "
                                f"{s['gzip_6']['ratio_total']}x; {s['gzip_6']['docs_grew_pct']}% of messages grew under gzip",
                      "path": "small.per_document_test_split"})
    if ok("binary"):
        b = N["binary"]["rows"]
        tiles.append({"type": "Binary encodings", "value": b["msgpack"]["vs_json_minified_pct"]["zstd_3"], "unit": "% vs JSON",
                      "codec": "MessagePack + zstd 3 vs minified JSON + zstd 3",
                      "detail": f"raw MessagePack {b['msgpack']['vs_json_minified_pct']['raw']}% vs raw minified JSON; "
                                f"Protobuf + zstd 3 {b['protobuf']['vs_json_minified_pct']['zstd_3']}%",
                      "path": "binary.rows"})
    if ok("config"):
        c = N["config"]["summary"]["config"]
        tiles.append({"type": "Config files", "value": c["gzip_9"]["grew"], "unit": f"of {c['files']} grew",
                      "codec": "gzip -9, each file alone",
                      "detail": f"median ratio gzip -9 {c['gzip_9']['ratio_median']}x, zstd 19 {c['zstd_19']['ratio_median']}x",
                      "path": "config.summary.config"})
    if ok("logs"):
        lg = N["logs"]["blocks"]
        key = "doomfly_audit_jsonl" if "doomfly_audit_jsonl" in lg else "access_log"
        z = lg[key]["zstd_3"]
        tiles.append({"type": "Logs (JSONL)", "value": z[str(1 << 20)]["ratio"] if str(1 << 20) in z else z["whole"]["ratio"],
                      "unit": "x", "codec": "zstd 3 in 1 MiB blocks",
                      "detail": f"{z['1024']['ratio']}x in 1 KiB blocks; {z['whole']['ratio']}x as one frame",
                      "path": f"logs.blocks.{key}.zstd_3"})
    if ok("tables"):
        f = N["tables"]["files"]
        tiles.append({"type": "Tables", "value": f["parquet_zstd3_dict"]["vs_csv_gzip_6_x"], "unit": "x smaller than CSV.gz",
                      "codec": "Parquet, dictionary + zstd 3",
                      "detail": f"CSV {f['csv']['bytes']:,} B, CSV.gz {f['csv_gzip_6']['bytes']:,} B, Parquet zstd 3 "
                                f"{f['parquet_zstd3_dict']['bytes']:,} B",
                      "path": "tables.files"})
    if ok("images"):
        t = N["images"]["lossy_totals_at_ssimulacra2"].get("80", {})
        if t.get("vs_jpeg_420_pct"):
            bestc = min(t["vs_jpeg_420_pct"], key=lambda c: t["vs_jpeg_420_pct"][c])
            tiles.append({"type": "Photos", "value": t["vs_jpeg_420_pct"][bestc], "unit": "% bytes vs JPEG",
                          "codec": f"{bestc} at SSIMULACRA 2 = 80",
                          "detail": ", ".join(f"{c} {v}%" for c, v in t["vs_jpeg_420_pct"].items()),
                          "path": "images.lossy_totals_at_ssimulacra2.80"})
    if ok("audio"):
        a = N["audio"]["rows"]
        tiles.append({"type": "Audio", "value": a["opus_96k"]["ratio_vs_wav"], "unit": "x smaller than WAV",
                      "codec": "Opus 96 kb/s",
                      "detail": f"FLAC -8 {a['flac_8']['ratio_vs_wav']}x (lossless)", "path": "audio.rows"})
    if ok("video"):
        v = N["video"]
        bdv = (v.get("bd_rate") or {}).get("svtav1_p8_vs_x264", {})
        tiles.append({"type": "Video", "value": bdv.get("bd_rate_pct"), "unit": "% BD-rate vs x264",
                      "codec": "SVT-AV1 preset 8",
                      "detail": f"x265 vs x264 {(v.get('bd_rate') or {}).get('x265_vs_x264', {}).get('bd_rate_pct')}%; "
                                f"VMAF {VMAF_MODEL}; PCHIP BD-rate (draft-ietf-netvc-testing-09 sec. 4.2)",
                      "path": "video.bd_rate"})
    if ok("recompress"):
        rg = N["recompress"]["media_saving_pct_range"]
        tiles.append({"type": "Already compressed", "value": max(abs(x) for v in rg.values() for x in v), "unit": "% max |saving|",
                      "codec": "gzip -9 / zstd 19 / xz -9 / brotli 11 on JPEG, PNG, MP4, Opus, FLAC, AAC",
                      "detail": "; ".join(f"{c} {v[0]}..{v[1]}%" for c, v in rg.items()),
                      "path": "recompress.media_saving_pct_range"})
    return {"tiles": tiles, "method": "One headline per data type, computed from the other keys; 'path' points to the "
                                      "source numbers."}


# ----------------------------------------------------------------------------------------------------------
# versions and machine
# ----------------------------------------------------------------------------------------------------------
def sh(cmd):
    try:
        return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def lib_version_c(soname, fn):
    import ctypes
    try:
        f = getattr(ctypes.CDLL(soname), fn)
        f.restype = ctypes.c_char_p
        return f().decode()
    except (OSError, AttributeError):
        return None


def versions_block():
    import importlib.metadata as md
    pkgs = {}
    for name in ("brotli", "lz4", "zlib-ng", "deflate", "pyarrow", "cbor2", "msgpack", "pymongo", "protobuf", "fastavro",
                 "pillow", "dnspython"):
        try:
            pkgs[name] = md.version(name)
        except md.PackageNotFoundError:
            pkgs[name] = None
    out = {"python": platform.python_version(), "python_executable": os.path.realpath(sys.executable),
           "uv": sh(["uv", "--version"]), "packages": pkgs,
           "libraries": {"libzstd (compression.zstd)": zstd.zstd_version, "zlib_compiled": zlib.ZLIB_VERSION,
                         "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
                         "liblzma": lib_version_c("liblzma.so.5", "lzma_version_string"),
                         "brotli_wheel": brotli.__version__, "lz4_library": lz4.library_version_string(),
                         "zlib_ng": getattr(zlib_ng, "ZLIBNG_VERSION", None),
                         "libdeflate": "bundled in the deflate 0.9.0 wheel (the binding does not expose its version)"}}
    try:
        import pyarrow as pa
        out["libraries"]["arrow_cpp"] = pa.cpp_build_info.version
        out["libraries"]["arrow_codecs_available"] = [c for c in ("snappy", "gzip", "brotli", "zstd", "lz4", "lz4_raw")
                                                      if pa.Codec.is_available(c)]
    except Exception:  # noqa: BLE001
        pass
    try:
        from google.protobuf.internal import api_implementation
        out["libraries"]["protobuf_backend"] = api_implementation.Type()
        import bson
        out["libraries"]["bson_c_extension"] = bson.has_c()
    except Exception:  # noqa: BLE001
        pass
    if "pillow_codecs" not in TOOLV:
        try:
            from PIL import _avif, features
            TOOLV["pillow_codecs"] = {"libjpeg_turbo": features.version("libjpeg_turbo"),
                                      "libwebp": features.version("webp"), "libavif": features.version("avif"),
                                      "avif_codecs": _avif.codec_versions(), "zlib_in_pillow": features.version("zlib"),
                                      "zlib_ng_in_pillow": features.version("zlib_ng")}
        except Exception:  # noqa: BLE001
            pass
    out["libraries"]["pillow"] = TOOLV.get("pillow_codecs")
    bins = {}
    for name, p, vcmd in (("ffmpeg", FFMPEG, [FFMPEG, "-hide_banner", "-version"]),
                          ("ffprobe", FFPROBE, [FFPROBE, "-hide_banner", "-version"]),
                          ("cjxl", CJXL, [CJXL, "--version"]), ("djxl", DJXL, [DJXL, "--version"]),
                          ("ssimulacra2", SSIMULACRA2, None), ("oxipng", OXIPNG, [OXIPNG, "--version"])):
        if Path(p).is_file():
            v = sh(vcmd).splitlines()[0] if vcmd and sh(vcmd) else None
            bins[name] = {"path": str(p), "sha256": sha_file(Path(p)), "version": v}
        else:
            bins[name] = {"path": str(p), "present": False}
    if bins.get("ssimulacra2", {}).get("sha256") and bins.get("cjxl", {}).get("version"):
        bins["ssimulacra2"]["version"] = ("no version flag; shipped in the same libjxl static tarball as cjxl ("
                                          + bins["cjxl"]["version"] + ")")
    if FFMPEG.is_file():
        conf = sh([FFMPEG, "-hide_banner", "-buildconf"]) or ""
        bins["ffmpeg"]["enabled_libraries"] = sorted(set(re.findall(r"--enable-(lib[a-z0-9_]+)", conf)))
    out["binaries"] = bins
    out["encoders_reported"] = {
        "x264": TOOLV.get("x264"), "x265": TOOLV.get("x265"), "svt_av1": TOOLV.get("svt_av1"),
        "libvmaf": TOOLV.get("libvmaf"),
        "libopus": "unknown: this FFmpeg build embeds the string 'libopus unknown' (BtbN builds libopus from git)",
        "libmp3lame": "LAME bundled in the FFmpeg static build (version string not exposed)",
        "source": "x264/x265 from the version SEI each writes into its bitstream; SVT-AV1 from its log banner; libvmaf "
                  "from its JSON log"}
    dls = {}
    for name, (url, path, exp, src) in DOWNLOADS.items():
        dls[name] = {"url": url, "path": str(path), "expected_sha256": exp, "checksum_source": src,
                     "sha256": sha_file(path) if path.is_file() else None,
                     "verified": (sha_file(path) == exp) if path.is_file() else None}
    out["downloads"] = dls
    return out


def machine_info():
    cpu = None
    for ln in Path("/proc/cpuinfo").read_text().splitlines():
        if ln.startswith("model name"):
            cpu = ln.split(":", 1)[1].strip()
            break
    return {
        "date_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "os": sh(["sh", "-c", ". /etc/os-release && echo $PRETTY_NAME"]), "kernel": platform.release(),
        "arch": platform.machine(), "cpu": cpu, "cpus_host": os.cpu_count(),
        "cpus_affinity": len(os.sched_getaffinity(0)),
        "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip() if Path("/sys/fs/cgroup/cpu.max").exists() else None,
        "mem_total": Path("/proc/meminfo").read_text().splitlines()[0].split(":")[1].strip(),
        "python": platform.python_version(),
    }


# ----------------------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------------------
PARTS = {"json": part_json, "small": part_small, "binary": part_binary, "config": part_config, "logs": part_logs,
         "tables": part_tables, "images": part_images, "audio": part_audio, "video": part_video}


def main(argv):
    global SMOKE
    SMOKE = "--smoke" in argv
    out_json = OUT_JSON if not SMOKE else WORK / "_numbers.smoke.json"
    WORK.mkdir(parents=True, exist_ok=True)
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
        bad = set(only) - set(ALL_KEYS)
        if bad:
            sys.exit(f"unknown keys: {sorted(bad)}")
    keys = [k for k in ALL_KEYS if only is None or k in only]
    numbers = {}
    if only and out_json.exists():
        numbers = json.loads(out_json.read_text())
        for name, c in numbers.get("corpora", {}).items():
            CORPORA[name] = c
        TOOLV.update({k: v for k, v in (numbers.get("versions", {}).get("encoders_reported") or {}).items()
                      if k in ("x264", "x265", "svt_av1", "libvmaf") and v})
        if numbers.get("versions", {}).get("libraries", {}).get("pillow"):
            TOOLV["pillow_codecs"] = numbers["versions"]["libraries"]["pillow"]
    t_start = time.monotonic()
    snap0 = contention_snapshot()
    phase = numbers.get("phase_seconds", {})
    runs = numbers.get("key_runs", {})
    for k in keys:
        log(f"{k} ...")
        t0 = time.monotonic()
        try:
            if k == "recompress":
                numbers[k] = part_recompress(numbers)
            elif k == "headline":
                derive(numbers)
                numbers[k] = part_headline(numbers)
            else:
                numbers[k] = PARTS[k]()
        except Exception as e:  # noqa: BLE001
            numbers[k] = {"error": f"{type(e).__name__}: {e}"}
            log(f"{k} FAILED:\n{traceback.format_exc()}")
        phase[k] = round(time.monotonic() - t0, 1)
        runs[k] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log(f"{k} done in {phase[k]:.0f} s")
    derive(numbers)
    snap1 = contention_snapshot()
    prev_machine = numbers.get("machine") or {}
    numbers["machine"] = machine_info()
    numbers["machine"]["run_contention"] = contention_delta(
        snap0, snap1, "whole run" if only is None else
        f"partial invocation (--only {','.join(keys)}); other keys keep the numbers of the runs in key_runs")
    if only is not None:                  # keep the record of the last complete run
        full = prev_machine.get("full_run")
        if full is None and (prev_machine.get("run_contention") or {}).get("note") == "whole run":
            full = {"date_utc": prev_machine.get("date_utc"), "run_contention": prev_machine["run_contention"]}
        if full:
            numbers["machine"]["full_run"] = full
    else:
        numbers["machine"]["full_run"] = {"date_utc": numbers["machine"]["date_utc"],
                                          "run_contention": numbers["machine"]["run_contention"]}
    numbers["versions"] = versions_block()
    numbers["machine"]["versions"] = {
        "full_record": "the top-level 'versions' key: every library and package version, binary paths and SHA-256s, "
                       "download URLs and checksums",
        "python": numbers["versions"]["python"], "libzstd": zstd.zstd_version,
        "ffmpeg": (numbers["versions"]["binaries"].get("ffmpeg") or {}).get("version"),
        "x264": TOOLV.get("x264"), "x265": TOOLV.get("x265"), "svt_av1": TOOLV.get("svt_av1"),
        "libvmaf": TOOLV.get("libvmaf"), "cjxl": (numbers["versions"]["binaries"].get("cjxl") or {}).get("version"),
        "oxipng": (numbers["versions"]["binaries"].get("oxipng") or {}).get("version"),
        "packages": numbers["versions"]["packages"]}
    numbers["corpora"] = dict(sorted(CORPORA.items()))
    numbers["method"] = {
        "harness": "_compute.py (PEP 723; uv run) on Python " + platform.python_version() + ": stdlib zlib, lzma, "
                   "compression.zstd; pinned wheels (see versions.packages); static binaries under " + str(BIN) +
                   " (FFmpeg n9.0.2 BtbN GPL build, libjxl 0.12.0 tools, oxipng 10.2.1), fetched and checked by " +
                   str(SETUP),
        "exactness": __doc__.split("Exactness.")[1].split("MB = ")[0].strip().replace("\n", " "),
        "units": "MB = 10^6 bytes; ratio = original / compressed; saving_pct = 100 * (original - compressed) / original",
        "private_data": "none read (no ~/.claude or ~/.quirq file is opened); the doomfly audit log is used for sizes "
                        "and ratios only",
        "heavy_artefacts": f"{BENCH} (outside the publication): media in {MEDIA}, encodes and scratch in {WORK}",
        "smoke": SMOKE,
    }
    numbers["phase_seconds"] = phase
    numbers["key_runs"] = runs
    numbers["runtime_seconds_this_invocation"] = round(time.monotonic() - t_start)
    ordered = {k: numbers[k] for k in ["method", "machine", "versions", "corpora", "key_runs", "phase_seconds",
                                       "runtime_seconds_this_invocation"] + ALL_KEYS if k in numbers}
    out_json.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n")
    log(f"wrote {out_json} ({out_json.stat().st_size:,} B) in {ordered['runtime_seconds_this_invocation']} s")


if __name__ == "__main__":
    main(sys.argv[1:])
