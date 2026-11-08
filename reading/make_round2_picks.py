"""Round 2 of the human reading: calibration and hidden check cases, picked outside the 20% sample by the
model readers' label (seeded), then read one by one by the authors; ambiguous picks were replaced (SWAPS).
Writes <out>/round2/picks.json (never sent to readers) and compares it with data/live_hp/reading/round2/picks.json.
  python make_round2_picks.py --data <data/live_hp> [--out DIR]"""
import csv, json, random
from pathlib import Path
from _paths import OUT, READING
import score
from make_csv import QUESTIONS

HERE = Path(__file__).resolve().parent
WANT = {'calib': {'H1': [('adopted', 'no'), ('attributed', 'no'), ('not_mentioned', 'no')], 'H2': [('yes',), ('no',)],
                  'H2b': [('yes', 'yes'), ('no', 'no')], 'H3': [('yes',), ('no',)], 'H4': [('explicit',), ('implicit',)],
                  'H5': [('yes',), ('no',)], 'H6': [('unconditional', 'cheaper'), ('unconditional', 'more_expensive'), ('conditional', 'na')]},
        'gold': {'H1': [('not_mentioned', 'no'), ('attributed', 'no')], 'H2': [('yes',), ('no',)], 'H2b': [('yes', 'yes'), ('yes', 'yes')],
                 'H3': [('yes',), ('no',)], 'H4': [('implicit',)], 'H5': [('no',), ('no',)],
                 'H6': [('unconditional', 'cheaper'), ('unconditional', 'more_expensive')]}}
# replaced after reading: the first pick was ambiguous (see READING_NOTES in picks.json)
SWAPS = {('gold', 'H5', 1): 'H5:a809d07e18', ('gold', 'H6', 1): 'H6:a4994eb912', ('gold', 'H1', 1): 'H1:92ec986c07'}
READING_NOTES = {
    'H5:db2ed39cde': 'replaced: brand-wide claim ("Ultra Game NBA features...") may apply to a same-brand offer',
    'H6:62401b21ba': 'replaced: hedged recommendation, not unambiguous for a check case',
    'H1:1147cd1b28': 'replaced: mixes an own-voice sentence with "the vendor notes"',
}
rng = random.Random(20261106)
used, picks = set(), {'calib': {}, 'gold': {}}
for s, qs in QUESTIONS.items():
    rows = [r for r in csv.DictReader(open(READING / f'csv_packet/{s}.csv', encoding='utf-8-sig', newline='')) if r['second_reader'] == 'no']
    lab = {r['case_id']: tuple(score.llm_label(s, score.KEY[r['case_id']]).get(q) for q, _ in qs) for r in rows}
    for kind in ('calib', 'gold'):
        picks[kind][s] = []
        for i, t in enumerate(WANT[kind][s]):
            pool = [c for c in lab if lab[c] == t and c not in used]
            rng.shuffle(pool)
            c = SWAPS.get((kind, s, i), pool[0])
            used.add(c)
            picks[kind][s].append({'case_id': c, 'expected': dict(zip([q for q, _ in qs], t))})
picks['reading_notes'] = READING_NOTES
(OUT / 'round2').mkdir(exist_ok=True)
(OUT / 'round2' / 'picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding='utf-8')
print({k: sum(len(v) for v in d.values()) for k, d in picks.items() if k != 'reading_notes'})
print('[check] picks.json equal (as JSON) to released:',
      picks == json.loads((READING / 'round2' / 'picks.json').read_text(encoding='utf-8')))
