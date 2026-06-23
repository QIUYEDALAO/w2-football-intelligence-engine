# W2 Gate0 Legacy Closure Audit

Generated at: `2026-06-23T16:26:59Z`

## Scope

This audit is W2-owned evidence for Master Phase 0 / Gate0. W1 was treated as read-only. No W1 checkout, reset, stash, clean, fetch, pull, tag, commit, or push was performed. No W1 sensitive runtime/config material was read, copied, or hashed.

## W1 Repository Verification

- Expected W1 path: `/Users/liudehua/.openclaw/workspace/w1-world-cup-engine`
- Expected path found: `False`
- Actual audited W1 path: `/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`
- Repo root: `/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`
- Branch: `w1-scout-reframe-review-c5a4d09`
- HEAD: `e92ffb119540797c7025007e492db73b66059288`
- Remote:
  origin	git@github.com:QIUYEDALAO/w1-world-cup-engine.git (fetch)  
origin	git@github.com:QIUYEDALAO/w1-world-cup-engine.git (push)
- `git status --short`:
  M README.md
  ?? W1_LEGACY_STATUS.md
  ?? data/results/world_cup_2026_results.json
  ?? docs/W1_LEGACY_CHANGE_POLICY.md
  ?? docs/W1_LEGACY_FREEZE_REPORT.md
  ?? reports/P0_BASELINE_SUMMARY.md
  ?? reports/W1_SCOUT_MEMORY_AND_TELEMETRY_TASKS.md
  ?? reports/W1_SCOUT_REFRAME_TASKS.md
  ?? reports/legacy_baseline/
  ?? reports/legacy_classification/
  ?? reports/legacy_decisions/
  ?? scripts/audit_w1_odds_collection_continuity.py
  ?? scripts/build_w1_legacy_decision_register.py
  ?? scripts/check_w1_legacy_baseline.py
  ?? scripts/check_w1_legacy_classification.py
  ?? scripts/check_w1_legacy_decisions.py
  ?? scripts/check_w1_legacy_freeze.py
  ?? scripts/classify_w1_legacy_files.py
- `w1-legacy-final` tag present: `False`
- `W1_LEGACY_STATUS.md` exists in working tree: `True`
- `W1_LEGACY_STATUS.md` tracked: `False`
- Tracked file count: `355`

## Checker Baseline

- Python version observed: `Python 3.9.6`
- Dependency lock/config hashes: `[]`

Checker results:

- `python3 scripts/check_w1_legacy_baseline.py`: exit=1 stdout=<empty>
- `python3 scripts/check_w1_legacy_classification.py --baseline reports/legacy_baseline/2026-06-21 --classification reports/legacy_classification/2026-06-21`: exit=1 stdout=<empty>
- `python3 scripts/check_w1_legacy_decisions.py --classification reports/legacy_classification/2026-06-21 --decisions reports/legacy_decisions/2026-06-21`: exit=0 stdout=W1 Legacy decisions check PASS: reports/legacy_decisions/2026-06-21
- `python3 scripts/check_w1_legacy_freeze.py`: exit=0 stdout=W1 Legacy freeze check PASS

The W1 freeze and decision checks pass, but baseline and classification checks fail because the current W1 HEAD differs from the recorded legacy baseline HEAD. This prevents Gate0 closure.

## Known Asset Locations

- Dashboard output: `reports/dashboard/`, including `reports/dashboard/W1_VISUAL_DASHBOARD.html` and `reports/dashboard/assets/w1_dashboard_data.json`.
- Model/config/threshold assets: `config/`, `reports/legacy_baseline/2026-06-21/08_MODEL_AND_POLICY_MANIFEST.json`.
- Match cards: `data/processed/match_cards/`, `reports/match_previews/`.
- Odds assets: `data/local_odds/`, `data/odds_snapshots/`, `reports/legacy_decisions/2026-06-21/10_ODDS_COLLECTION_CONTINUITY_AUDIT.json`.
- Results: `data/results/`, `reports/legacy_baseline/2026-06-21/09_DATA_ASSET_MANIFEST.json`.
- Logs/state: `logs/`, `state/`.

## SHA256 Manifest

- Manifest path: `reports/W2_GATE0_W1_SHA256_MANIFEST.json`
- Non-sensitive tracked files hashed: `355`
- Sensitive-looking tracked paths excluded without content reads: `0`

## Asset Classification Coverage

- Classification path: `reports/W2_GATE0_W1_ASSET_CLASSIFICATION.json`
- Classified or excluded tracked files: `355`
- Summary:
- ARCHIVE: 8
- DELETE_LATER: 12
- MIGRATE_DATA: 110
- PORT: 25
- REFERENCE: 200

Every current `git ls-files` path is either classified into `PORT`, `REFERENCE`, `MIGRATE_DATA`, `ARCHIVE`, `DELETE_LATER`, or explicitly excluded as a sensitive-looking path without reading content.

## Backup Verification

Candidate evidence:

- `reports/legacy_baseline/2026-06-21/11_SHA256SUMS.txt` exists=True sha256=3904fd3109e941d568151206a766bd00369021d4fb8bbd85e05a86ae8216bda6
- `reports/legacy_baseline/2026-06-21/13_RESTORE_AND_VERIFY.md` exists=True sha256=144753292580e2eb5756fb008019461d4bd879ddddb786eb010fc1715b1331b5
- `reports/legacy_baseline/2026-06-21/00_BASELINE_METADATA.json` exists=True sha256=91acc85696d0a4f6d1442be2b4149d8c85dc9e8eee21ceaf7aac747a7c3f33d1
- `reports/legacy_baseline/2026-06-21/09_DATA_ASSET_MANIFEST.json` exists=True sha256=24e05b7c6a8f47dac2d74ad508214270c93e8e7a6a418b45cf6c89c25dab7626
- `reports/legacy_baseline/2026-06-21/10_DASHBOARD_MANIFEST.json` exists=True sha256=9805bb5402ea290200a5c69a351e278a75ec2282f8fe05de3e0a93edd51194d8

The legacy baseline contains checksum and restore notes, but a complete current W1 backup cannot be verified because the current W1 HEAD differs from the recorded baseline HEAD, the legacy tag is missing, and the W1 worktree is not clean. Therefore `FULL_W1_BACKUP_NOT_VERIFIED` remains active.

## Unresolved Blockers

- `EXPECTED_W1_PATH_NOT_FOUND`: user-provided hyphenated path was absent; audited existing underscore W1 path instead.
- `W1_TAG_W1_LEGACY_FINAL_MISSING`
- `W1_WORKTREE_NOT_CLEAN`
- `W1_LEGACY_STATUS_UNTRACKED`
- `W1_CURRENT_HEAD_DIFFERS_FROM_LEGACY_BASELINE_HEAD`
- `FULL_W1_BACKUP_NOT_VERIFIED`

## Gate0 Recommendation

`Gate0` must remain `PARTIAL`. The current audit improves evidence coverage for tracked-file SHA256 and classification, but tag, clean freeze status, tracked legacy status, and full backup verification are not complete.
