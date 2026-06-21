# Historical Data Import Checkpoint

Stage 5A does not import real historical data.

Before any real import, BOSS must explicitly approve:

- selected provider/source registry entries
- licence and commercial-use status
- storage location and retention policy
- fixture/team/bookmaker provider ID mapping policy
- import date range and competition scope
- as-of snapshot phases
- quality thresholds
- rollback plan

The first real import must run offline against a bounded fixture subset and must
produce a new source coverage audit, manifest, quality run, leakage report, and
secret scan result.

No model training or recommendations are allowed at this checkpoint.
