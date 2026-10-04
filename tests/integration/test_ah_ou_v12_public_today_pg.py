import os
import socket
import subprocess
import time as clocktime
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.request import urlopen

import pytest
from apps.api.main import app
from apps.worker.celery_app import forward_outcome_ledger, result_materialize
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import (
    V3_RECOMMENDATION_CONFIRMED,
    delivery_route,
    enqueue_v3_daily_settlement_in_session,
    render_bark_message,
)
from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _live_api_to_web_probe(*, day: str, phase: str) -> None:
    """Browser reads the actual isolated-PG API through the Vite proxy."""
    if os.environ.get("W2_V12_RUN_WEB_LIVE") != "1":
        return
    root = Path(__file__).resolve().parents[2]
    api_port, web_port = _free_port(), _free_port()
    base = f"http://127.0.0.1:{web_port}"
    api = subprocess.Popen(
        [
            str(root / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        cwd=root,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    web_env = {
        **os.environ,
        "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{api_port}",
    }
    web = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(web_port), "--strictPort"],
        cwd=root / "apps/web",
        env=web_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            if api.poll() is not None or web.poll() is not None:
                raise RuntimeError("V12_LIVE_API_WEB_SERVER_EXITED")
            try:
                # Both URLs are generated above from 127.0.0.1 free ports.
                with (
                    urlopen(f"{base}/", timeout=1) as front,  # noqa: S310
                    urlopen(  # noqa: S310
                        f"http://127.0.0.1:{api_port}/openapi.json", timeout=1
                    ) as backend,
                ):
                    if front.status == backend.status == 200:
                        break
            except OSError:
                clocktime.sleep(0.1)
        else:
            raise RuntimeError("V12_LIVE_API_WEB_SERVER_TIMEOUT")
        probe_env = {
            **web_env,
            "W2_V12_WEB_BASE": base,
            "W2_V12_DAY": day,
            "W2_V12_PHASE": phase,
        }
        run = subprocess.run(
            ["node", "scripts/v12-live-web.mjs"],
            cwd=root / "apps/web",
            env=probe_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(run.stdout, run.stderr)
        assert run.returncode == 0, f"V12_LIVE_API_WEB_{phase}: {run.stderr}"
    finally:
        for process in (web, api):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_v3_selected_both_markets_reach_public_today(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    with Session(repo.engine) as session:
        decisions = list(session.scalars(select(AhOuDecisionLedgerModel)))
        odds = list(
            session.scalars(
                select(MatchdayEndpointCaptureModel).where(
                    MatchdayEndpointCaptureModel.endpoint == "odds"
                )
            )
        )
    print(
        {
            "kickoff": future["fixture"]["date"],
            "odds": [(r.provider_captured_at.isoformat(), r.capture_id) for r in odds],
        }
    )
    print(
        {
            "recording": card["ah_ou_result"]["recording"],
            "decisions": [(r.fixture_id, r.market, r.selected, r.skip_reason) for r in decisions],
        }
    )
    selected = {(row.fixture_id, row.market) for row in decisions if row.selected}
    assert selected == {("1489404", "ASIAN_HANDICAP"), ("1489404", "TOTALS")}
    with Session(repo.engine) as session:
        notices = list(
            session.scalars(
                select(CandidateNotificationOutboxModel).where(
                    CandidateNotificationOutboxModel.event_type == V3_RECOMMENDATION_CONFIRMED
                )
            )
        )
    assert len(notices) == 2
    assert all(delivery_route(row) == ("SEND", "ACTIONABLE") for row in notices)
    by_notice_market = {row.payload["market"]: row.payload for row in notices}
    for decision in decisions:
        notice = by_notice_market[decision.market]
        assert notice["decision_id"] == decision.decision_id
        assert notice["direction"] == decision.direction
        assert notice["line"] == decision.frozen_terms["selected_line"]
        assert notice["decimal_odds"] == decision.frozen_terms["entry_odds"]
        assert notice["terms_hash"] == decision.terms_hash
        rendered = render_bark_message(notice)
        assert "v3 推荐" in rendered["title"]
        assert decision.decision_id in rendered["body"]
        assert "EV" not in rendered["body"]
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    response = TestClient(app).get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    shown = payload["today_recommendations"]
    print(
        {
            "phase": "PRE_FT",
            "selected": sorted(selected),
            "today_recommendations": shown,
            "matches": len(payload["matches"]),
        }
    )
    assert len(shown) == 2
    by_market = {row["market"]: row for row in shown}
    assert set(by_market) == {"ASIAN_HANDICAP", "TOTALS"}
    assert {row["decision_id"] for row in shown} == {row.decision_id for row in decisions}
    assert all(
        row["status"] == "pending" and row["result"] is None and row["net_units"] is None
        for row in shown
    )
    assert payload["performance_summary"]["status"] == "AVAILABLE"
    assert payload["performance_summary"]["pending_count"] == 2
    assert payload["performance_summary"]["last_7_days"]["hit_rate"] is None
    fixture_match = next(row for row in payload["matches"] if row["fixture_id"] == "1489404")
    assert fixture_match["pick"] is None
    assert fixture_match["market"] is None and fixture_match["selection"] is None
    assert {row["decision_id"] for row in fixture_match["ah_ou_v3_recommendations"]} == {
        row.decision_id for row in decisions
    }
    full_workspace = TestClient(app).get(
        "/v1/dashboard/intelligence-workspace", params={"date": day.isoformat()}
    )
    assert full_workspace.status_code == 200, full_workspace.text
    full_match = next(
        row for row in full_workspace.json()["matches"] if row["fixture_id"] == "1489404"
    )
    assert {row["decision_id"] for row in full_match["ah_ou_v3_recommendations"]} == {
        row.decision_id for row in decisions
    }
    legacy_route = TestClient(app).get("/v1/dashboard", params={"date": day.isoformat()})
    assert legacy_route.status_code == 200, legacy_route.text
    assert {row["decision_id"] for row in legacy_route.json()["recommendations"]} == {
        row.decision_id for row in decisions
    }
    assert all(card["pick"] is None for card in legacy_route.json()["all"])
    assert legacy_route.json()["performance"]["pending_count"] == 2
    day_view = TestClient(app).get("/v1/dashboard/day-view", params={"date": day.isoformat()})
    assert day_view.status_code == 200, day_view.text
    assert {row["decision_id"] for row in day_view.json()["recommendations"]} == {
        row.decision_id for row in decisions
    }
    assert day_view.json()["counts"]["recommend"] == 2
    summary = TestClient(app).get("/v1/dashboard/summary", params={"date": day.isoformat()})
    assert summary.status_code == 200, summary.text
    assert summary.json()["totals"]["recommendations"] == 2
    assert summary.json()["performance"]["pending_count"] == 2
    for decision in decisions:
        public = by_market[decision.market]
        assert public["selection"] == decision.direction
        assert public["line"] == decision.frozen_terms["selected_line"]
        assert public["odds"] == decision.frozen_terms["entry_odds"]
        assert public["score"] == decision.score
        assert public["quote_capture_id"] == decision.capture_id
    detail = TestClient(app).get("/v1/dashboard/intelligence-workspace/matches/1489404")
    assert detail.status_code == 200, detail.text
    assert {row["decision_id"] for row in detail.json()["ah_ou_v3_recommendations"]} == {
        row["decision_id"] for row in shown
    }
    _live_api_to_web_probe(day=day.isoformat(), phase="PRE_FT")
    _ft_capture(repo, future)
    result = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert result["status"] == "PASS", result
    dispatch = OutcomeLedgerRuntimeRepository(repo.engine).prepare_dispatch(
        now=datetime.now(UTC), task_id="forward-outcome-ledger"
    )
    assert dispatch.status == "QUEUED", dispatch
    forward = forward_outcome_ledger.run(window="next7")
    assert forward["status"] not in {"BLOCKED", "ACTIVE_OR_RESERVED"}, forward
    validation = TestClient(app).get("/v1/dashboard/intelligence-workspace/validation")
    assert validation.status_code == 200, validation.text
    v3 = validation.json()["ah_ou_v3"]
    assert (
        v3["selected"] == 2
        and v3["by_market"]["ASIAN_HANDICAP"]["settled"] == 1
        and v3["by_market"]["TOTALS"]["settled"] == 1
    )
    after = TestClient(app).get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    assert after.status_code == 200, after.text
    print(
        {
            "phase": "POST_FT",
            "v3_selected": v3["selected"],
            "v3_settled": [v3["by_market"][m]["settled"] for m in ("ASIAN_HANDICAP", "TOTALS")],
            "today_recommendations": after.json()["today_recommendations"],
            "performance_summary": after.json()["performance_summary"],
        }
    )
    assert len([item for item in shown if item["fixture_id"] == "1489404"]) == 2
    assert (
        len(
            [
                item
                for item in after.json()["today_recommendations"]
                if item["fixture_id"] == "1489404"
            ]
        )
        == 2
    )
    post = after.json()
    post_rows = post["today_recommendations"]
    assert {row["decision_id"] for row in post_rows} == {row["decision_id"] for row in v3["rows"]}
    assert {row["market"]: row["net_units"] for row in post_rows} == {
        "ASIAN_HANDICAP": "0.25",
        "TOTALS": "0.9",
    }
    assert all(row["status"] == "settled" and row["result"] == "WIN" for row in post_rows)
    assert post["performance_summary"]["total_profit_units"] == 1.15
    legacy_route_after = TestClient(app).get("/v1/dashboard", params={"date": day.isoformat()})
    assert legacy_route_after.status_code == 200, legacy_route_after.text
    assert legacy_route_after.json()["performance"]["total_profit_units"] == 1.15
    summary_after = TestClient(app).get("/v1/dashboard/summary", params={"date": day.isoformat()})
    assert summary_after.status_code == 200, summary_after.text
    assert summary_after.json()["performance"]["total_profit_units"] == 1.15
    validation_summary = TestClient(app).get(
        "/v1/validation/summary", params={"date": day.isoformat()}
    )
    assert validation_summary.status_code == 200, validation_summary.text
    assert validation_summary.json()["validation"]["total_profit_units"] == 1.15
    assert {row["decision_id"] for row in legacy_route_after.json()["recommendations"]} == {
        row["decision_id"] for row in post_rows
    }
    assert post["performance_summary"]["by_market"]["ASIAN_HANDICAP"]["profit_units"] == 0.25
    assert post["performance_summary"]["by_market"]["TOTALS"]["profit_units"] == 0.9
    detail_after = TestClient(app).get("/v1/dashboard/intelligence-workspace/matches/1489404")
    assert detail_after.status_code == 200, detail_after.text
    assert {row["decision_id"] for row in detail_after.json()["ah_ou_v3_recommendations"]} == {
        row["decision_id"] for row in post_rows
    }
    _live_api_to_web_probe(day=day.isoformat(), phase="POST_FT")
    daily_at = datetime.combine(
        day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ
    ).astimezone(UTC)
    with Session(repo.engine) as session, session.begin():
        event_id = enqueue_v3_daily_settlement_in_session(session, now=daily_at)
        assert event_id
    with Session(repo.engine) as session:
        daily = session.get(CandidateNotificationOutboxModel, event_id)
        assert daily
        assert {row["decision_id"] for row in daily.payload["items"]} == {
            row["decision_id"] for row in post_rows
        }
        assert daily.payload["net_units"] == "1.15"


def test_v3_public_frozen_terms_tamper_has_same_path_control(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    url = "/v1/dashboard/intelligence-workspace/list"
    params = {"date": day.isoformat()}
    with Session(repo.engine) as session, session.begin():
        # Isolated-PG fault injection: the storage trigger normally refuses
        # even a no-op UPDATE. Temporarily bypass it in this transaction so
        # the public reader's own fail-closed check is independently exercised.
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        assert row is not None
        row.frozen_terms = deepcopy(row.frozen_terms)  # no-op write through attack path
    control = TestClient(app).get(url, params=params)
    assert control.status_code == 200 and len(control.json()["today_recommendations"]) == 2
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        row = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        assert row is not None and row.frozen_terms is not None
        tampered = deepcopy(row.frozen_terms)
        tampered["selected_line"] = "-1.25"
        row.frozen_terms = tampered
    with pytest.raises(ValueError, match="V3_PUBLIC_FROZEN_TERMS_HASH_MISMATCH"):
        TestClient(app).get(url, params=params)


def test_historical_opposite_pick_never_replaces_or_fills_missing_v3(chain):
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    with Session(repo.engine) as session:
        ah = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        assert ah is not None and ah.selected
        opposite = "AWAY" if ah.direction == "HOME" else "HOME"
    with Session(repo.engine) as session, session.begin():
        # Seed an actual old stored recommendation under the isolated fixture.
        # Ordinary writes remain forbidden by the retirement trigger.
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.add(
            ValidationSampleModel(
                fixture_id="1489404",
                market="ASIAN_HANDICAP",
                competition_id="allsvenskan",
                kickoff_utc=datetime.fromisoformat(future["fixture"]["date"]),
                selection=opposite,
                exact_line="+0.5" if opposite == "AWAY" else "-0.5",
                decimal_odds=1.92,
                evaluation_id="legacy-opposite",
                settlement="PENDING",
                projected_at=datetime.now(UTC),
            )
        )
    with Session(repo.engine) as session:
        legacy = session.get(ValidationSampleModel, ("1489404", "ASIAN_HANDICAP"))
        assert legacy is not None and legacy.selection == opposite
    client = TestClient(app)
    current = client.get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    assert current.status_code == 200, current.text
    rows = current.json()["today_recommendations"]
    assert len(rows) == 2
    ah_row = next(row for row in rows if row["market"] == "ASIAN_HANDICAP")
    assert ah_row["selection"] == ah.direction
    assert all(match["pick"] is None for match in current.json()["matches"])

    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(text("DELETE FROM ah_ou_decision_ledger"))
    old_only = client.get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    assert old_only.status_code == 200, old_only.text
    assert old_only.json()["today_recommendations"] == []
    assert all(match["pick"] is None for match in old_only.json()["matches"])
    assert old_only.json()["performance_summary"]["selected_count"] == 0
    dashboard = client.get("/v1/dashboard", params={"date": day.isoformat()})
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["recommendations"] == []
    day_view = client.get("/v1/dashboard/day-view", params={"date": day.isoformat()})
    assert day_view.status_code == 200, day_view.text
    assert day_view.json()["recommendations"] == []
    summary = client.get("/v1/dashboard/summary", params={"date": day.isoformat()})
    assert summary.status_code == 200, summary.text
    assert summary.json()["totals"]["recommendations"] == 0
    review = client.get("/v1/dashboard/intelligence-workspace/validation")
    assert review.status_code == 200, review.text
    assert review.json()["samples"] == []
    detail = client.get("/v1/dashboard/intelligence-workspace/matches/1489404")
    assert detail.status_code == 200, detail.text
    assert detail.json()["ah_ou_v3_recommendations"] == []
