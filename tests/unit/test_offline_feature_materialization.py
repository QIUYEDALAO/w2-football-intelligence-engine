from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from w2.features.offline_materialization import materialize_from_pro_cache

KICKOFF = datetime(2026, 7, 20, 12, tzinfo=UTC)


def test_materializes_target_snapshots_from_cached_history(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    fixtures = [
        _fixture(str(index), KICKOFF - timedelta(days=10 - index), "FT")
        for index in range(5)
    ]
    fixtures.append(_fixture("target", KICKOFF, "NS"))
    _write(raw_root / "fixtures" / "fixtures.json", _wrapper({}, fixtures))
    for index in range(5):
        _write(
            raw_root / "statistics" / f"statistics-{index}.json",
            _wrapper(
                {"fixture": str(index)},
                [
                    _stats("home", 1.4 + index * 0.1),
                    _stats("away", 1.0 + index * 0.1),
                ],
            ),
        )

    result = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("target",),
    )

    assert result.blockers == ()
    assert len(result.matches) == 10
    assert len(result.snapshots) == 2
    assert {row.team_id for row in result.snapshots} == {"home", "away"}
    assert all(row.match_count == 5 for row in result.snapshots)
    assert all(row.as_of_time == KICKOFF for row in result.snapshots)
    assert result.summary()["provider_calls"] == 0
    assert result.summary()["db_writes"] == 0


def test_missing_history_fails_closed(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    _write(
        raw_root / "fixtures" / "fixtures.json",
        _wrapper({}, [_fixture("target", KICKOFF, "NS")]),
    )

    result = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("target",),
    )

    assert len(result.snapshots) == 0
    assert result.blockers == (
        "FEATURE_HISTORY_INSUFFICIENT:target:away",
        "FEATURE_HISTORY_INSUFFICIENT:target:home",
    )


def _fixture(fixture_id: str, kickoff: datetime, status: str) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": status},
        },
        "league": {"id": 169, "season": 2026},
        "teams": {"home": {"id": "home"}, "away": {"id": "away"}},
        "goals": {"home": 2, "away": 1},
    }


def _stats(team_id: str, xg: float) -> dict[str, object]:
    return {
        "team": {"id": team_id},
        "statistics": [{"type": "expected_goals", "value": xg}],
    }


def _wrapper(params: dict[str, str], response: list[dict[str, object]]) -> dict[str, object]:
    return {
        "captured_at": "2026-07-10T00:00:00Z",
        "params": params,
        "payload": {"response": response},
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
