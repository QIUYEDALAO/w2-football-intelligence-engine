"""V9 production chain on isolated PostgreSQL, synthetic upstream, network=0."""

import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.orm import Session
from tests.integration import test_future_refresh_db_persistence as harness
from tests.integration.test_ah_ou_v3_real_chain import PinnacleAhOuClient

from w2.config import get_settings
from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.ingestion.future_refresh import sha256_payload
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.h2h_capture import capture_h2h_for_pair
from w2.ingestion.xg_backfill import XgBackfillConfig, XgHistoryBackfillService
from w2.prematch.analysis_calculator import ReadModelService
from w2.providers.api_football import LiveApiFootballResponse


def _build_chain(tmp_path, monkeypatch, *, existing_database_url=None, environment="test",
                 market_prices=None, ah_line="-0.5", bookmaker_id=None):
    import os
    import subprocess

    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    if existing_database_url is None:
        admin = create_engine(url, isolation_level="AUTOCOMMIT")
        name = "w2_v9chain_" + uuid.uuid4().hex[:12]
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        db = url.rsplit("/", 1)[0] + "/" + name
    else:
        # A replica rehearsal supplies its own dedicated, already-migrated DB.
        # It still runs every producer/capture/freeze operation below unchanged.
        db = existing_database_url
    monkeypatch.setenv("W2_DATABASE_URL", db)
    monkeypatch.setenv("W2_ENVIRONMENT", environment)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    # The public router is imported once per pytest process. Bind its read
    # service to this case's isolated database before the first API request.
    from w2.api import routers
    from w2.api.repository import ReadModelService as ApiReadModelService

    monkeypatch.setattr(routers, "service", ApiReadModelService())
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
        capture_output=True,
    )
    now = datetime.now(UTC).replace(microsecond=0)
    kickoff = now + timedelta(hours=7)
    monkeypatch.setattr(harness, "NOW", now)
    from w2.competitions.seed import (
        apply_collection_policy_update,
        seed_competition_runtime_authority,
    )

    repo = FutureRefreshDbRepository()
    seed_competition_runtime_authority(repo.engine, environment=environment, now=now)
    apply_collection_policy_update(repo.engine, updated_by="v9-isolated", now=now)
    harness.seed_odds_checkpoint("1489404", with_identity=True)
    from w2.matchday.repository import MatchdayRuntimeRepository

    plans = MatchdayRuntimeRepository().claim_due_checkpoint_plans(now=now, worker_id="v9")

    class Odds(PinnacleAhOuClient):
        def __init__(self) -> None:
            super().__init__(ah_line=ah_line)

        def payload(self, endpoint, params):
            raw = super().payload(endpoint, params)
            if endpoint == "fixtures":
                for observed in raw.get("response", []):
                    if str((observed.get("fixture") or {}).get("id")) == "1489404":
                        observed["fixture"]["date"] = kickoff.isoformat()
            if endpoint == "odds":
                if bookmaker_id is not None:
                    # P0: 非 Pinnacle 报价真实链——bookmaker 换成 Bet365（id=8）。
                    raw["response"][0]["bookmakers"][0]["id"] = bookmaker_id
                    raw["response"][0]["bookmakers"][0]["name"] = "Bet365"
                values = raw["response"][0]["bookmakers"][0]["bets"][0]["values"]
                values[0]["odd"] = "1.25"
                values[1]["odd"] = "4.50"
                if market_prices:
                    for market, bet in zip(("ASIAN_HANDICAP", "TOTALS"),
                                          raw["response"][0]["bookmakers"][0]["bets"], strict=True):
                        for value, price in zip(bet["values"], market_prices[market], strict=True):
                            value["odd"] = price
            return raw

        def request_live(self, endpoint, params):
            response = super().request_live(endpoint, params)
            return LiveApiFootballResponse(
                **{**response.__dict__, "captured_at": now, "requested_at": now}
            )

    harness.run_direct_checkpoint(tmp_path, Odds(), *plans)
    with Session(repo.engine) as session, session.begin():
        for pid, w2 in [("10", "H"), ("20", "A")]:
            session.add(
                CanonicalTeamModel(
                    w2_team_id=w2,
                    display_name=w2,
                    active_status="ACTIVE",
                    created_at=now,
                    identity_hash=pid * 32,
                    payload={},
                )
            )
            session.add(
                ProviderTeamIdentityCrosswalkModel(
                    id="v9-" + pid,
                    provider="api_football",
                    provider_team_id=pid,
                    w2_team_id=w2,
                    competition_id="allsvenskan",
                    season="2026",
                    valid_from=now - timedelta(days=400),
                    identity_status="PROVIDER_PRIMARY_READY",
                    evidence_hashes=[],
                    identity_hash=pid * 32,
                )
            )
        identity = session.get(MatchdayFixtureIdentityModel, "api_football:1489404")
        identity.kickoff_utc = kickoff
        identity.home_w2_team_id = "H"
        identity.away_w2_team_id = "A"
        identity.team_identity_status = "READY"

    def fixture(fid, date, status):
        return {
            "fixture": {"id": fid, "date": date.isoformat(), "status": {"short": status}},
            "league": {"id": 113, "season": 2026},
            "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
            "goals": {"home": 4, "away": 0},
        }

    future = fixture(1489404, kickoff, "NS")
    past = [fixture(9100 + i, now - timedelta(days=30 - i), "FT") for i in range(3)]
    raw = {"response": [future, *past]}
    repo.save_raw_payload(
        sha256=sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD),
        endpoint="fixtures",
        captured_at=now,
        payload=raw,
    )
    for item in past:
        payload = {
            "parameters": {"fixture": str(item["fixture"]["id"])},
            "response": [
                {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": "3.8"}]},
                {"team": {"id": 20}, "statistics": [{"type": "expected_goals", "value": "0.4"}]},
            ],
        }
        repo.save_raw_payload(
            sha256=sha256_payload(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD),
            endpoint="statistics",
            captured_at=now,
            payload=payload,
        )
    producer = XgHistoryBackfillService(
        repository=repo,
        client=object(),
        now=now,
        config=XgBackfillConfig(competition_ids=("allsvenskan",)),
    )
    plan = producer.build_saved_raw_plan()
    result = producer.run_saved_raw()
    assert result.rolling_snapshot_rows == 2, result.as_dict()

    class H2H:
        def request_live(self, endpoint, params):
            assert endpoint == "h2h"
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=200,
                elapsed_ms=1,
                payload={"response": past},
                headers={},
                captured_at=now,
                requested_at=now,
            )

    assert (
        capture_h2h_for_pair(
            home_provider_team_id="10",
            away_provider_team_id="20",
            competition_id="allsvenskan",
            season="2026",
            client=H2H(),
        )
        == 6
    )
    repo._v9_h2h_client = H2H()
    try:
        yield repo, future, plan, producer
    finally:
        evidence_dir = os.environ.get("W2_PG_EVIDENCE_DIR")
        if evidence_dir:
            import json
            from pathlib import Path

            from sqlalchemy import inspect

            output = Path(evidence_dir)
            output.mkdir(parents=True, exist_ok=True)
            tables = (
                "raw_payloads",
                "matchday_endpoint_captures",
                "matchday_market_observations",
                "team_xg_rolling_snapshot",
                "canonical_team_match_history",
                "ah_ou_decision_ledger",
                "ah_ou_forward_cohort",
                "results",
                "ah_ou_v3_settlement",
                "ah_ou_v3_validation_sample",
                "ah_ou_v3_monitoring_fact",
                "ah_ou_v3_monitoring_report",
                "candidate_notification_outbox",
            )
            with repo.engine.connect() as connection:
                snapshot = {
                    table: [
                        dict(row)
                        for row in connection.execute(
                            select(Table(table, MetaData(), autoload_with=connection))
                        ).mappings()
                    ]
                    for table in tables
                    if inspect(connection).has_table(table)
                }
            target = output / (str(repo.engine.url.database) + "-" + uuid.uuid4().hex + ".json")
            target.write_text(json.dumps(snapshot, default=str, sort_keys=True, indent=2))


@pytest.fixture
def chain(tmp_path, monkeypatch):
    yield from _build_chain(tmp_path, monkeypatch)


@pytest.mark.parametrize("ah_line", ["-0.25", "-0.75", "-1.25", "-1", "-2"])
def test_quarter_increment_line_selected_full_chain(tmp_path, monkeypatch, ah_line):
    """Quarter/integer AH lines must enter the recommendation (selected), not be
    refused by the old hemisphere-line gate."""
    built = _build_chain(tmp_path, monkeypatch, ah_line=ah_line)
    repo, item, _, _ = next(built)
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        rows = {row.market: row for row in session.scalars(select(AhOuDecisionLedgerModel))}
    assert rows["ASIAN_HANDICAP"].selected is True
    assert rows["ASIAN_HANDICAP"].skip_reason is None
    assert rows["ASIAN_HANDICAP"].direction in {"HOME", "AWAY"}


def test_non_pinnacle_bookmaker_selected_full_chain(tmp_path, monkeypatch):
    """P0 真实链：非 Pinnacle（Bet365 id=8）双侧报价落账本 selected=true，
    不再因账本记录路径硬编码 "4" 而 TERMS_INCOMPLETE；frozen_terms.bookmaker_id 读回实际 8。"""
    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _, _ = next(_build_chain(tmp_path, monkeypatch, bookmaker_id=8))
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(AhOuDecisionLedgerModel)))
    assert len(rows) == 2, [(r.market, r.skip_reason) for r in rows]
    assert all(row.selected for row in rows), [
        (r.market, r.selected, r.skip_reason) for r in rows
    ]
    for row in rows:
        dist = row.full_distribution or {}
        terms = dist.get("monitoring_terms") or {}
        assert terms.get("bookmaker_id") == "8", terms


def test_selected_full_chain_and_source_four_steps(chain):
    repo, item, plan, producer = chain
    frozen = repo.team_xg_rolling_snapshots(fixture_id="1489404")
    assert all(r["first_committed_at"] and r["pit_proven"] for r in frozen), frozen
    # Same original input, then new Session read-back/reconstruction.
    repo.upsert_team_xg_rolling_snapshots(list(plan.rolling_snapshots))
    repo.upsert_team_xg_rolling_snapshots(frozen)
    changed = deepcopy(frozen[0])
    changed["rolling_xg_for"] += 0.1
    with pytest.raises(RuntimeError, match="FIELD_CONFLICT"):
        repo.upsert_team_xg_rolling_snapshots([changed])
    changed = deepcopy(frozen[0])
    changed["source_matches"][0]["raw_serializer_version"] = "w2.canonical-json.v2"
    with pytest.raises(RuntimeError, match="FIELD_CONFLICT"):
        repo.upsert_team_xg_rolling_snapshots([changed])
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    service = ReadModelService()
    card = service.public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert card is not None
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(AhOuDecisionLedgerModel)))
        assert len(rows) == 2
        assert all(row.selected for row in rows), [
            (r.market, r.selected, r.skip_reason, r.full_distribution) for r in rows
        ]
        public = {m["market"]: m for m in card["markets"]}
        for row in rows:
            assert public[row.market]["selected"] == row.selected
            assert public[row.market]["direction"] == row.direction
            assert public[row.market]["tendency"] == (
                row.direction + "_AH" if row.market == "ASIAN_HANDICAP" else row.direction
            )
            assert public[row.market]["score"] == row.score
            assert public[row.market]["decision_hash"] == row.decision_id
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    repeat = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert repeat is not None
    markets = {"ASIAN_HANDICAP", "TOTALS"}
    assert {
        m["market"]: m["decision_hash"] for m in repeat["markets"] if m["market"] in markets
    } == {market: value["decision_hash"] for market, value in public.items() if market in markets}
    with Session(repo.engine) as session:
        assert len(list(session.scalars(select(AhOuDecisionLedgerModel)))) == 2


def test_actual_producer_after_decision_is_false(chain):
    repo, item, plan, producer = chain
    producer.now = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=1)
    rebuilt = producer.build_saved_raw_plan()
    assert all(not r["pit_proven"] for r in rebuilt.rolling_snapshots)


def test_database_proof_never_accepts_injected_first_commit(chain):
    repo, item, plan, producer = chain
    row = deepcopy(plan.rolling_snapshots[0])
    row["snapshot_id"] = "injected-first"
    row["as_of_fixture_id"] = "injected-target"
    row["first_committed_at"] = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    row["decision_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    repo.upsert_team_xg_rolling_snapshots([row])
    stored = repo.team_xg_rolling_snapshots(fixture_id="injected-target")[0]
    assert stored["first_committed_at"] is None  # target identity/cutoff is not proven
    assert not stored["pit_proven"]


def test_database_first_visibility_after_late_commit(chain):
    """An INSERT before the cutoff is not evidence if it commits afterward."""
    import time

    from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel

    repo, item, _, _ = chain
    control = repo.team_xg_rolling_snapshots(fixture_id="1489404")[0]
    assert control["pit_proven"] and control["first_committed_at"]
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    values = {
        key: control[key]
        for key in (
            "team_id",
            "as_of_fixture_id",
            "match_count",
            "rolling_xg_for",
            "rolling_xg_against",
            "rolling_goals_for",
            "rolling_goals_against",
            "regression_index",
            "source_system",
            "source_matches",
            "source_pit_requested",
            "candidate",
            "formal_recommendation",
        )
    }
    target_id = "late-commit-" + uuid.uuid4().hex
    values.update(
        snapshot_id=values["team_id"] + ":" + target_id,
        as_of_fixture_id=target_id,
        as_of_time=datetime.fromisoformat(control["as_of_time"]),
        first_captured_at=datetime.fromisoformat(control["first_captured_at"]),
        decision_at=cutoff,
        first_committed_at=cutoff - timedelta(days=1),
        pit_proven=True,
        proof_pending=True,
    )
    with Session(repo.engine) as session:
        inserted = TeamXgRollingSnapshotModel(**values)
        session.add(inserted)
        session.flush()
        session.refresh(inserted)
        assert inserted.first_committed_at is None
        time.sleep(max(0, (cutoff - datetime.now(UTC)).total_seconds()) + 0.1)
        session.commit()
    with Session(repo.engine) as session, session.begin():
        frozen = session.get(TeamXgRollingSnapshotModel, values["snapshot_id"])
        assert frozen.first_committed_at is None and not frozen.pit_proven
        frozen.proof_pending = False
    with Session(repo.engine) as session:
        frozen = session.get(TeamXgRollingSnapshotModel, values["snapshot_id"])
        assert frozen.first_committed_at >= cutoff
        assert not frozen.pit_proven


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("late", "F6_H2H_CAPTURED_AFTER_DECISION"),
        ("failed", "F6_H2H_CAPTURE_FAILED"),
        ("missing_raw", "F6_H2H_RAW_MISSING"),
        ("score", "F6_H2H_CAPTURE_SCORE_MISMATCH"),
        ("fixture", "F6_H2H_CAPTURE_FIXTURE_MISMATCH"),
        ("raw_time", "F6_H2H_RAW_CAPTURE_TIME_MISMATCH"),
        ("raw_hash", "F6_H2H_CAPTURE_RAW_HASH_MISMATCH"),
        ("team", "F6_H2H_CAPTURE_TEAM_MISMATCH"),
        ("not_ft", "F6_H2H_STATUS_NOT_FT"),
        ("ft_visible_late", "F6_H2H_STATUS_NOT_VISIBLE"),
    ],
)
def test_f6_actual_source_attacks_have_ready_controls(chain, attack, reason):
    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
    from w2.strategy.ah_ou_decision import build_ah_ou_selections

    repo, item, _, _ = chain
    kwargs = dict(
        fixture_id="1489404",
        home_team_id="H",
        away_team_id="A",
        kickoff=datetime.fromisoformat(item["fixture"]["date"]),
        competition_id="allsvenskan",
        season="2026",
        ah_line=-0.5,
        ah_home_odds=1.25,
        ah_away_odds=4.5,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert build_ah_ou_selections(repo, **kwargs)["status"] == "READY"
    with Session(repo.engine) as session, session.begin():
        h = session.scalar(
            select(CanonicalTeamMatchHistoryModel).where(
                CanonicalTeamMatchHistoryModel.team_w2_id == "H"
            )
        )
        cap = session.get(MatchdayEndpointCaptureModel, h.endpoint_capture_id)
        if attack == "late":
            cap.provider_captured_at = kwargs["kickoff"] - timedelta(hours=1)
        elif attack == "failed":
            cap.capture_status = "FAILED"
            cap.status_code = 500
        elif attack == "missing_raw":
            session.delete(session.get(RawPayloadModel, cap.raw_payload_sha256))
        elif attack == "score":
            h.goals_for += 1
        elif attack == "team":
            h.team_provider_id = "999"
        elif attack == "not_ft":
            # Keep the frozen FT row queryable while changing the genuinely
            # bound raw capture. Rebind its hashes so the status check, rather
            # than a preceding hash check, owns this negative case.
            from w2.matchday.intake_v2 import stable_hash

            source = session.get(RawPayloadModel, cap.raw_payload_sha256)
            payload = deepcopy(source.payload)
            item = next(
                row
                for row in payload["response"]
                if str(row["fixture"]["id"]) == str(h.provider_fixture_id)
            )
            item["fixture"]["status"]["short"] = "NS"
            replacement_hash = sha256_payload(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
            session.add(
                RawPayloadModel(
                    sha256=replacement_hash,
                    endpoint=source.endpoint,
                    captured_at=source.captured_at,
                    inserted_at=source.inserted_at,
                    storage_uri=source.storage_uri,
                    payload=payload,
                )
            )
            cap.raw_payload_sha256 = replacement_hash
            for bound in session.scalars(
                select(CanonicalTeamMatchHistoryModel).where(
                    CanonicalTeamMatchHistoryModel.provider_fixture_id == h.provider_fixture_id
                )
            ):
                bound.source_raw_hash = stable_hash(item)
        elif attack == "ft_visible_late":
            h.status_first_visible_at = kwargs["kickoff"] - timedelta(hours=1)
        elif attack == "fixture":
            cap.fixture_id = "api_football:foreign"
        elif attack == "raw_time":
            # raw 晚于 provider（回填/篡改）→ 时间防线仍未失效。
            session.get(RawPayloadModel, cap.raw_payload_sha256).captured_at += timedelta(minutes=5)
        elif attack == "raw_hash":
            source = session.get(RawPayloadModel, cap.raw_payload_sha256)
            source.payload = {**source.payload, "tampered": True}
    result = build_ah_ou_selections(repo, **kwargs)
    assert result["status"] == reason
    assert result["ah"] is None and result["ou"] is None


def test_f6_raw_earlier_than_provider_accepted_pg(chain):
    # 隔离 PG：h2h raw 按 sha256 去重，raw.captured_at 停在首次入库（早 5 天），
    # provider_captured_at 是本次采集。raw 早于 provider 合法，不再 MISMATCH。
    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
    from w2.strategy.ah_ou_decision import build_ah_ou_selections

    repo, item, _, _ = chain
    kwargs = dict(
        fixture_id="1489404",
        home_team_id="H",
        away_team_id="A",
        kickoff=datetime.fromisoformat(item["fixture"]["date"]),
        competition_id="allsvenskan",
        season="2026",
        ah_line=-0.5,
        ah_home_odds=1.25,
        ah_away_odds=4.5,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert build_ah_ou_selections(repo, **kwargs)["status"] == "READY"
    with Session(repo.engine) as session, session.begin():
        h = session.scalar(
            select(CanonicalTeamMatchHistoryModel).where(
                CanonicalTeamMatchHistoryModel.team_w2_id == "H"
            )
        )
        cap = session.get(MatchdayEndpointCaptureModel, h.endpoint_capture_id)
        raw = session.get(RawPayloadModel, cap.raw_payload_sha256)
        # raw 早于 provider 5 天（去重场景），provider 是本次采集。
        raw.captured_at = cap.provider_captured_at - timedelta(days=5)
    assert build_ah_ou_selections(repo, **kwargs)["status"] == "READY"


@pytest.mark.parametrize(
    "attack,ah_reason,ou_reason",
    [
        ("ah_late", "ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION", "DEPENDENCY_BLOCKED"),
        ("ou_late", "DEPENDENCY_BLOCKED", "TOTALS_QUOTE_CAPTURED_AFTER_DECISION"),
        ("different", "ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION", "TOTALS_QUOTE_SOURCE_CONTENT_MISMATCH"),
    ],
)
def test_market_reason_selector_public_and_new_session(
    chain, tmp_path, monkeypatch, attack, ah_reason, ou_reason
):
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
    from w2.strategy.ah_ou_quote_selector import select_v3_ah_ou_quotes

    repo, item, _, _ = chain
    # Commit the legal public control, then use a fresh isolated PG database for
    # the attack. Frozen decision rows must never be deleted to reset a test.
    control_kickoff = datetime.fromisoformat(item["fixture"]["date"])
    control = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=control_kickoff
    )
    assert control["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    assert all(
        m["selected"] for m in control["markets"] if m["market"] in ("ASIAN_HANDICAP", "TOTALS")
    )
    attack_root = tmp_path / "market_reason_attack"
    attack_root.mkdir()
    attack_chain = _build_chain(attack_root, monkeypatch)
    repo, item, _, _ = next(attack_chain)
    decision = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=2)
    with Session(repo.engine) as session, session.begin():
        rows = list(session.scalars(select(MatchdayMarketObservationModel)))
        for row in rows:
            if (
                row.canonical_market == "ASIAN_HANDICAP" and attack in {"ah_late", "different"}
            ) or (row.canonical_market == "TOTALS" and attack == "ou_late"):
                row.captured_at = decision + timedelta(seconds=1)
            if row.canonical_market == "TOTALS" and attack == "different":
                row.bookmaker_id = "8"
    observations = repo.latest_market_observations_for_fixtures(["1489404"])
    captures = list({r["capture_id"] for r in observations})
    selector = select_v3_ah_ou_quotes(
        observations,
        fixture_id="1489404",
        decision_at=decision,
        raw_payloads=repo.raw_payloads_for_captures(captures),
    )
    attack_kickoff = datetime.fromisoformat(item["fixture"]["date"])
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=attack_kickoff
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        ledger = {row.market: row for row in session.scalars(select(AhOuDecisionLedgerModel))}
        public = {m["market"]: m for m in card["markets"]}
        for market, reason, key in [
            ("ASIAN_HANDICAP", ah_reason, "ah"),
            ("TOTALS", ou_reason, "ou"),
        ]:
            assert public[market]["reason"] == ledger[market].skip_reason == reason
            assert not public[market]["selected"] and not ledger[market].selected
            assert selector[key]["status"] == (
                "READY" if reason == "DEPENDENCY_BLOCKED" else reason
            )


def test_t3_stale_quote_real_chain(chain, tmp_path, monkeypatch):
    """T3 报价新鲜度上界（真实链）：7 天前报价 → STALE_QUOTE，卡片/账本 SKIP。"""
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
    from w2.strategy.ah_ou_quote_selector import select_v3_ah_ou_quotes

    repo, item, _, _ = chain
    # 空操作控制：合法报价正常入选（COMMITTED + selected）。
    control_kickoff = datetime.fromisoformat(item["fixture"]["date"])
    control = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=control_kickoff
    )
    assert control["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    assert all(
        m["selected"] for m in control["markets"] if m["market"] in ("ASIAN_HANDICAP", "TOTALS")
    )
    # 单变量攻击：独立 DB，把报价 captured_at 改成 7 天前（只改时间）。
    attack_root = tmp_path / "t3_stale_attack"
    attack_root.mkdir()
    attack_chain = _build_chain(attack_root, monkeypatch)
    repo, item, _, _ = next(attack_chain)
    decision = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=2)
    with Session(repo.engine) as session, session.begin():
        for row in session.scalars(select(MatchdayMarketObservationModel)):
            row.captured_at = decision - timedelta(days=7)
    observations = repo.latest_market_observations_for_fixtures(["1489404"])
    captures = list({r["capture_id"] for r in observations})
    selector = select_v3_ah_ou_quotes(
        observations, fixture_id="1489404", decision_at=decision,
        raw_payloads=repo.raw_payloads_for_captures(captures),
    )
    assert selector["ah"]["status"] == "ASIAN_HANDICAP_STALE_QUOTE"
    assert selector["ou"]["status"] == "TOTALS_STALE_QUOTE"
    attack_kickoff = datetime.fromisoformat(item["fixture"]["date"])
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=attack_kickoff
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        ledger = {row.market: row for row in session.scalars(select(AhOuDecisionLedgerModel))}
        public = {m["market"]: m for m in card["markets"]}
        for market, reason in [
            ("ASIAN_HANDICAP", "ASIAN_HANDICAP_STALE_QUOTE"),
            ("TOTALS", "TOTALS_STALE_QUOTE"),
        ]:
            assert public[market]["reason"] == ledger[market].skip_reason == reason
            assert not public[market]["selected"] and not ledger[market].selected


def test_f6_source_freeze_four_steps(chain):
    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    from w2.ingestion.h2h_capture import _freeze_h2h_history_row

    repo, _, _, _ = chain
    assert (
        capture_h2h_for_pair(
            home_provider_team_id="10",
            away_provider_team_id="20",
            competition_id="allsvenskan",
            season="2026",
            client=repo._v9_h2h_client,
        )
        == 0
    )
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(CanonicalTeamMatchHistoryModel)))
        payloads = [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]
    with Session(repo.engine) as session, session.begin():
        assert all(not _freeze_h2h_history_row(session, row) for row in payloads)
    changed = deepcopy(payloads[0])
    changed["goals_for"] += 1
    with (
        Session(repo.engine) as session,
        pytest.raises(RuntimeError, match="F6_HISTORY_FIELD_CONFLICT:goals_for"),
    ):
        _freeze_h2h_history_row(session, changed)
    with Session(repo.engine) as session:
        stored = [
            {c.name: getattr(row, c.name) for c in row.__table__.columns}
            for row in session.scalars(select(CanonicalTeamMatchHistoryModel))
        ]
    assert stored == payloads


def test_actual_producers_repeat_later_capture_without_overwriting_frozen_sources(chain):
    from dataclasses import replace

    from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
    from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel

    repo, _, _, producer = chain

    def frozen_readback():
        with Session(repo.engine) as session:
            return {
                model.__tablename__: [
                    {column.name: getattr(row, column.name) for column in model.__table__.columns}
                    for row in session.scalars(
                        select(model).order_by(*model.__table__.primary_key.columns))
                ]
                for model in (CanonicalTeamMatchHistoryModel, TeamXgRollingSnapshotModel)
            }

    before = frozen_readback()
    original = repo._v9_h2h_client.request_live("h2h", {"h2h": "10-20", "last": "10"})

    class LaterCapture:
        def request_live(self, endpoint, params):
            return replace(original, captured_at=original.captured_at + timedelta(minutes=1),
                           requested_at=original.captured_at + timedelta(minutes=1))

    # Same-path empty-change control, then a genuinely new observation identity.
    for client in (repo._v9_h2h_client, LaterCapture()):
        assert capture_h2h_for_pair(
            home_provider_team_id="10", away_provider_team_id="20",
            competition_id="allsvenskan", season="2026", client=client,
        ) == 0
        assert frozen_readback() == before
    result = XgHistoryBackfillService(
        repository=repo, client=object(), now=producer.now + timedelta(minutes=1),
        config=producer.config,
    ).run_saved_raw()
    assert result.frozen_snapshot_no_ops == 2
    assert result.statistics_request_count == 0
    assert frozen_readback() == before
    with Session(repo.engine) as session:
        captures = session.scalars(select(MatchdayEndpointCaptureModel).where(
            MatchdayEndpointCaptureModel.endpoint == "h2h")).all()
        assert len(captures) == 2

    class ChangedScore:
        def request_live(self, endpoint, params):
            payload = deepcopy(original.payload)
            payload["response"][0]["goals"]["home"] += 1
            return replace(original, payload=payload,
                           captured_at=original.captured_at + timedelta(minutes=2),
                           requested_at=original.captured_at + timedelta(minutes=2))

    with pytest.raises(RuntimeError, match="F6_HISTORY_FIELD_CONFLICT:goals_for"):
        capture_h2h_for_pair(
            home_provider_team_id="10", away_provider_team_id="20",
            competition_id="allsvenskan", season="2026", client=ChangedScore(),
        )
    assert frozen_readback() == before


def test_unproven_legacy_snapshot_reproven_on_reseal(chain):
    """旧代码遗留的 pit=false 快照被新口径覆盖重证，不再 fail-closed 冲突。"""
    from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel

    repo, _item, plan, _producer = chain
    frozen = repo.team_xg_rolling_snapshots(fixture_id="1489404")
    assert all(r["pit_proven"] and r["first_committed_at"] for r in frozen), frozen

    # 模拟 489f160f 前旧代码遗留：内容字段由 PG trigger 冻结、不可 UPDATE，
    # 故 DELETE 已证明行后 INSERT 未证明行（PIT 字段全空、pit=false）。
    with Session(repo.engine) as session, session.begin():
        for row in list(session.scalars(select(TeamXgRollingSnapshotModel))):
            session.delete(row)
        session.flush()
        for r in frozen:
            session.add(
                TeamXgRollingSnapshotModel(
                    snapshot_id=r["snapshot_id"],
                    team_id=r["team_id"],
                    as_of_fixture_id=r["as_of_fixture_id"],
                    as_of_time=datetime.fromisoformat(r["as_of_time"]),
                    match_count=r["match_count"],
                    rolling_xg_for=r["rolling_xg_for"],
                    rolling_xg_against=r["rolling_xg_against"],
                    rolling_goals_for=r["rolling_goals_for"],
                    rolling_goals_against=r["rolling_goals_against"],
                    regression_index=r["regression_index"],
                    source_system=r["source_system"],
                    candidate=False,
                    formal_recommendation=False,
                    first_captured_at=None,
                    first_committed_at=None,
                    pit_proven=False,
                    decision_at=None,
                    source_matches=None,
                    proof_pending=False,
                    source_pit_requested=False,
                )
            )

    legacy = repo.team_xg_rolling_snapshots(fixture_id="1489404")
    assert all(not r["pit_proven"] and r["first_committed_at"] is None for r in legacy)

    # 新口径重新 upsert：覆盖重证，不抛 FIELD_CONFLICT。
    repo.upsert_team_xg_rolling_snapshots(list(plan.rolling_snapshots))

    reproven = repo.team_xg_rolling_snapshots(fixture_id="1489404")
    assert all(r["pit_proven"] and r["first_committed_at"] for r in reproven), reproven
    for r in reproven:
        assert r["first_captured_at"] and r["decision_at"]
        first_captured = datetime.fromisoformat(r["first_captured_at"])
        first_committed = datetime.fromisoformat(r["first_committed_at"])
        decision = datetime.fromisoformat(r["decision_at"])
        assert first_captured <= decision
        assert first_committed <= decision


def test_ah_ou_decision_forward_task_writes_ledger(chain):
    """决策点自动 forward 任务对就绪 fixture 落账本（AH/OU 两行），无需读取调用。"""
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    decision_at = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=2)
    # 清掉 chain seed 阶段（checkpoint 路径）已落的账本，隔离验证「任务」路径。
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    result = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert result["status"] == "COMPLETED", result
    assert result["card_built"] is True

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (r.market, r.skip_reason) for r in rows
    ]
    assert all(row.selected for row in rows), [(r.market, r.skip_reason) for r in rows]


def test_predecision_read_does_not_record(chain):
    """T1 ②：decision_at 前读取 → PREDECISION_NOT_RECORDED，不落正式账本（不锁槽）。"""
    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    decision_at = kickoff - timedelta(hours=2)
    # 读取路径在决策点前触发（真实墙钟 now < decision_at）。
    before = datetime.now(UTC)
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=before
    )
    assert card["ah_ou_result"]["recording"]["status"] == "PREDECISION_NOT_RECORDED", card[
        "ah_ou_result"
    ]
    assert card["ah_ou_result"]["recording"]["reason"] == "BEFORE_DECISION_AT"
    assert card["ah_ou_result"]["recording"]["decision_at"] == decision_at.isoformat()
    # 不落正式账本（不锁槽）：账本无任何行。
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(AhOuDecisionLedgerModel)))
    assert rows == [], [(r.fixture_id, r.market, r.selected) for r in rows]


def test_selected_slot_not_overwritten_after_decision(chain):
    """T1 ③：已 selected 槽位在到点后重复 forward 不被覆盖/重决策。"""
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    decision_at = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=2)
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    first = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert first["status"] == "COMPLETED"
    with Session(repo.engine) as session:
        first_rows = {
            row.market: row
            for row in session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        }
    assert {row.market for row in first_rows.values()} == {"ASIAN_HANDICAP", "TOTALS"}
    assert all(row.selected for row in first_rows.values())

    # 再次 forward（同一到点）→ 幂等，decision_id / selected / created_at 均不变。
    second = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert second["status"] == "COMPLETED"
    with Session(repo.engine) as session:
        second_rows = {
            row.market: row
            for row in session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        }
    for market in first_rows:
        assert second_rows[market].decision_id == first_rows[market].decision_id
        assert second_rows[market].selected == first_rows[market].selected
        assert second_rows[market].created_at == first_rows[market].created_at


def test_forward_created_at_is_current_not_early(chain):
    """T1 ④：forward 落账本 created_at 是到点后的当前墙钟，不再提前数天。"""
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    decision_at = datetime.fromisoformat(item["fixture"]["date"]) - timedelta(hours=2)
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    t0 = datetime.now(UTC)
    ah_ou_decision_forward(fixture_id="1489404", queued_at_utc=decision_at.isoformat())
    t1 = datetime.now(UTC)

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    assert rows
    for row in rows:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        assert t0 - timedelta(minutes=1) <= created <= t1 + timedelta(minutes=1), (
            row.market,
            created,
            t0,
            t1,
        )


def test_forward_reevaluates_old_skip_fixture(chain):
    """旧 SKIP（selected=false）未开赛 fixture → forward 重新评估覆盖 → selected=true。"""
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    decision_at = kickoff - timedelta(hours=2)  # DECISION_LEAD_TIME

    # 清掉 chain seed 已落的账本，seed 一条旧 SKIP 行（旧代码留下的 AH_LINE_NOT_HEMISPHERE）。
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))
        c.execute(
            text(
                """
                INSERT INTO ah_ou_decision_ledger
                (decision_id, fixture_id, market, decision_at, model_version,
                 calibration_version, input_hash, full_distribution,
                 quote_identity_hash, source_capture_sha256, capture_id, source_id,
                 home_team_id, away_team_id, selected, score, skip_reason, created_at)
                VALUES (:did, '1489404', 'ASIAN_HANDICAP', :at, 'm', 'c',
                        'x', '{}', 'q', 's', 'cap', 'src', 'H', 'A',
                        false, '0', 'AH_LINE_NOT_HEMISPHERE', :at)
                """
            ),
            {"did": "d" * 64, "at": decision_at},
        )

    result = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert result["status"] == "COMPLETED", result
    assert result["card_built"] is True

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    # 旧 SKIP 被覆盖，新决策落两市场且 selected=true。
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (r.market, r.skip_reason, r.selected) for r in rows
    ]
    assert all(row.selected for row in rows), [(r.market, r.skip_reason) for r in rows]


def test_forward_uses_timeline_not_latest_projection(chain):
    """决策报价读取用时间线：decision_at 前有合法报价 + 后又晚到采集 → 选决策前报价。

    最新投影只含最新一次采集（晚于 decision_at）会漏掉决策前报价 → AFTER_DECISION；
    时间线含历史捕获，selector 正确过滤 captured<=decision_at 选决策点前最新。
    """
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    decision_at = kickoff - timedelta(hours=2)  # now + 5h

    # 清账本，隔离验证「任务」路径。
    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    # 决策前报价 seed 阶段 captured_at=now (< decision_at)。构造一份「晚到采集」：
    # 新的 endpoint capture + observation（captured_at 晚于 decision_at，capture_id
    # 前缀 late-），复用原 raw payload，避免复用 capture_id 触发同名重复行。
    late_at = decision_at + timedelta(hours=1)
    with repo.engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO matchday_endpoint_captures
                (capture_id, fixture_id, competition_id, checkpoint, endpoint, sanitized_params,
                 params_hash, request_task_key, attempt, requested_at, provider_captured_at,
                 status_code, elapsed_ms, response_count, quota_values, raw_payload_sha256,
                 provider_event_time, capture_status, error_code)
                SELECT 'late-' || left(capture_id, 59), fixture_id, competition_id, checkpoint, endpoint,
                       sanitized_params, params_hash, request_task_key, attempt, requested_at, :late_at,
                       status_code, elapsed_ms, response_count, quota_values, raw_payload_sha256,
                       provider_event_time, capture_status, error_code
                FROM matchday_endpoint_captures
                WHERE fixture_id = 'api_football:1489404' AND endpoint = 'odds'
                """
            ),
            {"late_at": late_at},
        )
        c.execute(
            text(
                """
                INSERT INTO matchday_market_observations
                (observation_id, fixture_id, provider_fixture_id, competition_id, provider,
                 bookmaker_id, bookmaker_name, capture_id, provider_bet_id, raw_market_label,
                 canonical_market, canonical_selection, provider_selection, line, decimal_odds,
                 suspended, live, provider_updated_at, captured_at, ingested_at,
                 raw_payload_sha256, source_revision)
                SELECT 'late-' || left(observation_id, 59), fixture_id, provider_fixture_id, competition_id, provider,
                       bookmaker_id, bookmaker_name, 'late-' || left(capture_id, 59), provider_bet_id, raw_market_label,
                       canonical_market, canonical_selection, provider_selection, line, decimal_odds,
                       suspended, live, provider_updated_at, :late_at, ingested_at,
                       raw_payload_sha256, source_revision
                FROM matchday_market_observations
                WHERE fixture_id = 'api_football:1489404'
                """
            ),
            {"late_at": late_at},
        )

    def parsed(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    # 最新投影只含晚到采集（复现根因）：全部 captured_at 晚于 decision_at。
    latest = repo.latest_market_observations_for_fixtures(["1489404"])
    assert latest, "最新投影应含晚到采集"
    assert all(parsed(r["captured_at"]) > decision_at for r in latest), (
        "最新投影只应含最新（晚到）采集"
    )
    # 时间线含决策前 + 晚到。
    timeline = repo.market_observation_timeline_for_fixtures(["1489404"])
    timeline_times = [parsed(r["captured_at"]) for r in timeline]
    assert any(t <= decision_at for t in timeline_times), "时间线应含 decision_at 前报价"

    result = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert result["status"] == "COMPLETED", result
    assert result["card_built"] is True

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (r.market, r.skip_reason) for r in rows
    ]
    assert all(row.selected for row in rows), [(r.market, r.skip_reason) for r in rows]


def test_forward_timeline_only_late_still_after_decision(chain):
    """防线不失效：时间线里所有报价都晚于 decision_at → 仍 AFTER_DECISION 拒。"""
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )

    repo, item, _plan, _producer = chain
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    decision_at = kickoff - timedelta(hours=2)

    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))
        # 把决策前报价整体改成晚于 decision_at → 时间线只剩晚到报价。
        c.execute(
            text(
                """
                UPDATE matchday_market_observations
                SET captured_at = :late_at
                WHERE fixture_id = 'api_football:1489404'
                """
            ),
            {"late_at": decision_at + timedelta(minutes=5)},
        )

    result = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert result["status"] == "COMPLETED", result

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (r.market, r.skip_reason) for r in rows
    ]
    assert not any(row.selected for row in rows)
    assert all(
        row.skip_reason.endswith("_QUOTE_CAPTURED_AFTER_DECISION") for row in rows
    ), [(r.market, r.skip_reason) for r in rows]


def test_timeline_bounds_by_capture_instant_not_row_count(chain):
    """时间线按「捕获时间点」截断：单次大采集（>128 行）不挤掉 decision_at 前历史。

    生产 1569954 最新一次采集就有 128+ 行 AH，若按行数截断会把 decision_at 前的
    合法报价挤掉 → 决策仍 AFTER_DECISION。这里插入 130 行晚到大采集，断言时间线
    仍返回 decision_at 前的捕获时间点，且决策 forward 落账本 selected=true。
    """
    from apps.worker.celery_app import ah_ou_decision_forward

    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayMarketObservationModel,
    )

    repo, item, _plan, _producer = chain
    kickoff = datetime.fromisoformat(item["fixture"]["date"])
    decision_at = kickoff - timedelta(hours=2)
    late_at = decision_at + timedelta(hours=1)

    with repo.engine.begin() as c:
        c.execute(text("DELETE FROM ah_ou_decision_ledger"))
        c.execute(text("DELETE FROM ah_ou_forward_cohort"))

    with Session(repo.engine) as session:
        template = session.scalars(
            select(MatchdayMarketObservationModel).where(
                MatchdayMarketObservationModel.fixture_id == "api_football:1489404",
                MatchdayMarketObservationModel.canonical_market == "ASIAN_HANDICAP",
                MatchdayMarketObservationModel.bookmaker_id == "4",
            )
        ).first()
        assert template is not None
        fields = {
            "fid": template.fixture_id,
            "pfid": template.provider_fixture_id,
            "cid": template.competition_id,
            "provider": template.provider,
            "raw": template.raw_payload_sha256,
            "src": template.source_revision,
        }

    with repo.engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO matchday_endpoint_captures
                (capture_id, fixture_id, competition_id, checkpoint, endpoint, sanitized_params,
                 params_hash, request_task_key, attempt, requested_at, provider_captured_at,
                 status_code, elapsed_ms, response_count, quota_values, raw_payload_sha256,
                 provider_event_time, capture_status, error_code)
                VALUES ('latebig', :fid, :cid, NULL, 'odds', '{}', 'p', 'k', 1,
                        :late_at, :late_at, 200, 1, 130, '{}', :raw, NULL, 'CAPTURED', NULL)
                """
            ),
            {**fields, "late_at": late_at},
        )
        c.execute(
            text(
                """
                INSERT INTO matchday_market_observations
                (observation_id, fixture_id, provider_fixture_id, competition_id, provider,
                 bookmaker_id, bookmaker_name, capture_id, provider_bet_id, raw_market_label,
                 canonical_market, canonical_selection, provider_selection, line, decimal_odds,
                 suspended, live, provider_updated_at, captured_at, ingested_at,
                 raw_payload_sha256, source_revision)
                SELECT 'big-' || lpad(g::text, 58, '0'),
                       :fid, :pfid, :cid, :provider,
                       '4', 'Pinnacle', 'latebig', 'bet', 'Asian Handicap',
                       'ASIAN_HANDICAP',
                       CASE WHEN g % 2 = 0 THEN 'HOME' ELSE 'AWAY' END,
                       CASE WHEN g % 2 = 0 THEN 'Home' ELSE 'Away' END,
                       (g / 2)::text, '1.90', false, false, '2026', :late_at, :late_at,
                       :raw, :src
                FROM generate_series(1, 130) AS g
                """
            ),
            {**fields, "late_at": late_at},
        )

    timeline = repo.market_observation_timeline_for_fixtures(["1489404"])
    ah_times = {
        r["captured_at"]
        for r in timeline
        if r.get("canonical_market") == "ASIAN_HANDICAP"
    }
    assert len(ah_times) >= 2, ah_times  # 决策前 now + 晚到 late_at
    assert any(
        datetime.fromisoformat(t.replace("Z", "+00:00")) <= decision_at for t in ah_times
    ), ah_times

    result = ah_ou_decision_forward(
        fixture_id="1489404", queued_at_utc=decision_at.isoformat()
    )
    assert result["status"] == "COMPLETED", result

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(AhOuDecisionLedgerModel).where(
                    AhOuDecisionLedgerModel.fixture_id == "1489404"
                )
            )
        )
    assert {row.market for row in rows} == {"ASIAN_HANDICAP", "TOTALS"}, [
        (r.market, r.skip_reason) for r in rows
    ]
    assert all(row.selected for row in rows), [(r.market, r.skip_reason) for r in rows]


def test_xg_lag_stale_and_fresh(chain):
    """T2：team_xg_match 冻结 vs 最近 FT kickoff 超阈值报 XG_STALE；正常/无 FT 不报。"""
    import importlib.util
    from pathlib import Path

    repo, _item, _plan, _producer = chain
    now = datetime.now(UTC)

    source = Path(__file__).resolve().parents[2] / "ops/host/w2-v3-readonly-monitor.py"
    spec = importlib.util.spec_from_file_location("v3_readonly_monitor", source)
    assert spec is not None and spec.loader is not None
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    def lag_sql() -> float:
        with repo.engine.connect() as c:
            return float(
                c.execute(
                    text(
                        "SELECT COALESCE(EXTRACT(EPOCH FROM ("
                        "(SELECT MAX(mfi.kickoff_utc) FROM matchday_fixture_identities mfi "
                        "JOIN results r ON r.fixture_id = mfi.fixture_id "
                        "AND r.result_status IN ('FT','AET','PEN'))"
                        " - (SELECT MAX(captured_at) FROM team_xg_match)"
                        "))/3600.0, -1)::numeric(10,2)"
                    )
                ).scalar()
            )

    # 正常/无 FT 结果 → lag 非正，不报 XG_STALE。
    assert monitor.xg_stale_issue([{"lag_hours": lag_sql()}]) is None

    # 冻结：最近 FT 比赛 kickoff 很近 + team_xg_match 最新 captured_at 冻结 30 天。
    with repo.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matchday_fixture_identities "
                "(fixture_id, provider, provider_fixture_id, competition_id, provider_league_id, "
                " season, kickoff_utc, fixture_status, home_provider_team_id, away_provider_team_id, "
                " home_w2_team_id, away_w2_team_id, team_identity_status, raw_payload_sha256, "
                " captured_at, identity_hash, payload) "
                "VALUES ('api_football:ft-1', 'api_football', 'ft-1', 'allsvenskan', '113', '2026', "
                " :kickoff, 'FT', '10', '20', 'H', 'A', 'READY', :sha, now(), :hash, '{}')"
            ),
            {"kickoff": now - timedelta(hours=1), "sha": "a" * 64, "hash": "b" * 64},
        )
        c.execute(
            text(
                "INSERT INTO results (id, fixture_id, home_goals, away_goals, result_status, "
                " confirmed_at, source_payload_sha256, result_hash) "
                "VALUES ('result-ft-1', 'api_football:ft-1', 2, 1, 'FT', :kickoff, :sha, :hash)"
            ),
            {"kickoff": now - timedelta(hours=1), "sha": "c" * 64, "hash": "d" * 64},
        )
        c.execute(text("UPDATE team_xg_match SET captured_at = captured_at - interval '30 days'"))

    lag = lag_sql()
    assert lag > 120, lag  # 冻结 30 天 ≈ 719 小时（> 阈值 120）
    assert monitor.xg_stale_issue([{"lag_hours": lag}]) == f"XG_STALE:lag_hours={lag:.2f}"


def test_verify_persisted_xg_match_time_tolerance(chain):
    """356：xg 校验 raw 微秒 vs fact 秒级放行；大差异仍 fail-closed。"""
    from w2.infrastructure.persistence.future_refresh_models import (
        RawPayloadModel,
        TeamXgMatchModel,
    )
    from w2.ingestion.future_refresh_repository import (
        _index_fixture_sources,
        _verify_persisted_xg_match,
    )

    repo, _item, _plan, _producer = chain
    with Session(repo.engine) as session:
        fact = session.scalars(
            select(TeamXgMatchModel).order_by(TeamXgMatchModel.fixture_id)
        ).first()
        assert fact is not None
        fixture_raw = list(
            session.scalars(
                select(RawPayloadModel).where(RawPayloadModel.endpoint == "fixtures")
            )
        )
        fixture_sources = _index_fixture_sources(fixture_raw, {fact.fixture_id})

        # 亚秒差异（fact 微秒 vs raw 秒级）→ 放行
        fact.captured_at = fact.captured_at + timedelta(microseconds=370_000)
        assert _verify_persisted_xg_match(session, fact, fixture_sources) is not None

        # 大差异（再 +5min）→ 拒（None，fail-closed）
        fact.captured_at = fact.captured_at + timedelta(minutes=5)
        assert _verify_persisted_xg_match(session, fact, fixture_sources) is None
