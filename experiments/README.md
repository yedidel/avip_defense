# Raw provider responses and ledgers

This directory holds the raw model responses and append-only ledgers behind
every measurement in the paper, one subdirectory per experiment.

Each experiment directory contains:

- **`ledger.jsonl`** — one JSON record per model call, in the order it was
  issued. Each record carries a deterministic `unit_id` (experiment, model, and
  scenario id), token counts, cost, the provider and model, and
  `response_sha256`, the SHA-256 digest of the exact raw response bytes. The
  ledger is the index: a table in the paper is reproduced by re-scoring the
  responses it points to, with no provider access.
- **`raw.zip`** — the raw provider responses, one JSON file per call, named by
  `unit_id`. Extract in place (`unzip raw.zip`) to get a `raw/` directory whose
  filenames match each ledger record's `response_path`. Verify integrity by
  hashing a file and comparing to the record's `response_sha256`.

Scoring is by family and follows the paper: vault leaks are read from the tool
call; branded, selection, and branded-factual hits are read from the
recommendation or the committed outcome. The reading, not the code, is the
authority for the reply-scored families; see the benchmark's `review.py` and
`loader/judges.py`.

Absolute paths that appeared inside a handful of logged error tracebacks have
been replaced with `<repo>` so the release carries no local filesystem detail.
