from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

TARGET_TEAMS = (
    ("England", "Congo DR"),
    ("Belgium", "Senegal"),
    ("USA", "Bosnia"),
)

FORMAL_MIN_INDEPENDENT_SIGNALS = 3
MARKET_BLOCKERS = {
    "MISSING_AH_MARKET",
    "MISSING_MARKET_AH",
    "MISSING_ODDS",
    "AH_MAINLINE_AMBIGUOUS",
    "AH_PRIMARY_MAINLINE_MISSING",
    "AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION",
    "AH_MARKET_LINE_MAGNITUDE_MISMATCH",
    "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH",
    "AH_MARKET_ABS_LINE_MISMATCH",
    "AH_MARKET_LINE_SIDE_MISMATCH",
}
EV_BLOCKERS = {
    "AH_EV_BELOW_FORMAL_THRESHOLD",
    "REVERSE_FACTOR_VALUE_NOT_STRONG_ENOUGH",
    "INVALID_AH_EV_INPUTS",
    "INVALID_AH_SETTLEMENT_DISTRIBUTION",
}
S1_BLOCKERS = {
    "SIMULATION_NOT_READY",
    "MISSING_FAIR_AH",
    "MISSING_AH_SETTLEMENT_DISTRIBUTION",
    "SIMULATION_DIRECTION_CONTRADICTION",
    "SCORELINE_DIRECTION_CONTRADICTION",
}


def _load_payload(
    path: str | None,
    public_url: str | None,
    window: str,
    timeout: float,
) -> dict[str, Any]:
    if path:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        payload = json.loads(text)
    elif public_url:
        query = urlencode({"window": window, "include_debug": "true"})
        url = f"{public_url.rstrip('/')}/v1/dashboard?{query}"
        try:
            with urlopen(url, timeout=timeout) as response:  # noqa: S310 - user-supplied audit URL
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise SystemExit(f"failed to fetch dashboard payload: {exc}") from exc
    else:
        raise SystemExit("one of --input or --public-url is required")
    if not isinstance(payload, dict) or not isinstance(payload.get("all"), list):
        raise SystemExit("input must be a /v1/dashboard payload with an all[] list")
    return payload


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _team_text(match: dict[str, Any]) -> str:
    return f"{match.get('home_team_name') or ''} vs {match.get('away_team_name') or ''}".strip()


def _matches_target(match: dict[str, Any], target: tuple[str, str]) -> bool:
    text = _team_text(match).lower()
    return all(part.lower() in text for part in target)


def _target_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cards = [item for item in _list(payload.get("all")) if isinstance(item, dict)]
    for target in TARGET_TEAMS:
        match = next((card for card in cards if _matches_target(card, target)), None)
        if match is not None:
            rows.append(match)
    return rows


def _formal_recommendation_payload(recommendation: dict[str, Any]) -> dict[str, Any] | None:
    if str(recommendation.get("tier") or "").upper() != "FORMAL":
        return None
    return recommendation


def _classification(record: dict[str, Any]) -> dict[str, str]:
    signal_count = _number(record.get("independent_signal_count"))
    blockers = [str(item) for item in _list(record.get("formal_result", {}).get("blockers"))]
    canonical_blocker = record.get("canonical_ah_market_blocker")
    validation_status = record.get("canonical_ah_market_validation_status")
    market_ah = _number(record.get("market_ah"))
    fair_ah = _number(record.get("fair_ah"))
    calibration_version = record.get("calibration_version")
    recommendation = _dict(record.get("formal_result", {}).get("recommendation"))
    formal_suppressed_reason = str(record.get("formal_suppressed_reason") or "")

    if (
        record.get("pricing_shadow.status") == "INSUFFICIENT_INDEPENDENT_FACTORS"
        or signal_count is None
        or signal_count < FORMAL_MIN_INDEPENDENT_SIGNALS
    ):
        return {
            "code": "A",
            "label": "独立信号不足",
            "reason": "独立信号数未达到正式推荐最低要求。",
        }
    if (
        canonical_blocker in MARKET_BLOCKERS
        or validation_status not in {None, "READY", "VALID"}
        or market_ah is None
        or any(item in MARKET_BLOCKERS for item in blockers)
    ):
        return {
            "code": "B",
            "label": "盘口主线未就绪",
            "reason": "全场让球主线、赔率或 canonical AH market 未通过正式推荐输入检查。",
        }
    if any(item in EV_BLOCKERS for item in blockers):
        return {
            "code": "C",
            "label": "EV 未达标",
            "reason": "亚洲让球 EV 或逆因子强度未达到正式推荐门槛。",
        }
    if (
        not recommendation
        or formal_suppressed_reason
        or "FIXTURE_NOT_PREMATCH" in blockers
        or any("FORMAL_RECOMMENDATION_ENABLED" in item for item in blockers)
    ):
        return {
            "code": "D",
            "label": "recommendation payload 生成缺失",
            "reason": "正式推荐结果未输出有效 FORMAL recommendation payload。",
        }
    if fair_ah is None or not calibration_version or any(item in S1_BLOCKERS for item in blockers):
        return {
            "code": "E",
            "label": "calibration / S1 自洽问题",
            "reason": "S1 模拟、公平盘、结算分布或校准字段不足以形成自洽正式推荐。",
        }
    return {
        "code": "D",
        "label": "recommendation payload 生成缺失",
        "reason": "未命中数据、盘口或 EV blocker，但当前仍没有可报告的正式推荐 payload。",
    }


def _audit_match(match: dict[str, Any]) -> dict[str, Any]:
    pricing = _dict(match.get("pricing_shadow"))
    current_ah = _dict(_dict(match.get("current_odds")).get("ah"))
    recommendation = _dict(match.get("recommendation"))
    formal_recommendation = _formal_recommendation_payload(recommendation)
    canonical = _dict(pricing.get("canonical_ah_market"))
    scoreline_reference = _dict(match.get("scoreline_reference"))
    market_timeline = _dict(match.get("market_timeline"))
    simulation = _dict(pricing.get("simulation"))
    formal_result = {
        "formal_eligible": pricing.get("formal_eligible"),
        "recommendation": formal_recommendation,
        "blockers": pricing.get("formal_blockers") or [],
    }
    record: dict[str, Any] = {
        "fixture_id": match.get("fixture_id"),
        "teams": _team_text(match),
        "kickoff_utc": match.get("kickoff_utc"),
        "pricing_shadow.status": pricing.get("status"),
        "independent_signal_count": pricing.get("independent_signal_count"),
        "missing_independent_sources": pricing.get("missing_independent_sources") or [],
        "calibration_version": pricing.get("calibration_version")
        or simulation.get("calibration_version"),
        "fair_ah": pricing.get("fair_ah"),
        "market_ah": pricing.get("market_ah"),
        "edge_ah": pricing.get("edge_ah"),
        "current_odds.ah.display_line_cn": current_ah.get("display_line_cn"),
        "canonical_ah_market_validation_status": pricing.get(
            "canonical_ah_market_validation_status",
        )
        or canonical.get("validation_status"),
        "canonical_ah_market_blocker": pricing.get("canonical_ah_market_blocker")
        or canonical.get("blocker"),
        "formal_result": formal_result,
        "formal_suppressed_reason": match.get("formal_suppressed_reason"),
        "expected_value": recommendation.get("expected_value"),
        "ah_settlement_distribution": recommendation.get("ah_settlement_distribution"),
        "scoreline_reference.direction_top3": scoreline_reference.get("direction_top3") or [],
        "market_timeline.status": market_timeline.get("status"),
    }
    record["root_cause_category"] = _classification(record)
    return record


def build_audit(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [_audit_match(match) for match in _target_matches(payload)]
    counts: dict[str, int] = {}
    for row in rows:
        code = row["root_cause_category"]["code"]
        counts[code] = counts.get(code, 0) + 1
    return {
        "summary": {
            "target_count": len(TARGET_TEAMS),
            "audited_count": len(rows),
            "missing_targets": [
                " vs ".join(target)
                for target in TARGET_TEAMS
                if not any(_matches_target(row, target) for row in _list(payload.get("all")))
            ],
            "category_counts": counts,
            "read_only": True,
            "provider_calls": 0,
            "db_writes": 0,
        },
        "records": rows,
        "markdown_summary": render_markdown_summary(rows),
    }


def render_markdown_summary(records: list[dict[str, Any]]) -> str:
    lines = ["# W2 Formal Eligibility Root Cause Audit", ""]
    for row in records:
        category = row["root_cause_category"]
        formal = row["formal_result"]
        lines.extend(
            [
                f"## {row['teams']}",
                f"- fixture_id: {row['fixture_id']}",
                f"- kickoff_utc: {row['kickoff_utc']}",
                f"- 分类: {category['code']}. {category['label']}",
                f"- 原因: {category['reason']}",
                (
                    "- 输入: "
                    f"signals={row['independent_signal_count']}, "
                    f"missing={row['missing_independent_sources']}, "
                    f"calibration={row['calibration_version']}"
                ),
                (
                    "- AH: "
                    f"fair={row['fair_ah']}, market={row['market_ah']}, "
                    f"edge={row['edge_ah']}, display={row['current_odds.ah.display_line_cn']}"
                ),
                (
                    "- canonical: "
                    f"status={row['canonical_ah_market_validation_status']}, "
                    f"blocker={row['canonical_ah_market_blocker']}"
                ),
                (
                    "- formal_result: "
                    f"eligible={formal.get('formal_eligible')}, "
                    f"recommendation_present={formal.get('recommendation') is not None}, "
                    f"blockers={formal.get('blockers')}"
                ),
                f"- suppressed: {row['formal_suppressed_reason']}",
                f"- expected_value: {row['expected_value']}",
                f"- settlement_distribution: {row['ah_settlement_distribution']}",
                f"- direction_top3: {row['scoreline_reference.direction_top3']}",
                f"- market_timeline.status: {row['market_timeline.status']}",
                "",
            ],
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only FORMAL eligibility root-cause audit for W2 dashboard payloads.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Dashboard JSON payload path, or '-' for stdin.")
    source.add_argument("--public-url", help="Public W2 base URL, for example http://host")
    parser.add_argument("--window", default="today")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", help="Emit JSON audit. Default.")
    parser.add_argument("--markdown", action="store_true", help="Emit markdown summary only.")
    args = parser.parse_args()

    payload = _load_payload(args.input, args.public_url, args.window, args.timeout)
    audit = build_audit(payload)
    if args.markdown:
        print(audit["markdown_summary"])
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
