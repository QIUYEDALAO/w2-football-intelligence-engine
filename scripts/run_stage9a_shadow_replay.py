from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.enums import MarketType
from w2.markets.value_engine import OddsFormat, OddsQuote
from w2.strategy.shadow import (
    SHADOW_STRATEGY_VERSION,
    ShadowStrategyEngine,
    ShadowStrategyLedger,
    StrategyInput,
    manifest_payload,
    stable_sha256,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def quote(
    *,
    bookmaker: str,
    market: MarketType,
    selection: str,
    line: Decimal | None,
    odds: Decimal,
    now: datetime,
) -> OddsQuote:
    return OddsQuote(
        bookmaker_id=bookmaker.lower().replace(" ", "_"),
        bookmaker_name=bookmaker,
        market_type=market,
        selection=selection,
        line=line,
        raw_odds=odds,
        raw_odds_format=OddsFormat.DECIMAL,
        decimal_odds=odds,
        captured_at=now,
        provider_updated_at=now,
        suspended=False,
        live=False,
        provenance="stage9a_offline_replay",
    )


def demo_inputs() -> list[StrategyInput]:
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    score_matrix = {
        (0, 0): Decimal("0.08"),
        (1, 0): Decimal("0.19"),
        (2, 0): Decimal("0.18"),
        (2, 1): Decimal("0.17"),
        (1, 1): Decimal("0.14"),
        (0, 1): Decimal("0.08"),
        (1, 2): Decimal("0.06"),
        (3, 1): Decimal("0.06"),
        (3, 0): Decimal("0.04"),
    }
    return [
        StrategyInput(
            fixture_id="stage9a-france-iraq-demo",
            phase="RETROSPECTIVE_REPLAY",
            kickoff_utc=datetime(2026, 6, 22, 21, 0, tzinfo=UTC),
            as_of_time=now,
            score_matrix=score_matrix,
            independent_probabilities={
                "HOME": Decimal("0.62"),
                "DRAW": Decimal("0.23"),
                "AWAY": Decimal("0.15"),
                "YES": Decimal("0.49"),
                "NO": Decimal("0.51"),
            },
            quotes=[
                quote(
                    bookmaker="Pinnacle",
                    market=MarketType.ONE_X_TWO,
                    selection="HOME",
                    line=None,
                    odds=Decimal("1.80"),
                    now=now,
                ),
                quote(
                    bookmaker="Pinnacle",
                    market=MarketType.ASIAN_HANDICAP,
                    selection="AWAY",
                    line=Decimal("+2.75"),
                    odds=Decimal("2.02"),
                    now=now,
                ),
                quote(
                    bookmaker="SBO",
                    market=MarketType.TOTALS,
                    selection="OVER",
                    line=Decimal("4"),
                    odds=Decimal("2.38"),
                    now=now,
                ),
                quote(
                    bookmaker="Bet365",
                    market=MarketType.BTTS,
                    selection="NO",
                    line=None,
                    odds=Decimal("1.95"),
                    now=now,
                ),
            ],
            most_likely_outcome="HOME_WIN",
            evidence_refs=("offline_fixture_snapshot",),
        )
    ]


def run_replay() -> dict[str, Any]:
    engine = ShadowStrategyEngine()
    ledger = ShadowStrategyLedger()
    decisions = []
    locks = []
    for item in demo_inputs():
        decision = engine.evaluate(item)
        lock = ledger.lock(decision)
        repeated = ledger.lock(decision)
        assert repeated.decision_hash == lock.decision_hash
        decisions.append(decision.as_dict())
        locks.append(
            {
                "fixture_id": lock.fixture_id,
                "phase": lock.phase,
                "strategy_version": lock.strategy_version,
                "decision_hash": lock.decision_hash,
                "locked_at": lock.locked_at.isoformat().replace("+00:00", "Z"),
            }
        )
    manifest = manifest_payload(ROOT)
    manifest_hash = stable_sha256(manifest)
    return {
        "run_id": "stage9a-offline-shadow-replay",
        "strategy_version": SHADOW_STRATEGY_VERSION,
        "manifest": manifest,
        "manifest_sha256": manifest_hash,
        "mode": "OFFLINE_REPLAY",
        "network": "DISABLED",
        "formal_recommendation": False,
        "candidate": False,
        "decisions": decisions,
        "locks": locks,
        "events": ledger.events,
        "threshold_sensitivity": {
            "status": "RESEARCH_ONLY_NOT_PROMOTED",
            "tested_penalties": ["0.025", "0.035", "0.050"],
        },
    }


def main() -> None:
    replay = run_replay()
    grades: dict[str, int] = {}
    hard_gates: dict[str, int] = {}
    for decision in replay["decisions"]:
        grades[decision["published_grade"]] = grades.get(decision["published_grade"], 0) + 1
        if decision["primary"]:
            for reason in decision["primary"]["hard_gate_reasons"]:
                hard_gates[reason] = hard_gates.get(reason, 0) + 1
        for reason in decision["skip_reasons"]:
            hard_gates[reason] = hard_gates.get(reason, 0) + 1

    write_json(REPORTS / "W2_STAGE9A_SHADOW_REPLAY.json", replay)
    write_json(
        REPORTS / "W2_STAGE9A_GRADE_DISTRIBUTION.json",
        {"strategy_version": SHADOW_STRATEGY_VERSION, "grades": grades},
    )
    write_json(
        REPORTS / "W2_STAGE9A_HARD_GATE_AUDIT.json",
        {"strategy_version": SHADOW_STRATEGY_VERSION, "reason_counts": hard_gates},
    )
    result = (
        "# W2 Stage 9A Result\n\n"
        "STAGE_9A=COMPLETED_LOCAL\n\n"
        "SHADOW_STRATEGY=READY_LOCAL_STAGING\n\n"
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING\n\n"
        "GATE_5_STRATEGY=NOT_STARTED\n\n"
        "FORMAL_RECOMMENDATION=false\n\n"
        "CANDIDATE=false\n\n"
        "SERVER_DEPLOYMENT=NOT_PERFORMED\n"
    )
    (REPORTS / "W2_STAGE9A_RESULT.md").write_text(result, encoding="utf-8")
    print(json.dumps({"status": "PASS", "decisions": len(replay["decisions"])}, sort_keys=True))


if __name__ == "__main__":
    main()
