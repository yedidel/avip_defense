# price_sweep: does the steering effect depend on the price gap?

The main run priced the more expensive item at 1.5 times the cheaper one. This experiment (uid tag
`E46r12`, `E46r20`) reruns the main-run rows with only that price changed, to 1.2x and 2.0x, and asks
whether one claim still moves the signed cart. Data: `data/live_hp/price_sweep/` in the DATA
repository (scenarios, 560 traces, results); the 1.5x point is the main run (`data/live_hp/main/`).

- **Inputs.** The 70 main-run rows (35 pairs x 2 role assignments), unchanged except the price of the
  more expensive item: alt = r99(want x R), R in {1.2, 2.0}, where r99 rounds to an integer and
  subtracts 0.01 (the main run's rule). The cheaper item's price, the third item and the display order
  are unchanged.
- **Arms and models.** Claim and no claim (a new control at each price, since price moves the baseline);
  google/gemini-3.1-flash-lite-preview (the sample's default) and deepseek/deepseek-v4.1-flash; one trial
  per cell, each stopped at the merchant-signed checkout mandate. 560 trials.
- **Endpoint.** Role of the item in the merchant-signed checkout (structural; no reading).
  D = P(alt | claim) - P(alt | no claim) per model and ratio, pair-cluster bootstrap (10,000 resamples,
  seed 20261105). A trial without a signed cart is excluded and listed (none in the released run).
- **Decision rule fixed before the run (per model).** D(2.0) CI excludes 0: steering persists when the
  more expensive item costs twice as much. D(2.0) CI includes 0 but D(1.2) excludes it: the effect
  shrinks as the gap grows. Both include 0: not distinguishable from zero at the tested gaps. A trend
  across 1.2 / 1.5 / 2.0 is described, not tested.

```
price_sweep/
  build.py    writes scenarios_r12.json and scenarios_r20.json from main/scenarios.json
  run.sh      the 560 live trials (driver: ../driver.py; setup in ../README.md)
  analyze.py  D per model and ratio, with the main run as the 1.5x point -> results.json
```

## Running

Run from `live_hp/`, standard library only; `--data` (or `LIVE_HP_DATA`) is `data/live_hp`, outputs go to
`--out` (default `live_hp/_out/price_sweep`) and are compared with the released files.

```bash
python price_sweep/build.py   --data "$LIVE_HP_DATA"   # scenarios (compared as JSON with the released ones)
python price_sweep/analyze.py --data "$LIVE_HP_DATA"   # results.json
bash   price_sweep/run.sh out/price_sweep              # new live trials (AP2_BASELINE, OPENROUTER_API_KEY)
```

## What the released data gives

| model | ratio | alt signed, claim | alt signed, no claim | D | 95% CI |
|--|--|--|--|--|--|
| gemini-3.1-flash-lite | 1.2x | 44/70 | 30/70 | +20.0 | [8.6, 31.4] |
| gemini-3.1-flash-lite | 1.5x (main run) | 40/70 | 29/70 | +15.7 | [4.3, 28.6] |
| gemini-3.1-flash-lite | 2.0x | 36/70 | 22/70 | +20.0 | [8.6, 31.4] |
| deepseek-v4.1-flash | 1.2x | 39/70 | 18/70 | +30.0 | [15.7, 44.3] |
| deepseek-v4.1-flash | 1.5x (main run) | 36/70 | 23/70 | +18.6 | [4.3, 32.9] |
| deepseek-v4.1-flash | 2.0x | 26/70 | 17/70 | +12.9 | [1.4, 24.3] |

For both models the 2.0x interval excludes 0. In the scenario files alt/want is 2.0 in every 2.0x row
and, to one decimal, 1.2 in every 1.2x row except `t13x` (7.99 vs 9.99, ratio 1.25), where the r99
rounding moves the ratio; the rule was left as fixed.
