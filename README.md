# W2 Football Intelligence Engine

Current status: W2 F1 hardening is merged and documented, but the visible
boss-view product is not finished. `main` contains the verified spine: unified
DecisionCard contract, `w2-matchday` mainline, controlled refresh planning,
DayView/L1/L2 dashboard skeletons, replay, offline acceptance, Pro provider data
sprint evidence, league-whitelist audit inventory, and model validation
evidence. The next material work is S14: build the real L1 boss-view dashboard
and run a World Cup live-flow proof under explicit safety gates.

The old stage scripts remain regression safety nets. The product operating
surface is `w2-matchday`, which produces one DecisionCard-shaped decision
surface per fixture in dry-run or controlled-run modes. Dashboard, replay,
reporting, and audit code read the Decision Contract surface instead of
reconstructing decision meaning from legacy fields.

Recommendation governance follows staging A / production B. `ANALYSIS_PICK` is
analysis-only and must carry `分析参考·非稳赢`; production actionability remains
stricter, and production lockable recommendations come only from `RECOMMEND`.
The online champion is still `BASELINE_PRIOR`; the fitted Understat model is
merged as offline evidence and is not the live champion yet.

League whitelist status is evidence-driven. The full whitelist scope is 14
competitions. Provider mapping and fixtures are 14/14 PASS under the league-id
anchor. The current odds truth matrix shows PASS for World Cup 2026, Brasileirao
Serie A, Chinese Super League, Allsvenskan, and Eliteserien; Argentina Primera
and MLS remain thin/secondary-odds candidates; the five major European leagues,
Eredivisie, and Primeira Liga require August near-kickoff confirmation.

No new league has been enabled during F1, no staging or production deployment
has been performed, and scheduler/live production loops remain off. Existing
`world_cup_2026` is the live-enabled exception recorded in the ledger. Use
`docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md` as the current handoff source.

## Quick Start

Install locked dependencies with Python 3.12:

```bash
make setup
```

Run local checks:

```bash
python3 scripts/check_w2_stage1_contracts.py
make lint
make typecheck
make test
make smoke
```

Run the historical data-model checks:

```bash
uv run python scripts/check_w2_stage3_data_model.py
```

Start local infrastructure when Docker is available:

```bash
make up
make down
```

Render Stage 1 example cards:

```bash
python3 scripts/render_ai_card_text.py examples/recommend/card.json
python3 scripts/render_ai_card_text.py examples/watch/card.json
python3 scripts/render_ai_card_text.py examples/skip/card.json
```

## Stage Boundaries

- Stage 1 Product Contract boundaries remain protected and covered by
  `scripts/check_w2_stage1_contracts.py`.
- Contract boundary phrase: W2 does not have real recommendation capability in
  production until a separate approved enablement/deployment step connects the
  validated model, live data path, and runtime controls.
- Stage 2 establishes runtime and delivery foundations.
- Stage 3 established football data identity, time, odds, persistence, and
  provenance foundations. It is now a foundation layer, not the current product
  status.
- F1 consolidation added Decision Contract V2, the matchday mainline,
  controlled refresh, dashboard DayView/L1/L2, replay, acceptance, league
  whitelist audit, Pro data evidence, and offline model validation.
- S14/F2/F3 work may enable staging or production only through a separate
  approved PR with provider, DB, scheduler, deployment, and rollback evidence.
- API keys must come from environment variables or a future secret manager.
- Example values in `.env.example` are placeholders and must not be used as real
  credentials.
