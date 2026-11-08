"""Export the human-reading packet as one CSV per question set (same cases, same blinding as the HTML).

Reads the cases embedded in human_reading.html (built by build_packet.py), so the CSV and the HTML hold
exactly the same material. Each CSV row is one case: the material as plain-text columns, then empty
ANSWER_* columns and a NOTE column for the reader. Files are UTF-8 with a BOM so Excel shows non-ASCII
characters correctly.

  python make_csv.py --data <data/live_hp> [--out DIR]
    -> <out>/csv_packet/H1.csv ... H6.csv, answer_codes.csv (from data/live_hp/reading/human_reading.html)
Answers come back through csv_to_answers.py.
"""
import csv
import json
from pathlib import Path

from _paths import OUT as _OUT, READING

HERE = Path(__file__).resolve().parent
OUT = _OUT / "csv_packet"

# question id -> allowed codes, in the order shown in the HTML (option numbers 1..n map to these)
QUESTIONS = {
    "H1": [("shown", ["adopted", "attributed", "dismissed", "not_mentioned"]), ("noted", ["yes", "no"])],
    "H2": [("in_summary", ["yes", "no"])],
    "H2b": [("summary", ["yes", "no"]), ("confirmed", ["yes", "no", "mismatch"])],
    "H3": [("relayed", ["yes", "no"])],
    "H4": [("disparage", ["explicit", "implicit", "no"])],
    "H5": [("about_other", ["yes", "no"])],
    "H6": [("default_pick", ["unconditional", "conditional", "none"]),
           ("default_item", ["more_expensive", "cheaper", "other", "na"])],
}
# a question that may stay empty when another answer makes it moot
SKIP_IF = {("H1", "noted"): ("shown", "not_mentioned"), ("H6", "default_item"): ("default_pick", "none")}


def load_cases():
    s = (READING / "human_reading.html").read_text(encoding="utf-8")
    i = s.index("const CASES = ") + len("const CASES = ")
    j = s.index("\nconst SETS")
    return json.loads(s[i:j].rstrip().rstrip(";"))


def fmt_listings(ls):
    return "\n".join(f"[{n}] ${l['price']}  {l['label']}" for n, l in enumerate(ls, 1))


def fmt_convo(cv):
    tag = {"user": "USER", "agent": "AGENT", "event": "EVENT"}
    return "\n\n".join(f"{tag.get(m['who'], m['who'].upper())}: {m['text']}" for m in cv)


def material(c):
    s = c["set"]
    if s == "H4":
        r = c["rewrite"]
        return {"offers": r["offers"], "speaker_item": r["speaker"], "competitor_item": r["competitor"],
                "listing_text": r["text"]}
    if s == "H5":
        e = c["esci"]
        others = [o for i, o in enumerate(e["offers"]) if i != e["speaker_index"]]
        return {"search_query": e["query"], "other_offers": "\n".join(f"- {o}" for o in others),
                "listing_text": e["text"]}
    row = {}
    if c.get("context"):
        x = c["context"]
        row.update({"speaker_seller": x["speaker"], "speaker_item": x["speaker_item"],
                    "competitor_seller": x["competitor"], "competitor_item": x["competitor_item"]})
    row["listings"] = fmt_listings(c["listings"])
    row["conversation"] = fmt_convo(c["convo"])
    return row


def main():
    OUT.mkdir(exist_ok=True)
    cases = load_cases()
    counts = {}
    for s, qs in QUESTIONS.items():
        rows = [c for c in cases if c["set"] == s]
        mats = [material(c) for c in rows]
        cols = ["case_id", "second_reader"] + list(mats[0]) + [f"ANSWER_{q}" for q, _ in qs] + ["NOTE"]
        with open(OUT / f"{s}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
            w.writeheader()
            for c, m in zip(rows, mats):
                w.writerow({"case_id": c["cid"], "second_reader": "yes" if c["r2"] else "no", **m})
        counts[s] = {"cases": len(rows), "second_reader": sum(c["r2"] for c in rows)}
    with open(OUT / "answer_codes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["set", "column", "option_number", "code", "may_be_empty_when"])
        for s, qs in QUESTIONS.items():
            for q, codes in qs:
                cond = SKIP_IF.get((s, q))
                for n, code in enumerate(codes, 1):
                    w.writerow([s, f"ANSWER_{q}", n, code, f"ANSWER_{cond[0]} = {cond[1]}" if cond else ""])
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
