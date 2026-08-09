from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from importlib.util import resolve_name
from pathlib import Path
from typing import Any

import pytest

from w2.api.repository import ReadModelService, SystemDegradedError
from w2.domain.decision_contract import CONTRACT_OWNED_FIELDS

API_ROOTS = (Path("src/w2/api"), Path("apps/api"))
FULL_EXECUTION_SURFACE = (*API_ROOTS, Path("scripts"), Path("infra"))
RETIRED_SHADOW_PRODUCTION_SURFACES = (
    Path("src/w2"),
    Path("apps"),
    Path("scripts"),
    Path("infra"),
    Path(".github/workflows"),
    Path("pyproject.toml"),
    Path("Dockerfile.python"),
    Path("Dockerfile.web"),
)
PRODUCTION_DAY_VIEW_SURFACE = (
    *API_ROOTS,
    Path("src/w2/dashboard"),
    Path("apps/web/src"),
)
FORBIDDEN_API_PACKAGES = {
    "w2.ingestion",
    "w2.features",
    "w2.markets",
    "w2.pricing",
    "w2.strategy",
    "w2.simulation",
    "w2.prematch.analysis_calculator",
}
FORBIDDEN_PRODUCTION_FALLBACKS = {
    "prediction_locks.json",
    "result_events.json",
    "_uses_frozen_public_authority",
    "staging_seed_dashboard",
}
NON_PRODUCTION_FALLBACK_READERS = {
    Path("scripts/run_stage7i_observer.py"),
    Path("scripts/seed_staging_dashboard.py"),
}
FORBIDDEN_DAY_VIEW_FALLBACK_IDENTITIES = {
    "legacy_fallback",
    "CARD_SOURCE_LEGACY",
    "_legacy_card",
}
FORBIDDEN_DAY_VIEW_CONTRACT_BYPASS_IDENTITIES = {
    "compute_outcome_tracked",
    "_decision_field",
    "_field",
}
FORBIDDEN_DOMAIN_BOUNDARY_IMPORTS = {
    "os",
    "pathlib",
    "sqlalchemy",
    "w2.api",
    "w2.config",
    "w2.dashboard",
    "w2.infrastructure",
}
RETIRED_SHADOW_STRATEGY_IDENTITIES = {
    "shadow_strategy_models",
    "ShadowStrategyRunModel",
    "ShadowStrategyLockModel",
    "ShadowStrategyEvaluationModel",
    "w2.strategy.shadow",
    "w2.strategy.shadow_cycle_cli",
    "shadow_strategy_status",
    "shadow_strategy_locks",
    "shadow_strategy_evaluations",
    "shadow_strategy_replay",
    "/shadow-strategy/",
    "w2-shadow-cycle",
    "config/policies/shadow_strategy.v1.json",
}
FORBIDDEN_PERFORMANCE_API_COMPUTE_IMPORTS = {
    "w2.dashboard.performance",
    "w2.settlement",
    "w2.tracking.finished_match_scoring_projection",
    "w2.tracking.forward_ledger_performance",
    "w2.tracking.performance_scoring",
}


def _imports(path: Path, module: str | None = None) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current_module = module or _module_name(path)
    package = current_module if path.name == "__init__.py" else current_module.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name(f"{'.' * node.level}{base}", package)
            if base:
                imports.add(base)
            imports.update(
                f"{base}.{alias.name}" if base else alias.name
                for alias in node.names
                if alias.name != "*"
            )
    return imports


def _module_name(path: Path) -> str:
    relative = path.with_suffix("")
    if relative.parts[0] == "src":
        relative = Path(*relative.parts[1:])
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _production_module_paths() -> dict[str, Path]:
    return {
        _module_name(path): path
        for root in (Path("src"), Path("apps"))
        for path in root.rglob("*.py")
    }


def _matches_forbidden(module: str, forbidden: set[str]) -> bool:
    return any(module == package or module.startswith(f"{package}.") for package in forbidden)


def _import_graph_violations(
    roots: list[str],
    module_paths: dict[str, Path],
    forbidden: set[str] = FORBIDDEN_API_PACKAGES,
) -> list[str]:
    pending = list(roots)
    visited: set[str] = set()
    violations: list[str] = []
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = module_paths.get(module)
        if path is None:
            continue
        for imported in _imports(path, module):
            if _matches_forbidden(imported, forbidden):
                violations.append(f"{module}->{imported}")
            if imported in module_paths and imported not in visited:
                pending.append(imported)
    return sorted(violations)


def _retired_shadow_violations(surfaces: tuple[Path, ...]) -> list[str]:
    files = (
        path
        for surface in surfaces
        for path in ([surface] if surface.is_file() else surface.rglob("*"))
        if path.is_file() and not {"node_modules", "__pycache__", ".venv"}.intersection(path.parts)
    )
    return sorted(
        f"{path}:{identity}"
        for path in files
        for identity in RETIRED_SHADOW_STRATEGY_IDENTITIES
        if identity in path.read_text(encoding="utf-8", errors="ignore")
    )


def _write_modules(root: Path, sources: dict[str, str]) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for module, source in sources.items():
        path = root.joinpath(*module.split(".")).with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        modules[module] = path
    return modules


def test_api_imports_no_read_time_computation_packages() -> None:
    violations = sorted(
        f"{path}:{name}"
        for root in API_ROOTS
        for path in root.rglob("*.py")
        for name in _imports(path, _module_name(path))
        if _matches_forbidden(name, FORBIDDEN_API_PACKAGES)
    )
    assert violations == []


def test_api_transitive_import_graph_has_no_read_time_computation_packages() -> None:
    module_paths = _production_module_paths()
    roots = [_module_name(path) for root in API_ROOTS for path in root.rglob("*.py")]
    assert _import_graph_violations(roots, module_paths) == []


def test_performance_api_is_projection_only_and_has_no_compute_imports() -> None:
    performance_source = inspect.getsource(ReadModelService.performance)
    compute_imports = sorted(
        name for name in FORBIDDEN_PERFORMANCE_API_COMPUTE_IMPORTS if name in performance_source
    )
    non_projection_reads = sorted(
        identity
        for identity in (
            "dashboard.performance",
            "forward_ledger_performance",
            "outcome_ledger",
            "settlements",
            "runtime JSON",
        )
        if identity in performance_source
    )

    assert compute_imports == [], "API_COMPUTE_IMPORT_COUNT != 0"
    assert non_projection_reads == [], "API_PERFORMANCE_NON_PROJECTION_READ_COUNT != 0"
    assert 'self.repository.checkpoints("performance:cohort:")' in performance_source
    assert 'self.repository.checkpoints("performance:fixture:")' in performance_source
    assert 'fixture.status == "SCORED"' in performance_source
    assert "PERFORMANCE_CLV_POPULATION_MISMATCH" in performance_source


def test_performance_projection_uses_shared_canonical_settlement_authority() -> None:
    projection = Path("src/w2/tracking/finished_match_scoring_projection.py").read_text(
        encoding="utf-8"
    )
    authority = Path("src/w2/tracking/forward_ledger_performance.py").read_text(encoding="utf-8")
    shared_authority = authority[
        authority.index("def canonical_settlement_facts(") : authority.index(
            "\ndef _result_for_fixture("
        )
    ]

    assert "canonical_settlement_facts(" in projection
    assert "_canonical_pick_settlement" not in projection
    for helper in (
        "_validation_candidates(",
        "_validation_settlements(",
        "_canonical_rows(",
    ):
        assert helper in shared_authority


def test_performance_web_has_no_metric_recomputation_or_production_fixture() -> None:
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in Path("apps/web/src").rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    }
    performance_sources = "\n".join(
        text
        for path, text in sources.items()
        if "performance" in path.name.lower() or "PerformancePage" in text
    )
    forbidden = {
        "reliability_bins(",
        "bootstrap_ci(",
        "paired_bootstrap(",
        "calculateMean",
        "calculateHitRate",
        ".reduce(",
        "forward_ledger_performance",
    }

    assert performance_sources == ""
    assert sorted(identity for identity in forbidden if identity in performance_sources) == []
    assert not Path("apps/web/src/components/PerformancePage.tsx").exists()
    assert not Path("apps/web/src/lib/performanceApi.ts").exists()


def test_import_graph_detects_package_child_relative_and_transitive_bypasses(
    tmp_path: Path,
) -> None:
    cases = (
        (
            {"w2.api.root": "from w2 import features\n", "w2.features": ""},
            "w2.features",
        ),
        (
            {
                "w2.api.root": "from w2.dashboard import intermediate\n",
                "w2.dashboard.intermediate": "import w2.markets\n",
            },
            "w2.markets",
        ),
        (
            {
                "w2.api.root": "from .helper import x\n",
                "w2.api.helper": "import w2.simulation\n",
            },
            "w2.simulation",
        ),
        (
            {"w2.api.root": "from ..pricing import shadow\n"},
            "w2.pricing",
        ),
    )
    for index, (sources, expected) in enumerate(cases):
        modules = _write_modules(tmp_path / str(index), sources)
        violations = _import_graph_violations(["w2.api.root"], modules)
        assert any(expected in violation for violation in violations)


def test_import_graph_allows_pure_domain_and_read_only_dependencies(tmp_path: Path) -> None:
    modules = _write_modules(
        tmp_path,
        {
            "w2.api.root": (
                "from w2.domain import decision_contract\nfrom . import read_only_repository\n"
            ),
            "w2.domain.decision_contract": "from dataclasses import dataclass\n",
            "w2.api.read_only_repository": "from copy import deepcopy\n",
        },
    )
    assert _import_graph_violations(["w2.api.root"], modules) == []


def test_dashboard_uses_existing_shadow_projection_namespace() -> None:
    source = Path("src/w2/api/repository.py").read_text(encoding="utf-8")
    assert "dashboard:fixture_latest:" not in source
    assert "self.checkpoints(ANALYSIS_CARD_SHADOW_PREFIX)" in source


def test_full_execution_surface_has_no_removed_production_fallback_identity() -> None:
    # scripts/ and infra/ are intentionally part of this scan so a deployment
    # entrypoint cannot silently reintroduce the removed API fallback. The one
    # allowlist entries are audit/seed utilities and cannot serve API traffic.
    violations = sorted(
        f"{path}:{identity}"
        for root in FULL_EXECUTION_SURFACE
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".sh", ".yml", ".yaml"}
        and path not in NON_PRODUCTION_FALLBACK_READERS
        for identity in FORBIDDEN_PRODUCTION_FALLBACKS
        if identity in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert violations == []


def test_retired_shadow_strategy_has_no_production_reference() -> None:
    violations = _retired_shadow_violations(RETIRED_SHADOW_PRODUCTION_SURFACES)
    assert violations == [], (
        f"RETIRED_SHADOW_STRATEGY_PRODUCTION_REFERENCE_COUNT={len(violations)}: {violations}"
    )


def test_retired_shadow_guard_covers_every_production_surface(tmp_path: Path) -> None:
    mutations = (
        ("src/w2/prematch/reintroduced.py", "shadow_strategy_status"),
        ("src/w2/infrastructure/reintroduced.py", "ShadowStrategyRunModel"),
        (".github/workflows/reintroduced.yml", "/shadow-strategy/"),
        ("pyproject.toml", "w2-shadow-cycle"),
        ("Dockerfile.python", "config/policies/shadow_strategy.v1.json"),
        ("Dockerfile.web", "w2.strategy.shadow_cycle_cli"),
    )
    surface_names = tuple(str(path) for path in RETIRED_SHADOW_PRODUCTION_SURFACES)
    for index, (relative_path, identity) in enumerate(mutations):
        root = tmp_path / str(index)
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(identity, encoding="utf-8")
        surfaces = tuple(root / name for name in surface_names)
        assert f"{path}:{identity}" in _retired_shadow_violations(surfaces)


def test_retired_shadow_guard_allows_current_shadow_namespaces(tmp_path: Path) -> None:
    path = tmp_path / "src/w2/current.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            (
                "analysis-card:shadow:v1:",
                "w2.pricing.shadow",
                "w2.shadow.comparison_import_cli",
                "w2-shadow-comparison-import",
            )
        ),
        encoding="utf-8",
    )
    assert _retired_shadow_violations((tmp_path / "src/w2",)) == []


def test_production_day_view_has_no_legacy_fallback_identity() -> None:
    assert Path("src/w2/dashboard") in PRODUCTION_DAY_VIEW_SURFACE
    assert Path("apps/web/src") in PRODUCTION_DAY_VIEW_SURFACE
    violations = sorted(
        f"{path}:{identity}"
        for root in PRODUCTION_DAY_VIEW_SURFACE
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".mjs"}
        for identity in FORBIDDEN_DAY_VIEW_FALLBACK_IDENTITIES
        if identity in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert violations == []


def test_day_view_reads_contract_owned_fields_from_contract_only() -> None:
    path = Path("src/w2/dashboard/day_view.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    seen_identities = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    identity_violations = sorted(FORBIDDEN_DAY_VIEW_CONTRACT_BYPASS_IDENTITIES & seen_identities)
    contract_read_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"_day_view_card", "_contract_card"}
    ]
    top_level_reads = sorted(
        str(node.args[0].value)
        for function in contract_read_functions
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "card"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value in CONTRACT_OWNED_FIELDS
    )
    assert identity_violations == []
    assert top_level_reads == []


def test_decision_contract_validator_is_pure_domain() -> None:
    path = Path("src/w2/domain/decision_contract.py")
    imports = _imports(path)
    violations = sorted(
        name
        for name in imports
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_DOMAIN_BOUNDARY_IMPORTS
        )
    )
    assert violations == []


def test_infrastructure_does_not_import_upper_layers() -> None:
    """DEPENDENCY_CONTRACT_V1: infrastructure sits below api/dashboard/apps.

    Enforces the mandatory INFRASTRUCTURE -> {API, DASHBOARD, APPS} edges of the
    layer order. Reuses the AST import reader; the tree is clean today, so this
    only fixes the boundary in place.
    """
    forbidden = ("w2.api", "w2.dashboard", "apps")
    violations = sorted(
        f"{path}:{name}"
        for path in Path("src/w2/infrastructure").rglob("*.py")
        for name in _imports(path)
        if any(name == pkg or name.startswith(f"{pkg}.") for pkg in forbidden)
    )
    assert violations == []


def test_predeploy_projection_smoke_uses_write_side_calculator() -> None:
    source = Path("scripts/run_predeploy_e2e_smoke.sh").read_text(encoding="utf-8")
    assert (
        "from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService"
    ) in source
    assert "from w2.api.repository import ReadModelRepository, ReadModelService" not in source


class ProjectionRepository:
    def __init__(self, *, projection: dict[str, Any] | None) -> None:
        self.projection = projection
        self.fixture = {
            "fixture_id": "fixture-1",
            "competition_id": "competition-1",
            "competition_name": "Competition",
            "kickoff_utc": "2026-07-25T12:00:00Z",
            "status": "NS",
            "home_team_id": "home-1",
            "home_team_name": "Home",
            "away_team_id": "away-1",
            "away_team_name": "Away",
        }

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return [self.fixture]

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return self.fixture if fixture_id == "fixture-1" else None

    def analysis_card_projection(self, fixture_id: str) -> dict[str, Any] | None:
        return self.projection if fixture_id == "fixture-1" else None

    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 1,
            "matchday_card_count": 1,
            "future_fixture_count": 1,
            "result_event_count": 0,
        }


def test_analysis_endpoint_returns_projection_metadata_without_recomputation() -> None:
    projected = {
        "fixture_id": "fixture-1",
        "decision_tier": "NOT_READY",
        "data_status": "BLOCKED",
        "lifecycle_status": "DRAFT",
        "current_odds": {},
        "market_probabilities": {},
        "recommendation_decision_v3": {
            "schema_version": "w2.recommendation_decision.v3",
            "outcome": "NO_EDGE",
            "selected_candidate": None,
        },
        "read_model_projection": {
            "checkpoint_key": "analysis-card:shadow:v1:fixture-1",
            "projection_version": "w2.prematch-read-model-projection.v1",
            "projection_hash": "projection-hash",
            "source_event_type": "ODDS_CHANGED",
            "source_event_at": "2026-07-24T01:00:00Z",
            "last_projected_at": "2026-07-24T01:00:01Z",
        },
    }
    service = ReadModelService(repository=ProjectionRepository(projection=projected))  # type: ignore[arg-type]

    card = service.public_analysis_card_bounded("fixture-1")

    assert card == projected
    assert card["read_model_projection"]["projection_hash"] == "projection-hash"
    assert card["read_model_projection"]["source_event_type"] == "ODDS_CHANGED"


def test_missing_projection_is_explicit_system_degraded_not_empty() -> None:
    service = ReadModelService(repository=ProjectionRepository(projection=None))  # type: ignore[arg-type]

    card = service.public_analysis_card_bounded("fixture-1")

    assert card is not None
    assert card["recommendation_decision_v4"]["schema_version"] == (
        "w2.recommendation_decision.v4"
    )
    assert card["recommendation_decision_v4"]["outcome"] == "NOT_READY"
    assert card["recommendation_decision_v4"]["selected_candidate"] is None
    assert card["recommendation_decision_v3_role"] == "HISTORY_ONLY"
    assert "recommendation_decision_v3" not in card
    assert card["projection_health"] == {
        "status": "SYSTEM_DEGRADED",
        "reason_code": "ANALYSIS_PROJECTION_NOT_READY",
    }
    assert card["decision_tier"] == "NOT_READY"
    assert card["data_status"] == "BLOCKED"
    assert card["pick"] is None
    assert card["outcome_tracked"] is False
    assert card["lock_eligible"] is False
    assert card["current_odds"] == {}


@pytest.mark.parametrize(
    ("competition_id", "requirement", "risks", "reason"),
    (
        ("premier_league", "STRICT", [], "ANALYSIS_PROJECTION_NOT_READY"),
        (
            "world_cup_2026",
            "ADVISORY",
            ["LINEUP_UNOBSERVABLE"],
            "ANALYSIS_PROJECTION_NOT_READY",
        ),
        (
            None,
            "ADVISORY",
            ["LINEUP_UNOBSERVABLE"],
            "LINEUP_REQUIREMENT_IDENTITY_MISSING",
        ),
    ),
)
def test_missing_projection_preserves_lineup_requirement_identity(
    competition_id: str | None,
    requirement: str,
    risks: list[str],
    reason: str,
) -> None:
    repository = ProjectionRepository(projection=None)
    repository.fixture["competition_id"] = competition_id

    card = ReadModelService(repository=repository).public_analysis_card_bounded(  # type: ignore[arg-type]
        "fixture-1"
    )

    assert card is not None
    assert card["lineup_requirement"] == requirement
    assert card["risk_reason_codes"] == risks
    assert card["reason_code"] == reason


class FailedProjectionRepository(ProjectionRepository):
    def analysis_card_projection(self, fixture_id: str) -> dict[str, Any] | None:
        raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED")


def test_database_failure_propagates_system_degraded() -> None:
    service = ReadModelService(repository=FailedProjectionRepository(projection=None))  # type: ignore[arg-type]

    try:
        service.public_analysis_card_bounded("fixture-1")
    except SystemDegradedError as exc:
        assert exc.code == "SYSTEM_DEGRADED"
        assert str(exc) == "READ_MODEL_CHECKPOINT_QUERY_FAILED"
    else:
        raise AssertionError("database failure was silently converted to empty data")


def test_projection_read_is_read_only_across_twenty_calls() -> None:
    projection = {
        "fixture_id": "fixture-1",
        "decision_tier": "NOT_READY",
        "data_status": "BLOCKED",
        "lifecycle_status": "DRAFT",
        "recommendation_decision_v3": {
            "schema_version": "w2.recommendation_decision.v3",
            "outcome": "NO_EDGE",
            "selected_candidate": None,
        },
        "read_model_projection": {
            "checkpoint_key": "analysis-card:shadow:v1:fixture-1",
            "projection_version": "w2.prematch-read-model-projection.v1",
            "projection_hash": "stable",
            "source_event_type": "FIXTURE_CHANGED",
            "source_event_at": datetime(2026, 7, 24, tzinfo=UTC).isoformat(),
            "last_projected_at": datetime(2026, 7, 24, 0, 0, 1, tzinfo=UTC).isoformat(),
        },
    }
    repository = ProjectionRepository(projection=projection)
    service = ReadModelService(repository=repository)  # type: ignore[arg-type]

    hashes = [
        service.public_analysis_card_bounded("fixture-1")["read_model_projection"][
            "projection_hash"
        ]
        for _ in range(20)
    ]

    assert hashes == ["stable"] * 20
