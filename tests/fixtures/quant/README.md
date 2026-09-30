# Frozen F0 display labels

`official_148_display_labels.json` is a byte-for-byte copy of the trusted
`W2_OFFICIAL_148_RAW_20260909/_raw_official_recommendations.json` archive. Its
SHA-256 is `7e6bcbdc2baf4d8b255d8dbd79a907aa107d4536a642c13465b7828fd0b37110`,
which is the existing `EXPECTED_LABELS_SHA256` in the frozen F0 runner. The pin,
frozen bundle, models and research calculations are unchanged. F0 consumes this
auxiliary file only for team display labels. This tracked copy removes the
Mac-only absolute path from required Linux tests.
