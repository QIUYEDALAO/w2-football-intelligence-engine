"""偏差挖掘 T0 · 数据盘点（只盘数据，不看盈亏）。

Pinnacle 报价 × canonical 赛果 join，按「同场一次、互补侧一次、固定决策时点」去重，
输出：独立比赛数、半盘口(.5)样本量、日期分布、报价时点覆盖、缺口清单。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
from w2.infrastructure.persistence.models import ResultModel

PROVIDER = "api_football"
PINNACLE = "4"


def _is_half(line: str | None) -> bool:
    if not line:
        return False
    try:
        value = float(line)
    except ValueError:
        return False
    doubled = value * 2
    return abs(doubled - round(doubled)) < 1e-9 and int(round(doubled)) % 2 == 1


def main() -> None:
    engine = create_engine()
    with Session(engine) as session:
        obs = session.scalars(
            select(MatchdayMarketObservationModel).where(
                MatchdayMarketObservationModel.bookmaker_id == PINNACLE,
                MatchdayMarketObservationModel.canonical_market == "ASIAN_HANDICAP",
            )
        ).all()
        results = {
            r.fixture_id: r
            for r in session.scalars(select(ResultModel).where(ResultModel.result_status == "FT"))
        }

    # 按 fixture 聚合：每个 fixture 的报价（多 line / 多 captured_at / 双侧）。
    by_fixture: dict[str, list] = defaultdict(list)
    for o in obs:
        by_fixture[o.fixture_id].append(o)

    joined = {fid: rows for fid, rows in by_fixture.items() if fid in results}

    # 去重口径 1：同场一次 + 互补侧一次（两侧同 line 视为一场）。
    # 去重口径 2：固定决策时点 = 每场取 kickoff 前最近的 captured_at 所在 snapshot。
    independent: list[dict] = []
    for fid, rows in joined.items():
        if not rows:
            continue
        latest = max(rows, key=lambda r: r.captured_at)
        # 固定时点：以该场最新一次 capture 为决策时点，取该时点全部 line。
        snapshot = [r for r in rows if r.captured_at == latest.captured_at]
        half_lines = {r.line for r in snapshot if _is_half(r.line)}
        if not half_lines:
            continue
        independent.append(
            {
                "fixture_id": fid,
                "captured_at": latest.captured_at,
                "half_line_count": len(half_lines),
            }
        )

    # 半盘口(.5)独立比赛数 + 日期/联赛/盘口分布
    half_fixtures = [f for f in independent]
    by_month: Counter[str] = Counter()
    by_league: Counter[str] = Counter()
    obs_by_fixture = {o.fixture_id: o for o in obs}
    for f in half_fixtures:
        by_month[f["captured_at"].strftime("%Y-%m")] += 1
        o = obs_by_fixture.get(f["fixture_id"])
        if o is not None:
            by_league[o.competition_id] += 1

    # 报价时点覆盖：latest snapshot 的 captured_at 时点分布（按小时）。
    by_hour: Counter[int] = Counter()
    for f in half_fixtures:
        by_hour[f["captured_at"].hour] += 1

    # 缺口清单：有 Pinnacle 报价但无 FT 赛果的 fixture 数；无 Pinnacle 报价但有赛果的 fixture。
    result_fixtures = set(results.keys())
    with_pinnacle = set(by_fixture.keys())
    gap_no_result = with_pinnacle - result_fixtures
    gap_no_pinnacle = result_fixtures - with_pinnacle

    report = {
        "pinnacle_ah_quote_rows": len(obs),
        "distinct_fixtures_with_pinnacle": len(with_pinnacle),
        "distinct_ft_results": len(result_fixtures),
        "joined_fixtures": len(joined),
        "half_line_independent_fixtures": len(half_fixtures),
        "half_line_date_distribution": dict(sorted(by_month.items())),
        "half_line_league_distribution": dict(sorted(by_league.items(), key=lambda kv: -kv[1])),
        "capture_hour_distribution": dict(sorted(by_hour.items())),
        "gap_no_result_fixtures": len(gap_no_result),
        "gap_no_pinnacle_fixtures": len(gap_no_pinnacle),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
