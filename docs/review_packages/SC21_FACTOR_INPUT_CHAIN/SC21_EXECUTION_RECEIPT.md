# SC21 Execution Receipt

## Authority and release identity

- Gate: `OWNER_SC21_FACTOR_INPUT_CHAIN_POSTDEPLOY_REREVIEW`
- Local release commit: `635e9b54c2480ba2219c07632ad1ef60d9792b92`
- Local release tree: `4fa9a96d6f80aa761979d7775cf2a4a68ae2bd72`
- Local source manifest SHA-256: `c9f29beb530d068a1eca4f033427e32eefbb32387642fa60e1317b421abecc6e`
- Reproducible archive SHA-256: `07eb9975e4ea34a732367b72bad68e3d2f4bc3604de1d6ef2d5880f67f4127a6`
- Archive A/B byte comparison: `PASS`
- Web dist SHA-256: `2069700aeba88216fec02cc671a45f28cdaedc0de7dd50fad14948479cef59e8`
- Web build time: `2026-08-13T20:08:02Z`
- Source path: local clean commit -> `git archive` -> SCP -> VPS SHA-256 verification -> offline overlay build.
- GitHub, GitHub Actions, GitHub API and GHCR use: `0`

## Local verification

- Full Python: `2607 passed, 13 skipped, 2 warnings`
- Ruff: `PASS`
- MyPy: `PASS` (`279` source files)
- Web typecheck: `PASS`
- Web build: `PASS`
- Playwright contract suite: `60 passed`
- Architecture and canonical serialization guards: `PASS`
- Secret scan, tracked-output scan and repository hygiene: `PASS`

## VPS offline build and activation

- Previous API/Web source: `60a587180d54026e0f8d2537633448d89109e7f9`
- Python image: `127.0.0.1:5000/w2/python@sha256:69fadde3a55b7a8aa07d8a179c0eb9a27bbe7029e541e0a8891ef4ba43904584`
- Web image: `127.0.0.1:5000/w2/web@sha256:b37bbc7fc38341ac526c3e16a78b2cb9f6f747464f1af555f55e4ac3b88a148e`
- Python import-path/source smoke: `PASS`
- Web artifact/meta smoke: `PASS`
- Loopback registry manifest and exact-digest pull: `PASS`
- Warm switch: `PASS` in `33s` (target `<=300s`)
- API, Web, Worker and Scheduler exact source: `635e9b54c2480ba2219c07632ad1ef60d9792b92`
- API, Worker, Scheduler image ID: `sha256:69fadde3a55b7a8aa07d8a179c0eb9a27bbe7029e541e0a8891ef4ba43904584`
- Web image ID: `sha256:b37bbc7fc38341ac526c3e16a78b2cb9f6f747464f1af555f55e4ac3b88a148e`
- All four application containers: `running/healthy`
- Scheduler running count: `1`
- Alembic current/head: `MATCH`

## Postdeploy read and visual acceptance

- Public `/health`, `/ready`, `/v1/version`, `/meta.json`: `PASS`
- Provider request-log count around Dashboard read: `2369 -> 2369`
- Dashboard read contract: `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`
- Desktop 2026-08-14 screenshot SHA-256: `849f5ddbe396b80dcf994326e9cc4be89a183e276595de6397254a05fb42ef7b`
- Desktop 2026-08-15 settled-render screenshot SHA-256: `cda70c82c3832f6fd829dd9b92ae9358baee858e62d5f43af93541aaaf498787`
- Mobile 390px 2026-08-14 screenshot SHA-256: `70a78dc2fdbe703ed46b39f9f236770d46e9769d218c5f9f9102b509db4054a7`
- Public page horizontal overflow at all three viewports: `false`

## Postdeploy SC21 factor truth

- Current exact-13 T+7 fixtures: `36`
- Four-field xG READY: `9/36`
- Simulation READY: `9/36`
- Rating bilateral coverage: `8/36`
- Team Value bilateral coverage: `0/36`
- Due lineup READY: `0/36` (all audited fixtures were `NOT_YET_DUE` at the evidence time)
- AH current market READY: `0/36`
- OU current market READY: `0/36`
- AH exact quote READY: `0/36`
- OU exact quote READY: `0/36`
- Existing bookmaker-depth contract satisfied: `72/72` markets
- Current quote evidence outside the existing candidate-age contract: `72/72` markets
- Current Shadow Candidate ACTIVE: `0/36`
- Immutable historical Shadow Candidate records retained: `6`
- Decision V4 persisted outcomes: `ANALYSIS_PICK=6`, `NO_EDGE=3`, `NOT_READY=27`
- `BASELINE_PRIOR`: `9`

The `0` current candidates are accepted fail-closed output. No xG gate, quote-age contract,
bookmaker-depth contract, Decision V4 rule, cadence or model threshold was loosened to create
candidates. Existing forward records were not rewritten.

## Frozen stop lines

- Competition whitelist: exact `13`, unchanged
- Candidate: `SHADOW_ONLY`
- Formal: `OFF`
- Lock: `OFF`
- Production: `OFF`
- Round 4: `NOT_STARTED`
- P6 and real-money execution: `NOT_STARTED`

## Deferred Owner decisions

- Statistics/xG collection expansion remains disabled; see
  `XG_STATISTICS_COLLECTION_OWNER_DECISION_PACKET.md`.
- Team Value cannot be materialized from the existing 31,507 player valuations because the
  audited canonical roster/membership bridge is empty; see
  `TEAM_VALUE_MATERIALIZATION_OWNER_DECISION_PACKET.md`.
