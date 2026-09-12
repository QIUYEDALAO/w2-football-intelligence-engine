"""Persistence for runtime AH settlement facts.

Write side is append-only and idempotent: replaying the same fact is a no-op,
and a *different* fact claiming an already-used identity is refused rather than
overwriting. These are immutable business facts, so a silent revision is the one
outcome the store will not produce.

Read side serves two callers:

* the natural capture writer, which needs the pre-kickoff odds bucket and the
  terminal capture row to build facts;
* F5, which needs the consumed facts for a team, projected onto the team's side.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import RuntimeAhSettlementFactModel

#: The markers `_canonical_ah_rows` requires before it will admit a row.
CANONICAL_AH_FACT_SOURCE = "canonical_historical_ah_fact"
CANONICAL_AH_FACT_SOURCE_GROUP = "canonical_historical_ah_fact"
CANONICAL_AH_FACT_COLLECTION_STATUS = "CANONICAL_AH_FACT"

#: Stamped on the F5 history row so the policy is auditable from the row alone.
FACT_RECORD_KIND = "runtime_ah_settlement_fact"
MAX_QUOTE_ROWS = 4000


class RuntimeAhSettlementError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}:{detail}" if detail else code)


class RuntimeAhSettlementRepository:
    def __init__(self, *, engine: sa.Engine) -> None:
        self.engine = engine

    # --- write ------------------------------------------------------------
    def append_facts(self, facts: Sequence[Any]) -> dict[str, int]:
        """Append immutable facts. Idempotent per fact_id, never destructive."""
        appended = 0
        no_ops = 0
        with Session(self.engine) as session:
            for fact in facts:
                if getattr(fact, "status", None) != "READY":
                    # A refused build is not a fact. It is the caller's business
                    # to record the refusal; nothing is written here.
                    continue
                model = RuntimeAhSettlementFactModel(
                    fact_id=fact.fact_id,
                    fact_hash=fact.fact_hash,
                    source_set_hash=fact.source_set_hash,
                    schema_version=fact.schema_version,
                    hash_contract=fact.hash_contract,
                    record_kind=FACT_RECORD_KIND,
                    policy=fact.policy,
                    fixture_id=fact.fixture_id,
                    provider_fixture_id=fact.provider_fixture_id,
                    competition_id=fact.competition_id,
                    season=fact.season,
                    kickoff_utc=fact.kickoff_utc,
                    home_team_provider_id=fact.home_team_provider_id,
                    away_team_provider_id=fact.away_team_provider_id,
                    home_w2_team_id=fact.home_w2_team_id,
                    away_w2_team_id=fact.away_w2_team_id,
                    selected_line=_text(fact.line),
                    home_price=fact.home_price,
                    away_price=fact.away_price,
                    selected_bookmakers=list(fact.selected_bookmakers),
                    quote_capture_ids=list(fact.quote_capture_ids),
                    quote_payload_sha256s=list(fact.quote_payload_sha256s),
                    quote_captured_at=fact.quote_captured_at,
                    quote_identity_hash=fact.quote_identity_hash,
                    settlement_capture_id=fact.settlement_capture_id,
                    settlement_payload_sha256=fact.settlement_payload_sha256,
                    settlement_observed_at=fact.settlement_observed_at,
                    settlement_observed_at_semantics=fact.settlement_observed_at_semantics,
                    terminal_status=fact.fixture_status,
                    home_goals=fact.home_goals,
                    away_goals=fact.away_goals,
                    home_settlement=fact.home_settlement,
                    away_settlement=fact.away_settlement,
                    result_identity_hash=fact.result_identity_hash,
                    payload=fact.as_payload(),
                    created_at_utc=sa.func.now(),
                )
                try:
                    with session.begin_nested():
                        session.add(model)
                        session.flush()
                    appended += 1
                except sa.exc.IntegrityError:
                    existing = session.get(RuntimeAhSettlementFactModel, fact.fact_id)
                    if existing is not None and existing.fact_hash == fact.fact_hash:
                        no_ops += 1
                        continue
                    raise RuntimeAhSettlementError(
                        "RUNTIME_AH_SETTLEMENT_FACT_CONFLICT",
                        f"fact_id={fact.fact_id}",
                    ) from None
            session.commit()
        return {"appended": appended, "idempotent_no_ops": no_ops}

    # --- read: building inputs -------------------------------------------
    def closing_quote_bucket(self, *, fixture_id: str, kickoff: datetime) -> list[dict[str, Any]]:
        """Every quote of the last pre-kickoff capture bucket for one fixture.

        The bucket is resolved in SQL rather than by pulling a window and hoping
        the tail contains it: a fixture with many in-play updates must still
        yield its *closing* pre-kickoff quotes.
        """
        table = MatchdayMarketObservationModel
        latest = (
            sa.select(sa.func.max(table.captured_at))
            .where(
                table.fixture_id == fixture_id,
                table.canonical_market == "ASIAN_HANDICAP",
                table.captured_at < kickoff,
                table.live.is_(False),
                table.suspended.is_(False),
            )
            .scalar_subquery()
        )
        statement = (
            sa.select(table)
            .where(
                table.fixture_id == fixture_id,
                table.canonical_market == "ASIAN_HANDICAP",
                table.captured_at == latest,
                table.live.is_(False),
                table.suspended.is_(False),
            )
            .order_by(table.observation_id)
            .limit(MAX_QUOTE_ROWS)
        )
        with Session(self.engine) as session:
            rows = list(session.scalars(statement))
        return [_quote_row(row) for row in rows]

    def terminal_capture(self, capture_id: str | None) -> dict[str, Any] | None:
        if not capture_id:
            return None
        with Session(self.engine) as session:
            row = session.get(MatchdayEndpointCaptureModel, capture_id)
        if row is None:
            return None
        return {
            "capture_id": row.capture_id,
            "provider_captured_at": row.provider_captured_at,
            "raw_payload_sha256": row.raw_payload_sha256,
            "endpoint": row.endpoint,
            "capture_status": row.capture_status,
        }

    # --- read: F5 ---------------------------------------------------------
    def facts_for_teams(
        self,
        team_ids: Iterable[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        """Consumed ambient AH facts, projected onto each team's own side."""
        ids = sorted({str(item) for item in team_ids if item})
        if not ids:
            return []
        table = RuntimeAhSettlementFactModel
        statement = (
            sa.select(table)
            .where(
                sa.or_(
                    table.home_w2_team_id.in_(ids),
                    table.away_w2_team_id.in_(ids),
                ),
                table.kickoff_utc < before,
            )
            .order_by(table.kickoff_utc.desc())
            .limit(max(limit_per_team, 0) * len(ids) * 2)
        )
        with Session(self.engine) as session:
            rows = list(session.scalars(statement))
        per_team: dict[str, int] = {}
        out: list[dict[str, Any]] = []
        for row in rows:
            for team_id in (row.home_w2_team_id, row.away_w2_team_id):
                if team_id not in ids:
                    continue
                if per_team.get(team_id, 0) >= limit_per_team:
                    continue
                per_team[team_id] = per_team.get(team_id, 0) + 1
                out.append(_f5_row(row, team_id=team_id))
        return out


def _projection_side_value(row: RuntimeAhSettlementFactModel, team_id: str) -> tuple[Any, ...]:
    home = row.home_w2_team_id == team_id
    return (
        team_id,
        row.away_w2_team_id if home else row.home_w2_team_id,
        row.home_goals if home else row.away_goals,
        row.away_goals if home else row.home_goals,
        row.selected_line if home else _negate_line(row.selected_line),
        row.home_settlement if home else row.away_settlement,
    )


def _f5_row(row: RuntimeAhSettlementFactModel, *, team_id: str) -> dict[str, Any]:
    opponent, goals_for, goals_against, line, outcome = _projection_side_value(row, team_id)[1:]
    return {
        "team_id": team_id,
        "opponent_id": opponent,
        "kickoff_at": row.kickoff_utc,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "ah_line": _to_float(line),
        "settlement_outcome": outcome,
        "ah_fact_id": row.fact_id,
        "ah_fact_hash": row.fact_hash,
        "quote_identity_hash": row.quote_identity_hash,
        "result_identity_hash": row.result_identity_hash,
        "settlement_observed_at": row.settlement_observed_at,
        "ah_source_observed_at": row.settlement_observed_at,
        "ah_source_set_hash": row.source_set_hash,
        "ah_source_capture_id": row.settlement_capture_id,
        "ah_source_capture_sha256": row.settlement_payload_sha256,
        "ah_quote_capture_ids": tuple(row.quote_capture_ids or ()),
        "ah_quote_payload_sha256s": tuple(row.quote_payload_sha256s or ()),
        "ah_selected_bookmakers": tuple(row.selected_bookmakers or ()),
        "ah_policy": row.policy,
        "source": CANONICAL_AH_FACT_SOURCE,
        "source_group": CANONICAL_AH_FACT_SOURCE_GROUP,
        "collection_status": CANONICAL_AH_FACT_COLLECTION_STATUS,
    }


def _quote_row(row: MatchdayMarketObservationModel) -> dict[str, Any]:
    """The observation shape the canonical mainline selector and quote identity
    authority both already consume. Nothing is recomputed here."""
    return {
        "observation_id": row.observation_id,
        "fixture_id": row.fixture_id,
        "provider": row.provider,
        "bookmaker_id": row.bookmaker_id,
        "bookmaker_name": row.bookmaker_name,
        "capture_id": row.capture_id,
        "provider_bet_id": row.provider_bet_id,
        "raw_market_label": row.raw_market_label,
        "canonical_market": row.canonical_market,
        "selection": row.canonical_selection,
        "line": row.line,
        "decimal_odds": row.decimal_odds,
        "suspended": row.suspended,
        "live": row.live,
        "provider_last_update": row.provider_updated_at,
        "captured_at": row.captured_at,
        "raw_payload_sha256": row.raw_payload_sha256,
        "source_revision": row.source_revision,
    }


def _negate_line(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    try:
        from decimal import Decimal

        parsed = -Decimal(text)
    except Exception:  # noqa: BLE001 - a non-numeric line is passed through
        return text
    normalized = parsed.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    normalized = value.normalize() if hasattr(value, "normalize") else value
    if hasattr(normalized, "to_integral") and normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f") if hasattr(normalized, "to_integral") else str(normalized)
