"""Check a round-2 reader's returned files.

  python round2_check.py calib  <returned file or folder> <reader> [--data <data/live_hp>] [--out DIR]
      -> <out>/round2/feedback_<reader>.md (for the reader)
  python round2_check.py sample <returned file or folder> <reader> [--data <data/live_hp>] [--out DIR]
      -> quality report + <out>/round2/answers_<reader>.json
The released human sample: data/live_hp/reading/round2/returned/R3/{calib,sample}; its sample answers are
data/live_hp/reading/round2/answers_R3.json.

Accepts the per-set files as sent, or any single CSV that keeps the case_id and ANSWER_* columns (both earlier
readers merged everything into one file). The set is read from the case_id prefix.

Acceptance rule, fixed before any round-2 answers were seen (05.11.2026): a reader's sample is used only if
(1) every row passes the validity checks below after at most one correction round, and
(2) at least 12 of the 13 hidden check cases match the authors' reading.
Check cases never enter agreement or paper numbers.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from _paths import OUT, READING
import score
from make_csv import QUESTIONS, SKIP_IF

HERE = Path(__file__).resolve().parent
KEYS = READING / "round2"   # calib_key.json, gold_key.json
PRIV = OUT / "round2"       # outputs
PRIV.mkdir(parents=True, exist_ok=True)


def load_rows(src):
    src = Path(src)
    files = sorted(src.glob("*.csv")) if src.is_dir() else [src]
    rows = []
    for f in files:
        if f.name == "answer_codes.csv":
            continue
        rows += list(csv.DictReader(open(f, encoding="utf-8-sig", newline="")))
    return rows


def parse(rows, expected_ids):
    answers, problems = {}, []
    seen = set()
    for n, row in enumerate(rows, 2):
        cid = (row.get("case_id") or "").strip()
        if cid not in expected_ids:
            continue
        s = cid.split(":")[0]
        seen.add(cid)
        a = {}
        for q, codes in QUESTIONS[s]:
            v = (row.get(f"ANSWER_{q}") or "").strip().lower()
            if v.isdigit() and 1 <= int(v) <= len(codes):
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


def calib(src, reader):
    key = json.loads((KEYS / "calib_key.json").read_text(encoding="utf-8"))
    answers, problems = parse(load_rows(src), set(key))
    lines = [f"# Feedback on the calibration stage ({reader})", ""]
    ok = 0
    for cid, k in key.items():
        got = {q: answers.get(cid, {}).get(q) for q in k["expected"]}
        exp = {q: (None if (SKIP_IF.get((k["set"], q)) and k["expected"].get(SKIP_IF[(k["set"], q)][0]) == SKIP_IF[(k["set"], q)][1]) else v)
               for q, v in k["expected"].items()}
        match = all(got[q] == exp[q] for q in exp)
        ok += match
        mark = "correct" if match else "does not match"
        lines += [f"## {cid} ({k['set']}): {mark}",
                  "Your answer: " + ", ".join(f"{q} = {got[q] or 'empty'}" for q in exp),
                  "Expected answer: " + ", ".join(f"{q} = {exp[q] or 'empty'}" for q in exp),
                  "Explanation: " + k["why"], ""]
    lines.insert(2, f"{ok} of {len(key)} cases match. The explanations are below, also for the cases that match.")
    lines.insert(3, "")
    if problems:
        lines += ["## Fill problems", *[f"- {c}: {p}" for c, p in problems], ""]
    out = PRIV / f"feedback_{reader}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"calibration: {ok}/{len(key)} match, {len(problems)} fill problems -> {out}")


def sample(src, reader):
    gold = json.loads((KEYS / "gold_key.json").read_text(encoding="utf-8"))
    samp = {cid for cid, k in score.KEY.items() if k["set"] in QUESTIONS}
    sample_ids = set()
    for s in QUESTIONS:
        for r in csv.DictReader(open(READING / f"csv_packet/{s}.csv", encoding="utf-8-sig", newline="")):
            if r["second_reader"] == "yes":
                sample_ids.add(r["case_id"])
    answers, problems = parse(load_rows(src), sample_ids | set(gold))
    g_ok = []
    for cid, k in gold.items():
        a = answers.get(cid, {})
        g_ok.append((cid, all(a.get(q) == v for q, v in k["expected"].items()
                              if not (SKIP_IF.get((k["set"], q)) and k["expected"].get(SKIP_IF[(k["set"], q)][0]) == SKIP_IF[(k["set"], q)][1]))))
    n_ok = sum(x for _, x in g_ok)
    print(f"validity problems: {len(problems)}")
    for c, p in problems[:60]:
        print(f"  {c}: {p}")
    print(f"hidden checks: {n_ok}/{len(gold)} match" + "".join(f"\n  miss: {c}" for c, x in g_ok if not x))
    accepted = not problems and n_ok >= 12
    print("ACCEPTED (pre-set rule)" if accepted else "NOT ACCEPTED under the pre-set rule (fix problems / check cases)")
    by_q = defaultdict(list)
    for cid in sample_ids:
        if cid not in answers:
            continue
        s = score.KEY[cid]["set"]
        h, l = score.human_label(s, answers[cid]), score.llm_label(s, score.KEY[cid])
        for q in h:
            by_q[f"{s}.{q}"].append((h[q], l.get(q)))
    print("\nagreement with the model readers on the 304 sample cases (check cases excluded):")
    for q, pairs in sorted(by_q.items()):
        k, n = score.kappa(pairs)
        valid = [(x, y) for x, y in pairs if x is not None and y is not None]
        print(f"  {q}: {sum(x == y for x, y in valid)}/{n} kappa={k}")
    out = PRIV / f"answers_{reader}.json"
    out.write_text(json.dumps({"reader": reader, "accepted": accepted, "hidden_checks": f"{n_ok}/{len(gold)}",
                               "problems": len(problems),
                               "answers": {c: a for c, a in answers.items() if c in sample_ids}}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    mode, src, reader = sys.argv[1:4]
    {"calib": calib, "sample": sample}[mode](src, reader)
