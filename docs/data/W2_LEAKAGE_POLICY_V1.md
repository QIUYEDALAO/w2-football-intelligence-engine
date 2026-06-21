# W2 Leakage Policy V1

Historical as-of samples must preserve what was visible at `as_of_time`.

Blocked leakage classes:

- future result leakage
- closing odds used before closing
- future lineup or injury updates
- future team ratings
- `provider_updated_at > as_of_time`
- `ingested_at` or `data_cutoff` after `as_of_time`
- the same fixture crossing train/validation/test
- random cross-time splits
- season-end information influencing earlier samples
- label fields entering feature payloads

Supported splitters:

- chronological
- rolling
- expanding
- walk-forward

Random splitting is forbidden for historical as-of datasets.
