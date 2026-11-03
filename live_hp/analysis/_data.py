"""Access to the released live-flow data (data/live_hp in the DATA repository).

Every analysis script takes --data <path to data/live_hp> (or the LIVE_HP_DATA
environment variable). Traces are read from <experiment>/traces/ if that folder
exists (an extracted traces.zip), otherwise directly from <experiment>/traces.zip.
"""
import argparse
import glob
import json
import os
import sys
import zipfile
from pathlib import Path


def data_root(argv=None, extra=None) -> tuple[Path, argparse.Namespace]:
  ap = argparse.ArgumentParser()
  ap.add_argument("--data", default=os.environ.get("LIVE_HP_DATA"),
                  help="path to data/live_hp in the DATA repository (or set LIVE_HP_DATA)")
  for args, kw in (extra or []):
    ap.add_argument(*args, **kw)
  a = ap.parse_args(argv)
  if not a.data:
    ap.error("--data (or LIVE_HP_DATA) is required")
  root = Path(a.data)
  if not (root / "main").is_dir():
    sys.exit(f"{root} does not look like data/live_hp (no main/ folder)")
  return root, a


def iter_traces(exp_dir: Path):
  """Yield every trace dict of one experiment."""
  d = exp_dir / "traces"
  if d.is_dir():
    for f in glob.glob(str(d / "*.json")):
      yield json.load(open(f, encoding="utf-8"))
    return
  with zipfile.ZipFile(exp_dir / "traces.zip") as z:
    for n in z.namelist():
      if n.endswith(".json"):
        yield json.loads(z.read(n).decode("utf-8"))


class TraceStore:
  """Random access to traces by uid."""

  def __init__(self, exp_dir: Path):
    self.dir = exp_dir / "traces"
    self.zip = None if self.dir.is_dir() else zipfile.ZipFile(exp_dir / "traces.zip")

  def get(self, uid: str) -> dict:
    if self.zip is None:
      return json.load(open(self.dir / f"{uid}.json", encoding="utf-8"))
    return json.loads(self.zip.read(f"traces/{uid}.json").decode("utf-8"))

  def uids(self) -> list[str]:
    if self.zip is None:
      return sorted(Path(f).stem for f in glob.glob(str(self.dir / "*.json")))
    return sorted(Path(n).stem for n in self.zip.namelist() if n.endswith(".json"))
