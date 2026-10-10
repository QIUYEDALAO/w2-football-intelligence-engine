"""指令书 I 任务 A 的影子试点入口。

只写旁路表：``fs_request_log`` / ``fs_raw_payload`` / ``fs_league_season`` /
``fs_team`` / ``fs_fixture``。不触碰任何生产表，也不接入生产链路。

典型用法（研究库，非生产库）::

    W2_DATABASE_URL=postgresql+psycopg://.../w2_fs_shadow \\
    W2_FOOTYSTATS_API_KEY=... \\
    python scripts/quant/footystats_shadow_pilot.py run --out .local/pilot

``--details N`` 会额外抓 N 场完赛比赛的 ``match`` 详情——那是
``odds_comparison``（含 Pinnacle）唯一存在的端点。没有详情就测不出
「odds_comparison 非空率」，只能测出「该字段不存在」。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from w2.infrastructure.database import create_engine  # noqa: E402
from w2.quant_research import footystats_identity as identity  # noqa: E402
from w2.quant_research.footystats_client import FootyStatsClient  # noqa: E402
from w2.quant_research.footystats_shadow import (  # noqa: E402
    FootyStatsShadowCollector,
    FootyStatsShadowReporter,
)
from w2.quant_research.footystats_shadow_models import (  # noqa: E402
    FsFixtureModel,
    FsRequestLogModel,
)


def _quota_snapshot(engine) -> dict[str, object]:
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(FsRequestLogModel).order_by(FsRequestLogModel.requested_at)
            )
        )
    return {
        "calls_total": len(rows),
        "calls_failed": sum(1 for row in rows if row.payload_sha256 is None),
        "first_requested_at": rows[0].requested_at.astimezone(UTC).isoformat() if rows else None,
        "last_requested_at": rows[-1].requested_at.astimezone(UTC).isoformat() if rows else None,
        "first_remaining": rows[0].request_remaining if rows else None,
        "last_remaining": rows[-1].request_remaining if rows else None,
        "provider_limit": next(
            (row.request_limit for row in reversed(rows) if row.request_limit is not None), None
        ),
        "by_endpoint": _endpoint_counts(rows),
    }


def _endpoint_counts(rows) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.endpoint] = counts.get(row.endpoint, 0) + 1
    return counts


def _detail_targets(engine, limit: int) -> list[int]:
    """最近完赛的 N 场：按开球时间倒序取，确定性且可复现。"""
    with Session(engine) as session:
        rows = session.execute(
            select(FsFixtureModel.fs_match_id)
            .where(FsFixtureModel.status == "complete")
            .where(FsFixtureModel.competition_id.is_not(None))
            .order_by(FsFixtureModel.kickoff_utc.desc(), FsFixtureModel.fs_match_id.asc())
            .limit(limit)
        ).scalars()
        return [int(value) for value in rows]


def _detail_targets_per_competition(engine, per_competition: int) -> list[int]:
    """每个联赛抽 N 场完赛比赛抓详情。

    ``odds_comparison`` 只在 ``match`` 详情端点出现，所以要量逐联赛的
    odds_comparison / Pinnacle 覆盖率，就必须逐联赛去取详情；只取全局前 N 场
    会让大部分联赛的该指标恒为空，把「没测」伪装成「没有」。
    """
    with Session(engine) as session:
        rows = session.execute(
            select(
                FsFixtureModel.competition_id,
                FsFixtureModel.fs_match_id,
            )
            .where(FsFixtureModel.status == "complete")
            .where(FsFixtureModel.competition_id.is_not(None))
            .order_by(
                FsFixtureModel.competition_id,
                FsFixtureModel.kickoff_utc.desc(),
                FsFixtureModel.fs_match_id.asc(),
            )
        ).all()
    picked: list[int] = []
    counted: dict[str, int] = {}
    for competition_id, match_id in rows:
        key = str(competition_id)
        if counted.get(key, 0) >= per_competition:
            continue
        counted[key] = counted.get(key, 0) + 1
        picked.append(int(match_id))
    return picked


def _sync_summary(results) -> list[dict[str, object]]:
    return [
        {
            "endpoint": result.endpoint,
            "fixtures_seen": result.fixtures_seen,
            "fixtures_written": result.fixtures_written,
            "fixtures_rejected": result.fixtures_rejected,
            "teams_written": result.teams_written,
            "teams_conflicted": result.teams_conflicted,
            "matched": result.matched,
            "unmatched": result.unmatched,
            "ambiguous": result.ambiguous,
            "season_unmapped": result.season_unmapped,
            "blockers": result.blockers,
        }
        for result in results
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="FootyStats shadow pilot")
    parser.add_argument(
        "command", choices=["catalog", "run", "replay", "remap", "report"]
    )
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / ".local/pilot")
    parser.add_argument("--details", type=int, default=0, help="额外抓取的 match 详情场数")
    parser.add_argument(
        "--details-per-competition",
        type=int,
        default=0,
        help="每个联赛各抓 N 场完赛比赛的详情（用于逐联赛 odds_comparison 覆盖实测）",
    )
    parser.add_argument("--skip-todays", action="store_true")
    parser.add_argument("--skip-league-matches", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    engine = create_engine()
    client = FootyStatsClient(engine)
    reporter = FootyStatsShadowReporter(engine)
    results = []
    collisions: list[str] = []
    crosswalk_report: dict[str, Any] = {}

    if args.command == "catalog":
        collector = FootyStatsShadowCollector(engine, client)
        print(f"LEAGUE_SEASONS_WRITTEN={collector.sync_league_seasons()}")
        return 0

    if args.command in {"run", "replay", "remap"}:
        fixture_index = identity.load_production_fixture_index(engine)
        collector = FootyStatsShadowCollector(engine, client, fixture_index=fixture_index)
        if args.command == "replay":
            results.extend(collector.replay_raw_payloads())
        if args.command == "run":
            collector.sync_league_seasons()
            if not args.skip_league_matches:
                results.extend(
                    collector.sync_league_matches(sorted(identity.load_league_map()))
                )
            if not args.skip_todays:
                results.append(collector.sync_todays_matches(date.today()))
            targets = list(_detail_targets(engine, args.details)) if args.details else []
            if args.details_per_competition:
                targets.extend(
                    _detail_targets_per_competition(engine, args.details_per_competition)
                )
            if targets:
                results.extend(collector.sync_match_details(sorted(set(targets))))
        crosswalk_report = collector.resolve_team_crosswalk()
        results.append(collector.remap_existing())
        collisions = collector.resolve_mapping_collisions()

    payload = {
        "mapping_collisions": collisions,
        "crosswalk_report": crosswalk_report,
        "generated_at": datetime.now(UTC).isoformat(),
        "sync": _sync_summary(results),
        "quota": _quota_snapshot(engine),
    }
    if args.command in {"run", "replay", "remap", "report"}:
        payload["profile_report"] = reporter.profile_report()
        payload["mapping_report"] = reporter.mapping_report()
        payload["coverage_report"] = reporter.coverage_report()
        payload["xg_lag_report"] = reporter.xg_lag_report()
    (args.out / "pilot_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    quota = payload["quota"]
    print(
        f"PILOT_DONE calls={quota['calls_total']} failed={quota['calls_failed']} "
        f"remaining={quota['first_remaining']}->{quota['last_remaining']}"
    )
    for item in payload["sync"]:
        print(
            f"  {item['endpoint']:16} seen={item['fixtures_seen']:5} "
            f"written={item['fixtures_written']:5} matched={item['matched']:5} "
            f"unmatched={item['unmatched']:4} ambiguous={item['ambiguous']:3} "
            f"unmapped={item['season_unmapped']:4}"
        )
        for blocker in item["blockers"]:
            print(f"    BLOCKER {blocker}")
        for conflict in item["teams_conflicted"][:5]:
            print(f"    CONFLICT {conflict}")
    if crosswalk_report:
        print(
            f"  CROSSWALK production_teams={crosswalk_report['production_teams']} "
            f"resolved={crosswalk_report['crosswalk_resolved']} "
            f"rate={crosswalk_report['team_resolution_rate']:.4f} "
            f"methods={crosswalk_report['method_breakdown']}"
        )
    if "profile_report" in payload:
        profile = payload["profile_report"]
        print(
            f"  PROFILE fixtures={profile['fixtures']} "
            f"seasons={profile['distinct_seasons']} "
            f"competitions={profile['distinct_competitions']} "
            f"statuses={profile['status_breakdown']}"
        )
        if profile["unknown_statuses"]:
            print(f"  UNKNOWN_STATUSES {profile['unknown_statuses']}")
    if "mapping_report" in payload:
        report = payload["mapping_report"]
        print(
            f"  MAPPING reference={report['production_reference_fixtures']} "
            f"recall={report['production_recall']:.4f} "
            f"sampled={report['sampled']} accuracy={report['sampled_accuracy']:.4f} "
            f"pass={report['pass']} score_agree={report['sample_score_agree_rate']:.4f} "
            f"verdicts={report['sample_score_verdicts']}"
        )
        for collision in payload["mapping_collisions"]:
            print(f"    COLLISION {collision}")
        lag = payload["xg_lag_report"]
        print(
            f"  XG_LAG tracked={lag['tracked_with_xg']} "
            f"p50={lag['p50_seconds']} p90={lag['p90_seconds']}"
        )
    print(f"REPORT_WRITTEN {args.out / 'pilot_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
