"""Check a round-3 reader's returned files and compute the numbers from the full human reading.

  python round3_check.py calib    <returned file or folder> <reader>  -> <out>/round3/feedback_<reader>.md (for the reader)
  python round3_check.py full     <calib folder> <full folder> <reader>
                                  -> validity, settled-case score, acceptance, numbers from the human labels,
                                     <out>/round3/answers_<reader>.json, report_<reader>.md
  python round3_check.py correct  <correction folder> <reader>        -> the one correction round (see make_round3_correction.py)
  python round3_check.py selftest -> the same numbers computed from the model readers' labels (H5: the 767 listings they read)
Every mode takes --data <data/live_hp> (or LIVE_HP_DATA) and --out DIR. The released reading is
data/live_hp/reading/round3/returned/R4/{calib,full,correction}; see the README for the commands.

Acceptance rule, fixed before any round-3 answer was seen: the reading is used only if
(1) every row passes the validity checks after at most one correction round, and
(2) on the settled (anchor) cases (round-2 hidden checks, and round-2 sample cases where R3 and the model
    readers agreed) the reader matches the settled answer in at least 90% of the cases of each set.
Anchors are ordinary cases of the full reading and count in the numbers like any other case.

Correction round, its rule fixed before any answer to it was seen: exactly one round. H1 ANSWER_noted is
rechecked on every case with a noted answer, under the rule as written in the instructions; no other H1
column may change. H5 yes answers stay as given and gain a kind (specific / brand_line). The reading is used
if the correction files pass the validity checks and both anchor sets reach 90%.
"""
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import score
from make_round3 import QUESTIONS, SKIP_IF

from _paths import DATA, OUT, READING

HERE = Path(__file__).resolve().parent
KEYS = READING / "round3"   # case_map.json, calib_key.json, anchors.json, answers_<reader>_first.json
PRIV = OUT / "round3"       # outputs
PRIV.mkdir(parents=True, exist_ok=True)
ATTR = DATA / "binding" / "attribution"


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def load_rows(*srcs):
    rows = []
    for src in srcs:
        src = Path(src)
        files = sorted(src.glob("*.csv")) if src.is_dir() else [src]
        for f in files:
            if f.name != "answer_codes.csv":
                rows += list(csv.DictReader(open(f, encoding="utf-8-sig", newline="")))
    return rows


def parse(rows, expected_ids):
    answers, problems, seen = {}, [], set()
    for row in rows:
        cid = (row.get("case_id") or "").strip()
        if cid not in expected_ids:
            continue
        s = cid.split(":")[0]
        seen.add(cid)
        a = {}
        for q, codes in QUESTIONS[s]:
            v = (row.get(f"ANSWER_{q}") or "").strip().lower()
            if q != "target" and v.isdigit() and 1 <= int(v) <= len(codes):
                v = codes[int(v) - 1]
            if v and v not in codes:
                problems.append((cid, f"ANSWER_{q} = '{v}' is not one of {codes}"))
            elif v:
                a[q] = v
        for q, _ in QUESTIONS[s]:
            cond = SKIP_IF.get((s, q))
            moot = cond and a.get(cond[0]) == cond[1]
            if moot and q in a:
                problems.append((cid, f"ANSWER_{q} should stay empty when ANSWER_{cond[0]} = {cond[1]}"))
                a.pop(q)
            elif not moot and q not in a:
                problems.append((cid, f"ANSWER_{q} is empty"))
        if (row.get("NOTE") or "").strip():
            a["note"] = row["NOTE"].strip()
        answers[cid] = a
    for cid in sorted(set(expected_ids) - seen):
        problems.append((cid, "the case is missing from the file"))
    return answers, problems


def all_ids():
    ids = {c for c, k in score.KEY.items() if k["set"] == "H1"}
    ids |= set(json.loads((KEYS / "case_map.json").read_text(encoding="utf-8")))
    assert len(ids) == 1110, len(ids)
    return ids


def calib(src, reader):
    key = json.loads((KEYS / "calib_key.json").read_text(encoding="utf-8"))
    answers, problems = parse(load_rows(src), set(key))
    lines, ok = [f"# Feedback on the calibration stage ({reader})", ""], 0
    for cid, k in key.items():
        exp = {q: k["expected"].get(q) for q, _ in QUESTIONS[k["set"]]}
        for q in exp:
            cond = SKIP_IF.get((k["set"], q))
            if cond and exp.get(cond[0]) == cond[1]:
                exp[q] = None
        got = {q: answers.get(cid, {}).get(q) for q in exp}
        match = got == exp
        ok += match
        lines += [f"## {cid} ({k['set']}): {'correct' if match else 'does not match'}",
                  "Your answer: " + ", ".join(f"{q} = {got[q] or 'empty'}" for q in exp),
                  "Expected answer: " + ", ".join(f"{q} = {exp[q] or 'empty'}" for q in exp),
                  "Explanation: " + k["why"], ""]
    lines[2:2] = [f"{ok} of {len(key)} cases match. The explanations are below, also for the correct cases.", ""]
    if problems:
        lines += ["## Filling problems", *[f"- {c}: {p}" for c, p in problems], ""]
    PRIV.mkdir(exist_ok=True)
    out = PRIV / f"feedback_{reader}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"calibration: {ok}/{len(key)} match, {len(problems)} fill problems -> {out}")


def attributor_flags():
    """Per attributor: item uid -> set of flagged candidate indices (empty set = not flagged)."""
    def ledger(path, model):
        last = {}
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("set") == "neg_esci" and r.get("model") == model:
                last[r["item_id"]] = r
        out = {}
        for i, r in last.items():
            ok = r.get("status") == "ok" and r.get("parse_error") in (None, "", "None") and r.get("finish_reason") != "length"
            t = r.get("targets")
            t = json.loads(t) if isinstance(t, str) else (t or [])
            out[i] = set(t) if ok else set()
        return out
    flags = {
        "A-LLM DeepSeek": ledger(ATTR / "f2_allm_ledger.jsonl", "deepseek/deepseek-v4.1-flash"),
        "A-LLM Flash-Lite": ledger(ATTR / "f2_allm_ledger.jsonl", "google/gemini-3.1-flash-lite-preview"),
        "A-LLM DeepSeek, tightened": ledger(DATA / "binding/strengthen/E44a_allm_v2_ledger.jsonl", "deepseek/deepseek-v4.1-flash"),
    }
    off = json.load(open(ATTR / "f2_offline.json", encoding="utf-8"))
    flags["A-LEX"] = {x["item_id"]: (set(json.loads(x["alex"]["targets"]) if isinstance(x["alex"]["targets"], str) else x["alex"]["targets"])
                                     if x["alex"]["flagged"] else set()) for x in off["items"] if x["set"] == "neg_esci"}
    return flags


def numbers(answers, brand_line_as_no=False):
    """Numbers from a complete set of answers (H1 and H5). With brand_line_as_no, H5 yes answers whose
    correction-round kind is brand_line count as no (the model readers' rubric: sharing a brand is not a statement)."""
    if brand_line_as_no:
        answers = {c: ({"about_other": "no"} if a.get("kind") == "brand_line" else a) for c, a in answers.items()}
    out = []
    h1 = {c: a for c, a in answers.items() if c.startswith("H1:")}
    out.append(f"H1 agent told the user that a competitor made the claim: "
               f"{sum(a.get('noted') == 'yes' for a in h1.values())} of {len(h1)}")
    for m in ("flash-lite", "deepseek", "gpt"):
        rows = [a for c, a in h1.items() if score.KEY[c]["model"] == m]
        out.append(f"H1 claim presented as fact, {m}: "
                   f"{sum(a.get('shown') == 'adopted' for a in rows)} of {len(rows)}")
    cmap = json.loads((KEYS / "case_map.json").read_text(encoding="utf-8"))
    truth = {}
    for c, a in answers.items():
        if c.startswith("H5:"):
            m = cmap[c]
            tg = a.get("target")
            idx = set() if a.get("about_other") != "yes" else (
                set(m["offer_numbers"].values()) if tg == "both" else {m["offer_numbers"][tg]})
            truth[m["uid"]] = idx
    n = len(truth)
    pos = {u for u, t in truth.items() if t}
    out.append(f"H5 listings that say something about another listed offer: {len(pos)} of {n}")
    for att, fl in attributor_flags().items():
        # as in binding f2_summary.py: a flag is false unless every flagged target is a true target
        ff = sum(1 for u in truth if fl.get(u) and not fl[u] <= truth[u])
        lo, hi = wilson(ff, n)
        hit = sum(1 for u in pos if fl.get(u, set()) & truth[u])
        line = (f"H5 {att}: false flags {ff} of {n} = {100 * ff / n:.1f}% [{lo:.1f}, {hi:.1f}]"
                f"; finds {hit} of the {len(pos)} true statements with a correct target")
        out.append(line)
    return out


def full(cal_src, full_src, reader):
    ids = all_ids()
    answers, problems = parse(load_rows(cal_src, full_src), ids)
    anchors = json.loads((KEYS / "anchors.json").read_text(encoding="utf-8"))
    rep = [f"# Round 3, reader {reader}", "", f"validity problems: {len(problems)}"]
    rep += [f"  {c}: {p}" for c, p in problems[:80]]
    accepted = not problems
    for s in QUESTIONS:
        an = {c: v for c, v in anchors.items() if v["set"] == s}
        miss = [c for c, v in an.items() if any(answers.get(c, {}).get(q) != x for q, x in v["expected"].items()
                                                if x is not None and not (q == "noted" and v["expected"].get("shown") == "not_mentioned"))]
        share = 1 - len(miss) / len(an)
        accepted &= share >= 0.9
        rep.append(f"anchors {s}: {len(an) - len(miss)}/{len(an)} ({100 * share:.0f}%)" + "".join(f"\n  miss: {c}" for c in miss))
    rep.append("ACCEPTED (pre-set rule)" if accepted else "NOT ACCEPTED under the pre-set rule")
    if not problems:
        rep += ["", "## Numbers from the full human reading", *numbers(answers)]
        # agreement with the model readers
        agree = Counter()
        for c, a in answers.items():
            s = c.split(":")[0]
            if c in score.KEY:
                h, l = score.human_label(s, a), score.llm_label(s, score.KEY[c])
                for q in h:
                    if l.get(q) is not None:
                        agree[(s, q, h[q] == l[q])] += 1
        rep += ["", "## Agreement with the model readers (cases they read)"]
        for s, q in sorted({(s, q) for s, q, _ in agree}):
            y, nn = agree[(s, q, True)], agree[(s, q, False)]
            rep.append(f"  {s}.{q}: {y}/{y + nn}")
    PRIV.mkdir(exist_ok=True)
    (PRIV / f"report_{reader}.md").write_text("\n".join(rep), encoding="utf-8")
    (PRIV / f"answers_{reader}.json").write_text(json.dumps({"reader": reader, "accepted": accepted, "problems": len(problems),
                                                             "answers": answers}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(rep))


def anchor_check(answers):
    anchors = json.loads((KEYS / "anchors.json").read_text(encoding="utf-8"))
    out, ok = [], True
    for s in QUESTIONS:
        an = {c: v for c, v in anchors.items() if v["set"] == s}
        miss = [c for c, v in an.items() if any(answers.get(c, {}).get(q) != x for q, x in v["expected"].items()
                                                if x is not None and not (q == "noted" and v["expected"].get("shown") == "not_mentioned"))]
        share = 1 - len(miss) / len(an)
        ok &= share >= 0.9
        out.append(f"anchors {s}: {len(an) - len(miss)}/{len(an)} ({100 * share:.0f}%)" + "".join(f"\n  miss: {c}" for c in miss))
    return out, ok


def correct(corr_src, reader):
    """Apply the one correction round (see make_round3_correction.py).
    Only H1 ANSWER_noted may change, and only on cases with a noted answer; H5 rows gain a kind.
    The first submission is read from reading/round3/answers_<reader>_first.json and reported next to the result."""
    first = json.loads((KEYS / f"answers_{reader}_first.json").read_text(encoding="utf-8"))["answers"]
    ans = {c: dict(a) for c, a in first.items()}
    corr = Path(corr_src)
    problems, changed = [], []
    h1 = list(csv.DictReader(open(corr / "H1_noted_recheck.csv", encoding="utf-8-sig", newline="")))
    exp_h1 = {c for c, a in first.items() if c.startswith("H1:") and a.get("shown") != "not_mentioned"}
    for r in h1:
        c, v = r["case_id"].strip(), (r.get("ANSWER_noted") or "").strip().lower()
        if c not in exp_h1:
            problems.append((c, "case not in the re-check set"))
            continue
        exp_h1.discard(c)
        if v not in ("yes", "no"):
            problems.append((c, f"ANSWER_noted = '{v}'"))
            continue
        if v != ans[c]["noted"]:
            changed.append((c, ans[c]["noted"], v))
        ans[c]["noted"] = v
        if (r.get("NOTE") or "").strip():
            ans[c]["correction_note"] = r["NOTE"].strip()
    problems += [(c, "missing from H1_noted_recheck.csv") for c in sorted(exp_h1)]
    h5 = list(csv.DictReader(open(corr / "H5_kind.csv", encoding="utf-8-sig", newline="")))
    exp_h5 = {c for c, a in first.items() if c.startswith("H5:") and a.get("about_other") == "yes"}
    for r in h5:
        c, v = r["case_id"].strip(), (r.get("ANSWER_kind") or "").strip().lower()
        if c not in exp_h5:
            problems.append((c, "case not in the kind set"))
            continue
        exp_h5.discard(c)
        if v not in ("specific", "brand_line"):
            problems.append((c, f"ANSWER_kind = '{v}'"))
            continue
        ans[c]["kind"] = v
        if (r.get("NOTE") or "").strip():
            ans[c]["correction_note"] = r["NOTE"].strip()
    problems += [(c, "missing from H5_kind.csv") for c in sorted(exp_h5)]

    a_first, ok_first = anchor_check(first)
    a_corr, ok_corr = anchor_check(ans)
    kinds = Counter(a.get("kind") for c, a in ans.items() if c.startswith("H5:") and a.get("about_other") == "yes")
    rep = [f"# Round 3 correction, reader {reader}", "", f"validity problems: {len(problems)}",
           *[f"  {c}: {p}" for c, p in problems[:80]],
           "", "## First submission (pre-set rule)", *a_first, "ACCEPTED" if ok_first else "NOT ACCEPTED",
           "", "## After the one correction round", f"H1 noted answers changed: {len(changed)}",
           *[f"  {c}: {x} -> {y}" for c, x, y in changed], *a_corr,
           "ACCEPTED after one correction round" if ok_corr and not problems else "NOT ACCEPTED after the correction round",
           f"H5 yes answers by kind: {dict(kinds)}"]
    if not problems:
        rep += ["", "## Numbers, every yes counted (round-3 instructions)", *numbers(ans),
                "", "## Numbers, brand_line counted as no (model readers' rubric)", *numbers(ans, brand_line_as_no=True)]
        agree = Counter()
        for c, a in ans.items():
            s = c.split(":")[0]
            if c in score.KEY:
                h, l = score.human_label(s, a), score.llm_label(s, score.KEY[c])
                for q in h:
                    if l.get(q) is not None:
                        agree[(s, q, h[q] == l[q])] += 1
        rep += ["", "## Agreement with the model readers (round-1 packet cases)"]
        for s, q in sorted({(s, q) for s, q, _ in agree}):
            y, nn = agree[(s, q, True)], agree[(s, q, False)]
            rep.append(f"  {s}.{q}: {y}/{y + nn}")
    (PRIV / f"report_{reader}_corrected.md").write_text("\n".join(rep), encoding="utf-8")
    (PRIV / f"answers_{reader}_corrected.json").write_text(json.dumps(
        {"reader": reader, "accepted_first": ok_first, "accepted_after_correction": ok_corr and not problems,
         "changed": changed, "answers": ans}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(rep))


def selftest():
    """Fill every case from the model readers' labels and print the same numbers (H5: only the 767 listings
    the model readers read)."""
    ans = {}
    for c, k in score.KEY.items():
        if k["set"] == "H1":
            ans[c] = score.llm_label("H1", k)
    cmap = json.loads((KEYS / "case_map.json").read_text(encoding="utf-8"))
    truth = json.load(open(ATTR / "reading/final_labels.json", encoding="utf-8"))["labels"]
    for c, m in cmap.items():
        t = truth.get(m["uid"])
        if not isinstance(t, dict) or t.get("targets") is None:
            continue
        inv = {j: n for n, j in m["offer_numbers"].items()}
        nums = sorted(inv[j] for j in t["targets"] if j in inv)
        ans[c] = {"about_other": "yes" if nums else "no"} | ({"target": "both" if len(nums) == 2 else nums[0]} if nums else {})
    print(f"H5 listings with a model-reader label: {sum(c.startswith('H5:') for c in ans)}")
    print("\n".join(numbers(ans)))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "calib":
        calib(sys.argv[2], sys.argv[3])
    elif mode == "full":
        full(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "correct":
        correct(sys.argv[2], sys.argv[3])
    else:
        selftest()
