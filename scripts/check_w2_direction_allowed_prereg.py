from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_w2_r1_1_checkpoint_dry_run import (  # noqa: E402
    DEFAULT_CHECKPOINT_DATE,
    DEFAULT_ENVIRONMENT,
    DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
    DEFAULT_RUNTIME_ROOT,
    build_checkpoint_report,
)

DEFAULT_LEDGER_PATH = Path("docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md")
CANDIDATE_ORDER = ("eliteserien", "allsvenskan", "chinese_super_league")
DISABLED_LEAGUES = ("brasileirao_serie_a",)
ANALYSIS_MARKETS = ("ASIAN_HANDICAP", "TOTALS")
MIN_ENTRY_WINDOW_RATE = 0.80
MIN_CLOSING_PAIR_COVERAGE = 0.80
MIN_OUTCOME_COVERAGE = 0.90
MAX_PROVIDER_CALLS_PER_DAY = 120
LATEST_GAP_BY_LEAGUE = {
    "eliteserien": 0.0164,
    "allsvenskan": 0.0188,
    "chinese_super_league": 0.0354,
}
LATEST_GAP_BY_LEAGUE_MARKET: dict[str, dict[str, float | None]] = {
    league: {
        "ASIAN_HANDICAP": gap,
        # No market-specific TOTALS gap has been accepted yet; fail closed until one exists.
        "TOTALS": None,
    }
    for league, gap in LATEST_GAP_BY_LEAGUE.items()
}


def build_prereg_report(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    evaluation_date: str | None = None,
    environment: str = DEFAULT_ENVIRONMENT,
    min_double_snapshot_cards: int = DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
) -> dict[str, Any]:
    try:
        prereg_conditions = load_prereg_conditions(ledger_path)
        condition_blockers: list[str] = []
    except PreregConditionError as exc:
        prereg_conditions = {
            "source": str(ledger_path),
            "conditions": [],
            "source_lines": [],
        }
        condition_blockers = [str(exc)]
    checkpoint = build_checkpoint_report(
        runtime_root,
        checkpoint_date=DEFAULT_CHECKPOINT_DATE,
        environment=environment,
        min_double_snapshot_cards=min_double_snapshot_cards,
    )
    per_league_status = _per_league_status(
        checkpoint,
        min_double_snapshot_cards=min_double_snapshot_cards,
        conditions_available=not condition_blockers,
    )
    per_league_market_status = _per_league_market_status(
        checkpoint,
        min_sample_count=min_double_snapshot_cards,
        conditions_available=not condition_blockers,
    )
    blockers = [*condition_blockers]
    release_blockers = [*condition_blockers]
    if checkpoint.get("readiness_status") == "ACCUMULATING":
        blockers.append("R1_1_ACCUMULATING")
    elif checkpoint.get("readiness_status") == "NOT_ENOUGH_SAMPLE":
        blockers.append("R1_1_NOT_ENOUGH_SAMPLE")
    elif checkpoint.get("readiness_status") == "NO_EVIDENCE_SOURCE":
        blockers.append("R1_1_NO_EVIDENCE_SOURCE")
        release_blockers.append("R1_1_NO_EVIDENCE_SOURCE")
    release_decision = _release_decision(per_league_market_status, release_blockers)

    return {
        "evaluation_date": evaluation_date or datetime.now(UTC).date().isoformat(),
        "environment": environment,
        "candidate_order": list(CANDIDATE_ORDER),
        "disabled_leagues": list(DISABLED_LEAGUES),
        "prereg_conditions": prereg_conditions,
        "authoritative_scope": "per_league_market_status",
        "per_league_status": per_league_status,
        "per_league_market_status": per_league_market_status,
        "evidence_summary": {
            "checkpoint_date": checkpoint.get("checkpoint_date"),
            "readiness_status": checkpoint.get("readiness_status"),
            "double_snapshot_card_count": checkpoint.get("double_snapshot_card_count"),
            "shadow_nonempty_rate": checkpoint.get("shadow_nonempty_rate"),
            "clv_shadow_sample_count": checkpoint.get("clv_shadow_sample_count"),
            "clv_shadow_median": checkpoint.get("clv_shadow_median"),
            "entry_window_met_rate": checkpoint.get("entry_window_met_rate"),
            "provider_usage_curve_summary": checkpoint.get("provider_usage_curve_summary"),
            "model_family_distribution": checkpoint.get("model_family_distribution"),
            "r4_1_artifact_provenance_distribution": checkpoint.get(
                "r4_1_artifact_provenance_distribution"
            ),
            "checkpoint_blockers": checkpoint.get("blockers"),
        },
        "release_decision": release_decision,
        "direction_allowed_changes": [],
        "blockers": blockers,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "staging_deploy": False,
        "production_deploy": False,
        "scheduler_restart": False,
        "direction_allowed_changed": False,
        "ev_recommend_leg_changed": False,
    }


def load_prereg_conditions(ledger_path: Path) -> dict[str, Any]:
    if not ledger_path.exists():
        raise PreregConditionError("BLOCKER_DIRECTION_ALLOWED_PREREG_CONDITIONS_NOT_FOUND")
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    source_lines = [
        line.strip()
        for line in lines
        if "direction_allowed" in line
        and ("shadow CLV" in line or "预注册" in line or "三条件" in line)
    ]
    text = "\n".join(source_lines)
    has_sample_count = "shadow CLV" in text and ("100" in text or ">=100" in text)
    has_positive_median = "中位" in text and ">0" in text
    has_gap = "gap" in text and ("0.04" in text or "≤0.04" in text or "<=0.04" in text)
    has_separate_pr = "单独批准 PR" in text
    has_entry_window = "entry window" in text.lower() or "entry_window" in text.lower()
    has_closing_coverage = "closing" in text.lower() or "收盘" in text
    has_outcome_coverage = "outcome" in text.lower() or "结算" in text
    has_provider_cap = "120" in text and "provider" in text.lower()
    if not (
        has_sample_count
        and has_positive_median
        and has_gap
        and has_entry_window
        and has_closing_coverage
        and has_outcome_coverage
        and has_provider_cap
        and has_separate_pr
    ):
        raise PreregConditionError("BLOCKER_DIRECTION_ALLOWED_PREREG_CONDITIONS_NOT_FOUND")
    return {
        "source": str(ledger_path),
        "source_lines": source_lines,
        "conditions": [
            {
                "id": "shadow_clv_sample_count",
                "requirement": "shadow CLV sample count >= 100",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "shadow_clv_median",
                "requirement": "shadow CLV median > 0",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "latest_market_gap",
                "requirement": "latest market_baseline_eval gap <= 0.04",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "entry_window_met_rate",
                "requirement": "entry window met rate >= 80%",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "closing_pair_coverage_rate",
                "requirement": "valid closing pair coverage >= 80%",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "outcome_coverage_rate",
                "requirement": "settled outcome coverage >= 90%",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "provider_daily_cap",
                "requirement": "provider daily usage <= 120",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
            {
                "id": "approval",
                "requirement": "separate approved PR required before per-league release",
                "source": "W2_TASK_ACCEPTANCE_LEDGER",
            },
        ],
    }


class PreregConditionError(RuntimeError):
    pass


def _per_league_status(
    checkpoint: dict[str, Any],
    *,
    min_double_snapshot_cards: int,
    conditions_available: bool,
) -> list[dict[str, Any]]:
    checkpoint_candidates = checkpoint.get("direction_allowed_candidate_leagues")
    candidate_map = (
        {
            str(item.get("competition_id")): item
            for item in checkpoint_candidates
            if isinstance(item, dict)
        }
        if isinstance(checkpoint_candidates, list)
        else {}
    )
    rows: list[dict[str, Any]] = []
    no_evidence_source = checkpoint.get("readiness_status") == "NO_EVIDENCE_SOURCE"
    for league in CANDIDATE_ORDER:
        item = candidate_map.get(league, {})
        sample_count = _int(item.get("clv_shadow_sample_count")) if item else 0
        median_value = item.get("clv_shadow_median") if item else "ACCUMULATING"
        latest_gap = LATEST_GAP_BY_LEAGUE[league]
        condition_results = {
            "shadow_clv_sample_count": sample_count >= min_double_snapshot_cards,
            "shadow_clv_median": _positive(median_value),
            "latest_market_gap": latest_gap <= 0.04,
            "approval": False,
        }
        if no_evidence_source:
            status = "NO_EVIDENCE_SOURCE"
        elif not conditions_available:
            status = "BLOCKED"
        elif sample_count == 0:
            status = "ACCUMULATING"
        elif not condition_results["shadow_clv_sample_count"]:
            status = "NOT_ENOUGH_SAMPLE"
        elif not all(
            condition_results[key]
            for key in ("shadow_clv_sample_count", "shadow_clv_median", "latest_market_gap")
        ):
            status = "NOT_ELIGIBLE"
        else:
            status = "ELIGIBLE_FOR_REVIEW"
        rows.append(
            {
                "competition_id": league,
                "status": status,
                "latest_market_gap": latest_gap,
                "clv_shadow_sample_count": sample_count,
                "clv_shadow_median": median_value,
                "condition_results": condition_results,
                "direction_allowed_change": False,
            }
        )
    for league in DISABLED_LEAGUES:
        rows.append(
            {
                "competition_id": league,
                "status": "DISABLED",
                "reason": (
                    "Brazil guard retained; R4.1 worsened Brazil gap and latest gap "
                    "is not a candidate"
                ),
                "direction_allowed_change": False,
            }
        )
    return rows


def _release_decision(
    per_league_market_status: list[dict[str, Any]],
    condition_blockers: list[str],
) -> str:
    if condition_blockers:
        return "REVIEW_ONLY"
    statuses = {
        str(row.get("status"))
        for row in per_league_market_status
        if str(row.get("competition_id")) in CANDIDATE_ORDER
    }
    if "ELIGIBLE_FOR_REVIEW" in statuses:
        return "ELIGIBLE_FOR_REVIEW"
    if statuses <= {"ACCUMULATING"}:
        return "REVIEW_ONLY"
    return "NOT_ELIGIBLE"


def _per_league_market_status(
    checkpoint: dict[str, Any],
    *,
    min_sample_count: int,
    conditions_available: bool,
) -> list[dict[str, Any]]:
    evidence = checkpoint.get("league_market_evidence")
    evidence_rows = evidence if isinstance(evidence, list) else []
    evidence_map = {
        (_normalize_league(str(row.get("league") or "")), str(row.get("market") or "")): row
        for row in evidence_rows
        if isinstance(row, dict)
    }
    provider_summary = checkpoint.get("provider_usage_curve_summary")
    provider_summary = provider_summary if isinstance(provider_summary, dict) else {}
    daily_usage = provider_summary.get("daily_provider_calls")
    daily_usage = daily_usage if isinstance(daily_usage, dict) else {}
    provider_evidence_available = bool(daily_usage)
    provider_within_cap = provider_evidence_available and all(
        _int(value) <= MAX_PROVIDER_CALLS_PER_DAY for value in daily_usage.values()
    )
    rows: list[dict[str, Any]] = []
    no_evidence_source = checkpoint.get("readiness_status") == "NO_EVIDENCE_SOURCE"
    for league in CANDIDATE_ORDER:
        for market in ANALYSIS_MARKETS:
            evidence_row = evidence_map.get((league, market), {})
            market_gap = LATEST_GAP_BY_LEAGUE_MARKET[league][market]
            sample_count = _int(evidence_row.get("same_line_decimal_clv_sample_count"))
            median_value = evidence_row.get("median_decimal_clv")
            entry_rate = _number(evidence_row.get("entry_window_met_rate"))
            closing_rate = _number(evidence_row.get("closing_pair_coverage_rate"))
            outcome_rate = _number(evidence_row.get("outcome_coverage_rate"))
            condition_results = {
                "shadow_clv_sample_count": sample_count >= min_sample_count,
                "shadow_clv_median": _positive(median_value),
                "latest_market_gap": market_gap is not None and market_gap <= 0.04,
                "entry_window_met_rate": entry_rate is not None
                and entry_rate >= MIN_ENTRY_WINDOW_RATE,
                "closing_pair_coverage_rate": closing_rate is not None
                and closing_rate >= MIN_CLOSING_PAIR_COVERAGE,
                "outcome_coverage_rate": outcome_rate is not None
                and outcome_rate >= MIN_OUTCOME_COVERAGE,
                "provider_daily_cap": provider_within_cap,
                "approval": False,
            }
            if no_evidence_source:
                status = "NO_EVIDENCE_SOURCE"
            elif not conditions_available:
                status = "BLOCKED"
            elif sample_count == 0:
                status = "ACCUMULATING"
            elif sample_count < min_sample_count:
                status = "NOT_ENOUGH_SAMPLE"
            elif all(value for key, value in condition_results.items() if key != "approval"):
                status = "ELIGIBLE_FOR_REVIEW"
            else:
                status = "NOT_ELIGIBLE"
            rows.append(
                {
                    "competition_id": league,
                    "market": market,
                    "status": status,
                    "latest_market_gap": market_gap,
                    "market_gap_evidence_available": market_gap is not None,
                    "same_line_decimal_clv_sample_count": sample_count,
                    "median_decimal_clv": median_value,
                    "entry_window_met_rate": entry_rate,
                    "closing_pair_coverage_rate": closing_rate,
                    "outcome_coverage_rate": outcome_rate,
                    "provider_usage_evidence_available": provider_evidence_available,
                    "condition_results": condition_results,
                    "direction_allowed_change": False,
                }
            )
    for league in DISABLED_LEAGUES:
        for market in ANALYSIS_MARKETS:
            rows.append(
                {
                    "competition_id": league,
                    "market": market,
                    "status": "DISABLED",
                    "reason": "Brazil guard retained",
                    "direction_allowed_change": False,
                }
            )
    return rows


def _positive(value: Any) -> bool:
    return isinstance(value, int | float) and value > 0


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _normalize_league(value: str) -> str:
    return value.lower().strip().replace(" ", "_").replace("-", "_")


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only prereg gate for W2 direction_allowed per-league review."
    )
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument(
        "--evidence-snapshot-root",
        type=Path,
        help="Sanitized staging evidence snapshot root; overrides --runtime-root.",
    )
    parser.add_argument("--evaluation-date")
    parser.add_argument("--environment", default=DEFAULT_ENVIRONMENT)
    parser.add_argument(
        "--min-double-snapshot-cards",
        type=int,
        default=DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_prereg_report(
        ledger_path=args.ledger_path,
        runtime_root=args.evidence_snapshot_root or args.runtime_root,
        evaluation_date=args.evaluation_date,
        environment=args.environment,
        min_double_snapshot_cards=args.min_double_snapshot_cards,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "decision={decision} blockers={blockers}".format(
                decision=payload["release_decision"],
                blockers=",".join(payload["blockers"]),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
