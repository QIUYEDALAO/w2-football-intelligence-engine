from __future__ import annotations

import json
from pathlib import Path

CORPUS = Path(__file__).parents[1] / "fixtures" / "recommendation_v3" / "corpus.json"
REQUIRED_SCENARIOS = {
    "fresh_ah_fresh_ou", "stale_ah_fresh_ou", "fresh_ah_stale_ou", "both_markets_stale",
    "quote_identity_conflict", "missing_market", "no_edge", "ou_analysis_primary",
    "ah_analysis_primary", "major_league_lineups_missing", "major_league_value_coverage_low",
    "non_major_grade_c", "provider_budget_exhausted", "api_web_release_mismatch",
    "live_or_finished", "locked_formal_historical", "canonical_settled",
}
REQUIRED_FIELDS = {
    "analysis_card", "dashboard_card", "day_view", "decision_contract_v2",
    "lifecycle_evidence", "performance_cohort_membership",
}


def test_recommendation_v3_baseline_corpus_is_complete_and_cross_surface() -> None:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "w2.recommendation_v3_baseline.v1"
    fixtures = payload["fixtures"]
    assert {item["id"] for item in fixtures} == REQUIRED_SCENARIOS
    assert len(fixtures) == len(REQUIRED_SCENARIOS)
    for item in fixtures:
        assert REQUIRED_FIELDS <= item.keys()
        assert item["analysis_card"]["decision_tier"] == item["dashboard_card"]["decision_tier"]
        assert item["decision_contract_v2"]["lock_eligible"] is (
            item["id"] == "locked_formal_historical"
        )


def test_recommendation_v3_baseline_corpus_keeps_formal_ah_and_settlement_semantics_explicit() -> (
    None
):
    fixtures = {item["id"]: item for item in json.loads(CORPUS.read_text())["fixtures"]}

    assert fixtures["ou_analysis_primary"]["analysis_card"]["primary_market"] == "TOTALS"
    assert fixtures["ah_analysis_primary"]["analysis_card"]["primary_market"] == "ASIAN_HANDICAP"
    assert (
        fixtures["locked_formal_historical"]["analysis_card"]["primary_market"]
        == "ASIAN_HANDICAP"
    )
    assert fixtures["canonical_settled"]["performance_cohort_membership"] == "eligible"
