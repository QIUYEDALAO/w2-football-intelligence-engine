from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.summarize_w2_league_whitelist_scope import build_scope_summary

from w2.backtest.free_tier_2024 import build_free_tier_2024_backtest_report
from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError

ROOT = Path(__file__).resolve().parents[2]


class FakeRegistry:
    def __init__(self, entries: dict[str, SimpleNamespace]) -> None:
        self.current_entries = entries
        self.calls = 0

    def entries(self) -> dict[str, SimpleNamespace]:
        self.calls += 1
        return self.current_entries


def _entry(
    competition_id: str,
    *,
    group: str,
    cohort: str = "",
    order: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        competition_id=competition_id,
        scope_group=group,
        audit_cohort=cohort,
        audit_order=order,
        enabled=False,
        season="2025",
        provider_mapping={"api_football_league_id": "1", "api_football_season": "2025"},
    )


def test_scope_hot_switches_without_module_reload() -> None:
    registry = FakeRegistry({"alpha": _entry("alpha", group="top_five")})
    assert load_league_whitelist_scope(registry).all_whitelist == ("alpha",)  # type: ignore[arg-type]

    registry.current_entries = {
        "beta": _entry("beta", group="national_leagues", cohort="IN_SEASON")
    }

    assert load_league_whitelist_scope(registry).all_whitelist == ("beta",)  # type: ignore[arg-type]
    assert registry.calls == 2


def test_summary_uses_one_registry_snapshot() -> None:
    registry = FakeRegistry(
        {
            "alpha": _entry("alpha", group="top_five"),
            "beta": _entry("beta", group="national_leagues", cohort="IN_SEASON"),
        }
    )

    payload = build_scope_summary(registry=registry)  # type: ignore[arg-type]

    assert payload["competition_count"] == 2
    assert registry.calls == 1


def test_explicit_backtest_scope_does_not_read_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_entries(self: CompetitionRegistry) -> object:
        raise AssertionError("registry must not be read for explicit competitions")

    monkeypatch.setattr(CompetitionRegistry, "entries", fail_entries)

    report = build_free_tier_2024_backtest_report(
        raw_dirs=(tmp_path,),
        competitions=("alpha",),
    )

    assert report["scope"]["annual_competitions"] == ["alpha"]


def test_default_backtest_scope_reads_one_registry_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def entries(self: CompetitionRegistry) -> dict[str, SimpleNamespace]:
        nonlocal calls
        calls += 1
        return {"alpha": _entry("alpha", group="top_five")}

    monkeypatch.setattr(CompetitionRegistry, "entries", entries)

    report = build_free_tier_2024_backtest_report(raw_dirs=(tmp_path,))

    assert report["scope"]["annual_competitions"] == ["alpha"]
    assert calls == 1


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ({}, "COMPETITION_DB_AUTHORITY_EMPTY"),
        (
            {"alpha": _entry("alpha", group="invalid")},
            "COMPETITION_SCOPE_GROUP_INVALID:alpha",
        ),
        (
            {"alpha": _entry("alpha", group="national_leagues", cohort="")},
            "COMPETITION_AUDIT_COHORT_INVALID:alpha",
        ),
        (
            {"alpha": _entry("alpha", group="top_five", order=999)},
            "COMPETITION_AUDIT_ORDER_INVALID:alpha",
        ),
    ],
)
def test_scope_fails_closed_for_empty_or_malformed_entries(
    entries: dict[str, SimpleNamespace],
    message: str,
) -> None:
    with pytest.raises(CompetitionRegistryError, match=message):
        load_league_whitelist_scope(FakeRegistry(entries))  # type: ignore[arg-type]


def test_scope_propagates_registry_unavailable() -> None:
    class UnavailableRegistry:
        def entries(self) -> object:
            raise CompetitionRegistryError("COMPETITION_DB_AUTHORITY_UNAVAILABLE")

    with pytest.raises(CompetitionRegistryError, match="COMPETITION_DB_AUTHORITY_UNAVAILABLE"):
        load_league_whitelist_scope(UnavailableRegistry())  # type: ignore[arg-type]


def test_audit_backtest_import_chain_has_no_runtime_side_effects() -> None:
    code = """
import importlib
from pathlib import Path
import urllib.request
import w2.competitions.registry as registry
import w2.infrastructure.database as database

def blocked(*args, **kwargs):
    raise AssertionError("import-time side effect")

database.create_engine = blocked
registry.CompetitionRegistry = blocked
urllib.request.urlopen = blocked
Path.write_text = blocked
for name in (
    "w2.competitions.league_whitelist_scope",
    "scripts.summarize_w2_league_whitelist_scope",
    "w2.backtest.free_tier_2024",
    "scripts.run_w2_free_tier_2024_backtest",
    "scripts.run_w2_league_whitelist_audit",
):
    importlib.import_module(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_removed_dynamic_scope_symbols_have_no_source_references() -> None:
    removed = (
        "TOP_FIVE_" + "COMPETITIONS",
        "WORLD_CUP_" + "COMPETITIONS",
        "IN_SEASON_NATIONAL_" + "LEAGUES",
        "NATIONAL_LEAGUES_" + "OFFSEASON",
        "ALL_WHITELIST_" + "COMPETITIONS",
        "REMAINING_UNAUDITED_" + "WHITELIST",
        "ANNUAL_" + "COMPETITIONS",
    )
    source_roots = (ROOT / "src", ROOT / "scripts")
    offenders = [
        path
        for source_root in source_roots
        for path in source_root.rglob("*.py")
        if any(symbol in path.read_text(encoding="utf-8") for symbol in removed)
    ]
    assert offenders == []
