# W2 Replay Evidence deployment receipt

Collected in UTC on 2026-09-07.

## Independent acceptance

- Candidate commit: `b0cea180b100085d971a52930b28ffb45adbd8fa`; parent baseline: `f0eab4a59ab30dc9be52ddac402cf3251f3a3683`.
- Manifest inputs: all 12 listed hashes matched before deployment.
- Directed replay/settlement/ledger tests: 192 passed; Ruff and `git diff --check` passed.
- Linux/PostgreSQL migration and replay check: `LINUX_POSTGRES_REPLAY_ACCEPTANCE=PASS`, schema `0070_notification_delivery_routing`.
- API isolated check reached `READY` with database, Redis, schema, mounts, and four artifact hashes; `/v1/version` requires the production competition whitelist and was therefore not claimed as an isolated contract pass.

## Build and deployment

- Python registry digest: `sha256:316d1ab43fdd165733057b5c694d17f760e305a37fb520d457e2a3602bdc2e16`.
- Web registry digest: `sha256:7bd7127ea8c41104542e083e616c9b2beb89d469526bbd53b55b491bc8aca0ea` (amd64; bundle unchanged from production, metadata/revision corrected).
- Database backup: `/opt/w2/backups/predeploy-b0cea180-20260907T211039Z.dump`, SHA-256 `b30bf5b5b91ba77383e54f787cfb82f0ad3e0270f468998a20f7598890527d33`.
- Previous release configuration: `/opt/w2/shared/releases/release-pre-b0cea180.env`.
- First activation auto-rolled back due to an arm64 Web image; rollback passed in 45 seconds. No database migration or business write occurred.
- Corrected activation: `WARM_SWITCH=PASS`, 52 seconds; subsequent Web metadata correction: `WEB_WARM_SWITCH=PASS`, 26 seconds.
- Release record: `/opt/w2/shared/releases/b0cea180b100085d971a52930b28ffb45adbd8fa.json`.

## Online technical acceptance

- API `/ready`: `READY`; schema matches 0070; API, worker, scheduler, web, PostgreSQL and Redis healthy.
- `/v1/version` release and Python digest match candidate; Web `meta.json` release matches candidate after correction.
- Watchdog: `ready=PASS`, `version=PASS`, `web_meta=PASS`, `watchdog_status=PASS`.
- Provider calls remain disabled; formal/production recommendation and recommendation flags remain false; `W2_TASK3_T30_CAPTURE_ENABLED` is unset. Scheduler retained its pre-existing enabled refresh/provider values; no new probe was added.
- Read-only PostgreSQL query (`BEGIN READ ONLY … ROLLBACK`) found 423 existing captures and 0 captures with `w2.capture_replay_evidence.v1`; no new natural capture exists yet.

Final online state: **DEPLOYED_HEALTHY_CAPTURE_PENDING**. This is a technical deployment result only; it is not model-validity evidence, profitability evidence, Task 3 scientific closure, or Task 4 unlock.
