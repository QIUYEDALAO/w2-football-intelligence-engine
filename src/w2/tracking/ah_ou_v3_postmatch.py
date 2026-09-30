"""One post-event authority for frozen AH/OU v3.1 decisions.

Both natural result workers call this writer. It never derives a price or a
line from post-event market observations, and historical v3 rows without terms
remain pending for explicit review rather than being rewritten.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.ah_ou_decision_identity import (
    build_ah_ou_decision_id,
    build_ah_ou_input_hash,
    canonical_decision_score_text,
    canonical_decision_time,
)
from w2.domain.canonical_serialization import HashDomain, SerializerVersion, canonical_sha256
from w2.domain.decision_contract import DecisionContractViolation
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AH_OU_FROZEN_TERMS_SCHEMA,
    AhOuCohortModel,
    AhOuDecisionLedgerModel,
)
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
    AhOuV3ValidationSampleModel,
)
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
from w2.infrastructure.persistence.future_refresh_models import (
    RawPayloadModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.tracking.outcome_ledger_repository import _result_hash

SETTLEMENT_SCHEMA = "w2.ah_ou_v3_settlement.v1"
VALIDATION_SCHEMA = "w2.ah_ou_v3_validation_sample.v1"


def _result_source(session: Session, result: ResultModel) -> dict[str, Any]:
    if result.result_status not in {"FT", "AET", "PEN"}:
        raise ValueError("V3_RESULT_STATUS_INVALID")
    raw = session.get(RawPayloadModel, result.source_payload_sha256)
    if raw is None or raw.endpoint != "fixtures" or not isinstance(raw.payload, dict):
        raise ValueError("V3_RESULT_RAW_MISSING")
    actual_hash = canonical_sha256(
        raw.payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    )
    if actual_hash != result.source_payload_sha256:
        raise ValueError("V3_RESULT_RAW_HASH_MISMATCH")
    if not result.source_capture_id:
        raise ValueError("V3_RESULT_CAPTURE_MISSING")
    capture = session.get(MatchdayEndpointCaptureModel, result.source_capture_id)
    if (
        capture is None
        or capture.endpoint != "fixtures"
        or capture.raw_payload_sha256 != raw.sha256
        or capture.capture_status != "CAPTURED"
        or capture.status_code is None
        or not 200 <= capture.status_code < 300
        or capture.provider_captured_at != raw.captured_at
        or capture.provider_captured_at != result.confirmed_at
    ):
        raise ValueError("V3_RESULT_CAPTURE_INVALID")
    provider_id = result.fixture_id.removeprefix("api_football:")
    identity = session.get(MatchdayFixtureIdentityModel, result.fixture_id)
    if (
        identity is None
        or identity.provider != "api_football"
        or identity.provider_fixture_id != provider_id
        or capture.fixture_id != result.fixture_id
        or str(capture.sanitized_params.get("id") or "") != provider_id
    ):
        raise ValueError("V3_RESULT_FIXTURE_BINDING_INVALID")
    if capture.provider_captured_at < identity.kickoff_utc:
        raise ValueError("V3_RESULT_CAPTURE_BEFORE_KICKOFF")
    if result.result_hash != _result_hash(result.fixture_id, result.home_goals, result.away_goals):
        raise ValueError("V3_RESULT_HASH_MISMATCH")
    items = [
        item
        for item in raw.payload.get("response", [])
        if isinstance(item, dict) and str((item.get("fixture") or {}).get("id")) == provider_id
    ]
    if len(items) != 1:
        raise ValueError("V3_RESULT_FIXTURE_MISMATCH")
    item = items[0]
    teams = item.get("teams") or {}
    if (
        str((teams.get("home") or {}).get("id") or "") != identity.home_provider_team_id
        or str((teams.get("away") or {}).get("id") or "") != identity.away_provider_team_id
    ):
        raise ValueError("V3_RESULT_TEAM_BINDING_INVALID")
    status = str(((item.get("fixture") or {}).get("status") or {}).get("short") or "")
    score = (item.get("score") or {}).get("fulltime") or {}
    if (
        status != result.result_status
        or score.get("home") != result.home_goals
        or score.get("away") != result.away_goals
    ):
        raise ValueError("V3_RESULT_SCORE_MISMATCH")
    return {"raw_sha256": raw.sha256, "capture_id": capture.capture_id}


def _net_units(outcome: str, odds: Decimal) -> Decimal:
    if outcome == "WIN":
        return odds - 1
    if outcome == "HALF_WIN":
        return (odds - 1) / 2
    if outcome == "PUSH" or outcome == "VOID":
        return Decimal(0)
    if outcome == "HALF_LOSS":
        return Decimal("-0.5")
    if outcome == "LOSS":
        return Decimal(-1)
    raise ValueError("V3_SETTLEMENT_OUTCOME_UNKNOWN")


def _business_fields(row: Any, fields: dict[str, Any]) -> bool:
    return all(getattr(row, key) == value for key, value in fields.items())


def _verify_v3_frozen_decision_in_session(
    session: Session, decision: AhOuDecisionLedgerModel
) -> dict[str, Any]:
    """Read-only admission shared by public reads, writers and notification delivery.

    Validate before looking for FT. A missing result cannot make a corrupt
    prematch decision eligible for publication or sending.
    """
    if decision.decision_contract != "w2.ah_ou_decision.v3.1" or not decision.selected:
        raise DecisionContractViolation("V3_SELECTED_CONTRACT_INVALID")
    terms = decision.frozen_terms
    if not isinstance(terms, dict) or terms.get("schema_version") != AH_OU_FROZEN_TERMS_SCHEMA:
        raise DecisionContractViolation("V3_SELECTED_TERMS_INCOMPLETE")
    terms_hash = canonical_sha256(terms, domain=HashDomain.RECOMMENDATION_DECISION_V4)
    if terms_hash != decision.terms_hash:
        raise DecisionContractViolation("V3_PUBLIC_FROZEN_TERMS_HASH_MISMATCH")
    bindings = {
        "selection": decision.direction,
        "quote_identity_hash": decision.quote_identity_hash,
        "model_version": decision.model_version,
        "calibration_version": decision.calibration_version,
        "input_hash": decision.input_hash,
        "capture_id": decision.capture_id,
        "raw_payload_sha256": decision.source_capture_sha256,
    }
    for field, expected in bindings.items():
        if terms.get(field) != expected:
            raise DecisionContractViolation("V3_PUBLIC_FROZEN_TERMS_BINDING_INVALID")
    if decision.skip_reason is not None or decision.direction is None:
        raise DecisionContractViolation("V3_SELECTED_DECISION_STATE_INVALID")
    if decision.source_id != decision.capture_id:
        raise DecisionContractViolation("V3_PUBLIC_SOURCE_ID_MISMATCH")
    allowed = {"ASIAN_HANDICAP": {"HOME", "AWAY"}, "TOTALS": {"OVER", "UNDER"}}
    if decision.direction not in allowed.get(decision.market, set()):
        raise DecisionContractViolation("V3_PUBLIC_MARKET_DIRECTION_INVALID")
    odds = Decimal(str(terms.get("entry_odds")))
    line = Decimal(str(terms.get("selected_line")))
    source_line = Decimal(
        str(terms.get("home_line" if decision.market == "ASIAN_HANDICAP" else "total_line"))
    )
    expected_line = (
        -source_line
        if decision.market == "ASIAN_HANDICAP" and (decision.direction == "AWAY")
        else source_line
    )
    if (
        not odds.is_finite()
        or odds <= 1
        or not line.is_finite()
        or not source_line.is_finite()
        or line != expected_line
        or line * 4 != (line * 4).to_integral_value()
    ):
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_TERMS_INVALID")
    score = Decimal(str(decision.score))
    if not score.is_finite():
        raise DecisionContractViolation("V3_PUBLIC_SCORE_INVALID")
    fixture = session.get(
        MatchdayFixtureIdentityModel,
        "api_football:" + decision.fixture_id.removeprefix("api_football:"),
    )
    if (
        fixture is None
        or fixture.home_w2_team_id != decision.home_team_id
        or fixture.away_w2_team_id != decision.away_team_id
        or canonical_decision_time(fixture.kickoff_utc - timedelta(hours=2))
        != canonical_decision_time(decision.decision_at)
    ):
        raise DecisionContractViolation("V3_PUBLIC_FIXTURE_TEAM_BINDING_INVALID")
    expected_id = build_ah_ou_decision_id(
        fixture_id=decision.fixture_id,
        market=decision.market,
        decision_at=decision.decision_at,
        model_version=decision.model_version,
        calibration_version=decision.calibration_version,
        input_hash=decision.input_hash,
        quote_identity_hash=decision.quote_identity_hash,
        source_capture_sha256=decision.source_capture_sha256,
        direction=decision.direction,
        score=decision.score,
        skip_reason=decision.skip_reason,
        selected=decision.selected,
        terms_hash=terms_hash,
    )
    if decision.decision_id != expected_id:
        raise DecisionContractViolation("V3_PUBLIC_DECISION_ID_MISMATCH")
    capture = session.get(MatchdayEndpointCaptureModel, decision.capture_id)
    if (
        capture is None
        or capture.endpoint != "odds"
        or capture.capture_status != "CAPTURED"
        or not 200 <= capture.status_code < 300
        or capture.provider_captured_at > decision.decision_at
    ):
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_CAPTURE_INVALID")
    raw = session.get(RawPayloadModel, capture.raw_payload_sha256)
    if raw is None or raw.endpoint != "odds" or not isinstance(raw.payload, dict):
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_RAW_MISSING")
    if (
        canonical_sha256(
            raw.payload,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            version=SerializerVersion.LEGACY_V1,
        )
        != raw.sha256
        or canonical_sha256(raw.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
        != decision.source_capture_sha256
        or raw.captured_at != capture.provider_captured_at
    ):
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_RAW_BINDING_INVALID")
    observations = list(
        session.scalars(
            select(MatchdayMarketObservationModel).where(
                MatchdayMarketObservationModel.capture_id == decision.capture_id,
                MatchdayMarketObservationModel.fixture_id == fixture.fixture_id,
                MatchdayMarketObservationModel.bookmaker_id == "4",
                MatchdayMarketObservationModel.canonical_market == decision.market,
                MatchdayMarketObservationModel.canonical_selection == decision.direction,
            )
        )
    )
    matching = [
        row
        for row in observations
        if row.line is not None and Decimal(row.line) == Decimal(str(terms.get("selected_line")))
    ]
    if len(matching) != 1:
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_SELECTED_ROW_INVALID")
    observed = matching[0]
    raw_values = [
        value
        for item in raw.payload.get("response", [])
        if str((item.get("fixture") or {}).get("id")) == fixture.provider_fixture_id
        for company in item.get("bookmakers", [])
        if str(company.get("id")) == "4"
        for bet in company.get("bets", [])
        if str(bet.get("id")) == observed.provider_bet_id
        for value in bet.get("values", [])
        if value.get("value") == observed.provider_selection
    ]
    if (
        len(raw_values) != 1
        or raw_values[0].get("odd") is None
        or Decimal(str(raw_values[0]["odd"])) != Decimal(str(terms.get("entry_odds")))
        or Decimal(observed.decimal_odds) != Decimal(str(terms.get("entry_odds")))
        or observed.raw_payload_sha256 != raw.sha256
        or observed.captured_at != capture.provider_captured_at
        or observed.live
        or observed.suspended
        or terms.get("bookmaker_id") != "4"
        or terms.get("captured_at") != capture.provider_captured_at.isoformat()
    ):
        raise DecisionContractViolation("V3_PUBLIC_QUOTE_TERMS_CONFLICT")
    distribution = decision.full_distribution
    selection = distribution.get("selection") if isinstance(distribution, dict) else None
    if (
        not isinstance(selection, dict)
        or selection.get("selected") is not True
        or distribution.get("market") != decision.market
        or (decision.market == "ASIAN_HANDICAP" and selection.get("side") != decision.direction)
    ):
        raise DecisionContractViolation("V3_PUBLIC_DISTRIBUTION_BINDING_INVALID")
    value = selection.get("score" if decision.market == "ASIAN_HANDICAP" else "edge")
    if canonical_decision_score_text(value) != decision.score:
        raise DecisionContractViolation("V3_PUBLIC_DISTRIBUTION_SCORE_MISMATCH")
    # Reconstruct the original input digest from frozen features and the actual
    # source identities. No model is re-evaluated during a public read.
    snapshots = list(
        session.scalars(
            select(TeamXgRollingSnapshotModel).where(
                TeamXgRollingSnapshotModel.as_of_fixture_id == fixture.provider_fixture_id,
                TeamXgRollingSnapshotModel.team_id.in_(
                    [
                        fixture.home_provider_team_id,
                        fixture.away_provider_team_id,
                    ]
                ),
            )
        )
    )
    by_team = {row.team_id: row for row in snapshots}
    if len(snapshots) != 2 or set(by_team) != {
        fixture.home_provider_team_id,
        fixture.away_provider_team_id,
    }:
        raise DecisionContractViolation("V3_PUBLIC_INPUT_SOURCE_BINDING_INVALID")
    history = list(
        session.scalars(
            select(CanonicalTeamMatchHistoryModel)
            .where(
                CanonicalTeamMatchHistoryModel.team_w2_id == decision.home_team_id,
                CanonicalTeamMatchHistoryModel.opponent_w2_id == decision.away_team_id,
                CanonicalTeamMatchHistoryModel.fixture_status == "FT",
                CanonicalTeamMatchHistoryModel.kickoff_utc < decision.decision_at,
                CanonicalTeamMatchHistoryModel.captured_at <= decision.decision_at,
            )
            .order_by(
                CanonicalTeamMatchHistoryModel.kickoff_utc.desc(),
                CanonicalTeamMatchHistoryModel.provider_fixture_id.desc(),
            )
            .limit(10)
        )
    )
    history.reverse()
    sides = ("HOME", "AWAY") if decision.market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    prices = {}
    for side in sides:
        side_line = -source_line if side == "AWAY" else source_line
        pair_rows = list(
            session.scalars(
                select(MatchdayMarketObservationModel).where(
                    MatchdayMarketObservationModel.capture_id == decision.capture_id,
                    MatchdayMarketObservationModel.fixture_id == fixture.fixture_id,
                    MatchdayMarketObservationModel.bookmaker_id == "4",
                    MatchdayMarketObservationModel.canonical_market == decision.market,
                    MatchdayMarketObservationModel.canonical_selection == side,
                )
            )
        )
        pair_rows = [
            row for row in pair_rows if row.line is not None and Decimal(row.line) == side_line
        ]
        if len(pair_rows) != 1:
            raise DecisionContractViolation("V3_PUBLIC_QUOTE_PAIR_INVALID")
        prices[side.lower()] = float(pair_rows[0].decimal_odds)
    features = distribution.get("features")
    if not isinstance(features, dict):
        raise DecisionContractViolation("V3_PUBLIC_INPUT_CONTENT_HASH_MISMATCH")
    expected_input_hash = build_ah_ou_input_hash(
        features=features,
        home_snapshot={"snapshot_id": by_team[fixture.home_provider_team_id].snapshot_id},
        away_snapshot={"snapshot_id": by_team[fixture.away_provider_team_id].snapshot_id},
        # The v3 input contract stores scores here; fixture identity is carried
        # by the history source, not by the legacy meeting feature projection.
        meetings=[
            {"goals_for": row.goals_for, "goals_against": row.goals_against} for row in history
        ],
        quote={"capture_id": decision.capture_id, "line": source_line, "side_prices": prices},
    )
    if expected_input_hash != decision.input_hash:
        raise DecisionContractViolation("V3_PUBLIC_INPUT_CONTENT_HASH_MISMATCH")
    return terms


def verify_v3_frozen_decision_in_session(
    session: Session, decision: AhOuDecisionLedgerModel
) -> dict[str, Any]:
    try:
        return _verify_v3_frozen_decision_in_session(session, decision)
    except DecisionContractViolation:
        raise
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise DecisionContractViolation("V3_PUBLIC_FROZEN_CONTENT_INVALID") from exc


def _expected_postmatch_fields(
    session: Session, decision: AhOuDecisionLedgerModel, result: ResultModel
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive both immutable postmatch records from prematch terms and FT source."""
    terms = verify_v3_frozen_decision_in_session(session, decision)
    terms_hash = decision.terms_hash
    fixture = session.get(
        MatchdayFixtureIdentityModel,
        "api_football:" + decision.fixture_id.removeprefix("api_football:"),
    )
    if (
        fixture is None
        or fixture.home_w2_team_id != decision.home_team_id
        or fixture.away_w2_team_id != decision.away_team_id
        or result.fixture_id != fixture.fixture_id
    ):
        raise ValueError("V3_RESULT_DECISION_FIXTURE_BINDING_INVALID")
    source = _result_source(session, result)
    if result.result_status in {"AET", "PEN"}:
        outcome = "VOID"
    elif decision.market == "ASIAN_HANDICAP":
        outcome = settle_asian_handicap(
            result.home_goals,
            result.away_goals,
            str(terms["selection"]),
            Decimal(str(terms["selected_line"])),
        ).value
    elif decision.market == "TOTALS":
        outcome = settle_total_goals(
            result.home_goals + result.away_goals,
            str(terms["selection"]),
            Decimal(str(terms["selected_line"])),
        ).value
    else:
        raise ValueError("V3_SETTLEMENT_MARKET_INVALID")
    odds = Decimal(str(terms["entry_odds"]))
    if not odds.is_finite() or odds <= 1:
        raise ValueError("V3_ENTRY_ODDS_INVALID")
    net = str(_net_units(outcome, odds))
    settlement_fields = dict(
        fixture_id=decision.fixture_id,
        market=decision.market,
        schema_version=SETTLEMENT_SCHEMA,
        terms_hash=terms_hash,
        result_id=result.id,
        result_hash=result.result_hash,
        result_raw_sha256=source["raw_sha256"],
        result_capture_id=source["capture_id"],
        home_goals=result.home_goals,
        away_goals=result.away_goals,
        outcome=outcome,
        net_units=net,
    )
    settlement_hash = canonical_sha256(
        {"decision_id": decision.decision_id, **settlement_fields},
        domain=HashDomain.RECOMMENDATION_DECISION_V4,
    )
    settlement_fields["settlement_hash"] = settlement_hash
    sample_fields = dict(
        fixture_id=decision.fixture_id,
        market=decision.market,
        schema_version=VALIDATION_SCHEMA,
        selection=str(terms["selection"]),
        exact_line=str(terms["selected_line"]),
        decimal_odds=str(terms["entry_odds"]),
        terms_hash=terms_hash,
        result_hash=result.result_hash,
        settlement_hash=settlement_hash,
        settlement=outcome,
        net_units=net,
    )
    return settlement_fields, sample_fields


def _verify_public_postmatch(
    session: Session,
    decision: AhOuDecisionLedgerModel,
    result: ResultModel | None,
    settlement: AhOuV3SettlementModel | None,
    sample: AhOuV3ValidationSampleModel | None,
) -> None:
    verify_v3_frozen_decision_in_session(session, decision)
    if result is None:
        if settlement is not None or sample is not None:
            raise DecisionContractViolation("V3_PUBLIC_POSTMATCH_WITHOUT_RESULT")
        return
    try:
        expected_settlement, expected_sample = _expected_postmatch_fields(session, decision, result)
    except ValueError as exc:
        raise DecisionContractViolation(str(exc)) from exc
    if settlement is None and sample is None:
        return  # Confirmed FT exists, but the natural writer has not completed.
    if settlement is None or sample is None:
        raise DecisionContractViolation("V3_PUBLIC_POSTMATCH_PAIR_INCOMPLETE")
    if settlement.settlement_hash != canonical_sha256(
        {
            "decision_id": settlement.decision_id,
            **{
                field: getattr(settlement, field)
                for field in expected_settlement
                if field != "settlement_hash"
            },
        },
        domain=HashDomain.RECOMMENDATION_DECISION_V4,
    ):
        raise DecisionContractViolation("V3_PUBLIC_SETTLEMENT_HASH_MISMATCH")
    for field, expected in expected_settlement.items():
        if getattr(settlement, field) != expected:
            raise DecisionContractViolation(f"V3_PUBLIC_SETTLEMENT_FIELD_CONFLICT:{field}")
    for field, expected in expected_sample.items():
        if getattr(sample, field) != expected:
            raise DecisionContractViolation(f"V3_PUBLIC_SAMPLE_FIELD_CONFLICT:{field}")


def settle_ah_ou_v3_in_session(
    session: Session,
    *,
    fixture_ids: Iterable[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconcile all selected decisions with confirmed results in one transaction.

    The caller commits only if this function and its legacy projections succeed.
    Missing FT is PENDING; a confirmed result with invalid provenance is an
    explicit error, never a successful empty projection.
    """
    ids = set(fixture_ids) if fixture_ids is not None else None
    stmt = select(AhOuDecisionLedgerModel).where(AhOuDecisionLedgerModel.selected.is_(True))
    if ids is not None:
        aliases = ids | {value.removeprefix("api_football:") for value in ids}
        stmt = stmt.where(AhOuDecisionLedgerModel.fixture_id.in_(aliases))
    decisions = list(session.scalars(stmt.order_by(AhOuDecisionLedgerModel.decision_id)))
    counts = {
        "selected": len(decisions),
        "pending": 0,
        "settled": 0,
        "void": 0,
        "blocked": 0,
        "created": 0,
        "idempotent": 0,
        "legacy_terms_missing": 0,
    }
    observed_at = now or datetime.now(UTC)
    for decision in decisions:
        if decision.decision_contract != "w2.ah_ou_decision.v3.1":
            counts["legacy_terms_missing"] += 1
            confirmed = session.scalar(
                select(ResultModel.id).where(
                    ResultModel.fixture_id
                    == "api_football:" + decision.fixture_id.removeprefix("api_football:")
                )
            )
            counts["blocked" if confirmed is not None else "pending"] += 1
            continue
        result = session.scalar(
            select(ResultModel).where(
                ResultModel.fixture_id
                == "api_football:" + decision.fixture_id.removeprefix("api_football:")
            )
        )
        if result is None:
            counts["pending"] += 1
            continue
        settlement_fields, sample_fields = _expected_postmatch_fields(session, decision, result)
        outcome = settlement_fields["outcome"]
        stored = session.get(AhOuV3SettlementModel, decision.decision_id)
        if stored is None:
            session.add(
                AhOuV3SettlementModel(
                    decision_id=decision.decision_id, **settlement_fields, settled_at=observed_at
                )
            )
            counts["created"] += 1
        elif not _business_fields(stored, settlement_fields):
            raise ValueError("V3_SETTLEMENT_FIELD_CONFLICT")
        else:
            counts["idempotent"] += 1
        sample = session.get(AhOuV3ValidationSampleModel, decision.decision_id)
        if sample is None:
            session.add(
                AhOuV3ValidationSampleModel(
                    decision_id=decision.decision_id, **sample_fields, projected_at=observed_at
                )
            )
        elif not _business_fields(sample, sample_fields):
            raise ValueError("V3_VALIDATION_SAMPLE_FIELD_CONFLICT")
        if outcome == "VOID":
            counts["void"] += 1
        else:
            counts["settled"] += 1
    if (
        counts["selected"]
        != counts["pending"] + counts["settled"] + counts["void"] + counts["blocked"]
    ):
        raise ValueError("V3_SETTLEMENT_SET_CONSERVATION_FAILED")
    session.flush()
    return {
        "schema_version": SETTLEMENT_SCHEMA,
        "status": "BLOCKED" if counts["blocked"] else "PASS",
        **counts,
    }


def v3_validation_snapshot(session: Session) -> dict[str, Any]:
    """Read-only, per-decision reconciliation for API and daily settlement."""
    cohorts = list(session.scalars(select(AhOuCohortModel)))
    all_decisions = list(session.scalars(select(AhOuDecisionLedgerModel)))
    decisions = list(
        session.scalars(
            select(AhOuDecisionLedgerModel)
            .where(AhOuDecisionLedgerModel.selected.is_(True))
            .order_by(AhOuDecisionLedgerModel.decision_at, AhOuDecisionLedgerModel.decision_id)
        )
    )
    decision_ids = [decision.decision_id for decision in decisions]
    fixture_ids = {
        "api_football:" + decision.fixture_id.removeprefix("api_football:")
        for decision in decisions
    }
    settlements = (
        {
            row.decision_id: row
            for row in session.scalars(
                select(AhOuV3SettlementModel).where(
                    AhOuV3SettlementModel.decision_id.in_(decision_ids)
                )
            )
        }
        if decision_ids
        else {}
    )
    samples = (
        {
            row.decision_id: row
            for row in session.scalars(
                select(AhOuV3ValidationSampleModel).where(
                    AhOuV3ValidationSampleModel.decision_id.in_(decision_ids)
                )
            )
        }
        if decision_ids
        else {}
    )
    results = (
        {
            str(row.fixture_id): row
            for row in session.scalars(
                select(ResultModel).where(ResultModel.fixture_id.in_(fixture_ids))
            )
        }
        if fixture_ids
        else {}
    )
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        settlement = settlements.get(decision.decision_id)
        sample = samples.get(decision.decision_id)
        result = results.get("api_football:" + decision.fixture_id.removeprefix("api_football:"))
        if decision.decision_contract == "w2.ah_ou_decision.v3.1":
            _verify_public_postmatch(session, decision, result, settlement, sample)
        if settlement is not None and sample is None:
            state = "BLOCKED"
        elif sample is not None and settlement is None:
            state = "BLOCKED"
        elif settlement is not None and sample is not None:
            if sample.settlement_hash != settlement.settlement_hash:
                state = "BLOCKED"
            else:
                state = "VOID" if settlement.outcome == "VOID" else "SETTLED"
        elif result is not None:
            state = "BLOCKED"
        else:
            state = "PENDING"
        terms = decision.frozen_terms or {}
        if decision.decision_contract == "w2.ah_ou_decision.v3.1":
            if (
                not terms
                or canonical_sha256(terms, domain=HashDomain.RECOMMENDATION_DECISION_V4)
                != decision.terms_hash
            ):
                raise DecisionContractViolation("V3_PUBLIC_FROZEN_TERMS_HASH_MISMATCH")
            if any(
                (
                    terms.get("selection") != decision.direction,
                    terms.get("capture_id") != decision.capture_id,
                    terms.get("raw_payload_sha256") != decision.source_capture_sha256,
                    terms.get("quote_identity_hash") != decision.quote_identity_hash,
                    terms.get("model_version") != decision.model_version,
                    terms.get("calibration_version") != decision.calibration_version,
                    terms.get("input_hash") != decision.input_hash,
                )
            ):
                raise DecisionContractViolation("V3_PUBLIC_FROZEN_TERMS_BINDING_INVALID")
        rows.append(
            {
                "decision_id": decision.decision_id,
                "fixture_id": decision.fixture_id,
                "home_team_id": decision.home_team_id,
                "away_team_id": decision.away_team_id,
                "market": decision.market,
                "decision_at": decision.decision_at.isoformat(),
                "kickoff_utc": (
                    (
                        decision.decision_at.replace(tzinfo=UTC)
                        if decision.decision_at.tzinfo is None
                        else decision.decision_at
                    ).astimezone(UTC)
                    + timedelta(hours=2)
                ).isoformat(),
                "model_version": decision.model_version,
                "calibration_version": decision.calibration_version,
                "decision_contract": decision.decision_contract or "w2.ah_ou_decision_ledger.v3",
                "score": decision.score,
                "selection": terms.get("selection"),
                "exact_line": terms.get("selected_line"),
                "decimal_odds": terms.get("entry_odds"),
                "quote_capture_id": decision.capture_id,
                "quote_raw_sha256": decision.source_capture_sha256,
                "terms_hash": decision.terms_hash,
                "result_hash": result.result_hash if result else None,
                "result_capture_id": result.source_capture_id if result else None,
                "settlement_hash": settlement.settlement_hash if settlement else None,
                "settlement": settlement.outcome if settlement else None,
                "net_units": settlement.net_units if settlement else None,
                "validation_sample_id": sample.decision_id if sample else None,
                "state": state,
            }
        )
    by_market: dict[str, dict[str, Any]] = {}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        subset = [row for row in rows if row["market"] == market]
        settled = [row for row in subset if row["state"] == "SETTLED"]
        outcomes = {
            name: sum(row["settlement"] == name for row in settled)
            for name in ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
        }
        by_market[market] = {
            "registered_cohorts": sum(
                bool(cohort.ah_capture_id if market == "ASIAN_HANDICAP" else cohort.ou_capture_id)
                for cohort in cohorts
            ),
            "completed_decisions": sum(decision.market == market for decision in all_decisions),
            "selected": len(subset),
            "pending": sum(row["state"] == "PENDING" for row in subset),
            "blocked": sum(row["state"] == "BLOCKED" for row in subset),
            "void": sum(row["state"] == "VOID" for row in subset),
            "settled": len(settled),
            "outcomes": outcomes,
            "hit_rate_denominator": len(settled) - outcomes["PUSH"],
            "hit_rate": (
                (outcomes["WIN"] + outcomes["HALF_WIN"] / Decimal(2))
                / (len(settled) - outcomes["PUSH"])
                if len(settled) - outcomes["PUSH"]
                else None
            ),
            "net_units": str(sum((Decimal(str(row["net_units"])) for row in settled), Decimal(0))),
        }
        if by_market[market]["hit_rate"] is not None:
            by_market[market]["hit_rate"] = float(by_market[market]["hit_rate"])
    return {
        "schema_version": "w2.ah_ou_v3_validation_view.v1",
        "rows": rows,
        "registered_cohorts": len(cohorts),
        "completed_decisions": len(all_decisions),
        "selected": len(decisions),
        "by_market": by_market,
    }
