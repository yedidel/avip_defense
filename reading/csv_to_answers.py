"""Read the CSV files a reader returns and write the answers JSON that score.py reads (the same format the
HTML page exports). Checks every answer against the allowed codes, accepts an option number in place of a
code, and lists every missing or invalid answer.

  python csv_to_answers.py <folder with H1.csv..H6.csv> <reader name> primary|second [--data <data/live_hp>] [--out DIR]
  -> <out>/answers/human_reading_<reader>_<role>.json, then:  python score.py <that file>
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _paths import OUT, READING
from make_csv import QUESTIONS, SKIP_IF

HERE = Path(__file__).resolve().parent


def main():
    folder, reader, role = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    assert role in ("primary", "second"), "role must be primary or second"
    key = json.load(open(READING / "answer_key_llm.json", encoding="utf-8"))
    answers, problems = {}, []
    for s, qs in QUESTIONS.items():
        p = folder / f"{s}.csv"
        if not p.exists():
            problems.append(f"{s}: file {p.name} not found")
            continue
        with open(p, encoding="utf-8-sig", newline="") as f:
            for n, row in enumerate(csv.DictReader(f), 2):
                cid = (row.get("case_id") or "").strip()
                if cid not in key or key[cid]["set"] != s:
                    problems.append(f"{s} row {n}: unknown case_id {cid!r}")
                    continue
                if role == "second" and (row.get("second_reader") or "").strip() != "yes":
                    continue
                a = {}
                for q, codes in qs:
                    v = (row.get(f"ANSWER_{q}") or "").strip().lower()
                    if v.isdigit() and 1 <= int(v) <= len(codes):
                        v = codes[int(v) - 1]
                    if v:
                        if v not in codes:
                            problems.append(f"{s} row {n} ({cid}): ANSWER_{q} = {v!r} is not one of {codes}")
                            continue
                        a[q] = v
                for q, codes in qs:
                    cond = SKIP_IF.get((s, q))
                    if q not in a and not (cond and a.get(cond[0]) == cond[1]):
                        problems.append(f"{s} row {n} ({cid}): ANSWER_{q} is empty")
                note = (row.get("NOTE") or "").strip()
                if note:
                    a["note"] = note
                if a:
                    answers[cid] = a
    expected = {cid for cid, k in key.items()} if role == "primary" else None
    out_dir = OUT / "answers"
    out_dir.mkdir(exist_ok=True)
    out = {"reader": reader, "role": role, "exported": datetime.now(timezone.utc).isoformat(),
           "source": "csv", "n": len(answers), "answers": answers}
    dest = out_dir / f"human_reading_{reader}_{role}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {dest} with {len(answers)} answered cases")
    if expected is not None:
        print(f"primary reader: {len(expected - set(answers))} of {len(expected)} cases have no answer")
    print(f"{len(problems)} problems")
    for x in problems[:200]:
        print("  " + x)


if __name__ == "__main__":
    main()
