from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, cast

from w2.dashboard.day_view import _simulation_projection
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.simulation_reconciliation import canonical_public_simulation
from w2.tracking.formal_results import _simulation_evidence

_ROW = {
    "fixture_id": "reachability-1",
    "status": None,
    "kickoff_utc": "2026-07-27T12:00:00+00:00",
    "competition_id": "C1",
}

_LEGACY_GUARD_SURFACES = ("src", "apps", "scripts", "infra")


def _service() -> ReadModelService:
    return ReadModelService(repository=cast(Any, object()))


def _canonical_card(**overrides: Any) -> dict[str, Any]:
    simulation = {"status": "READY", "simulations": 10000, "seed": 7}
    card: dict[str, Any] = {
        "fixture_id": "reachability-1",
        "kickoff_utc": "2026-07-27T12:00:00+00:00",
        "decision_tier": "SKIP",
        "markets": [],
        "primary_market": "",
        "current_odds": {},
        "market_candidates": {},
        "pricing_shadow": {"simulation": dict(simulation)},
        "home_cn": "主",
        "away_cn": "客",
        "generated_at": "2026-07-26T00:00:00Z",
        "simulation": dict(simulation),
    }
    card.update(overrides)
    return card


def _legacy_decision_contract_code_count() -> int:
    repository = Path(__file__).resolve().parents[2]
    forbidden = {
        "_legacy_decision_tier",
        "_public_market_is_legacy_pick",
        "legacy_decision_tier",
        "legacy_decision_view",
        "legacy_formal",
        "run_simulation_from_shadow",
    }
    roots = tuple(repository / surface for surface in _LEGACY_GUARD_SURFACES)
    count = sum(
        path.name == "legacy_decision_shim.py"
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    )
    count += sum(
        source.count(symbol)
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        for source in (path.read_text(encoding="utf-8", errors="ignore"),)
        for symbol in forbidden
    )
    adapter = (repository / "src/w2/domain/decision_adapter.py").read_text(
        encoding="utf-8"
    )
    return count + sum(
        adapter.count(symbol)
        for symbol in {
            "build_data_readiness_from_legacy_payload",
            "_pricing_keys_for_market",
            "adapter_fallback",
            "formal_blockers",
            "canonical_ah_market_blocker",
            "ah_mainline_blocker",
        }
    )


def test_legacy_decision_contract_code_is_zero() -> None:
    code_count = _legacy_decision_contract_code_count()
    assert code_count == 0, f"LEGACY_DECISION_CONTRACT_CODE = {code_count}"
    assert "pricing_shadow" not in inspect.getsource(canonical_public_simulation)


def test_current_frozen_fallback_dashboard_and_formal_use_canonical_contract() -> None:
    service = _service()

    current = service._dashboard_card_from_matchday(
        _ROW,
        analysis_override=_canonical_card(),
    )
    fallback_source = service._fallback_analysis_card(
        fixture_id="reachability-1",
        market_coverage={},
        source="reachability-fallback",
        fixture_context={
            "kickoff_utc": _ROW["kickoff_utc"],
            "home_name": "主",
            "away_name": "客",
        },
    )
    fallback = service._dashboard_card_from_matchday(
        _ROW,
        analysis_override=fallback_source,
    )
    frozen_source = _canonical_card(
        decision_contract=current["decision_contract"],
        frozen_artifact_provenance={"status": "VERIFIED"},
    )
    frozen = service._dashboard_card_from_matchday(
        _ROW,
        analysis_override=frozen_source,
    )

    for card in (current, fallback, frozen):
        _simulation_projection(card)
        _simulation_evidence(card)


def test_legacy_noise_does_not_change_canonical_public_business_fields() -> None:
    service = _service()
    canonical = service._dashboard_card_from_matchday(
        _ROW,
        analysis_override=_canonical_card(),
    )
    noisy = service._dashboard_card_from_matchday(
        _ROW,
        analysis_override=_canonical_card(
            decision="PICK",
            candidate=True,
            formal_recommendation=True,
        ),
    )
    fields = (
        "recommendation",
        "decision_tier",
        "pick",
        "non_pick",
        "scoreline_reference",
        "formal_recommendation",
        "formal_suppressed",
        "formal_suppressed_reason",
    )
    assert {field: canonical.get(field) for field in fields} == {
        field: noisy.get(field) for field in fields
    }
