"""Build the human-reading packet (one self-contained HTML file) for every reader-dependent number in the
paper. Readers see only what the user saw (agent and user messages, thought parts excluded) plus the
listings; they never see a model's label. The LLM-reader labels are written to a separate answer key used
only by score.py after the humans finish.

  python build_packet.py --data <data/live_hp> [--out DIR]
    -> <out>/human_reading.html, answer_key_llm.json, packet_manifest.json, each compared with data/live_hp/reading/
Inputs (all in data/live_hp): cross_seller/ (H1), main/ (H2, H2b, H6), binding/residual/ (H3),
binding/adaptive/reading/ (H4), binding/attribution/ (H5).
"""
import hashlib
import json
import random
import re
import zipfile
from pathlib import Path

from _paths import DATA, OUT, READING

HERE = Path(__file__).resolve().parent
SEED = 20261105
SECOND_READER_SHARE = 0.2

E39 = DATA / "main"                  # main run (tag E39)
E41 = DATA / "cross_seller"          # cross-seller run (tag E41)
RESIDUAL = DATA / "binding" / "residual"
ADAPTIVE = DATA / "binding" / "adaptive"
ATTRIBUTION = DATA / "binding" / "attribution"
DEFER = "I'll go with the one you recommend"


def load(p):
    return json.load(open(p, encoding="utf-8"))


def traces(folder):
    """Every trace of one data folder, in file-name order (traces/ if extracted, else traces.zip)."""
    d = Path(folder) / "traces"
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            yield load(f)
        return
    with zipfile.ZipFile(Path(folder) / "traces.zip") as z:
        for n in sorted(x for x in z.namelist() if x.endswith(".json")):
            yield json.loads(z.read(n).decode("utf-8"))


def short_model(m):
    return {"google/gemini-3.1-flash-lite-preview": "flash-lite", "deepseek/deepseek-v4.1-flash": "deepseek",
            "openai/gpt-6.1-sol": "gpt", "google/gemini-4-argon": "argon",
            "anthropic/claude-sonnet-5.5": "claude"}.get(m, m)


def listings(d):
    out = []
    for c in d["carts"]:
        out.append({"label": c["item_label"], "price": c.get("amount")})
    return out


def visible_convo(trace, stop_at_call=None, stop_after_user=None):
    """Agent and user text turns in order (no thoughts, no tool payloads); tool calls shown as a one-line
    marker so readers see when a cart was selected or the mandate signed."""
    conv = []
    for e in trace:
        who = e["author"]
        for p in e["parts"]:
            if "thought" in p:
                continue
            if "text" in p and p["text"].strip():
                conv.append({"who": "user" if who == "user" else "agent", "text": p["text"].strip()})
                if stop_after_user and who == "user" and stop_after_user in p["text"]:
                    return conv, True
            elif "call" in p:
                name = p["call"]
                if name in ("select_cart", "create_checkout", "create_checkout_mandate"):
                    arg = p.get("args", {}).get("cart_id", "")
                    conv.append({"who": "event", "text": f"[{name}{(' ' + arg) if arg else ''}]"})
                if stop_at_call and name == stop_at_call:
                    return conv, True
    return conv, False


def summary_before_signing(trace):
    """The summary the user saw before signing: the last agent message before the user's last reply ahead of
    the mandate call. If the user did not reply after it, the last agent message before the call. (Taking
    simply the last agent message picks up "Thank you for confirming..." in some trials.)"""
    last_agent, before_user = None, None
    for e in trace:
        for p in e["parts"]:
            if "thought" in p:
                continue
            if "text" in p and p["text"].strip():
                if e["author"] == "user":
                    before_user = last_agent
                else:
                    last_agent = p["text"].strip()
            if "call" in p and p["call"] == "create_checkout_mandate":
                if before_user and "$" not in (last_agent or "") and "$" in before_user:
                    return before_user
                return last_agent
    return None


def selected_role(d, trace):
    """Role of the cart selected last before the checkout (an agent may select, then switch)."""
    by_id = {c["cart_id"]: c["role"] for c in d["carts"] if "cart_id" in c}
    role = None
    for e in trace:
        for p in e["parts"]:
            if "call" in p and p["call"] == "select_cart":
                role = by_id.get(p["args"].get("cart_id"))
            if "call" in p and p["call"] == "create_checkout":
                return role
    return role


cases, key = [], {}


def add(set_id, uid, payload, llm_label):
    cid = f"{set_id}:{hashlib.sha1(uid.encode()).hexdigest()[:10]}"
    payload.update({"set": set_id, "cid": cid})
    cases.append(payload)
    key[cid] = {"set": set_id, "uid": uid, "llm": llm_label, "model": payload.get("model", ""),
                "extra": payload.pop("_key_extra", None)}


# ---- H1: cross-seller claim trials (E41, X setting, claim arm), 210 ----
lab41 = load(E41 / "reading" / "final_labels.json")
for d in traces(E41):
    uid = d["uid"]
    if "X__claim" not in uid:
        continue
    conv, _ = visible_convo(d["trace"], stop_at_call="create_checkout_mandate")
    alt = next(c for c in d["carts"] if c["role"] == "alt")
    want = next(c for c in d["carts"] if c["role"] == "want")
    add("H1", uid, {"model": short_model(d["model"]), "listings": listings(d), "convo": conv,
                    "context": {"speaker": "Harbor Lane Supply", "speaker_item": alt["item_label"].split(" — ")[0],
                                "competitor": "Brightway Goods", "competitor_item": want["item_label"].split(" — ")[0]}},
        {k: lab41[uid].get(k) for k in ("merchant_sentence", "cross_seller_noted")})

# ---- H2 / H2b: main run (E39) ----
conf39 = load(E39 / "reading" / "final_confirm.json")
lab39 = load(E39 / "reading" / "final_labels.json")
dec39 = load(E39 / "reading" / "final_decision.json")
raw39 = {d["uid"]: d for d in traces(E39)}
for uid, d in sorted(raw39.items()):
    c = conf39.get(uid, {})
    # H2: claim arm, more expensive item signed, summary shown before signing -> does the summary mention the claim?
    if "__claim__" in uid and d.get("e_sel_role") == "alt" and c.get("summary_before_sign") == "yes":
        s = summary_before_signing(d["trace"])
        add("H2", uid, {"model": short_model(d["model"]), "listings": listings(d),
                        "convo": [{"who": "agent", "text": s or "(no summary found)"}]},
            {"sentence_in_summary": c.get("sentence_in_summary")})
    # H2b: default model, every trial -> summary and confirmation before signing?
    if "flash-lite" in uid:
        conv, _ = visible_convo(d["trace"], stop_at_call="create_checkout_mandate")
        sel_idx = next((i for i, x in enumerate(conv) if x["text"].startswith("[select_cart")), 0)
        add("H2b", uid, {"model": short_model(d["model"]), "listings": listings(d), "convo": conv[sel_idx:]},
            {k: c.get(k) for k in ("summary_before_sign", "user_confirmed")})
    # H6 (extended): every main-run trial -> did the agent pick before the user deferred?
    conv, found = visible_convo(d["trace"], stop_after_user=DEFER)
    add("H6", uid, {"model": short_model(d["model"]), "listings": listings(d), "convo": conv,
                    "_key_extra": {"selected_role": selected_role(d, d["trace"]), "arm": d["arm"]}},
        {k: dec39.get(uid, {}).get(k) for k in ("default_pick", "default_item")})

# ---- H3: ANNOTATE arm, default model, 70 ----
lab5 = load(RESIDUAL / "reading" / "final_labels.json")
seen = set()
for d in traces(RESIDUAL):
    uid = d["uid"]
    if not uid.startswith("E43F5ANN__google_gemini-3.1-flash-lite") or "__claim__" not in uid or uid in seen:
        continue
    seen.add(uid)
    conv, _ = visible_convo(d["trace"], stop_at_call="create_checkout_mandate")
    add("H3", uid, {"model": "flash-lite", "listings": listings(d), "convo": conv},
        {k: lab5.get(uid, {}).get(k) for k in ("provenance_relayed", "cross_seller_noted")})

# ---- H4: adaptive rewrites that passed the attributor, 15 ----
pk = load(ADAPTIVE / "reading" / "packet.json")
f6 = load(ADAPTIVE / "reading" / "final.json")
for it in pk["items"]:
    add("H4", it["chain_id"], {"model": "", "listings": [], "convo": [],
                               "rewrite": {"offers": it["offers"], "competitor": it["competitor_offer"],
                                           "speaker": it["speaking_offer"], "text": it["listing_text"]}},
        {"R1": f6["R1"].get(it["chain_id"]), "confirmed": it["chain_id"] in f6["confirmed_chain_ids"]})

# ---- H5: real listings: every listing any attributor flagged + 60 random unflagged ----
neg = load(ATTRIBUTION / "f2_negatives_frozen.json")
truth = load(ATTRIBUTION / "reading" / "final_labels.json")["labels"]
ledger = [json.loads(l) for l in open(ATTRIBUTION / "f2_allm_ledger.jsonl", encoding="utf-8")]
last = {}
for r in ledger:
    if r["set"] == "neg_esci":
        last[(r["model"], r["item_id"])] = r
by_att = {"deepseek": set(), "flash-lite": set()}
for (m, i), r in last.items():
    if r.get("status") == "ok" and not r.get("parse_error") and r.get("finish_reason") != "length" and r.get("targets"):
        by_att[short_model(m)].add(i)
off = load(ATTRIBUTION / "f2_offline.json")
by_att["A-LEX"] = {x["item_id"] for x in off["items"] if x["set"] == "neg_esci" and x["alex"]["flagged"]}
flag = set().union(*by_att.values())
items = {}
for q in neg["queries"]:
    prods = q["candidates"]
    for i, p in enumerate(prods):
        iid = f"esci:{q['query_id']}:{p['product_id']}"
        items[iid] = {"query": q["query"], "offers": [x["title"] for x in prods], "speaker_index": i,
                      "text": p["text"]}
# the original 60 random unflagged listings of the E43 reading: read listings that no attributor
# (including the old input scanner, B4) flagged
b4 = {x["item_id"] for x in off["items"] if x["set"] == "neg_esci" and x["b4"]["flagged"]}
orig_random = sorted(set(truth) - flag - b4)
assert len(orig_random) == 60, len(orig_random)
read_set = sorted(flag & set(items)) + orig_random
for iid in read_set:
    it = items[iid]
    add("H5", iid, {"model": "", "listings": [], "convo": [],
                    "esci": {"query": it["query"], "offers": it["offers"], "speaker_index": it["speaker_index"],
                             "text": it["text"]},
                    "_key_extra": {"flagged_by": sorted(a for a, v in by_att.items() if iid in v)}},
        {"targets": truth.get(iid, {}).get("targets") if isinstance(truth.get(iid), dict) else None})

# ---- order, second-reader subset, write ----
by_set = {}
for c in cases:
    by_set.setdefault(c["set"], []).append(c)
ordered = []
for s in sorted(by_set):
    lst = by_set[s]
    random.Random(f"{SEED}-{s}").shuffle(lst)
    k = max(1, round(SECOND_READER_SHARE * len(lst)))
    sub = set(random.Random(f"{SEED}-{s}-r2").sample(range(len(lst)), k))
    for i, c in enumerate(lst):
        c["r2"] = i in sub
        ordered.append(c)

data = json.dumps(ordered, ensure_ascii=False)
template = (HERE / "template.html").read_text(encoding="utf-8")
(OUT / "human_reading.html").write_text(template.replace("/*__DATA__*/[]", data), encoding="utf-8")
(OUT / "answer_key_llm.json").write_text(json.dumps(key, ensure_ascii=False, indent=0), encoding="utf-8")
manifest = {s: {"n": len(v), "second_reader": sum(c["r2"] for c in v)} for s, v in by_set.items()}
(OUT / "packet_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
print(json.dumps(manifest, indent=1), "\nbytes:", len(data))
for name in ("human_reading.html", "answer_key_llm.json", "packet_manifest.json"):
    a, b = (OUT / name).read_bytes().replace(b"\r\n", b"\n"), (READING / name).read_bytes().replace(b"\r\n", b"\n")
    print(f"[check] {name} equal to released {READING / name}: {a == b}")
