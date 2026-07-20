from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "tests/fixtures/w2_acceptance/acceptance_day_view.json"
AUTHORIZED_ENDPOINTS = ["status", "fixtures", "odds", "lineups"]
FORBIDDEN_ENDPOINTS = {"statistics", "injuries", "h2h", "history", "xg"}
FORBIDDEN_WORDS = ("稳赢", "必中", "保证", "包赢")
VALID_DECISION_TIERS = {"NOT_READY", "SKIP", "WATCH", "ANALYSIS_PICK", "RECOMMEND"}
VALID_DATA_STATUSES = {"READY", "PARTIAL", "STALE", "BLOCKED"}
VALID_LIFECYCLE_STATUSES = {"DRAFT", "LOCKED", "SUPERSEDED", "VOID", "SETTLED"}
RAW_FIRST_SCREEN_TERMS = (
    "raw_payload",
    "raw payload",
    "provider_request_hash",
    "lambda",
    "blocker_codes",
)

from w2.dashboard.l1_html import render_boss_dashboard_l1_html  # noqa: E402
from w2.dashboard.l1_view import build_boss_dashboard_l1  # noqa: E402
from w2.matchday.orchestrator import build_matchday_dry_run  # noqa: E402
from w2.replay.front_door import build_replay_front_door  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline W2 acceptance suite.")
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help="Local DayView fixture JSON. Defaults to tests/fixtures/w2_acceptance.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_acceptance(fixture_path=Path(args.fixture))
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(_text_report(result))
    return 0 if result["status"] == "PASS" else 1


def run_acceptance(*, fixture_path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    day_view = _load_json(fixture_path)
    checks = {
        "boss_5s_test": _boss_5s_test(day_view),
        "contract_acceptance": _contract_acceptance(day_view),
        "refresh_safety_acceptance": _refresh_safety_acceptance(),
        "dashboard_visual_acceptance": _dashboard_visual_acceptance(day_view),
        "matchday_dry_run_acceptance": _matchday_dry_run_acceptance(),
        "replay_acceptance": _replay_acceptance(day_view),
        "stage16_guard": _stage16_guard(),
    }
    blockers = [
        f"{name}:{blocker}"
        for name, check in checks.items()
        for blocker in _string_list(check.get("blockers"))
    ]
    warnings = [
        f"{name}:{warning}"
        for name, check in checks.items()
        for warning in _string_list(check.get("warnings"))
    ]
    return {
        "status": "PASS" if not blockers else "FAIL",
        **checks,
        "warnings": warnings,
        "blockers": blockers,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "checkpoint_write": False,
        "staging_deploy": False,
        "production_deploy": False,
        "scheduler_restart": False,
        "lock_capture_write": False,
        "settlement_write": False,
        "historical_locked_snapshot_rewrite": False,
    }


def _boss_5s_test(day_view: Mapping[str, Any]) -> dict[str, Any]:
    html = render_boss_dashboard_l1_html(day_view)
    model = build_boss_dashboard_l1(day_view)
    counts = _mapping(model.get("counts"))
    freshness = _mapping(model.get("freshness"))
    first_screen = _visible_first_screen(html)
    required = [
        "正式可锁",
        "分析推荐",
        "未就绪",
        "LINEUPS_PENDING",
        "MARKET_UNAVAILABLE",
        "下一次刷新",
        str(freshness.get("next_refresh_tick") or ""),
        "RECOMMEND-only",
    ]
    blockers = _missing_texts(first_screen, required)
    if "主要未出原因" not in first_screen and "reason summary" not in first_screen:
        blockers.append("MISSING_REASON_SUMMARY")
    if _int(counts.get("analysis_pick")) < 1:
        blockers.append("ANALYSIS_PICK_COUNT_MISSING")
    blockers.extend(_raw_leaks(first_screen))
    return {
        "status": _status(blockers),
        "lock_eligible": _int(counts.get("lock_eligible")),
        "analysis_pick": _int(counts.get("analysis_pick")),
        "not_ready": _int(counts.get("not_ready")),
        "next_refresh_tick": freshness.get("next_refresh_tick"),
        "blockers": blockers,
        "warnings": [],
    }


def _contract_acceptance(day_view: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if not _mapping(day_view.get("environment_policy")):
        blockers.append("MISSING_ENVIRONMENT_POLICY")
    for index, card in enumerate(_cards(day_view)):
        prefix = f"card[{index}]"
        for key in (
            "decision_tier",
            "data_status",
            "lifecycle_status",
            "reason_code",
            "action",
            "next_eval_at",
            "outcome_tracked",
            "lock_eligible",
            "recommendation_id",
        ):
            if key not in card:
                blockers.append(f"{prefix}:MISSING_{key.upper()}")
        tier = _text(card.get("decision_tier"))
        data_status = _text(card.get("data_status"))
        lifecycle_status = _text(card.get("lifecycle_status"))
        if tier and tier not in VALID_DECISION_TIERS:
            blockers.append(f"{prefix}:INVALID_DECISION_TIER:{tier}")
        if data_status and data_status not in VALID_DATA_STATUSES:
            blockers.append(f"{prefix}:INVALID_DATA_STATUS:{data_status}")
        if lifecycle_status and lifecycle_status not in VALID_LIFECYCLE_STATUSES:
            blockers.append(f"{prefix}:INVALID_LIFECYCLE_STATUS:{lifecycle_status}")
        if tier == "ANALYSIS_PICK":
            disclaimer = _analysis_disclaimer(card)
            if "分析参考" not in disclaimer:
                blockers.append(f"{prefix}:ANALYSIS_PICK_MISSING_ANALYSIS_DISCLAIMER")
            if "非稳赢" not in disclaimer:
                blockers.append(f"{prefix}:ANALYSIS_PICK_MISSING_NON_CERTAIN_DISCLAIMER")
        blockers.extend(f"{prefix}:{item}" for item in _forbidden_word_hits(card))
    policy = _mapping(day_view.get("environment_policy"))
    if _text(policy.get("environment")) == "production":
        allowed = _mapping(policy.get("lock_policy")).get("production_action_allowed_tiers")
        if allowed != ["RECOMMEND"]:
            blockers.append("PRODUCTION_STAMP_NOT_RECOMMEND_ONLY")
    return {"status": _status(blockers), "blockers": blockers, "warnings": []}


def _refresh_safety_acceptance() -> dict[str, Any]:
    payload = _matchday_payload()
    refresh = _mapping(payload.get("refresh_plan_summary"))
    ticks = _mapping_list(refresh.get("ticks"))
    labels = {str(tick.get("label")) for tick in ticks}
    blockers: list[str] = []
    expected_labels = {
        "T24_ODDS",
        "T6_ODDS",
        "T60_ODDS_LINEUPS",
        "T45_LINEUPS_RETRY",
        "T30_LINEUPS_RETRY",
        "T30_FINAL_PREMATCH",
    }
    if not expected_labels.issubset(labels):
        blockers.append("MISSING_REFRESH_TICKS")
    endpoint_allowlist = _string_list(refresh.get("endpoint_allowlist"))
    if endpoint_allowlist != AUTHORIZED_ENDPOINTS:
        blockers.append(f"BAD_ENDPOINT_ALLOWLIST:{endpoint_allowlist}")
    skipped = set(_string_list(refresh.get("skipped_endpoints")))
    if "statistics" not in skipped:
        blockers.append("MISSING_SKIPPED_STATISTICS")
    if skipped - FORBIDDEN_ENDPOINTS:
        blockers.append(f"UNEXPECTED_SKIPPED_ENDPOINTS:{sorted(skipped - FORBIDDEN_ENDPOINTS)}")
    if FORBIDDEN_ENDPOINTS.intersection(endpoint_allowlist):
        blockers.append("FORBIDDEN_ENDPOINT_IN_ALLOWLIST")
    if _int(refresh.get("projected_calls_total")) > _int(refresh.get("hard_cap")):
        blockers.append("PROJECTED_CALLS_ABOVE_HARD_CAP")
    if _int(payload.get("provider_calls")) != 0:
        blockers.append("PROVIDER_CALLS_NON_ZERO")
    return {
        "status": _status(blockers),
        "endpoint_allowlist": endpoint_allowlist,
        "skipped_endpoints": sorted(skipped),
        "provider_calls": payload.get("provider_calls"),
        "blockers": blockers,
        "warnings": [],
    }


def _dashboard_visual_acceptance(day_view: Mapping[str, Any]) -> dict[str, Any]:
    html = render_boss_dashboard_l1_html(day_view)
    first_screen = _visible_first_screen(html)
    blockers = _missing_texts(
        html,
        [
            "正式可锁",
            "分析推荐",
            "重点观察",
            "未就绪",
            "技术诊断",
            "RECOMMEND-only / 正式可锁；ANALYSIS_PICK 仅分析参考",
            "上一天",
            "下一天",
        ],
    )
    blockers.extend(_raw_leaks(first_screen))
    normalized = html.replace("非稳赢", "")
    for word in FORBIDDEN_WORDS:
        if word in normalized:
            blockers.append(f"FORBIDDEN_WORD:{word}")
    if "<details" not in html:
        blockers.append("L2_DETAILS_NOT_COLLAPSED")
    return {"status": _status(blockers), "blockers": blockers, "warnings": []}


def _matchday_dry_run_acceptance() -> dict[str, Any]:
    payload = _matchday_payload()
    blockers: list[str] = []
    if _int(payload.get("provider_calls")) != 0:
        blockers.append("PROVIDER_CALLS_NON_ZERO")
    if _int(payload.get("db_writes")) != 0:
        blockers.append("DB_WRITES_NON_ZERO")
    if payload.get("would_enqueue") is not False:
        blockers.append("WOULD_ENQUEUE_NOT_FALSE")
    if not _mapping(payload.get("environment_policy")):
        blockers.append("MISSING_ENVIRONMENT_POLICY")
    lock_candidates = _mapping_list(payload.get("lock_candidates"))
    for candidate in lock_candidates:
        if candidate.get("needs_approval") is not True:
            blockers.append("LOCK_CANDIDATE_NOT_APPROVAL_ONLY")
        if candidate.get("would_write_lock") is not False:
            blockers.append("LOCK_CANDIDATE_WOULD_WRITE")
    return {
        "status": _status(blockers),
        "provider_calls": payload.get("provider_calls"),
        "db_writes": payload.get("db_writes"),
        "would_enqueue": payload.get("would_enqueue"),
        "lock_candidate_count": len(lock_candidates),
        "blockers": blockers,
        "warnings": [],
    }


def _replay_acceptance(day_view: Mapping[str, Any]) -> dict[str, Any]:
    payload = build_replay_front_door(
        football_day=_text(day_view.get("football_day")),
        environment=_text(day_view.get("environment")) or "staging",
        day_view=deepcopy(day_view),
        audit_manifest={"provider_calls": 0, "db_writes": 0, "read_only": True},
        audit_tables={"cards": _cards(day_view)},
        outcomes=[
            {
                "fixture_id": "fixture-analysis",
                "result_status": "FINAL",
                "settlement_status": "DRY_RUN_ONLY",
                "score": "2-1",
                "pnl": 0,
                "unit_result": "push",
            }
        ],
        as_of="2026-07-05T00:00:00Z",
    )
    blockers: list[str] = []
    if payload.get("replay_status") != "READY":
        blockers.append(f"REPLAY_STATUS:{payload.get('replay_status')}")
    summary = _mapping(payload.get("outcome_tracking_summary"))
    if _int(summary.get("tracked_count")) < 1:
        blockers.append("NO_OUTCOME_TRACKED_CARD")
    hash_statuses = {
        str(item.get("hash_status")) for item in _mapping_list(payload.get("card_hash_checks"))
    }
    if not hash_statuses:
        blockers.append("MISSING_CARD_HASH_STATUS")
    for key in ("provider_calls", "db_reads", "db_writes"):
        if _int(payload.get(key)) != 0:
            blockers.append(f"{key.upper()}_NON_ZERO")
    return {
        "status": _status(blockers),
        "replay_status": payload.get("replay_status"),
        "hash_statuses": sorted(hash_statuses),
        "provider_calls": payload.get("provider_calls"),
        "db_reads": payload.get("db_reads"),
        "db_writes": payload.get("db_writes"),
        "blockers": blockers,
        "warnings": [],
    }


def _stage16_guard() -> dict[str, Any]:
    tracked, warnings = _tracked_stage16_files()
    return {
        "status": "PASS" if not tracked else "FAIL",
        "tracked_stage16_files": tracked,
        "blockers": [f"STAGE16_FILE:{path}" for path in tracked],
        "warnings": warnings,
    }


def _tracked_stage16_files() -> tuple[list[str], list[str]]:
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                ":(glob)**/*stage16*",
                ":(glob)**/check_w2_stage16.py",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return [], ["GIT_NOT_AVAILABLE_STAGE16_GUARD_WARN_ONLY"]
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
        return [], [f"GIT_LS_FILES_STAGE16_GUARD_WARN_ONLY:{detail}"]
    files = sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
    return files, []


def _matchday_payload() -> dict[str, Any]:
    now = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
    return build_matchday_dry_run(
        football_day=date(2026, 7, 5),
        environment="staging",
        as_of=now,
        fixtures=[
            {
                "fixture_id": "fixture-analysis",
                "kickoff_utc": now + timedelta(hours=25),
                "home_team": "Home Analysis",
                "away_team": "Away Analysis",
                "market": "ASIAN_HANDICAP",
                "line": "-0.25",
                "odds": "1.95",
                "recommendation_id": "rec-analysis-1",
                "lineups_available": True,
                "xg_available": True,
                "ratings_available": True,
                "team_value_available": True,
            }
        ],
        provider_allowed_endpoints=("status", "fixtures", "odds", "lineups", "statistics"),
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"fixture must be a JSON object: {path}")
    return payload


def _text_report(result: Mapping[str, Any]) -> str:
    lines = [
        f"status {result['status']}",
        f"boss_5s_test {result['boss_5s_test']['status']}",
        f"contract_acceptance {result['contract_acceptance']['status']}",
        f"refresh_safety_acceptance {result['refresh_safety_acceptance']['status']}",
        f"dashboard_visual_acceptance {result['dashboard_visual_acceptance']['status']}",
        f"matchday_dry_run_acceptance {result['matchday_dry_run_acceptance']['status']}",
        f"replay_acceptance {result['replay_acceptance']['status']}",
        f"stage16_guard {result['stage16_guard']['status']}",
        f"warnings {len(_string_list(result.get('warnings')))}",
        f"blockers {len(_string_list(result.get('blockers')))}",
        f"provider_calls {result['provider_calls']}",
        f"db_reads {result['db_reads']}",
        f"db_writes {result['db_writes']}",
    ]
    for blocker in _string_list(result.get("blockers")):
        lines.append(f"BLOCKER {blocker}")
    for warning in _string_list(result.get("warnings")):
        lines.append(f"WARN_ONLY {warning}")
    return "\n".join(lines)


def _cards(day_view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = day_view.get("cards")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _analysis_disclaimer(card: Mapping[str, Any]) -> str:
    pick = _mapping(card.get("pick"))
    return _text(pick.get("disclaimer"), card.get("disclaimer"), card.get("one_liner"))


def _forbidden_word_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).replace("非稳赢", "")
    return [f"FORBIDDEN_WORD:{word}" for word in FORBIDDEN_WORDS if word in text]


def _visible_first_screen(html: str) -> str:
    return re.sub(r"<details\b.*?</details>", "", html, flags=re.IGNORECASE | re.DOTALL)


def _raw_leaks(html: str) -> list[str]:
    return [f"RAW_DEBUG_LEAK:{term}" for term in RAW_FIRST_SCREEN_TERMS if term in html]


def _missing_texts(text: str, required: Sequence[str]) -> list[str]:
    return [f"MISSING_TEXT:{item}" for item in required if item and item not in text]


def _status(blockers: Sequence[str]) -> str:
    return "FAIL" if blockers else "PASS"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value]


def _text(*values: Any) -> str:
    for value in values:
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
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


if __name__ == "__main__":
    sys.exit(main())
