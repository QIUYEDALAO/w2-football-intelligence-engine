# W2 Factor Model Remediation Master Task Context - 2026-07-21

## User Instruction

Run `W2 FACTOR-MODEL-REMEDIATION-MASTER`.

## Scope

This is an implementation remediation task, not another diagnostic-only report. Known gaps such as team identity, history, ratings, xG, F5, F8, LMM and calibration are the work list and must not be used as an early stopping reason.

Required outcomes:

- Create branch `codex/w2-factor-model-remediation-master` from the remote head of `codex/w2-analysis-recommendation-closure`.
- Create worktree `/Users/liudehua/.hermes/workspace/w2-factor-model-remediation-master`.
- Establish provider-primary W2 canonical team identity for the 16 Allsvenskan provider teams.
- Materialize canonical match history, ratings, and real xG where available.
- Prove or precisely block Allsvenskan xG/F5/F8 sources without proxies.
- Bind canonical factors to exact AH/OU quotes.
- Produce model probability, market devig probability, delta, EV, uncertainty, V3, manifests and acceptance package.
- Keep formal, lock, production, recommendation writes, OFFICIAL writes and cohort writes disabled.

## Safety Defaults

- Scheduler remains stopped.
- Provider calls default disabled.
- Provider calls may only be temporarily enabled for a controlled historical backfill/probe window with hard cap and quota checks.
- No production access.
- No model weight, threshold or factor changes.
- No raw provider payload or private data in Git.

## Allowed Final States

- `ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED`
- `ANALYSIS_CHAIN_XG_SOURCE_UNAVAILABLE`
- `ANALYSIS_CHAIN_MODEL_INPUT_REMEDIATION_REQUIRED`

Formal evidence may additionally remain:

- `FORMAL_EVIDENCE_EXTERNAL_DATA_PENDING`

## GitHub Synchronization

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Current branch before fork: `codex/w2-analysis-recommendation-closure`
- Context-only update: yes
- CI required: no
