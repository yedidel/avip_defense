"""Shared helpers for the binding scripts: data location, trace access, statistics, output checks.

Every script that reads released data takes --data <path to data/live_hp in the DATA repository>
(or the LIVE_HP_DATA environment variable). The binding data is under <data>/binding/; the
cross-seller, main and held-out inputs it reuses are under <data>/cross_seller/, <data>/main/ and
<data>/heldout/. Traces are read from <folder>/traces/ if that folder exists (an extracted
traces.zip), otherwise directly from <folder>/traces.zip.

Scripts write only to --out (default: binding/_out/), never into the data folder. Where a released
file exists for an output, the script compares its own output with it and prints the result.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

BINDING = Path(__file__).resolve().parent
REPO = BINDING.parent
DEFAULT_OUT = BINDING / "_out"


def parse_args(doc: str | None = None, extra=None, need_data: bool = True):
  """Common arguments: --data, --out, plus `extra` = [((flags...), {kwargs}), ...]."""
  ap = argparse.ArgumentParser(description=(doc or "").strip().split("\n")[0] or None)
  ap.add_argument("--data", default=os.environ.get("LIVE_HP_DATA"),
                  help="path to data/live_hp in the DATA repository (or set LIVE_HP_DATA)")
  ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory (default: binding/_out)")
  for flags, kw in (extra or []):
    ap.add_argument(*flags, **kw)
  a = ap.parse_args()
  if need_data:
    if not a.data:
      ap.error("--data (or LIVE_HP_DATA) is required")
    root = Path(a.data)
    if not (root / "binding").is_dir() or not (root / "cross_seller").is_dir():
      sys.exit(f"{root} does not look like data/live_hp (needs binding/ and cross_seller/)")
    a.data = root
  a.out = Path(a.out)
  a.out.mkdir(parents=True, exist_ok=True)
  return a


def load_json(p):
  return json.load(open(p, encoding="utf-8"))


def iter_jsonl(p):
  for line in open(p, encoding="utf-8"):
    if line.strip():
      yield json.loads(line)


def trace_files(folder: Path):
  """Yield (uid, raw bytes) for every trace of one folder, in uid order."""
  d = Path(folder) / "traces"
  if d.is_dir():
    for f in sorted(glob.glob(str(d / "*.json"))):
      yield Path(f).stem, open(f, "rb").read()
    return
  with zipfile.ZipFile(Path(folder) / "traces.zip") as z:
    for n in sorted(z.namelist()):
      if n.endswith(".json"):
        yield Path(n).stem, z.read(n)


def iter_traces(folder: Path):
  """Yield every trace dict of one folder, in uid order."""
  for _, b in trace_files(folder):
    yield json.loads(b.decode("utf-8"))


def wilson(k, n, z=1.96):
  if n == 0:
    return None
  p = k / n
  d = 1 + z * z / n
  c = (p + z * z / (2 * n)) / d
  h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
  return [round(c - h, 4), round(c + h, 4)]


def rate(k, n):
  return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def sha_obj(obj) -> str:
  """Hash convention of the frozen inputs: sha256(json.dumps(obj, sort_keys=True)), UTF-8."""
  return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def write_json(path: Path, obj, indent=1):
  Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def same_json(mine: Path, released: Path) -> None:
  """Print whether two JSON (or JSONL) files hold equal data."""
  def load(p):
    if str(p).endswith(".jsonl"):
      return list(iter_jsonl(p))
    return load_json(p)
  if not Path(released).exists():
    print(f"[check] {released} not found; nothing to compare")
    return
  print(f"[check] {Path(mine).name} equal (as JSON) to released {released}: {load(mine) == load(released)}")


def same_text(mine: Path, released: Path) -> None:
  """Print whether two text files are equal up to line endings."""
  if not Path(released).exists():
    print(f"[check] {released} not found; nothing to compare")
    return
  a = Path(mine).read_bytes().replace(b"\r\n", b"\n")
  b = Path(released).read_bytes().replace(b"\r\n", b"\n")
  print(f"[check] {Path(mine).name} equal (text) to released {released}: {a == b}")


def same_bytes(mine: Path, released: Path) -> None:
  """Print whether two files are byte-identical, with both SHA-256 digests."""
  if not Path(released).exists():
    print(f"[check] {released} not found; nothing to compare")
    return
  a, b = Path(mine).read_bytes(), Path(released).read_bytes()
  print(f"[check] {Path(mine).name} byte-identical to released {released}: {a == b} "
        f"(sha256 {hashlib.sha256(a).hexdigest()[:16]}... vs {hashlib.sha256(b).hexdigest()[:16]}...)")
