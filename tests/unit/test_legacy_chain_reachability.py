from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, cast

import pytest

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
_LEGACY_ADAPTER_FIELDS = {
    "pricing_shadow",
    "formal_blockers",
    "canonical_ah_market_blocker",
    "ah_mainline_blocker",
    "fair_ah",
    "fair_ou",
    "market_ah",
    "market_ou",
    "edge_ah",
    "edge_ou",
}
_LEGACY_CARD_MARKET_FIELDS = {
    "model_market_divergence",
    "fair_line",
    "market_line",
    "edge",
    "value_edge",
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
    adapter = (repository / "src/w2/domain/decision_adapter.py").read_text(encoding="utf-8")
    return count + len(_adapter_semantic_violations(adapter))


def _adapter_semantic_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "pricing_shadow":
            violations.append("pricing_shadow")
        key: str | None = None
        owner: str | None = None
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            owner, key = node.value.id, node.slice.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_get"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            owner, key = node.args[0].id, node.args[1].value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            owner, key = node.func.value.id, node.args[0].value
        if key in _LEGACY_ADAPTER_FIELDS:
            violations.append(f"{owner}.{key}")
        if owner in {"card", "market", "recommendation"} and key in _LEGACY_CARD_MARKET_FIELDS:
            violations.append(f"{owner}.{key}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_pick_payload"
            and (
                len(node.keywords) != 1
                or node.keywords[0].arg != "evaluated_candidate"
                or not isinstance(node.keywords[0].value, ast.Name)
                or node.keywords[0].value.id != "evaluated_candidate"
            )
        ):
            violations.append("_pick_payload.call_source")

    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    pick = functions["_pick_payload"]
    if [argument.arg for argument in pick.args.kwonlyargs] != ["evaluated_candidate"]:
        violations.append("_pick_payload.signature")
    if {
        node.id
        for node in ast.walk(pick)
        if isinstance(node, ast.Name) and node.id in {"card", "market", "recommendation"}
    }:
        violations.append("_pick_payload.legacy_source")

    divergence = functions["_model_market_divergence"]
    if [argument.arg for argument in divergence.args.args] != ["candidate"]:
        violations.append("_model_market_divergence.signature")
    for node in ast.walk(divergence):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "candidate"
            and node.func.attr == "get"
            and (
                not node.args
                or not isinstance(node.args[0], ast.Constant)
                or node.args[0].value != "analysis_evidence"
            )
        ):
            violations.append("_model_market_divergence.non_evidence_source")
    return violations


def test_legacy_decision_contract_code_is_zero() -> None:
    code_count = _legacy_decision_contract_code_count()
    assert code_count == 0, f"LEGACY_DECISION_CONTRACT_CODE = {code_count}"
    assert "pricing_shadow" not in inspect.getsource(canonical_public_simulation)


@pytest.mark.parametrize(
    "mutation",
    (
        "pricing_shadow",
        "legacy_blocker",
        "legacy_fair_line",
        "legacy_edge",
        "legacy_subscript_edge",
        "top_level_divergence",
        "market_pick_source",
        "recommendation_pick_source",
        "pick_call_source",
        "non_evidence_divergence_source",
    ),
)
def test_adapter_ast_guard_rejects_legacy_semantic_mutations(mutation: str) -> None:
    repository = Path(__file__).resolve().parents[2]
    source = (repository / "src/w2/domain/decision_adapter.py").read_text(encoding="utf-8")
    snippets = {
        "pricing_shadow": '\ndef injected(card):\n    return _get(card, "pricing_shadow")\n',
        "legacy_blocker": '\ndef injected(card):\n    return _get(card, "formal_blockers")\n',
        "legacy_fair_line": '\ndef injected(card):\n    return _get(card, "fair_line")\n',
        "legacy_edge": '\ndef injected(market):\n    return _get(market, "edge")\n',
        "legacy_subscript_edge": '\ndef injected(market):\n    return market["edge"]\n',
        "top_level_divergence": (
            '\ndef injected(card):\n    return _get(card, "model_market_divergence")\n'
        ),
    }
    if mutation in snippets:
        mutated = source + snippets[mutation]
    elif mutation == "non_evidence_divergence_source":
        mutated = source.replace(
            '    evidence = _as_mapping(candidate.get("analysis_evidence")) if candidate else {}\n',
            '    evidence = _as_mapping(candidate.get("fair_line")) if candidate else {}\n',
            1,
        )
    elif mutation == "pick_call_source":
        mutated = source.replace(
            "            evaluated_candidate=evaluated_candidate,\n",
            "            evaluated_candidate=market,\n",
            1,
        )
    else:
        mutated = source.replace(
            "    evaluated = _as_mapping(evaluated_candidate)\n",
            f"    {mutation.removesuffix('_pick_source')}\n"
            "    evaluated = _as_mapping(evaluated_candidate)\n",
            1,
        )

    assert _adapter_semantic_violations(mutated)


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
