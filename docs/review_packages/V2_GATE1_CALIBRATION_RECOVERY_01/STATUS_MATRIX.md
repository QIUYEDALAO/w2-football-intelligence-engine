# V2-GATE1-CALIBRATION-RECOVERY-01 status matrix

| Requirement | Status | Evidence |
|---|---|---|
| protocol frozen before results | PASS | commit `577c4cc4`; protocol SHA `4f01820d...10b` |
| current corpus is a new experiment | PASS | 18,978/9,489 source; new corpus identity in `artifacts/CURRENT_XG_CORPUS.json` |
| no inferred missing xG fields | PASS | 176 rows excluded as `MISSING_OPPONENT_GOALS_RAW_HASH_EXACT_JOIN` |
| TRAIN denominator preserved | PASS | 3,118 = 2,684 scorable + 434 excluded |
| only TRAIN outcomes used | PASS | sealed mutation produces byte-identical artifacts |
| VALIDATION and HOLDOUT equally sealed | PASS | 4,520 / 2,628; no metrics emitted or read |
| current preprocessing identity | PASS | `c6530ef5...029e` |
| current feature identity | PASS | `9e514a36...de92` |
| F3/F7 only; F6 excluded | PASS | model artifact and frozen protocol |
| chronological four-block OOF | PASS | block 1 warmup; blocks 2-4 yield 2,133 OOF predictions |
| temperature chosen by TRAIN OOF NLL | PASS | `T=0.928709586`; no ECE/Gate selection |
| exact complete score matrix | PASS | 2,684 matrices, each 13x13 and sum 1 |
| ECE failure mechanism answered | PASS | REPORT §4; descriptive TRAIN OOF only |
| deterministic replay | PASS | `--check` and `--self-test-check` |
| sealed outcome mutation | PASS | every generated artifact byte-identical |
| TRAIN outcome mutation | PASS | model or calibration identity changes |
| source/protocol mismatch fail closed | PASS | nine exact source-file hash guards |
| Ruff / mypy | PASS | full Ruff; 299 `src apps` files and strict runner mypy |
| full pytest | BASELINE-EQUIVALENT | 2,971 passed / 5 failed / 9 skipped; same five failures reproduced at `cb8f5d22` |
| Gate 1 | **FAIL** | task cannot create confirmatory evidence |
| Gate 2 | **CLOSED** | no admission authority |
| forward confirmation | NOT STARTED | requires preregistration amendment before first row, then one-look evaluation |
| Provider / production R/W | PASS | `0 / 0 / 0` |
| deployment / migration / collector | PASS | `0 / 0 / 0` |
| candidate / notification | PASS | `0 / 0` |
| alpha / beta | PASS | `NULL / NULL` |

Terminal role: `PROSPECTIVE_CANDIDATE_IDENTITY_ONLY`.
