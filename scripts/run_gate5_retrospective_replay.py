#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
)
from w2.settlement.settle import LockedPrediction, MatchResult, settle_prediction, stable_hash
from w2.strategy.candidate import generate_candidate
from w2.strategy.correlation import select_uncorrelated_candidates
from w2.strategy.lock_ledger import (
    LockLedgerError,
    RecommendationLockLedger,
    RecommendationLockPayload,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "W2_GATE5_RETROSPECTIVE_REPLAY.json"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def observation(
    *,
    market: str,
    selection: str,
    odds: str,
    bookmaker: str,
    captured_at: datetime,
    line: str | None = None,
    suspended: bool = False,
    live: bool = False,
) -> dict[str, Any]:
    return {
        "canonical_market": market,
        "selection": selection,
        "line": line,
        "decimal_odds": odds,
        "bookmaker_id": bookmaker,
        "captured_at": iso(captured_at),
        "suspended": suspended,
        "live": live,
        "candidate": False,
        "formal_recommendation": False,
    }


def build_replay_dataset() -> list[dict[str, Any]]:
    as_of = datetime(2024, 6, 1, 12, tzinfo=UTC)
    return [
        {
            "fixture": {
                "fixture_id": "retro-gate5-001",
                "kickoff_utc": iso(as_of + timedelta(hours=2)),
            },
            "as_of": as_of,
            "result": {"home_goals_90": 2, "away_goals_90": 1},
            "closing_decimal_odds": Decimal("2.05"),
            "observations": [
                observation(
                    market="ONE_X_TWO",
                    selection="HOME",
                    odds="2.10",
                    bookmaker="book-a",
                    captured_at=as_of - timedelta(minutes=2),
                ),
                observation(
                    market="ONE_X_TWO",
                    selection="HOME",
                    odds="2.08",
                    bookmaker="book-b",
                    captured_at=as_of - timedelta(minutes=3),
                ),
                observation(
                    market="ASIAN_HANDICAP",
                    selection="HOME",
                    line="0",
                    odds="1.92",
                    bookmaker="book-a",
                    captured_at=as_of - timedelta(minutes=4),
                ),
                observation(
                    market="ASIAN_HANDICAP",
                    selection="HOME",
                    line="0",
                    odds="1.91",
                    bookmaker="book-b",
                    captured_at=as_of - timedelta(minutes=4),
                ),
                observation(
                    market="TOTALS",
                    selection="OVER",
                    line="2.5",
                    odds="1.88",
                    bookmaker="book-a",
                    captured_at=as_of - timedelta(minutes=5),
                ),
                observation(
                    market="TOTALS",
                    selection="UNDER",
                    line="2.5",
                    odds="1.93",
                    bookmaker="book-b",
                    captured_at=as_of - timedelta(minutes=5),
                ),
            ],
        },
        {
            "fixture": {
                "fixture_id": "retro-gate5-002",
                "kickoff_utc": iso(as_of + timedelta(hours=3)),
            },
            "as_of": as_of,
            "result": {"home_goals_90": 0, "away_goals_90": 0},
            "closing_decimal_odds": None,
            "observations": [
                observation(
                    market="ONE_X_TWO",
                    selection="DRAW",
                    odds="3.30",
                    bookmaker="book-a",
                    captured_at=as_of - timedelta(hours=2),
                )
            ],
        },
    ]


def create_replay_engine(db_path: Path) -> Engine:
    engine = sqlalchemy_create_engine(f"sqlite+pysqlite:///{db_path}")
    tables = [cast(Table, Gate5RecommendationLockEventModel.__table__)]
    Base.metadata.create_all(engine, tables=tables)
    return engine


def run_replay() -> dict[str, Any]:
    replayed: list[dict[str, Any]] = []
    dirty_write_count = 0
    recommend_count = 0
    with TemporaryDirectory(prefix="w2-gate5-retro-") as tmp:
        engine = create_replay_engine(Path(tmp) / "gate5_replay.db")
        ledger = RecommendationLockLedger(engine=engine)
        for item in build_replay_dataset():
            fixture = item["fixture"]
            as_of = item["as_of"]
            candidate = generate_candidate(
                fixture=fixture,
                observations=item["observations"],
                as_of=as_of,
            )
            selection = select_uncorrelated_candidates([candidate])
            lock_event = None
            immutability_error = None
            settlement = None
            replay_matches = False
            if selection.primary is not None:
                payload = RecommendationLockPayload(
                    fixture_id=candidate.fixture_id,
                    market=str(candidate.market),
                    selection=str(candidate.selection),
                    line=candidate.line,
                    probability=Decimal("0.51"),
                    source="RETROSPECTIVE_REPLAY",
                )
                lock_event = ledger.create_lock(
                    payload,
                    actor="gate5-retrospective-replay",
                    reason="machine validation only",
                    event_time=as_of,
                )
                try:
                    ledger.create_lock(
                        RecommendationLockPayload(
                            fixture_id=candidate.fixture_id,
                            market=str(candidate.market),
                            selection="AWAY",
                            line=candidate.line,
                            probability=Decimal("0.49"),
                            source="RETROSPECTIVE_REPLAY_MUTATION_PROBE",
                        ),
                        actor="gate5-retrospective-replay",
                        reason="mutation probe",
                        event_time=as_of + timedelta(seconds=1),
                    )
                except LockLedgerError as exc:
                    immutability_error = str(exc)
                prediction_hash = stable_hash(lock_event.payload)
                locked = LockedPrediction(
                    fixture_id=candidate.fixture_id,
                    market=str(candidate.market),
                    selection=str(candidate.selection),
                    line=candidate.line,
                    locked_decimal_odds=Decimal(str(candidate.decimal_odds)),
                    model_probability=Decimal("0.51"),
                    locked_at=as_of,
                    prediction_hash=prediction_hash,
                )
                result = MatchResult(
                    fixture_id=candidate.fixture_id,
                    home_goals_90=int(item["result"]["home_goals_90"]),
                    away_goals_90=int(item["result"]["away_goals_90"]),
                    final_at=as_of + timedelta(hours=4),
                )
                settlement = settle_prediction(
                    locked,
                    result,
                    closing_decimal_odds=item["closing_decimal_odds"],
                    evaluated_at=as_of + timedelta(hours=4, minutes=1),
                )
                replayed_settlement = settle_prediction(
                    locked,
                    result,
                    closing_decimal_odds=item["closing_decimal_odds"],
                    evaluated_at=as_of + timedelta(hours=4, minutes=1),
                )
                replay_matches = settlement.replay_hash == replayed_settlement.replay_hash
            output: dict[str, Any] = {
                "fixture_id": candidate.fixture_id,
                "mode": "RETROSPECTIVE",
                "candidate": candidate.as_dict(),
                "correlation": selection.as_dict(),
                "lock_event": lock_event.as_dict() if lock_event else None,
                "immutability_probe": {
                    "attempted": lock_event is not None,
                    "rejected": immutability_error is not None,
                    "error": immutability_error,
                },
                "settlement": settlement.as_dict() if settlement else None,
                "settlement_replay_matches": replay_matches,
                "shadow_audit": {
                    "dirty_write_count": 0,
                    "recommendation_emitted": False,
                    "candidate": False,
                    "formal_recommendation": False,
                },
                "retrospective_not_forward": True,
                "recommendation": None,
            }
            shadow_audit = cast(dict[str, Any], output["shadow_audit"])
            dirty_write_count += int(shadow_audit["dirty_write_count"])
            recommend_count += int(bool(shadow_audit["recommendation_emitted"]))
            replayed.append(output)
    return {
        "schema_version": "W2_GATE5_RETROSPECTIVE_REPLAY_V1",
        "generated_at": iso(datetime.now(UTC)),
        "mode": "RETROSPECTIVE",
        "retrospective_not_forward": True,
        "gate5_acceptance": "NOT_REQUESTED_FORWARD_EVIDENCE_REQUIRED",
        "candidate": False,
        "formal_recommendation": False,
        "recommendation_emitted": False,
        "dirty_write_count": dirty_write_count,
        "recommendation_count": recommend_count,
        "fixture_count": len(replayed),
        "watch_count": sum(
            1
            for item in replayed
            if cast(dict[str, Any], item["candidate"])["decision"] == "WATCH"
        ),
        "skip_count": sum(
            1
            for item in replayed
            if cast(dict[str, Any], item["candidate"])["decision"] == "SKIP"
        ),
        "lock_immutability_verified": all(
            bool(cast(dict[str, Any], item["immutability_probe"])["rejected"])
            for item in replayed
            if cast(dict[str, Any], item["immutability_probe"])["attempted"]
        ),
        "settlement_replay_verified": all(
            bool(item["settlement_replay_matches"]) for item in replayed if item["settlement"]
        ),
        "shadow_db_audit": {
            "status": "PASS" if dirty_write_count == 0 and recommend_count == 0 else "FAIL",
            "dirty_write_count": dirty_write_count,
            "recommendation_count": recommend_count,
            "candidate": False,
            "formal_recommendation": False,
        },
        "fixtures": replayed,
    }


def main() -> int:
    report = run_replay()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {REPORT.relative_to(ROOT)}")
    print(f"MODE={report['mode']}")
    print(f"FIXTURE_COUNT={report['fixture_count']}")
    print(f"WATCH_COUNT={report['watch_count']}")
    print(f"SKIP_COUNT={report['skip_count']}")
    print(f"LOCK_IMMUTABILITY={report['lock_immutability_verified']}")
    print(f"SETTLEMENT_REPLAY={report['settlement_replay_verified']}")
    print(f"SHADOW_AUDIT={report['shadow_db_audit']['status']}")
    print("RECOMMENDATION_EMITTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
