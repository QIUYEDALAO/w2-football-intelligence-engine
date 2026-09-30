"""F9 回测口径快照生成（离线，供偏差挖掘回测）。

对回测场次清单 CSV 的每场，为双方生成 F9 xG 滚动快照，写独立表
``team_xg_rolling_snapshot_backtest``，**不触碰线上 ``team_xg_rolling_snapshot``**。

回测口径：历史回填 xG 的 ``captured_at``（8 月回填时点）视为「比赛时点」，只要求
``kickoff_at < 目标开球`` 即算可用，不再要求 ``captured_at < 目标开球``
（即 ``materialize_rolling_xg(captured_before_cutoff=False)``）。

这是「假设数据最终回填完整」的回测口径，不是线上 PIT 口径；回测结论不得冒充线上 PIT 事实。

用法：
  python scripts/generate_f9_backtest_snapshots.py --csv <清单.csv> --dry-run
  python scripts/generate_f9_backtest_snapshots.py --csv <清单.csv> \
      --report-out /tmp/f9_bt_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.features.xg_materialization import TeamXgMatch, materialize_rolling_xg
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotBacktestModel,
)

BACKTEST_SOURCE_SYSTEM = "team_xg_match_backtest"
WINDOW = 5
MIN_MATCHES = 3


def _parse_kickoff(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def load_matches(session: Session) -> list[TeamXgMatch]:
    rows = session.scalars(select(TeamXgMatchModel)).all()
    matches: list[TeamXgMatch] = []
    for row in rows:
        matches.append(
            TeamXgMatch(
                fixture_id=row.fixture_id,
                team_id=row.team_id,
                opponent_team_id=row.opponent_team_id,
                kickoff_at=_as_utc(row.kickoff_at),
                captured_at=_as_utc(row.captured_at),
                xg_for=row.xg_for,
                xg_against=row.xg_against,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                raw_payload_sha256=row.raw_payload_sha256,
                source_system=row.source_system,
            )
        )
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-out", default=None)
    args = parser.parse_args()

    engine = create_engine()
    TeamXgRollingSnapshotBacktestModel.__table__.create(engine, checkfirst=True)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fixtures = []
    for row in rows:
        kickoff = _parse_kickoff(row.get("kickoff_at") or "")
        if kickoff is None:
            continue
        fixtures.append(
            {
                "fixture_id": row["fixture_id"],
                "home_team_id": row["home_team_id"],
                "away_team_id": row["away_team_id"],
                "kickoff_at": kickoff,
            }
        )

    with Session(engine) as session:
        matches = load_matches(session)

    snapshots = []
    ready = 0
    for fx in fixtures:
        home_snap = materialize_rolling_xg(
            team_id=fx["home_team_id"],
            as_of_fixture_id=fx["fixture_id"],
            as_of_time=fx["kickoff_at"],
            matches=matches,
            window=WINDOW,
            min_matches=MIN_MATCHES,
            captured_before_cutoff=False,
        )
        away_snap = materialize_rolling_xg(
            team_id=fx["away_team_id"],
            as_of_fixture_id=fx["fixture_id"],
            as_of_time=fx["kickoff_at"],
            matches=matches,
            window=WINDOW,
            min_matches=MIN_MATCHES,
            captured_before_cutoff=False,
        )
        if home_snap is not None and away_snap is not None:
            ready += 1
        if home_snap is not None:
            snapshots.append(home_snap)
        if away_snap is not None:
            snapshots.append(away_snap)

    total = len(fixtures)
    if not args.dry_run:
        with Session(engine) as session:
            for snap in snapshots:
                session.merge(
                    TeamXgRollingSnapshotBacktestModel(
                        snapshot_id=snap.snapshot_id,
                        team_id=snap.team_id,
                        as_of_fixture_id=snap.as_of_fixture_id,
                        as_of_time=snap.as_of_time,
                        match_count=snap.match_count,
                        rolling_xg_for=snap.rolling_xg_for,
                        rolling_xg_against=snap.rolling_xg_against,
                        rolling_goals_for=snap.rolling_goals_for,
                        rolling_goals_against=snap.rolling_goals_against,
                        regression_index=snap.regression_index,
                        source_system=BACKTEST_SOURCE_SYSTEM,
                    )
                )
            session.commit()

    report = {
        "schema_version": "w2.f9_backtest_snapshot.v1",
        "scope": "BACKTEST_LOOKBACK",
        "note": "captured_at 视为比赛时点；非线上 PIT 口径，回测结论不得冒充线上事实",
        "fixtures_total": total,
        "snapshots_generated": len(snapshots),
        "f9_ready_fixtures": ready,
        "f9_ready_rate": round(ready / total, 6) if total else None,
        "dry_run": args.dry_run,
        "target_table": "team_xg_rolling_snapshot_backtest",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report_out:
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
