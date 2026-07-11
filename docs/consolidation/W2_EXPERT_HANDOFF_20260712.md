# W2 Expert Handoff — 2026-07-12

## Review objective

Review the current staging recommendation system after the optional-lineup and
validation-recommendation A–D sequence. Focus on decision-source consistency,
scoreline explanation semantics, validation/official/shadow isolation, and
staging release reliability. This is a review handoff, not authorization to
enable production, RECOMMEND, EV, locks, providers, leagues, or scheduler changes.

## Repository and runtime truth

- GitHub repository: `QIUYEDALAO/w2-football-intelligence-engine`
- GitHub main observed before this handoff PR: `c79d29283f1a0617f3e3abbd771c640ef0ca0265`
- Staging API/Web release: `493b4b6baf1fb42183a86183622aa3d65ec2cf39`
- Staging URL: `http://43.155.208.138/`
- Data profile/source: `real-db / read-model-db`
- Production deployment: no
- Current execution queue: A–D complete

Read these files in order:

1. `PROJECT_STATE.yaml`
2. this handoff
3. `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`
4. `docs/consolidation/W2_DECISION_CONTRACT_V2.md`
5. `docs/consolidation/W2_SELECTIVE_ANALYSIS_RECOMMENDATION_IMPLEMENTATION_20260710.md`
6. `docs/consolidation/W2_REVISED_ROADMAP_2026_07.md`

## Delivered sequence

| PR | Scope | Merge SHA |
| --- | --- | --- |
| #247 | Optional lineup enrichment contract | `794c37a` |
| #248 | FairMarketEstimate authority and legacy simulation isolation | `725df8d` |
| #249 | Validation recommendation freeze, settlement, and statistics isolation | `4d04133` |
| #250 | Dashboard validation/enrichment wording | `52a39e2` |
| #251 | Execution-queue closeout | `493b4b6` |
| #252 | Staging deployment acceptance record | `c79d292` |

Core invariants:

- `FairMarketEstimate` is the decision source for fair lines, direction,
  score distribution, and same-source settlement probability.
- `pricing_shadow.simulation` is
  `LEGACY_BASELINE_NOT_DECISION_SOURCE` and must not alter a visible pick.
- A declared missing or inconsistent FairMarketEstimate fails closed to WATCH.
- ANALYSIS_PICK is a validation recommendation: tracked, never lock eligible,
  and isolated from OFFICIAL and SHADOW outcomes.
- Lineups and player value are optional enrichment. Current player impact is
  `NOT_SUPPORTED`, `affects_estimate=false`, and `net_adjustment=0`.

## Current staging observation

Observed at `2026-07-11T16:52Z`:

- `/health`: PASS
- API/Web SHA: `493b4b6`
- future DayView: 32 cards
- decision tiers: WATCH 15, NOT_READY 17, ANALYSIS_PICK 0, RECOMMEND 0
- data status: PARTIAL 15, BLOCKED 17
- provider request logs: 381
- future refresh run audit: 1423
- Celery queue: 0
- scheduler container: `7e3dc0913f2a...`, unchanged
- worker container: `0019f0a8d961...`, unchanged

## Open finding: direction-consistent scoreline explanation

Fixture `1494207`, Orgryte IS vs BK Hacken, exposed a product-semantics bug:

- pick: `TOTALS / OVER 3.25 @ 1.93`
- FairMarketEstimate: `home_mu=1.2761135334`, `away_mu=2.3328932777`,
  `fair_line=3.5`, artifact `9fd99938...`
- displayed global score modes: `1-2 9.4% / 1-1 8.1% / 0-2 7.4%`
- same-source OVER 3.25 settlement distribution:
  - WIN (4+ goals): 48.67%
  - HALF_LOSS (3 goals): 21.21%
  - LOSS (0–2 goals): 30.12%
- direction-consistent top scorelines: `1-3 7.3% / 2-2 6.0% / 2-3 4.7%`

The data source is consistent; the UI meaning is not. It labels unconditional
global score modes as the explanation for an OVER direction. Recommended review:
keep global modes only if explicitly labelled, and add direction-conditioned
representative scorelines plus the five-way settlement distribution. Do not
replace the FairMarketEstimate or reintroduce legacy simulation.

## Open finding: staging API cold-start/restart seam

During the approved API/Web-only deployment of `493b4b6`:

1. API startup executed `uv run` dependency synchronization and took long enough
   to cross the health window.
2. Docker restarted the API twice in total before it stabilized.
3. nginx retained an obsolete API container address and returned temporary 502s.
4. Recreating Web after the API stabilized refreshed DNS and restored public
   `/health`, `/ready`, fixture, Dashboard, and DayView routes.

Final observed API state: healthy, restart count 2, stable start time
`2026-07-11T16:38:13Z`. Scheduler and worker identities did not change;
provider logs, refresh audit, and queue remained unchanged.

Recommended review:

- make runtime commands use the already-built environment without package sync;
- make API health start-period cover measured cold start or remove the cold sync;
- configure nginx for Docker DNS re-resolution or enforce API-stable-before-Web
  recreation in the release procedure;
- add a post-deploy stability window, not only a single successful probe.

## Evidence and validation

- Unit suite: 1065 passed
- All-stage suite: 1179 passed, 4 environment-dependent skips
- Web production build: PASS
- GitHub checks on #247–#252: verify, staging-parity, predeploy-e2e PASS
- Acceptance, tracked-output, Ruff, mypy, and secret scan: PASS

## Questions for expert review

1. Is using fair-line divergence alone sufficient to emit an OVER/UNDER
   validation direction when the same estimate's fair-line probabilities are
   close to 50/50, or should eligibility use selection-line expected settlement?
2. Should scoreline presentation expose both unconditional modes and
   direction-conditioned modes, or only the latter for visible picks?
3. Is the current FairMarketEstimate provenance consistency check strong enough
   to bind fair line, mu values, artifact, and feature-as-of to one immutable
   estimate?
4. Does `recommendation_scope=VALIDATION|OFFICIAL|SHADOW` adequately prevent
   historical and future performance leakage across tracks?
5. What is the smallest safe release change that removes API cold synchronization
   and nginx upstream staleness without touching scheduler or worker behavior?

## Non-authorizations

This handoff does not authorize provider calls, business database writes,
production deployment, league enablement, scheduler restart/reconfiguration,
EV/RECOMMEND activation, lock capture, settlement writes, or changes to Draft
PR #203.
