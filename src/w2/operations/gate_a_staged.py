from __future__ import annotations

from datetime import datetime
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.prematch.lifecycle import (
    DYNAMIC_EVALUATION_V2_SCHEMA,
    DynamicEvaluationInput,
    LineupConfirmedEvent,
    classify_evaluation,
)
from w2.prematch.repository import DynamicPrematchRepository


def persist_staged_lineup_event(event: LineupConfirmedEvent) -> None:
    """Route staged canary lineup persistence through the sole lifecycle writer."""
    DynamicPrematchRepository().append_lineup_event(event)


def materialize_staged_dynamic_v2(
    rows: list[dict[str, Any]],
    *,
    captured_at: datetime,
    lineup_input_hash: str | None,
    lineup_confirmed_at: datetime | None,
    checkpoint: str,
    competition_id: str,
    season: str,
) -> None:
    if (lineup_input_hash is None) != (lineup_confirmed_at is None):
        raise ValueError("GATE_A_CANARY_LINEUP_BINDING_INVALID")
    eligible = sorted(
        (
            row
            for row in rows
            if row.get("canonical_market") in {"ASIAN_HANDICAP", "TOTALS"}
            and row.get("line") is not None
            and row.get("decimal_odds") is not None
        ),
        key=lambda row: (
            str(row.get("bookmaker_id") or ""),
            str(row.get("canonical_market") or ""),
            str(row.get("canonical_selection") or ""),
        ),
    )
    if not eligible:
        raise ValueError("GATE_A_CANARY_EXACT_QUOTE_MISSING")
    preferred = next(
        (row for row in eligible if row.get("canonical_selection") in {"HOME", "OVER"}),
        eligible[0],
    )
    same_market = [
        row
        for row in eligible
        if row.get("bookmaker_id") == preferred.get("bookmaker_id")
        and row.get("canonical_market") == preferred.get("canonical_market")
    ]
    inverse = [1.0 / float(str(row["decimal_odds"])) for row in same_market]
    if len(inverse) < 2 or sum(inverse) <= 0:
        raise ValueError("GATE_A_CANARY_EXACT_QUOTE_INCOMPLETE")
    probability = (1.0 / float(str(preferred["decimal_odds"]))) / sum(inverse)
    quote_identity = {
        "fixture_id": preferred["fixture_id"],
        "market": preferred["canonical_market"],
        "selection": preferred["canonical_selection"],
        "line": preferred["line"],
        "bookmaker_id": preferred["bookmaker_id"],
        "capture_id": preferred["capture_id"],
    }
    value = DynamicEvaluationInput(
        fixture_id=str(preferred["fixture_id"]),
        market=str(preferred["canonical_market"]),
        selection=str(preferred["canonical_selection"]),
        exact_line=float(str(preferred["line"])),
        bookmaker_id=str(preferred["bookmaker_id"]),
        capture_id=str(preferred["capture_id"]),
        quote_identity_hash=canonical_sha256(
            quote_identity,
            domain=HashDomain.PREMATCH_READ_MODEL_QUOTE_IDENTITY,
        ),
        model_input_hash=canonical_sha256(
            {
                "contract": "w2.gate_a_staged_market_bootstrap.v1",
                "quote_identity": quote_identity,
                "lineup_input_hash": lineup_input_hash,
            },
            domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION,
        ),
        evaluated_at=captured_at,
        checkpoint=checkpoint,
        capture_at=captured_at,
        model_probability=probability,
        market_probability=probability,
        expected_value=probability * float(str(preferred["decimal_odds"])) - 1.0,
        ev_se=0.0,
        decimal_odds=float(str(preferred["decimal_odds"])),
        lineup_input_hash=lineup_input_hash,
        lineup_confirmed_at=lineup_confirmed_at,
        post_lineup_quote=lineup_input_hash is not None,
        schema_version=DYNAMIC_EVALUATION_V2_SCHEMA,
        competition_id=competition_id,
        season=season,
        provider=str(preferred["provider"]),
        model_settlement_distribution={
            "WIN": probability,
            "HALF_WIN": 0.0,
            "PUSH": 0.0,
            "HALF_LOSS": 0.0,
            "LOSS": 1.0 - probability,
        },
    )
    DynamicPrematchRepository().append_evaluation(classify_evaluation(value))
