# W2 R3 read-only staging candidate — 2026-07-18

## Result

> Superseded candidate note: the repeated-capture freshness correction was
> accepted later on 2026-07-18 as implementation
> `94bcd62c67ed3fe50bba5ee65be10133556f83d0`. The cycle count remains `0/3`
> and starts from that immutable implementation. See
> [W2 repeated-capture freshness canary](W2_REPEAT_CAPTURE_FRESHNESS_STAGING_CANARY_20260718.md).

Implementation SHA `7e4c0aea790f2bce678b4ab6a2d20ba51d583316` is the
staging candidate for the three daily read-only acceptance cycles. The cycle
count is `0/3`; the first eligible patrol is the real Beijing 09:00 patrol on
2026-07-19. The candidate is not yet read-only production approved.

Delivery used a local `git archive`. No GitHub fetch, pull, push, workflow or PR
was used.

## Dashboard correction

The rejected layout redesign was reverted. The accepted candidate retains the
original command bar, trust strip, schedule tables, selected-fixture evidence,
verification, league performance and technical-details layout.

Only displayed data semantics changed:

- all qualifying recommendations are shown; there is no three-match cap;
- `record_count` remains an L2 row audit and is not displayed as a fixture or
  validation recommendation count;
- the trust strip uses the real ledger evidence window and VALIDATION fixture,
  settled, pending and outcome figures;
- OFFICIAL, SHADOW and VALIDATION outcomes remain separate;
- the deployed view showed 23 validation fixtures, 15 settled, 8 pending,
  10 hit, 3 miss, 2 push and 0 void, with decisive hit rate 76.923%.

## Local gates

- Pytest: `1163 passed, 4 skipped`.
- Ruff and Mypy (`src apps`, 230 source files): PASS.
- TypeScript typecheck and production Web build: PASS.
- Playwright: 6 PASS, including four simultaneously qualifying recommendations
  remaining visible.
- Acceptance, tracked-output guard, secret scan and `git diff --check`: PASS.

## Staging canary

- `/health`, `/ready`, `/v1/version`, DayView and Dashboard: HTTP 200.
- API and Web release identity: exact implementation SHA.
- Alembic current/head: `0023_create_checkpoint_refresh_schedule`, MATCH.
- Readiness manifest and all required artifact hashes: VALID/MATCH.
- Public probe provider ledger: 719 before and 719 after; delta 0.
- Redis DB1 Celery queue: 0.
- API, worker, scheduler and Web: healthy; restart/OOM/exit137 all zero.
- Scheduler returned to its predeploy `running`, `unless-stopped` state; watchdog
  timer is active.
- Anonymous RSS bytes: API 248,741,888; worker 284,536,832; scheduler
  152,367,104; Web 8,962,048. Against the immediately preceding candidate's
  API baseline 208,384,000, the highest relevant ratio is 1.194, within 1.20.
- Browser verification confirmed the original Dashboard layout and corrected
  ledger figures on the public host.

## Rollback and cycle rule

The predeploy release and four service images for
`f20edb694aad63a784b24c7891fa322e156a1d4c` remain revision-tagged rollback
targets. Any hard failure during the three real 09:00 patrols invalidates that
day; a data-contract, statistics or runtime correction resets consecutive
cycles to zero. Pure copy changes do not reset cycles.

Champion, RECOMMEND/lock and OFFICIAL remain unchanged and are not authorized by
this candidate.
