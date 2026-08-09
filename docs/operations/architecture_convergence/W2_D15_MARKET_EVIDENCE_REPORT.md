# D15 persisted market-evidence report

```text
AUTHORITY = W2_DASHBOARD_OWNER_MARKET_EVIDENCE_CONSISTENCY_REMEDIATION_V1
INSPECTION_MODE = EXISTING_UNIFIED_READ_ENDPOINT_ONLY
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
WOULD_WRITE_CHECKPOINT = false
NO_CALL_ON_READ = true
FIXTURE_IDENTITY = SANITIZED_REPORTED_FIXTURE
```

The existing persisted payload was inspected through the deployed unified read
endpoint. No Provider probe, refresh, checkpoint mutation or business-data write
was performed. The reported fixture has two real prematch captures.

## Asian handicap

```text
captured_at = 2026-08-02T16:03:23Z -> 2026-08-03T06:53:58Z
canonical_line = -0.5 -> -0.5
bookmaker_count = 4 -> 5
HOME median price = 1.815 -> 1.850 (delta +0.035)
AWAY median price = 1.910 -> 1.900 (delta -0.010)
HOME probability delta = -0.014844
AWAY probability delta = +0.014844
movement.status = PRICE_MOVEMENT
movement.line_delta = 0
source_status = READY
public_evidence_status = STALE
```

## Totals

```text
captured_at = 2026-08-02T16:03:23Z -> 2026-08-03T06:53:58Z
canonical_line = 2.5 -> 2.5
bookmaker_count = 10 -> 11
OVER median price = 1.830 -> 1.850 (delta +0.020)
UNDER median price = 1.950 -> 1.950 (delta 0)
OVER probability delta = -0.004530
UNDER probability delta = +0.004530
movement.status = PRICE_MOVEMENT
movement.line_delta = 0
source_status = READY
public_evidence_status = STALE
```

## Classification

The persisted evidence proves legitimate price-only movement. Bookmaker-count
changes are accompanying coverage changes, not classification inputs. The
authoritative four-class movement calculation is correct for this fixture, so
no movement-engine bug fix is required. The bounded remediation is to expose
the price-median evidence, use the exact public label `赔率变化`, and fail stale
Market Memory closed under one public readiness authority.
