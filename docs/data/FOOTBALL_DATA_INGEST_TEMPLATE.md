# Football-Data.co.uk Ingest Artifacts

Run privately:

```bash
uv run --python 3.12 python scripts/ingest_football_data_co_uk.py \
  --source-root /Users/liudehua/.hermes/data/w2/football-data-co-uk
```

The command writes source snapshots, closing AH facts, pre-closing AH facts, F5
dataset rows, phase market evidence, and coverage artifacts under the private
data directory. Raw CSV, ZIP, XLSX, and generated private JSONL artifacts are not
tracked in Git.

Football-Data `Date` and `Time` are kickoff fields only. Generated artifacts keep
`captured_at` as `null`, `capture_time_precision` as `SOURCE_PHASE_ONLY`, and
never label the evidence as `EXACT_CAPTURED_AT`.
