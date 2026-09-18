from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.candidate_notifications import (
    materialize_validation_samples,
    validation_sample_totals,
    validation_samples_snapshot,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_competition(session: Session, competition_id: str = "chinese_super_league") -> None:
    session.add(
        LeagueSeasonModel(
            competition_id=competition_id,
            season="2026",
            lifecycle="ACTIVE",
            payload={"enabled": True},
        )
    )


def _seed_fixture(
    session: Session,
    *,
    fixture_id: str,
    kickoff: datetime,
    competition_id: str = "chinese_super_league",
) -> None:
    session.add(
        MatchdayFixtureIdentityModel(
            fixture_id=f"api_football:{fixture_id}",
            provider="api_football",
            provider_fixture_id=fixture_id,
            competition_id=competition_id,
            provider_league_id="169",
            season="2026",
            kickoff_utc=kickoff,
            fixture_status="NS",
            home_provider_team_id="1",
            away_provider_team_id="2",
            home_w2_team_id=None,
            away_w2_team_id=None,
            team_identity_status="PROVIDER_ONLY",
            raw_payload_sha256="3" * 64,
            endpoint_capture_id=None,
            captured_at=kickoff - timedelta(days=1),
            identity_hash="4" * 64,
            payload={"home_team_name": "主队", "away_team_name": "客队"},
        )
    )


def _seed_sample(
    session: Session,
    *,
    fixture_id: str,
    market: str = "ASIAN_HANDICAP",
    evaluated_at: datetime,
    selection: str = "HOME",
    line: str = "-0.5",
    odds: str = "1.90",
) -> None:
    suffix = f"{fixture_id}-{market}"
    session.add(
        DynamicPrematchEvaluationModel(
            evaluation_id=f"eval-{suffix}",
            identity_hash=hashlib.sha256(f"eval-{suffix}".encode()).hexdigest(),
            fixture_id=fixture_id,
            market=market,
            selection=selection,
            checkpoint="T3_ODDS",
            evaluated_at=evaluated_at,
            capture_at=evaluated_at,
            original_state="EVALUATED_CANDIDATE",
            official_funnel_eligible=True,
            opportunity_identity_hash=f"opp-{suffix}",
            attempt_identity_hash=f"att-{suffix}",
            payload={
                "state": "ANALYSIS_PICK_ACTIVE",
                "exact_line": line,
                "decimal_odds": odds,
            },
        )
    )
    session.add(
        DynamicPrematchOpportunityModel(
            opportunity_identity_hash=f"opp-{suffix}",
            fixture_id=fixture_id,
            market=market,
            model_forecast_capture_identity_hash="m" * 64,
            evaluation_policy_version="candidate-eval.v1",
            evaluation_slot_id="T3_ODDS",
            scheduled_checkpoint_at=evaluated_at,
            checkpoint_plan_identity=f"plan-{suffix}",
            state="EVALUATED_CANDIDATE",
            recorded_at=evaluated_at,
            latest_attempt_identity_hash=f"att-{suffix}",
            payload={},
        )
    )


def _seed_result(session: Session, *, fixture_id: str, home: int, away: int) -> None:
    session.add(
        ResultModel(
            id=f"result-{fixture_id}",
            fixture_id=f"api_football:{fixture_id}",
            home_goals=home,
            away_goals=away,
            result_status="FT",
            confirmed_at=NOW + timedelta(hours=2),
            source_payload_sha256="c" * 64,
            source_capture_id=None,
            result_hash="d" * 64,
        )
    )


def test_materialize_writes_in_window_samples() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW)
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        session.commit()

        report = materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    assert report["window_fixtures"] == 1
    assert report["window_rows"] == 1
    with Session(engine) as session:
        rows = list(session.scalars(select(ValidationSampleModel)))
        assert len(rows) == 1
        assert rows[0].fixture_id == "1523202"
        assert rows[0].market == "ASIAN_HANDICAP"
        assert rows[0].settlement == "PENDING"
        assert rows[0].profit_units is None


def test_materialize_settles_with_result() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW)
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        _seed_result(session, fixture_id="1523202", home=2, away=1)
        session.commit()

        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    with Session(engine) as session:
        row = session.scalar(select(ValidationSampleModel))
        assert row.settlement == "WIN"
        assert row.profit_units is not None
        assert row.settled_at is not None


def test_materialize_freezes_out_of_window_rows() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW)
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        session.commit()
        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    # 第二次物化：样本仍在窗口内 → 保留（deleted=0）。
    with Session(engine) as session:
        report = materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()
        assert report["deleted"] == 0

    # 窗口外：物化时间前进，样本开球已离开窗口 → 冻结不动（不删除）。
    later = NOW + timedelta(days=5)
    with Session(engine) as session:
        report = materialize_validation_samples(session, now=later, window_before_days=3, window_after_days=1)
        session.commit()
        assert report["window_rows"] == 0
        assert report["deleted"] == 0  # 窗口外冻结，不删除

    with Session(engine) as session:
        assert session.scalar(select(ValidationSampleModel)) is not None  # 冻结保留


def test_materialize_deletes_window_row_no_longer_a_sample() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW)
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        session.commit()
        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    # 把 opportunity 状态改为不再候选（样本不再属于验证样本集）→ 窗口内重算后删除。
    with Session(engine) as session:
        opp = session.scalar(select(DynamicPrematchOpportunityModel))
        opp.state = "EVALUATED_NO_EDGE"
        session.commit()

        report = materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()
        assert report["window_rows"] == 0
        assert report["deleted"] == 1

    with Session(engine) as session:
        assert session.scalar(select(ValidationSampleModel)) is None


def test_materialize_filters_withdrawn_competition() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session, competition_id="enabled_league")
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW, competition_id="withdrawn_league")
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        session.commit()

        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    # 撤出白名单（enabled_league 才是 active），withdrawn_league 的样本不计入。
    with Session(engine) as session:
        assert session.scalar(select(ValidationSampleModel)) is None


def test_snapshot_sorted_desc_with_ah_before_totals() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="early", kickoff=NOW - timedelta(hours=1))
        _seed_fixture(session, fixture_id="late", kickoff=NOW)
        _seed_sample(session, fixture_id="early", market="ASIAN_HANDICAP", evaluated_at=NOW - timedelta(hours=2))
        _seed_sample(session, fixture_id="early", market="TOTALS", evaluated_at=NOW - timedelta(hours=2))
        _seed_sample(session, fixture_id="late", market="ASIAN_HANDICAP", evaluated_at=NOW - timedelta(hours=2))
        session.commit()
        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    with Session(engine) as session:
        rows = validation_samples_snapshot(session)
    assert [(r["fixture_id"], r["market"]) for r in rows] == [
        ("late", "ASIAN_HANDICAP"),
        ("early", "ASIAN_HANDICAP"),
        ("early", "TOTALS"),
    ]


def test_snapshot_pagination_and_totals() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        for index in range(5):
            fid = f"fix{index}"
            _seed_fixture(session, fixture_id=fid, kickoff=NOW + timedelta(minutes=index))
            _seed_sample(session, fixture_id=fid, evaluated_at=NOW - timedelta(hours=3))
        session.commit()
        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

    with Session(engine) as session:
        page = validation_samples_snapshot(session, limit=2, offset=0)
        assert len(page) == 2
        totals = validation_sample_totals(session)
    assert totals["total_count"] == 5
    assert totals["settled_count"] == 0
    assert totals["total_profit_units"] == 0.0
    assert totals["by_calibration_identity"] == [
        {"calibration_identity": None, "count": 5, "profit_units": 0.0}
    ]


def test_reconcile_table_matches_projection() -> None:
    """物化后表内容与投影一一对应（条数、赔率、结算、profit_units 全等）。"""
    engine = _engine()
    with Session(engine) as session:
        _seed_competition(session)
        _seed_fixture(session, fixture_id="1523202", kickoff=NOW)
        _seed_sample(session, fixture_id="1523202", evaluated_at=NOW - timedelta(hours=3))
        _seed_result(session, fixture_id="1523202", home=2, away=1)
        session.commit()

        materialize_validation_samples(session, now=NOW, window_before_days=3, window_after_days=1)
        session.commit()

        from w2.prematch.candidate_notifications import (
            _official_recommendations_dashboard_scope,
        )

        projected = _official_recommendations_dashboard_scope(session)
        rows = {r.fixture_id: r for r in session.scalars(select(ValidationSampleModel))}

    assert len(rows) == len(projected) == 1
    proj = projected[0]
    row = rows["1523202"]
    assert row.decimal_odds == proj["decimal_odds"]
    assert row.settlement == proj["settlement"]
    assert row.profit_units == proj["profit_units"]
    assert row.exact_line == proj["exact_line"]
    assert row.selection == proj["selection"]
