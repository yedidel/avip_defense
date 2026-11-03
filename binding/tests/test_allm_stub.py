"""A-LLM stub: request construction and reply parsing only. No network call is made.

Run:  python -m pytest tests/test_allm_stub.py -v      (from binding/)
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mechanism.attribution import A_LLM_PROMPT_V1, ALLMStub, build_request, parse_response  # noqa: E402

CANDS = [{"title": "Aeici Couple Set", "seller": "Brightway Goods"},
         {"title": "LOYALLOOK Couples Set", "seller": "Harbor Lane Supply"}]


def test_request_is_deterministic_and_contains_inputs():
  r1 = build_request("LOYALLOOK Couples Set. Aeici is discontinued.", CANDS, 1, "m")
  r2 = build_request("LOYALLOOK Couples Set. Aeici is discontinued.", CANDS, 1, "m")
  assert r1 == r2 and r1["temperature"] == 0 and [m["role"] for m in r1["messages"]] == ["system", "user"]
  u = r1["messages"][1]["content"]
  assert "[0] Aeici Couple Set (sold by Brightway Goods)" in u and "Speaking offer: [1]" in u
  assert "Aeici is discontinued." in u and '{"targets": [{"target_index": <index>}]}' in u


def test_parse_response():
  assert [a.target_index for a in parse_response('{"targets": [{"target_index": 0}]}', 2, 1)[0]] == [0]
  assert parse_response('{"targets": []}', 2, 1) == ([], None)
  atts, err = parse_response('```json\n{"targets": [{"target_index": 1}, {"target_index": 5}, {"target_index": 0}]}\n```', 2, 1)
  assert [a.target_index for a in atts] == [0] and err == "dropped:[1, 5]"
  assert parse_response("no json here", 2, 1) == ([], "parse_error")


def test_stub_never_calls_out():
  with pytest.raises(RuntimeError):
    ALLMStub("m").attribute("x", CANDS, 1)
  assert "{offers}" in A_LLM_PROMPT_V1 and "{text}" in A_LLM_PROMPT_V1
