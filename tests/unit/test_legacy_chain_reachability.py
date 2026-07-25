from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

from w2.dashboard.day_view import _simulation_projection
from w2.domain import decision_adapter
from w2.prematch.analysis_calculator import ReadModelService
from w2.tracking.formal_results import _simulation_evidence

_ROW = {
    "fixture_id": "reachability-1",
    "status": None,
    "kickoff_utc": "2026-07-27T12:00:00+00:00",
    "competition_id": "C1",
}


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


def _call_names() -> dict[str, list[str]]:
    root = Path(__file__).resolve().parents[2] / "src"
    callers: dict[str, list[str]] = {
        "_public_market_is_legacy_pick": [],
        "legacy_decision_view": [],
    }
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative == "w2/domain/legacy_decision_shim.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in callers:
                callers[name].append(relative)
    return callers


def test_legacy_pick_and_shim_have_zero_public_runtime_callers() -> None:
    assert _call_names() == {
        "_public_market_is_legacy_pick": [],
        "legacy_decision_view": [],
    }


def test_current_frozen_fallback_dashboard_and_formal_skip_legacy_adapter(
    monkeypatch,
) -> None:
    activations = 0

    def legacy_adapter_trap(**_: Any):
        nonlocal activations
        activations += 1
        raise AssertionError("legacy adapter reached")

    monkeypatch.setattr(decision_adapter, "_legacy_decision_tier", legacy_adapter_trap)
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

    assert activations == 0


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
