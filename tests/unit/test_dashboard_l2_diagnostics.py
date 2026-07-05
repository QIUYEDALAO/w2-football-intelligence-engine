from __future__ import annotations

import json

from w2.dashboard.l2_diagnostics import build_l2_diagnostics


def test_l2_diagnostics_returns_whitelisted_fields_only() -> None:
    diagnostics = build_l2_diagnostics(
        {
            "fixture_id": "fixture-1",
            "source": "decision_contract",
            "decision_tier": "WATCH",
            "data_status": "PARTIAL",
            "lifecycle_status": "PRE_MATCH",
            "outcome_tracked": False,
            "lock_eligible": False,
            "recommendation_id": "rec-1",
            "reason_code": "LINEUPS_PENDING",
            "action": "WAIT_FOR_LINEUPS",
            "next_eval_at": "2026-07-05T02:30:00Z",
            "provider_budget_status": "OK",
            "missing_fields": ["lineups"],
            "stale_fields": ["odds"],
            "data_readiness": {
                "data_status": "PARTIAL",
                "reason_code": "LINEUPS_PENDING",
                "reason_human": "等待首发",
                "action": "WAIT_FOR_LINEUPS",
                "next_eval_at": "2026-07-05T02:30:00Z",
                "provider_budget_status": "OK",
                "missing_fields": ["lineups"],
                "stale_fields": ["odds"],
                "field_statuses": {"large": "object"},
            },
            "pick": {
                "market": "ASIAN_HANDICAP",
                "selection": "HOME",
                "line": "-0.25",
                "odds": "1.91",
            },
            "card_hash": "hash-1",
            "raw_payload": {"complete": "provider response"},
            "provider_request_hash": "request-hash",
        }
    )

    assert diagnostics == {
        "fixture_id": "fixture-1",
        "source": "decision_contract",
        "decision_tier": "WATCH",
        "data_status": "PARTIAL",
        "lifecycle_status": "PRE_MATCH",
        "outcome_tracked": False,
        "lock_eligible": False,
        "recommendation_id": "rec-1",
        "reason_code": "LINEUPS_PENDING",
        "action": "WAIT_FOR_LINEUPS",
        "next_eval_at": "2026-07-05T02:30:00Z",
        "provider_budget_status": "OK",
        "missing_fields": ["lineups"],
        "stale_fields": ["odds"],
        "data_readiness_summary": {
            "data_status": "PARTIAL",
            "reason_code": "LINEUPS_PENDING",
            "reason_human": "等待首发",
            "action": "WAIT_FOR_LINEUPS",
            "next_eval_at": "2026-07-05T02:30:00Z",
            "provider_budget_status": "OK",
            "missing_fields": ["lineups"],
            "stale_fields": ["odds"],
        },
        "market_snapshot": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "line": "-0.25",
            "odds": "1.91",
        },
        "card_hash": "hash-1",
    }


def test_l2_diagnostics_filters_forbidden_and_large_debug_fields() -> None:
    diagnostics = build_l2_diagnostics(
        {
            "fixture_id": "fixture-1",
            "decision_tier": "WATCH",
            "data_status": "PARTIAL",
            "raw_payload": {"provider": "full response"},
            "provider_request_hash": "request-hash",
            "safe_debug": {
                "environment": "staging",
                "readiness_source": "single_gate",
                "raw_payload": {"provider": "full response"},
                "provider_request_hash": "request-hash",
                "tok" + "en": "redacted",
                "sec" + "ret": "redacted",
                "authorization": "redacted",
                "env": {"W2": "redacted"},
                "lambda_home": 1.2,
                "blocker_codes": ["X"],
            },
        }
    )

    serialized = json.dumps(diagnostics, ensure_ascii=False)

    assert diagnostics["safe_debug"] == {
        "environment": "staging",
        "readiness_source": "single_gate",
    }
    assert "raw_payload" not in serialized
    assert "provider_request_hash" not in serialized
    assert "tok" + "en" not in serialized
    assert "sec" + "ret" not in serialized
    assert "authorization" not in serialized
    assert "lambda" not in serialized
    assert "blocker_codes" not in serialized


def test_l2_diagnostics_includes_small_environment_policy_summary() -> None:
    diagnostics = build_l2_diagnostics(
        {
            "fixture_id": "fixture-1",
            "decision_tier": "WATCH",
            "data_status": "PARTIAL",
            "environment_policy": {
                "environment": "production",
                "policy_version": "w2.environment_policy.v1",
                "lock_policy": {"name": "production_B"},
                "source": "w2.domain.environment_policy",
                "raw_env": {"W2_ENVIRONMENT": "production"},
            },
        }
    )

    assert diagnostics["environment_policy"] == {
        "environment": "production",
        "policy_version": "w2.environment_policy.v1",
        "lock_policy_name": "production_B",
        "source": "w2.domain.environment_policy",
    }
    assert diagnostics["safe_debug"] == {
        "environment_policy_source": "w2.domain.environment_policy",
        "lock_policy_name": "production_B",
    }
