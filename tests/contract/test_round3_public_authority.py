from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.model_forecast_models import (
    canonical_model_forecast_fixture_id,
    model_forecast_fixture_aliases,
)
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    _fixture_aliases,
    _round3_active_whitelist,
)

ACTIVE_13 = {
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
    "brasileirao_serie_a",
    "argentina_primera",
    "mls",
    "chinese_super_league",
    "allsvenskan",
    "eliteserien",
    "eredivisie",
    "primeira_liga",
}


def test_exact_public_root_chain_is_intelligence_console_not_legacy_recommendations() -> None:
    app = Path("apps/web/src/App.tsx").read_text(encoding="utf-8")
    page = Path("apps/web/src/components/DashboardPage.tsx").read_text(encoding="utf-8")
    console = Path("apps/web/src/components/IntelligenceConsole.tsx").read_text(encoding="utf-8")
    active_chain = "\n".join((app, page, console))

    assert 'import { DashboardPage } from "./components/DashboardPage"' in app
    assert "<DashboardPage />" in app
    assert 'import { IntelligenceConsole } from "./IntelligenceConsole"' in page
    assert "<IntelligenceConsole" in page
    for legacy_component in (
        "BossDecisionView",
        "RecommendationBoard",
        "RecommendationCard",
    ):
        assert f"import {{ {legacy_component} }}" not in active_chain


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }


def test_round3_authority_isolated_from_legacy_action_modules() -> None:
    path = Path("src/w2/markets/round3_intelligence.py")
    imports = _imports(path)

    assert "w2.markets.analysis_evidence" not in imports
    assert "w2.domain.decision_adapter" not in imports
    assert "w2.markets.value_engine" not in imports
    assert not any(name.startswith("w2.providers") for name in imports)


def test_round3_whitelist_is_exact_13_and_fixture_aliases_are_not_conflicts() -> None:
    rows = [(value, {"scope_group": "top_five"}) for value in sorted(ACTIVE_13)]
    rows.append(("world_cup_2026", {"scope_group": "world_cup"}))

    assert _round3_active_whitelist(rows) == ACTIVE_13
    assert _round3_active_whitelist(rows[:-2]) == set()
    assert "1494218" in _fixture_aliases("api_football:1494218")


def test_model_forecast_fixture_ids_have_one_cross_table_form() -> None:
    assert canonical_model_forecast_fixture_id("1494244") == "api_football:1494244"
    assert (
        canonical_model_forecast_fixture_id("api_football:1494244")
        == "api_football:1494244"
    )
    assert model_forecast_fixture_aliases("1494244") == (
        "1494244",
        "api_football:1494244",
    )


def test_capture_priority_queries_cannot_bare_join_fixture_ids() -> None:
    for relative in (
        "src/w2/matchday/repository.py",
        "src/w2/ingestion/future_refresh_repository.py",
    ):
        source = Path(relative).read_text(encoding="utf-8")
        assert "canonical_model_forecast_fixture_id_sql" in source
        assert (
            "MatchdayCheckpointPlanModel.fixture_id\n"
            "                    == ModelForecastCaptureModel.fixture_id"
        ) not in source


def test_round3_materialization_read_query_count_is_constant_and_read_only() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    statements: list[str] = []

    def record_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lstrip().upper())

    event.listen(engine, "before_cursor_execute", record_statement)
    repository = FutureRefreshDbRepository(engine=engine)
    for fixture_ids in (["1"], [str(value) for value in range(64)]):
        statements.clear()
        repository.round3_market_evidence_for_fixtures(fixture_ids)
        assert len([value for value in statements if value.startswith("SELECT")]) == 2
        assert not any(
            value.startswith(("INSERT", "UPDATE", "DELETE", "MERGE")) for value in statements
        )


def test_round3_web_copy_has_no_action_or_profit_claims() -> None:
    source = Path("apps/web/src/components/IntelligenceConsole.tsx").read_text(encoding="utf-8")
    for forbidden in (
        "value bet",
        "edge opportunity",
        "recommended bet",
        "bet now",
        "high value",
        "profitable signal",
        "价值机会",
        "值得介入",
    ):
        assert forbidden.lower() not in source.lower()
    assert "优先检查模型校准、特征时效、盘口身份和数据质量" in source
    assert "HISTORICAL_INCREMENTAL_EDGE" in source
    assert 'data-ui="attention-feed"' in source
    assert "opportunity_score" not in source.lower()
    assert "value_score" not in source.lower()
