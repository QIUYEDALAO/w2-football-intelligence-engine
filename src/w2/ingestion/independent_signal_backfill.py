from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from w2.ingestion.future_refresh import fixture_id_from_payload, kickoff_from_payload
from w2.ingestion.quota_budget import independent_signal_quota_decision
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse

IndependentSignalTask = Literal[
    "team_fixture_history_backfill",
    "h2h_backfill",
    "squad_value_mapping",
    "ratings_backfill",
    "all",
]


class FixturePayloadProvider(Protocol):
    def fixture_payloads(self) -> list[dict[str, Any]]:
        pass


class IndependentSignalProvider(Protocol):
    def fixtures_by_team(
        self,
        *,
        team_id: str,
        season: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        pass

    def h2h(
        self,
        *,
        team_a_id: str,
        team_b_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        pass


@dataclass(frozen=True)
class IndependentSignalBackfillConfig:
    task: IndependentSignalTask
    competition_id: str
    season: str
    window: str = "next36"
    fixture_id: str | None = None
    dry_run: bool = True
    write_artifacts: bool = False
    max_fixtures: int = 20
    remaining_quota_override: Any = None
    runtime_root: Path = Path("runtime/independent_signal_backfill")


@dataclass
class IndependentSignalBackfillService:
    fixture_provider: FixturePayloadProvider
    client: IndependentSignalProvider | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    def run(self, config: IndependentSignalBackfillConfig) -> dict[str, Any]:
        tasks = _expand_tasks(config.task)
        selected = self._selected_fixtures(config)
        results = [self._run_single(task=task, fixtures=selected, config=config) for task in tasks]
        if len(results) == 1:
            return results[0]
        return _combine_results(config=config, results=results, selected_fixtures=len(selected))

    def _run_single(
        self,
        *,
        task: str,
        fixtures: list[dict[str, Any]],
        config: IndependentSignalBackfillConfig,
    ) -> dict[str, Any]:
        decision = independent_signal_quota_decision(
            remaining_quota=config.remaining_quota_override,
            task_type=task,
        )
        result = _empty_result(
            task=task,
            dry_run=config.dry_run,
            selected_fixtures=len(fixtures),
            quota_decision=decision,
        )
        if not decision["allowed"]:
            result["status"] = "blocked"
            result["blockers"].append(decision["reason"])
            return result
        if config.dry_run:
            return result
        if task in {"squad_value_mapping", "ratings_backfill"}:
            return result
        if not config.write_artifacts:
            return result
        provider = self.client or ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset({"fixtures", "h2h"}),
        )
        if task == "team_fixture_history_backfill":
            return self._run_team_fixture_history(
                provider=provider,
                fixtures=fixtures,
                config=config,
                result=result,
            )
        if task == "h2h_backfill":
            return self._run_h2h(
                provider=provider,
                fixtures=fixtures,
                config=config,
                result=result,
            )
        return result

    def _run_team_fixture_history(
        self,
        *,
        provider: IndependentSignalProvider,
        fixtures: list[dict[str, Any]],
        config: IndependentSignalBackfillConfig,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        for team_id in _team_ids(fixtures):
            response = provider.fixtures_by_team(team_id=team_id, season=config.season)
            result["provider_calls"] += 1
            result["artifacts_written"] += write_raw_artifact(
                runtime_root=config.runtime_root,
                endpoint="fixtures",
                key=f"team_{team_id}",
                response=response,
            )
        result["would_call_provider"] = bool(_team_ids(fixtures))
        result["would_write_artifacts"] = result["artifacts_written"] > 0
        return result

    def _run_h2h(
        self,
        *,
        provider: IndependentSignalProvider,
        fixtures: list[dict[str, Any]],
        config: IndependentSignalBackfillConfig,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        for home_id, away_id in _fixture_pairs(fixtures):
            response = provider.h2h(team_a_id=home_id, team_b_id=away_id)
            result["provider_calls"] += 1
            result["artifacts_written"] += write_raw_artifact(
                runtime_root=config.runtime_root,
                endpoint="h2h",
                key=f"{home_id}_{away_id}",
                response=response,
            )
        result["would_call_provider"] = bool(_fixture_pairs(fixtures))
        result["would_write_artifacts"] = result["artifacts_written"] > 0
        return result

    def _selected_fixtures(self, config: IndependentSignalBackfillConfig) -> list[dict[str, Any]]:
        rows = [
            item
            for item in self.fixture_provider.fixture_payloads()
            if _fixture_matches_window(item, now=self.now, window=config.window)
        ]
        if config.fixture_id:
            rows = [item for item in rows if fixture_id_from_payload(item) == config.fixture_id]
        return rows[: max(config.max_fixtures, 0)]


def write_raw_artifact(
    *,
    runtime_root: Path,
    endpoint: str,
    key: str,
    response: LiveApiFootballResponse,
) -> int:
    payload_hash = hashlib.sha256(
        json.dumps(response.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path = runtime_root / "raw_payloads" / endpoint / f"{key}_{payload_hash}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": endpoint,
                "captured_at": response.captured_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "payload": response.payload,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 1


def _expand_tasks(task: IndependentSignalTask) -> list[str]:
    if task == "all":
        return [
            "team_fixture_history_backfill",
            "h2h_backfill",
            "squad_value_mapping",
            "ratings_backfill",
        ]
    return [task]


def _empty_result(
    *,
    task: str,
    dry_run: bool,
    selected_fixtures: int,
    quota_decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "task": task,
        "dry_run": dry_run,
        "would_call_provider": False,
        "would_write_artifacts": False,
        "quota_decision": quota_decision,
        "selected_fixtures": selected_fixtures,
        "provider_calls": 0,
        "artifacts_written": 0,
        "blockers": [],
        "errors": [],
    }


def _combine_results(
    *,
    config: IndependentSignalBackfillConfig,
    results: list[dict[str, Any]],
    selected_fixtures: int,
) -> dict[str, Any]:
    blockers = [blocker for result in results for blocker in result["blockers"]]
    errors = [error for result in results for error in result["errors"]]
    return {
        "status": "error" if errors else "blocked" if blockers else "ok",
        "task": config.task,
        "dry_run": config.dry_run,
        "would_call_provider": any(result["would_call_provider"] for result in results),
        "would_write_artifacts": any(result["would_write_artifacts"] for result in results),
        "quota_decision": {result["task"]: result["quota_decision"] for result in results},
        "selected_fixtures": selected_fixtures,
        "provider_calls": sum(int(result["provider_calls"]) for result in results),
        "artifacts_written": sum(int(result["artifacts_written"]) for result in results),
        "blockers": blockers,
        "errors": errors,
        "tasks": results,
    }


def _fixture_matches_window(item: dict[str, Any], *, now: datetime, window: str) -> bool:
    kickoff = kickoff_from_payload(item)
    if kickoff is None:
        return False
    if window == "all":
        return True
    if kickoff < now:
        return False
    if window == "today":
        return kickoff.date() == now.date()
    if window == "next36":
        return kickoff <= now + timedelta(hours=36)
    return False


def _team_ids(fixtures: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for home_id, away_id in _fixture_pairs(fixtures):
        ids.extend([home_id, away_id])
    return list(dict.fromkeys(ids))


def _fixture_pairs(fixtures: list[dict[str, Any]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in fixtures:
        raw_teams = item.get("teams")
        teams = raw_teams if isinstance(raw_teams, dict) else {}
        raw_home = teams.get("home")
        raw_away = teams.get("away")
        home = raw_home if isinstance(raw_home, dict) else {}
        away = raw_away if isinstance(raw_away, dict) else {}
        home_id = str(home.get("id") or "")
        away_id = str(away.get("id") or "")
        if home_id and away_id:
            pairs.append((home_id, away_id))
    return pairs
