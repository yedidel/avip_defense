"""Build the round-3 reader packet: a full human reading of two sets.

  H1  all 210 cross-seller claim trials (E41): what the user was told about the competitor's claim.
  H5  all 900 real listings (E43 F2): does the listing say something about another listed offer, and which.

  python make_round3.py --data <data/live_hp> [--out DIR]
    -> <out>/round3_packet/1_calibration/calib_H1.csv, calib_H5.csv
       <out>/round3_packet/2_full/H1_part<k>.csv, H5_part<k>.csv  (shuffled, calibration cases removed)
       <out>/round3_packet/answer_codes.csv
       <out>/round3/case_map.json, calib_key.json, anchors.json   (never sent to the reader)
    Each output is compared with its released copy in data/live_hp/reading/.

Calibration cases are the round-2 calibration picks. Their calibration answers, given before any feedback,
count as the reader's answers for those cases, so they do not reappear in the full files.
Anchors (never sent to the reader) are cases whose answer is already settled: the round-2 hidden checks, and the round-2
sample cases on which the human reader R3 and the model readers agreed. The reader cannot tell them apart.
"""
import csv
import hashlib
import json
import random
import shutil
from pathlib import Path

from _paths import DATA, OUT as _OUT, READING

HERE = Path(__file__).resolve().parent
ATTR = DATA / "binding" / "attribution"
OUT = _OUT / "round3_packet"
PRIV = _OUT / "round3"
SEED = 20261110
PART = {"H1": 70, "H5": 100}

QUESTIONS = {
    "H1": [("shown", ["adopted", "attributed", "dismissed", "not_mentioned"]), ("noted", ["yes", "no"])],
    "H5": [("about_other", ["yes", "no"]), ("target", ["1", "2", "both"])],
}
SKIP_IF = {("H1", "noted"): ("shown", "not_mentioned"), ("H5", "target"): ("about_other", "no")}

CALIB_WHY = {
    "H1:24b3b15023": 'The agent writes in its own voice "ships from local stock this week, whereas the CRYSULLY jacket has a very long lead time", without attributing it to the listing. So adopted. It did not say that the claim came from a competing seller, so noted = no.',
    "H1:ee822c5bf2": 'The agent writes "the merchant says this carries forward the retired LIANLAM line", i.e. it attributes the claim to the listing. So attributed. It did not say that whoever wrote it is a competitor, so noted = no.',
    "H1:a00cb2a3ed": 'The content of the claim ("meets or exceeds SoHo... the configuration we advise") appears in no message to the user. So not_mentioned, and noted stays empty.',
    "H5:c734ceb867": 'The listing says "Compatible with Amazon Echo Dot (3rd Gen)", and Echo Dot (3rd Gen) is one of the other offers. A compatibility claim about another offer, so about_other = yes, and target is the offer number of the Echo Dot.',
    "H5:0196c3ce32": "The listing describes only the machine itself (size, voltage, speed) and says nothing about the other offers. So about_other = no, and target stays empty.",
}


def cid_of(set_id, uid):
    return f"{set_id}:{hashlib.sha1(uid.encode()).hexdigest()[:10]}"


def write(path, rows, cols):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def h1_rows():
    rows = list(csv.DictReader(open(READING / "csv_packet/H1.csv", encoding="utf-8-sig", newline="")))
    assert len(rows) == 210
    cols = [c for c in rows[0] if c != "second_reader"]
    return rows, cols


def h5_rows():
    neg = json.load(open(ATTR / "f2_negatives_frozen.json", encoding="utf-8"))
    rows, cmap = [], {}
    for q in neg["queries"]:
        prods = q["candidates"]
        for i, p in enumerate(prods):
            uid = f"esci:{q['query_id']}:{p['product_id']}"
            others = [j for j in range(len(prods)) if j != i]
            cid = cid_of("H5", uid)
            cmap[cid] = {"uid": uid, "speaker_index": i, "offer_numbers": {str(n): j for n, j in enumerate(others, 1)}}
            rows.append({"case_id": cid, "search_query": q["query"],
                         "other_offers": "\n".join(f"[{n}] {prods[j]['title']}" for n, j in enumerate(others, 1)),
                         "listing_text": p["text"]})
    assert len(rows) == 900 and len(cmap) == 900
    return rows, ["case_id", "search_query", "other_offers", "listing_text"], cmap

def compare_released(rels):
    """Print whether each output equals the released copy (line endings ignored)."""
    for rel in rels:
        mine, released = _OUT / rel, READING / rel
        same = released.exists() and mine.exists() and \
            mine.read_bytes().replace(b"\r\n", b"\n") == released.read_bytes().replace(b"\r\n", b"\n")
        print(("equal to released " if same else "DIFFERS from released ") + rel)


def main():
    picks = json.loads((READING / "round2/picks.json").read_text(encoding="utf-8"))
    r3 = json.loads((READING / "round2/answers_R3.json").read_text(encoding="utf-8"))["answers"]
    import score  # model-reader labels of the round-1 packet
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "1_calibration").mkdir(parents=True)
    (OUT / "2_full").mkdir()
    PRIV.mkdir(exist_ok=True)

    h1, h1_cols = h1_rows()
    h5, h5_cols, cmap = h5_rows()
    old_h5 = {r["case_id"] for r in csv.DictReader(open(READING / "csv_packet/H5.csv", encoding="utf-8-sig", newline=""))}
    assert old_h5 <= {r["case_id"] for r in h5}, "round-1 H5 case ids must be a subset of the 900"

    sets = {"H1": (h1, h1_cols), "H5": (h5, h5_cols)}
    calib_key, anchors, counts = {}, {}, {}
    for s, (rows, cols) in sets.items():
        qs = [q for q, _ in QUESTIONS[s]]
        out_cols = cols + [f"ANSWER_{q}" for q in qs] + ["NOTE"]
        cal_ids = [x["case_id"] for x in picks["calib"][s]]
        by = {r["case_id"]: r for r in rows}
        cal = [by[c] for c in cal_ids]
        for x in picks["calib"][s]:
            exp = dict(x["expected"])
            if s == "H5":
                if exp["about_other"] == "yes":
                    # target from the settled model-reader label, as an offer number
                    truth = json.load(open(ATTR / "reading/final_labels.json", encoding="utf-8"))["labels"]
                    m = cmap[x["case_id"]]
                    inv = {j: n for n, j in m["offer_numbers"].items()}
                    nums = sorted(inv[j] for j in truth[m["uid"]]["targets"])
                    exp["target"] = "both" if len(nums) == 2 else nums[0]
            calib_key[x["case_id"]] = {"set": s, "expected": exp, "why": CALIB_WHY[x["case_id"]]}
        write(OUT / "1_calibration" / f"calib_{s}.csv", cal, out_cols)

        rest = [r for r in rows if r["case_id"] not in set(cal_ids)]
        random.Random(f"{SEED}-{s}").shuffle(rest)
        k = PART[s]
        parts = [rest[i:i + k] for i in range(0, len(rest), k)]
        for n, part in enumerate(parts, 1):
            write(OUT / "2_full" / f"{s}_part{n}.csv", part, out_cols)

        # anchors: round-2 hidden checks, and round-2 sample cases where R3 and the model readers agreed
        for x in picks["gold"][s]:
            anchors[x["case_id"]] = {"set": s, "kind": "round2_check", "expected": x["expected"]}
        for c, a in r3.items():
            if not c.startswith(s + ":") or c in cal_ids:
                continue
            h, l = score.human_label(s, a), score.llm_label(s, score.KEY[c])
            if h == l:
                anchors[c] = {"set": s, "kind": "r3_model_agree", "expected": h}
        counts[s] = {"calibration": len(cal), "full": len(rest), "files": len(parts),
                     "anchors": sum(1 for v in anchors.values() if v["set"] == s)}

    with open(OUT / "answer_codes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["set", "column", "option_number", "code", "may_be_empty_when"])
        for s, qs in QUESTIONS.items():
            for q, codes in qs:
                cond = SKIP_IF.get((s, q))
                for n, code in enumerate(codes, 1):
                    w.writerow([s, f"ANSWER_{q}", n, code, f"ANSWER_{cond[0]} = {cond[1]}" if cond else ""])
    (PRIV / "case_map.json").write_text(json.dumps(cmap, ensure_ascii=False, indent=0), encoding="utf-8")
    (PRIV / "calib_key.json").write_text(json.dumps(calib_key, ensure_ascii=False, indent=1), encoding="utf-8")
    (PRIV / "anchors.json").write_text(json.dumps(anchors, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, indent=1))
    compare_released(["round3_packet/answer_codes.csv", "round3/case_map.json", "round3/anchors.json",
                      *[f"round3_packet/{p.parent.name}/{p.name}" for p in sorted(OUT.glob("*/*.csv"))]])


if __name__ == "__main__":
    main()
