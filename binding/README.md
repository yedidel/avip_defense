# binding: decision-basis binding with an authority rule

Reference implementation of a decision-basis binding mechanism for the AP2
human-present flow, its integration into the live AP2 v0.2.0 sample shopping
agent, and the code that recomputes every measurement of it from the released
data. The data (scenarios, traces, model replies, reading labels) is in the
companion DATA repository under `data/live_hp/binding/`; every command below
takes `data/live_hp` as `--data` (or the `LIVE_HP_DATA` environment variable).

```
binding/
  mechanism/      W (capture), A (attribution: A-LEX, A-LLM), authority rule + policies, R (record), verifier
  tests/          offer-identity cases (F3) and A-LLM request/parse tests; no model calls
  attribution/    F2 sets and attributor runs, F6 adaptive attacker against the attributor
  replay/         F4 offline replay of recorded traces through W + A-LEX + R + verifier
  live/           the mechanism inside the live flow (inflow.py), scenario builders, run scripts, analyses
  reading/        reading packets, reader-label merging and adjudication
  strengthen/     honest-seller cost of ANNOTATE, tightened attributor (A-LLM v2), off-the-shelf injection
                  detectors, overhead, ANNOTATE composed with the measured attributor (see strengthen/README.md)
  live_defenses/  ANNOTATE with the live attributor in the flow, and HARDEN in every agent (see live_defenses/README.md)
  _common.py      data location, trace access, Wilson CI, output checks
  _openrouter.py  minimal OpenRouter client for the scripts that call models (f2_allm, f6_adaptive)
```

The bounded TLA+ model of the mechanism is `../tla/DecisionBinding.tla`
(results and how to run TLC in `../tla/README.md`). The live-flow driver that
runs trials with the mechanism in place is `../live_hp/driver.py`
(`--defense`, `--attributor`, `--harden`, `--harden-all`; see `../live_hp/README.md`).

## The mechanism

The property it serves, stated without reference to the mechanism: *a statement
about offer o can change which offer is signed only if its speaker is
responsible for o, or the user saw the statement together with its speaker.*

1. **Capture W** (`mechanism/capture.py`). Non-LLM code on the shopping-agent
   provider's side of the merchant calls. It records every offer the merchant
   returned, in order (cart_id, seller, raw label, amount, currency), and
   hashes the list (SHA-256 over canonical JSON). It is the only source of the
   candidate set; the agent never reports the candidates. An offer is
   identified by the pair (seller, cart_id), never by its title. AP2 v0.2.0's
   `Cart` has no seller field, so `build_capture` takes the seller as a
   structured input; `capture_from_carts` parses it from the harness label
   convention `"<title> — Sold by <seller>"` for replaying recorded traces only
   (a parsed seller is seller-controlled text; `tests/test_identity.py` shows
   it can be spoofed). In the live flow W wraps both the search call and the
   checkout call (`live/inflow.py`), because merchant text reaches the agent
   again through the checkout response (channel analysis in the data,
   `binding/replay/channels.md`).
2. **Attribution A** (`mechanism/attribution.py`). For each offer's listing
   text, A finds statements about another offer in the same candidate set and
   records (speaker offer, target offer). Two attributors:
   - **A-LEX v1**, code only: a sentence attributes a claim to offer j if it
     contains j's brand (or the first content token of j's title), or an
     adjacent pair of j's title tokens, where at least one of those tokens is
     distinctive to j (not in the speaker's own title and not a seller-name
     token). The exact rule is in the module docstring; the tokenizer and
     sentence splitter are in `mechanism/text.py`.
   - **A-LLM v1**: a frozen prompt (`A_LLM_PROMPT_V1`, SHA-256 of system +
     prompt `7b2af7b4...621d`) sent at temperature 0; the model answers with
     JSON `{"targets": [{"target_index": k}]}`. `build_request` returns the
     exact request and `parse_response` parses the reply; the package itself
     makes no network call (the live integration and `attribution/f2_allm.py`
     supply the transport). A reply cut off at the token limit or that does
     not parse carries no decision and is never read as "no claim".
3. **Authority rule** (`mechanism/authority.py`). A claim is authoritative iff
   the speaker's seller equals the target's seller (the merchant answers for
   its own inventory and pricing). An attributed target is expanded to every
   candidate with the same normalized title, so seller A cannot make a claim
   about B's item authoritative by listing a copy of it. Non-authoritative
   claims are handled by one of two policies, applied to what the agent reads
   (W and R keep the raw label):
   - **STRIP**: every sentence carrying a non-authoritative claim is removed
     (with A-LLM, which gives no sentence span, the offer's whole free text);
   - **ANNOTATE**: the label is kept and a provenance note is appended once per
     (speaker, target): `[Marketplace note: the statement above about {WANT}
     was made by {SPEAKER}, which does not sell that item. The marketplace has
     not verified it.]`.
   Authoritative claims (a seller about its own offers) are kept and recorded.
4. **Decision record R** (`mechanism/record.py`). The candidate digest, the
   digest of the labels the agent was shown, the policy, the attributor, the
   chosen offer as a (seller, cart_id) key, every attributed claim with speaker,
   target, sentence hash, authority status and action, and whether the user
   confirmed. Its SHA-256 over canonical JSON is the value to bind into the
   checkout flow.
5. **Verifier V** (`mechanism/verifier.py`). A third party that already checks
   the mandate chain (credentials provider or payment processor) checks R
   against W's capture:
   V1 candidate digest; V2 the chosen offer is a captured (seller, cart_id)
   key; V3 claim keys are distinct captured keys; V4 authority status equals
   the rule; V5 action matches the policy; V6 the presented-label digest equals
   the policy applied to the capture; V7 (with an attributor) re-running
   attribution gives the same claims.

## The measurements

Each sub-experiment measures one assumption the property rests on, or what the
rule leaves by design. Identifiers (F0-F6) match the uid tags of the traces
(`E43F0`, `E43F1`, `E43F5ANN`, `E43F5SELF`, `E43F5HARD`, `E43F6`). Every model
reply that carries a verdict was read by two independent readers; code only
counts reader labels and structural fields (the role of the merchant-signed
cart, the mechanism's own records).

| ID | Measurement | What is measured | Data (`data/live_hp/binding/`) |
|---|---|---|---|
| F0 | integration | the mechanism (W on search and checkout, A-LLM, STRIP, R, verifier) inside the unmodified live AP2 sample: 20 trials (flash-lite agent, 5 pairs x 2 role assignments x claim/no-claim); capture, checkout binding, verifier verdicts, latency added, R size | `integration/` |
| F1 | mediation | which channels carry merchant text to the agent's model (code analysis of the sample), plus 10 live trials whose listing tells the agent to search again or to ignore the other results | `replay/channels.md`, `integration/` |
| F2 | attribution | A-LLM (two models), A-LEX and the A-VIP input scanner (B4) on constructed claims with known targets (cross-seller and held-out claims, brand aliases) and on negatives: the frozen self-claims, a seller's notice about its own item, and 900 real listings from the ESCI dataset, whose ground truth two readers decided | `attribution/`, `self_claims/` |
| F3 | identity | constructed cases: same title under two sellers, same seller with two ids, a copy of a competitor's item, spoofed seller text, tampered records | `replay/f3_identity_tests.txt` |
| F4 | utility replay | every recorded main, cross-seller and held-out trace (1,960) replayed offline through W + A-LEX + STRIP + R + verifier: false flags on no-claim traces, recall on claim traces, verifier rejections, R size | `replay/` |
| F5 | residual arms | 840 live trials in the cross-seller X setting (3 models x 70 rows): ANNOTATE (claim + provenance note), SELF (the claim replaced by a positive statement about the speaker's own item, all the authority rule leaves an attacker), HARDEN (one added line in the agent's prompt, claim and no-claim). D = P(alt \| arm) - P(alt \| control), pair-cluster bootstrap | `residual/` |
| F6 | adaptive attacker | two attacker models rewrite each of the 16 claim framings, seeing the attributor's full prompt and its verdict, for up to 5 rounds; readers decide whether a text that passes still disparages the competitor; each confirmed evasion is then run live (3 models x 2 repetitions) | `adaptive/` |

## Setup

```bash
pip install pytest                       # tests
pip install pyarrow pandas               # build_f2.py only (reads the ESCI parquet files)
pip install -r ../requirements.txt       # f2_offline.py only (the B4 scanner and its SBERT model)
export LIVE_HP_DATA=/path/to/repo_ap2_whisperbench/data/live_hp
```

All other scripts need only the Python standard library (3.10+). Run them from
this folder (`binding/`). Scripts write to `--out` (default `binding/_out/`),
never into the data folder, and where the data holds a released copy of an
output they compare their own output with it and print the result
(`[check] ... True`). On Windows, set `PYTHONIOENCODING=utf-8` when printing.

## Recomputing every table from the released data

No command in this section calls a model or the network.

```bash
# F3 identity cases and the A-LLM request/parse tests
python -m pytest tests -v -p no:cacheprovider

# F2 attribution: A-LLM recall / false flags (reader ground truth), A-LEX and B4 rows
python attribution/f2_summary.py --data "$LIVE_HP_DATA"
python reading/f2_merge.py       --data "$LIVE_HP_DATA"    # reader agreement and ground truth on real listings
python reading/self_claims_merge.py --data "$LIVE_HP_DATA" # the two readers' check of the frozen self-claims
python attribution/f2_offline.py --data "$LIVE_HP_DATA"    # A-LEX and B4 on the F2 sets (needs ../requirements.txt and the SBERT model)
python attribution/build_f2.py   --data "$LIVE_HP_DATA" --positives-only   # rebuilds f2_positives.json

# F4 utility replay over the main, cross-seller and held-out traces
python replay/f4_replay.py --data "$LIVE_HP_DATA"

# F0 integration and F1 live mediation (structural tallies of the mechanism's records)
python live/analyze_integration.py --data "$LIVE_HP_DATA"

# F5 residual arms: D per arm and model, then the reading
python live/analyze_f5.py          --data "$LIVE_HP_DATA"
python reading/f5_merge.py         --data "$LIVE_HP_DATA"   # agreement per field, disagreements
python reading/f5_adjudicate.py    --data "$LIVE_HP_DATA"   # final labels, open items, reading tallies
python reading/f5_packets.py       --data "$LIVE_HP_DATA"   # the packets the readers labelled

# F6 adaptive attacker: chain outcomes, reader merge, evasion rate; then the live check
python reading/f6_merge.py         --data "$LIVE_HP_DATA"
python live/analyze_f6_live.py     --data "$LIVE_HP_DATA"
```

What the released data gives (all reproduced by the commands above):

- **F2.** A-LLM deepseek-v4.1-flash: held-out positives 133/140 with the
  correct target (0.95, Wilson 95% CI [0.90, 0.98]), brand-alias claims 49/56,
  cross-seller positives 67/70, 0/70 self-claims and 0/70 own notices flagged,
  false flags on real listings 18/900 = 2.0% [1.3, 3.1] (reader ground truth).
  A-LLM gemini-3.1-flash-lite: 120/140, 36/56, 62/70, 0/70, 0/70, 36/900 = 4.0%.
  A-LEX: 58/70 cross-seller cells (17/28 brand-alias), 150/900 false flags on
  real listings. B4 flags 665/900 real listings, 654 of which make no statement
  about another offer. Readers: agreement on targets 761/767, 6 adjudicated;
  18 listings make a statement about another listed offer (1 of the 60
  unflagged controls). Six deepseek replies cut off at the token limit were
  re-run and are not counted.
- **F3.** 11/11 identity cases pass.
- **F4.** All 1,960 recorded captures equal the recorded tool responses. No
  false flag on any no-claim trace (350 main, 420 cross-seller). A-LEX recall
  with the correct target: 58/70 main cells, 58/70 per cross-seller setting,
  116/140 held-out cells (brand-alias pairs 17/28, 17/28, 34/56). The
  verifier accepts every signed trace; the one unsigned no-claim trace fails V2.
- **F0/F1.** 30/30 trials signed with the checkout bound to the captured offer
  (cart_id, label, amount, signed title) and the record accepted by the
  verifier; every search captured (including trials with 2 or 3 searches);
  claim detected in 9/10 claim trials (the miss names the competitor by a
  brand alias), no flag in 10/10 no-claim trials. The
  "ignore the other results" directive was stripped 5/5; the "search again"
  directive (about the speaker's own item) was kept 5/5. Seconds added per
  search: median 3.5 (F0) and 4.0 (F1), max 17.6; R is 379-588 bytes.
- **F5.** D in points [95% CI], 35 pairs per model:

  | model | D_X (no defense) | D_ANNOTATE | D_SELF | D_HARDEN | D_X - D_ANNOTATE |
  |---|---|---|---|---|---|
  | gemini-3.1-flash-lite | +17.1 [7.1, 27.1] | -2.9 [-15.7, 8.6] | +14.3 [5.7, 24.3] | +15.7 [1.4, 30.0] | +20.0 [11.4, 28.6] |
  | deepseek-v4.1-flash | +15.7 [2.9, 27.1] | -17.1 [-25.7, -8.6] | +14.3 [4.3, 25.7] | -8.6 [-17.1, 0.0] | +32.9 [22.9, 42.9] |
  | gpt-6.1-sol | +7.1 [-2.9, 17.1] | -10.0 [-17.1, -4.3] | -2.9 [-8.6, 2.9] | +1.4 [-5.7, 10.0] | +17.1 [8.6, 27.1] |

  Reading: all 840 trials read by two readers; the read choice equals the
  signed cart in 840/840; 52 trials adjudicated, no open item. Under ANNOTATE
  the agent relayed the provenance to the user in 5 (flash-lite), 64
  (deepseek) and 35 (gpt) of 70 trials.
- **F6.** grok-4.7 declined all 16 chains. qwen3.8-max: 15 of 16 chains passed
  the attributor (one at round 0, the rest within 2 rounds); both readers agreed
  on all 15 and confirmed 12 that still disparage the competitor (2 explicitly,
  10 implicitly). Evasion rate 12/16 = 75% [51, 90] for the attacker that
  attacked, 12/32 = 38% [23, 55] counting the declined chains as failures.
  Live check, P(alt) with the evasion vs the same pairs' cross-seller X-claim
  and X-noclaim: flash-lite 18/24 vs 7/12 and 3/12; deepseek 9/24 vs 6/12 and
  2/12; gpt 1/22 vs 4/12 and 1/12 (two gpt trials reached no signed checkout
  and carry no decision).

## Rebuilding the inputs

The scenario builders regenerate the released scenario files byte for byte
from released inputs (each prints the comparison):

```bash
python live/build_f1.py --data "$LIVE_HP_DATA"   # -> integration/scenarios_f1.json (also prints the F0 pair list)
python live/build_f5.py --data "$LIVE_HP_DATA"   # -> residual/scenarios_f5_{annotate,self,harden}.json
python live/build_f6.py --data "$LIVE_HP_DATA"   # -> adaptive/scenarios_f6.json (from the chains and the reader-confirmed list)
```

The F2 negative set is a frozen sample of the Amazon ESCI Shopping Queries
Dataset (Apache-2.0, <https://github.com/amazon-science/esci-data>), which is
not redistributed beyond the 900 listing texts used. With the dataset's
`shopping_queries_dataset_examples.parquet` and
`shopping_queries_dataset_products.parquet`:

```bash
python attribution/build_f2.py --data "$LIVE_HP_DATA" \
    --esci-examples shopping_queries_dataset_examples.parquet \
    --esci-products shopping_queries_dataset_products.parquet
```

This rebuilds `f2_negatives_frozen.json` and `f2_positives.json` and checks
their hashes against `f2_hashes.json`, which were recorded before any model was
called. The self-claims (`self_claims/self_claims_frozen.json`) were written by
a fixed rule (one positive statement about the speaker's own item per framing,
never naming or implying another offer) and frozen before the SELF arm ran.

## Rerunning the model-dependent parts

These call models through OpenRouter (`OPENROUTER_API_KEY`) and produce new
model outputs; the released replies and traces are the record the tables are
computed from.

```bash
python attribution/f2_allm.py --data "$LIVE_HP_DATA" --out out/f2      # A-LLM on the F2 sets (2 models, ~2.5k calls)
python attribution/f6_adaptive.py --data "$LIVE_HP_DATA" --out out/f6  # 32 attacker chains
```

The live trials use the driver in `../live_hp/` (setup in
`../live_hp/README.md`: AP2 sample checkout, routing hook, `AP2_BASELINE`,
`OPENROUTER_API_KEY`, `LIVE_HP_DATA`):

```bash
bash live/run_f0_f1.sh out/integration   # F0 (20) + F1 (10), mechanism in the flow (STRIP, A-LLM)
bash live/run_f5.sh    out/residual      # F5: ANNOTATE, SELF, HARDEN, 3 models, 840 trials
bash live/run_f6.sh    out/adaptive      # F6 live check, 72 trials
```

With `--defense`, the driver loads `live/inflow.py`, which replaces the
shopper's `find_products` and the root agent's `create_checkout` tools with
wrappers that keep their names, signatures and docstrings: the search wrapper
captures, attributes, applies the policy and returns the presented labels; the
checkout wrapper binds the checkout's cart_id, label, amount and signed title
to the captured offer (a mismatch stops the trial), builds R, runs the verifier
and returns only the fields the agent needs. Everything the mechanism produced
is stored in the trace's `e43` field.

## Notes

- The A-LEX rule was written after looking at the scenario format and before
  any F2 or F4 output, and was not changed after seeing outputs. One fix was
  made to the replay label parser (`capture.parse_label`) after the first F4
  run: its title/claim split failed when a title ended in "…" or a full-width
  bracket, or when the claim started with a digit, so the claim was read as part
  of the speaker's own title. After the fix, 1164 of 1170 scenario labels parse
  to their true title; the 6 that do not are one ESCI filler title that itself
  contains ". Ships UPS". The released F4 outputs are from the fixed parser.
- STRIP works at sentence level with A-LEX; a sentence that only implies the
  other half of a claim ("... is the mapped continuation for the line") names
  no target and stays.
