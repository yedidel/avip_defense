"""Locations used by the strengthen scripts.

Released data: data/live_hp of the DATA repository, given as --data <path> or the LIVE_HP_DATA
environment variable. Outputs go to --out <dir> (default binding/_out/strengthen), never into the
data folder. Both options are taken out of sys.argv here, so each script keeps its own arguments.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = HERE.parent
if str(BINDING) not in sys.path:
  sys.path.insert(0, str(BINDING))  # mechanism/, _common.py, _openrouter.py


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
if not (DATA / "binding").is_dir() or not (DATA / "cross_seller").is_dir():
  sys.exit(f"{DATA} does not look like data/live_hp (needs binding/ and cross_seller/)")

STRENGTHEN = DATA / "binding" / "strengthen"     # released outputs of these scripts, traces, scenarios
ATTRIBUTION = DATA / "binding" / "attribution"   # frozen F2 sets, A-LLM v1 ledger, A-LEX/B4 outputs, reader truth
ADAPTIVE = DATA / "binding" / "adaptive"         # F6 chains and the readers' confirmed list
INTEGRATION = DATA / "binding" / "integration"   # F0/F1 traces (mechanism in the flow)
RESIDUAL = DATA / "binding" / "residual"         # F5 traces
CROSS_SELLER = DATA / "cross_seller"             # scenarios and traces of the cross-seller run
OUT = Path(_out) if _out else BINDING / "_out" / "strengthen"
OUT.mkdir(parents=True, exist_ok=True)
