"""Locations used by the reading scripts.

Released data: data/live_hp of the DATA repository, given as --data <path> or the LIVE_HP_DATA
environment variable; the reading material is in its reading/ folder. Outputs go to --out <dir>
(default reading/_out), never into the data folder. Both options are taken out of sys.argv here, so
each script keeps its own positional arguments.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _pop(flag):
  if flag in sys.argv:
    i = sys.argv.index(flag)
    val = sys.argv[i + 1]
    del sys.argv[i:i + 2]
    return val
  return None


_data = _pop("--data") or os.environ.get("LIVE_HP_DATA")
_out = _pop("--out")
if not _data:
  sys.exit("set --data <path to data/live_hp> or the LIVE_HP_DATA environment variable")
DATA = Path(_data)
READING = DATA / "reading"
if not READING.is_dir():
  sys.exit(f"{DATA} does not look like data/live_hp (no reading/ folder)")
OUT = Path(_out) if _out else HERE / "_out"
OUT.mkdir(parents=True, exist_ok=True)
