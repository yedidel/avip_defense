"""F0 integration and F1 live mediation: structural tallies of the mechanism inside the live flow.

Reads binding/integration/traces (tags E43F0, E43F1; flash-lite shopping agent, policy STRIP, A-LLM
deepseek-v4.1-flash in the flow) and counts only structural fields that the mechanism and the driver
recorded (the "e43" field of each trace, the tool calls in the trace, the signed checkout). No model
reply is judged here.

Per trial:
  signed           a checkout mandate was signed
  captured         every find_products call in the trace has a capture in e43.searches
  bound            the checkout's cart_id, item_label, amount and JWT line-item title equal the
                   captured offer (e43.checkout.binding)
  verifier         DEFAULT and STRICT verdicts of the decision record R at checkout
  claim detected   (claim arm) a non-authoritative claim spoken by the ALT offer about the WANT offer
                   was attributed in the first search; (no-claim arm) any attributed claim is a flag
  presented        whether the ALT label the agent was shown differs from the raw label (text removed)
Cost of the mechanism: seconds added per search (e43.searches[].seconds_added) and R size in bytes.

Usage (from binding/):  python live/analyze_integration.py --data <data/live_hp>
"""
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import iter_traces, parse_args  # noqa: E402


def alt_want(d):
  role = {c["cart_id"]: c["role"] for c in d.get("carts", [])}
  return role


def main():
  a = parse_args(__doc__)
  T = list(iter_traces(a.data / "binding" / "integration"))
  all_secs, rbytes = [], []
  for tag in ("E43F0", "E43F1"):
    secs = []
    xs = [d for d in T if d["uid"].startswith(tag + "__")]
    print(f"== {tag}: {len(xs)} trials")
    c = Counter()
    strict_rej, missed, flagged, researched = [], [], [], []
    by_dir = Counter()
    for d in xs:
      e = d.get("e43") or {}
      role = alt_want(d)
      n_find = sum(1 for ev in d.get("trace", []) for p in ev["parts"] if p.get("resp") == "find_products")
      searches = e.get("searches", [])
      ck = e.get("checkout") or {}
      b = ck.get("binding") or {}
      c["signed"] += bool(d.get("checkout_mandate_signed"))
      c["captured_all_searches"] += n_find == len(searches) and n_find > 0
      c["bound"] += all(b.get(k) for k in ("cart_id_match", "label_match", "amount_match", "jwt_title_match"))
      v = ck.get("verdicts") or {}
      c["verifier_DEFAULT_ok"] += bool((v.get("DEFAULT") or {}).get("ok"))
      if v.get("STRICT") and not v["STRICT"]["ok"]:
        strict_rej.append((d["uid"], v["STRICT"]["codes"], d.get("e_sel_role")))
      c[f"searches={len(searches)}"] += 1
      if len(searches) > 1:
        researched.append(d["uid"])
      for s in searches:
        if s.get("seconds_added") is not None:
          secs.append(s["seconds_added"])
      if ck.get("record_bytes"):
        rbytes.append(ck["record_bytes"])
      first = searches[0] if searches else {}
      cl = first.get("claims", [])
      if d["arm"] == "claim" and tag == "E43F0":
        hit = any(not x["authoritative"] and role.get(x["speaker"]["cart_id"]) == "alt"
                  and role.get(x["target"]["cart_id"]) == "want" for x in cl)
        c["claim_detected"] += hit
        if not hit:
          missed.append(d["uid"])
      if d["arm"] == "noclaim" and cl:
        flagged.append(d["uid"])
      if tag == "E43F1" and first:
        k = next(i for i, x in enumerate(first["raw_carts"]) if role.get(x["cart_id"]) == "alt")
        changed = first["presented_labels"][k] != first["raw_carts"][k]["item_label"]
        by_dir[(d["pair_id"].rsplit("_", 1)[1], "alt text removed" if changed else "alt text kept")] += 1
    n_claim = sum(d["arm"] == "claim" for d in xs)
    for k in sorted(c):
      print(f"  {k}: {c[k]}/{n_claim if k == 'claim_detected' else len(xs)}")
    if tag == "E43F0":
      print(f"  claim trials without detection: {missed}")
      print(f"  no-claim trials with any attributed claim: {flagged}")
    else:
      print(f"  per directive (rq = search again, ig = ignore other results): {dict(sorted(by_dir.items()))}")
    print(f"  trials with more than one search: {researched}")
    print(f"  STRICT (V8) rejections: {strict_rej}")
    print(f"  seconds added per search: median {statistics.median(secs):.2f}, max {max(secs):.1f} (n={len(secs)} searches)")
    all_secs += secs
  print(f"== all {len(T)} trials: seconds added per search median {statistics.median(all_secs):.2f}, "
        f"max {max(all_secs):.1f} (n={len(all_secs)}); R size {min(rbytes)}-{max(rbytes)} bytes")


if __name__ == "__main__":
  main()
