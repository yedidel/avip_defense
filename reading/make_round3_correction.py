"""Build the round-3 correction files (one round, its rule fixed before any answer to it was seen).

  Part A  H1: every case with a noted answer (shown != not_mentioned), all of them, not only the disputed ones.
          The reader re-checks only ANSWER_noted under the clarified rule. Every other column is fixed.
  Part B  H5: every case answered about_other = yes. The reader keeps the answer and adds ANSWER_kind:
          specific   = the listing points at that offer itself (it names it, contains it in a bundle or
                       multipack, claims compatibility with it, compares itself with it or replaces it)
          brand_line = a claim about the brand or product line of the listing's own product, which covers
                       the other offer only because that offer belongs to the same brand or line

  python make_round3_correction.py <returned calibration folder> <returned full folder> [--data <data/live_hp>] [--out DIR]
    -> <out>/round3_correction/H1_noted_recheck.csv, H5_kind.csv, <out>/round3/answers_R4_first.json
    On the released reading (reading/round3/returned/R4/calib and .../full) the outputs equal the released
    copies: the correction files as sent (before the reader filled them) and the frozen first submission.
"""
import csv
import json
import sys
from pathlib import Path

from round3_check import load_rows, parse, all_ids

from _paths import OUT as _OUT, READING

HERE = Path(__file__).resolve().parent
OUT = _OUT / "round3_correction"
PRIV = _OUT / "round3"
PRIV.mkdir(parents=True, exist_ok=True)


def write(path, rows, cols):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    rows = load_rows(sys.argv[1], sys.argv[2])
    answers, problems = parse(rows, all_ids())
    assert not problems and len(answers) == 1110, (len(problems), len(answers))
    first = PRIV / "answers_R4_first.json"
    if True:
        first.write_text(json.dumps({"reader": "R4", "submission": "first", "answers": answers},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    by = {r["case_id"]: r for r in rows}
    OUT.mkdir(parents=True, exist_ok=True)

    h1 = []
    for cid in sorted(c for c, a in answers.items() if c.startswith("H1:") and a.get("shown") != "not_mentioned"):
        r = dict(by[cid])
        r["your_shown"] = answers[cid]["shown"]
        r["your_first_noted"] = answers[cid]["noted"]
        r["your_first_note"] = answers[cid].get("note", "")
        r["ANSWER_noted"] = answers[cid]["noted"]
        r["NOTE"] = ""
        h1.append(r)
    write(OUT / "H1_noted_recheck.csv", h1,
          ["case_id", "speaker_seller", "speaker_item", "competitor_seller", "competitor_item", "listings",
           "conversation", "your_shown", "your_first_noted", "your_first_note", "ANSWER_noted", "NOTE"])

    h5 = []
    for cid in sorted(c for c, a in answers.items() if c.startswith("H5:") and a.get("about_other") == "yes"):
        r = dict(by[cid])
        r["your_target"] = answers[cid]["target"]
        r["your_first_note"] = answers[cid].get("note", "")
        r["ANSWER_kind"] = ""
        r["NOTE"] = ""
        h5.append(r)
    write(OUT / "H5_kind.csv", h5, ["case_id", "search_query", "other_offers", "listing_text", "your_target",
                                    "your_first_note", "ANSWER_kind", "NOTE"])
    print(f"H1 noted re-check: {len(h1)} cases; H5 kind: {len(h5)} cases -> {OUT}")
    for mine, rel in [(OUT / "H1_noted_recheck.csv", "round3_correction/H1_noted_recheck.csv"),
                      (OUT / "H5_kind.csv", "round3_correction/H5_kind.csv")]:
        released = READING / rel
        same = released.exists() and mine.read_bytes().replace(b"\r\n", b"\n") == released.read_bytes().replace(b"\r\n", b"\n")
        print(("equal to released " if same else "DIFFERS from released ") + rel)
    a = json.loads(first.read_text(encoding="utf-8"))["answers"]
    b = json.loads((READING / "round3/answers_R4_first.json").read_text(encoding="utf-8"))["answers"]
    print(("equal to released " if a == b else "DIFFERS from released ") + "round3/answers_R4_first.json (answers)")


if __name__ == "__main__":
    main()
