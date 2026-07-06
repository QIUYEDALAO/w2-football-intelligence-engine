# W2 League Whitelist Re-Audit Readiness 2026-07-06

## Purpose

The remediation implementation split readiness into two gates:

- evidence re-audit readiness
- enablement audit readiness

This matters because the next provider audit is needed to collect sanitized
observed provider evidence. Missing observed evidence should allow an
`EVIDENCE_ONLY` audit, while still blocking any enablement decision.

## Current Readiness

The current offline checker reports:

- `ready_for_evidence_reaudit=true`
- `ready_for_enablement_audit=false`
- `next_provider_audit_mode=EVIDENCE_ONLY`
- `provider_calls=0`
- `db_reads=0`
- `db_writes=0`

The evidence re-audit is allowed because its purpose is to collect the missing
sanitized observed fields:

- provider league id
- provider league name
- provider country
- provider season
- provider team count
- fixture query params
- fixture response count
- bookmaker count
- AH/OU market names
- line presence

## Enablement Remains Blocked

Enablement remains blocked because:

- sanitized observed evidence is not yet present
- squad value source is still missing
- the seven-item audit is not passing

`SQUAD_VALUE_SOURCE_MISSING` blocks enablement only. It must not block an
evidence-only audit whose purpose is provider mapping and coverage diagnosis.

## Evidence-Only Audit Rules

An `EVIDENCE_ONLY` provider audit:

- cannot set `enabled=true`
- cannot deploy staging or production
- cannot write DB
- cannot write checkpoint, lock, or settlement artifacts
- cannot commit raw provider payloads
- must write reports only under `/tmp`
- must use an approved daily cap and reserve
- must stop on provider key failure, quota warning/exhaustion, 429, endpoint
  outside allowlist, or hard-cap breach

## Provider Preconditions

Before the next evidence-only audit, operators must confirm:

- provider key exists in process environment and is header-safe
- provider quota is available
- hard cap and reserve are approved
- no league requires `enabled=true`
- no staging or production deploy is part of the audit

Without those preconditions, `ready_for_evidence_reaudit=false`.

## Enablement Preconditions

No competition may move to enablement until all seven items pass:

1. provider mapping
2. fixtures
3. results
4. xG/statistics
5. lineups and injuries
6. bookmaker depth with AH/OU and line
7. squad value mapping

Passing evidence re-audit is not enablement. A separate approved PR is required
for any future `enabled=true` change.
