# W2 Single-Chain Convergence Task List

Status: `LOCAL_VERIFIED_PENDING_VPS_DEPLOY`

This task removes duplicate runtime authorities from fixture collection through public
recommendation. Work is local-repository to VPS only. GitHub, hosted CI, GHCR and manual
Provider probes are outside this task unless the Owner explicitly authorizes them later.

## Target chain

```text
Scheduler
  -> matchday_checkpoint_plans
  -> persisted fixture identity
  -> one Provider collection path
  -> raw payload / endpoint capture / capture-plan link
  -> market observations and lineup snapshots
  -> one analysis projection
  -> Recommendation Decision V4 / DecisionTier
  -> shadow candidate
  -> forward outcome ledger / result settlement
  -> unified dashboard read model
```

## Retained invariants

- API reads make zero Provider calls and zero business writes.
- The existing exact-13 competition authority is unchanged.
- Formal, Lock, Production and real-money execution remain off.
- Scheduler collection stays within the existing quota and cadence policy.
- Historical audit and outcome evidence is retained unless separately exported, hashed and
  approved for deletion.
- Independent xG Poisson, formal simulation and offline model evaluation remain separate,
  documented roles; they are not treated as duplicate recommendation authorities.

## Execution checklist

### SC-01 Collection producer convergence

- [x] Make the free-plan bridge fixture-discovery-only.
- [x] Remove its odds and lineup requests.
- [x] Remove its checkpoint plan transitions.
- [x] Remove its market-observation, lineup-snapshot and public-projection writes.
- [x] Preserve date-scoped fixture discovery until that capability is hosted by the canonical
      future-refresh path.
- [x] Move discovery into the canonical path and physically delete the bridge task/runtime.
- [x] Prove one producer owns each market capture and each checkpoint transition.

### SC-02 Checkpoint authority convergence

- [x] Redirect every next-refresh read to `matchday_checkpoint_plans`.
- [x] Prove public next-evaluation time equals the earliest applicable persisted plan.
- [x] Delete `future_refresh_checkpoint_plan`, its due reader and its status updater.
- [x] Retain historical checkpoint audit evidence.

### SC-03 Decision authority convergence

- [x] Stop creating new `recommendation_decision_v3` objects.
- [x] Keep a bounded read adapter only for genuinely historical V3 records.
- [x] Replace `RecommendationTier` consumers with `DecisionTier` / V4 outcome semantics.
- [x] Delete the deprecated enum and old candidate/formal validation mapping.
- [x] Prove one fixture produces one current decision identity.

### SC-04 Dormant runtime removal and public truth

- [x] Remove automatic market-timeline scheduling and the worker task.
- [x] Retain an explicit offline CLI only if it still has a verified research caller.
- [x] Remove the duplicate forward-ledger-after-timeline trigger.
- [x] Emit `simulations_completed=10000` only for a READY simulation; otherwise emit null.

### SC-05 Evidence and legacy product cleanup

- [x] Replace full-table outcome-ledger scans with database-filtered current-cohort reads.
- [x] Isolate imported historical ledger evidence without deleting it.
- [x] Archive required visual evidence, then delete Boss L1/L2, Dashboard V2 development routes,
      old acceptance code and their current-code tests.
- [x] Delete confirmed uncalled helpers such as `_poisson_score_matrix`.

### SC-06 Verification and deployment

- [x] Run focused unit, contract and integration suites for every cutover.
- [x] Run the single-public-authority and no-call-on-read guards.
- [x] Run Ponytail deletion/duplication review.
- [ ] Build locally, transfer local images/artifacts to VPS without GitHub/GHCR, and deploy.
- [ ] Verify exact API/Web source identity, health, quota, one scheduler and one collection writer.
- [ ] Verify a real persisted fixture from capture through market fact, V4 decision, shadow ledger,
      result/replay and dashboard, without a manual Provider probe.
- [ ] Update the W2 Obsidian vault only after deployed evidence is complete.
- [ ] Stop at Owner acceptance.

## Deletion order

Readers switch before writers stop; writers stop before code or tables are deleted. A phase does
not proceed while its replacement evidence is incomplete.
