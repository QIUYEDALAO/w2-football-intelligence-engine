"""xG 增量补采：赛后 < 48h 跳过、>= 48h 补采（真实 PG repo + mock client）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.ingestion.xg_backfill import XgBackfillConfig, XgHistoryBackfillService
from w2.providers.api_football import LiveApiFootballResponse

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _finished(kickoff: datetime, *, home: str, away: str) -> dict:
    return {
        "fixture": {
            "id": f"rec-{home}",
            "date": kickoff.isoformat(),
            "status": {"short": "FT"},
        },
        "league": {"id": 113, "season": 2026},
        "teams": {"home": {"id": int(home)}, "away": {"id": int(away)}},
        "goals": {"home": 2, "away": 1},
    }


def _client(*, days_ago: int) -> "_RecorderClient":
    return _RecorderClient(days_ago)


class _RecorderClient:
    def __init__(self, days_ago: int) -> None:
        self.days_ago = days_ago
        self.statistics_calls = 0

    def request_live(self, endpoint: str, params: dict):
        if endpoint == "fixtures":
            team = params["team"]
            opponent = "20" if team == "10" else "10"
            recent = _finished(
                datetime.now(UTC) - timedelta(days=self.days_ago),
                home=team,
                away=opponent,
            )
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=200,
                elapsed_ms=1,
                payload={"response": [recent]},
                headers={"x-apisports-requests-remaining": "6000"},
                captured_at=datetime.now(UTC),
                requested_at=datetime.now(UTC),
            )
        self.statistics_calls += 1
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=1,
            payload={
                "response": [
                    {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": "1.7"}]},
                    {"team": {"id": 20}, "statistics": [{"type": "expected_goals", "value": "0.8"}]},
                ]
            },
            headers={"x-apisports-requests-remaining": "6000"},
            captured_at=datetime.now(UTC),
            requested_at=datetime.now(UTC),
        )


def test_xg_incremental_backfill_skips_recent_finished(chain) -> None:
    """任务2 验收①③：赛后 < 48h 的 FT 缺 xG → 跳过补采（真实 repo，避免白采）。"""
    repo, _future, _plan, _producer = chain
    client = _client(days_ago=1)  # 24h < 48h
    XgHistoryBackfillService(
        repository=repo,
        client=client,
        now=datetime.now(UTC),
        config=XgBackfillConfig(competition_ids=("allsvenskan",)),
    ).run()
    assert client.statistics_calls == 0


def test_xg_incremental_backfill_captures_old_finished(chain) -> None:
    """反向控制：赛后 >= 48h 的 FT 缺 xG → 补采 statistics（每次 tick 增量补采）。"""
    repo, _future, _plan, _producer = chain
    client = _client(days_ago=3)  # 72h >= 48h
    result = XgHistoryBackfillService(
        repository=repo,
        client=client,
        now=datetime.now(UTC),
        config=XgBackfillConfig(competition_ids=("allsvenskan",)),
    ).run()
    assert result.team_count == 2, result.as_dict()
    assert client.statistics_calls == 2, f"statistics_calls={client.statistics_calls}, result={result.as_dict()}"
