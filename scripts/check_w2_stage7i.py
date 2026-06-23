#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ID = "1489401"
REQUIRED = [
    "scripts/run_stage7i_observer.py",
    "scripts/check_w2_stage7i.py",
    "docs/runbooks/STAGE7I_24H_OBSERVATION.md",
    "reports/W2_STAGE7I_OBSERVATION_START.json",
    "reports/W2_STAGE7I_RESULT.md",
]
ALLOWED_OBSERVER_STATUS = {
    "IN_PROGRESS",
    "OBSERVATION_ALREADY_RUNNING",
    "BLOCKED",
    "BLOCKED_NON_QUALIFYING",
    "INTERRUPTED",
    "COMPLETED",
}
UTC = timezone.utc  # noqa: UP017 - local python3 can be 3.9 while project runtime is 3.12.


class Stage7ICheckError(Exception):
    pass


def fail(message: str) -> None:
    print(f"W2 Stage7I check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(read(path))
    except json.JSONDecodeError as exc:
        raise Stage7ICheckError(f"malformed JSON: {path}") from exc


def parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise Stage7ICheckError(f"{field} must be a non-empty UTC ISO string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise Stage7ICheckError(f"{field} is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise Stage7ICheckError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def require_bool(payload: dict[str, Any], field: str, expected: bool) -> None:
    if payload.get(field) is not expected:
        raise Stage7ICheckError(f"{field} must be {expected}")


def require_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise Stage7ICheckError(f"{field} must be a non-empty string")
    return value


def validate_start_report(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise Stage7ICheckError("start report must be an object")
    if payload.get("stage") != "W2-STAGE7I":
        raise Stage7ICheckError("start report stage mismatch")
    if str(payload.get("fixture_id")) != FIXTURE_ID:
        raise Stage7ICheckError("start report fixture_id mismatch")
    require_str(payload, "branch")
    require_str(payload, "repository_head")
    require_str(payload, "server_current_revision")
    require_str(payload, "scheduled_kickoff_utc")
    parse_utc(payload.get("captured_at_utc"), "captured_at_utc")
    parse_utc(payload.get("scheduled_kickoff_utc"), "scheduled_kickoff_utc")
    if payload.get("scheduled_kickoff_at") != payload.get("scheduled_kickoff_utc"):
        raise Stage7ICheckError("scheduled_kickoff_at must mirror scheduled_kickoff_utc")
    status = payload.get("status") or payload.get("observer_status")
    if status not in ALLOWED_OBSERVER_STATUS:
        raise Stage7ICheckError(f"invalid observer_status: {status}")
    if "PLACEHOLDER" in json.dumps(payload) or "TODO" in json.dumps(payload):
        raise Stage7ICheckError("start report contains placeholder text")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    if status == "BLOCKED_NON_QUALIFYING":
        validate_blocked_non_qualifying(payload)
    return payload


def validate_blocked_non_qualifying(payload: dict[str, Any]) -> None:
    if payload.get("observer_status") != "BLOCKED_NON_QUALIFYING":
        raise Stage7ICheckError("observer_status must be BLOCKED_NON_QUALIFYING")
    require_str(payload, "expected_server_revision")
    if int(payload.get("observer_pid", 0)) != 343187:
        raise Stage7ICheckError("blocked archive must preserve observer_pid 343187")
    evidence = payload.get("evidence_classification")
    if not isinstance(evidence, dict):
        raise Stage7ICheckError("evidence_classification must be an object")
    if evidence.get("forward_complete") is not False:
        raise Stage7ICheckError("forward_complete=false required")
    if evidence.get("gate5_eligible") is not False:
        raise Stage7ICheckError("gate5_eligible=false required")
    if evidence.get("retrospective_allowed") is not True:
        raise Stage7ICheckError("retrospective_allowed=true required")
    recovery = payload.get("recovery_policy")
    if not isinstance(recovery, dict):
        raise Stage7ICheckError("recovery_policy must be an object")
    if recovery.get("same_fixture_restart_allowed") is not False:
        raise Stage7ICheckError("same_fixture_restart_allowed=false required")
    if recovery.get("successor_fixture_required") is not True:
        raise Stage7ICheckError("successor_fixture_required=true required")
    blockers = payload.get("blocker_codes")
    required = {
        "OBSERVER_INTERRUPTED_BY_APPROVED_DEPLOYMENT",
        "OBSERVATION_WINDOW_INCOMPLETE",
        "CURRENT_REVISION_CHANGED",
        "FORWARD_LIFECYCLE_NOT_CONTINUOUS",
    }
    if not isinstance(blockers, list) or not required <= set(blockers):
        raise Stage7ICheckError("blocked archive missing required blocker_codes")
    forbidden = [
        "actual_kickoff_utc",
        "closing_observation_utc",
        "settlement",
        "evaluation",
        "final_shadow_db_audit",
    ]
    for field in forbidden:
        if field in payload:
            raise Stage7ICheckError(f"blocked archive must not include {field}")


def validate_result_report(path: Path, start: dict[str, Any]) -> None:
    text = read(path)
    if "formal_recommendation=false" not in text:
        raise Stage7ICheckError("result must record formal_recommendation=false")
    if "candidate=false" not in text:
        raise Stage7ICheckError("result must record candidate=false")
    if "RECOMMEND" in text and "正式推荐尚未启用" not in text:
        raise Stage7ICheckError("result contains recommendation wording without guard")
    status = start.get("status") or start.get("observer_status")
    if status != "COMPLETED" and "STAGE_7I_OBSERVATION=COMPLETED" in text:
        raise Stage7ICheckError("incomplete observation must not claim COMPLETED")
    if status in {"BLOCKED", "BLOCKED_NON_QUALIFYING", "INTERRUPTED"} and "BLOCKER" not in text:
        raise Stage7ICheckError("blocked observation result must name BLOCKER")
    if status == "BLOCKED_NON_QUALIFYING":
        for token in [
            "STAGE_7I_OBSERVATION=BLOCKED_NON_QUALIFYING",
            "forward_complete=false",
            "gate5_eligible=false",
            "same_fixture_restart_allowed=false",
            "successor_fixture_required=true",
        ]:
            if token not in text:
                raise Stage7ICheckError(f"blocked result missing {token}")


def validate_evidence_event(event: dict[str, Any]) -> tuple[str, str]:
    event_id = require_str(event, "event_id")
    category = event.get("evidence_category")
    if category not in {"FORWARD", "RETROSPECTIVE"}:
        raise Stage7ICheckError(f"invalid evidence_category for {event_id}")
    if str(event.get("fixture_id")) != FIXTURE_ID:
        raise Stage7ICheckError(f"fixture_id mismatch for {event_id}")
    parse_utc(event.get("event_time_utc"), f"{event_id}.event_time_utc")
    if event.get("candidate") is not False:
        raise Stage7ICheckError(f"candidate must be false for {event_id}")
    if event.get("formal_recommendation") is not False:
        raise Stage7ICheckError(f"formal_recommendation must be false for {event_id}")
    return event_id, str(category)


def validate_evidence_file(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise Stage7ICheckError("evidence file must be an object")
    if str(payload.get("fixture_id")) != FIXTURE_ID:
        raise Stage7ICheckError("evidence fixture_id mismatch")
    scheduled = parse_utc(payload.get("scheduled_kickoff_utc"), "scheduled_kickoff_utc")
    actual = parse_utc(payload.get("actual_kickoff_utc"), "actual_kickoff_utc")
    closing = parse_utc(payload.get("closing_observation_utc"), "closing_observation_utc")
    if closing >= actual:
        raise Stage7ICheckError("closing observation must be before actual kickoff")
    if abs((actual - scheduled).total_seconds()) > 6 * 60 * 60:
        raise Stage7ICheckError("actual kickoff is implausibly far from scheduled kickoff")
    events = payload.get("evidence_events")
    if not isinstance(events, list) or not events:
        raise Stage7ICheckError("evidence_events must be a non-empty list")
    seen: set[str] = set()
    last_time: datetime | None = None
    for raw in events:
        if not isinstance(raw, dict):
            raise Stage7ICheckError("each evidence event must be an object")
        event_id, category = validate_evidence_event(raw)
        if event_id in seen:
            raise Stage7ICheckError(f"duplicate evidence event: {event_id}")
        seen.add(event_id)
        event_time = parse_utc(raw.get("event_time_utc"), f"{event_id}.event_time_utc")
        if last_time is not None and event_time < last_time:
            raise Stage7ICheckError("evidence events must be chronological")
        last_time = event_time
        event_type = raw.get("event_type")
        if category == "FORWARD" and event_time >= actual:
            raise Stage7ICheckError(f"forward event after actual kickoff: {event_id}")
        if category == "RETROSPECTIVE" and event_time < actual:
            raise Stage7ICheckError(f"retrospective event before actual kickoff: {event_id}")
        if category == "FORWARD" and event_type in {"SETTLEMENT", "EVALUATION"}:
            raise Stage7ICheckError(f"settlement/evaluation cannot be forward: {event_id}")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    return payload


def validate_runtime(runtime_dir: Path | None) -> None:
    if runtime_dir is None:
        return
    observations = runtime_dir / "observations.jsonl"
    if not observations.exists():
        raise Stage7ICheckError(f"missing runtime observations: {observations}")
    previous: datetime | None = None
    seen_lines: set[str] = set()
    for line_number, line in enumerate(read(observations).splitlines(), start=1):
        if not line.strip():
            continue
        if line in seen_lines:
            raise Stage7ICheckError(f"duplicate observation line {line_number}")
        seen_lines.add(line)
        try:
            sample = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Stage7ICheckError(f"malformed observation JSON line {line_number}") from exc
        if not isinstance(sample, dict):
            raise Stage7ICheckError(f"observation line {line_number} must be an object")
        timestamp = parse_utc(sample.get("timestamp_utc"), f"line {line_number} timestamp_utc")
        if previous is not None and timestamp <= previous:
            raise Stage7ICheckError("observation timestamps must strictly increase")
        previous = timestamp


def validate_static_files() -> None:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            raise Stage7ICheckError(f"missing {path}")
    script = read(ROOT / "scripts/run_stage7i_observer.py")
    for token in [
        "observations.jsonl",
        "observer.pid",
        "COMPLETED",
        "SAMPLE_INTERVAL_SECONDS = 300",
        "OBSERVATION_SECONDS = 24 * 60 * 60",
        "CURRENT_REVISION_CHANGED",
        "PUBLIC_BUSINESS_PORT_DETECTED",
        "SCHEDULER_HEARTBEAT_STALE",
    ]:
        if token not in script:
            raise Stage7ICheckError(f"observer missing token {token}")
    if "shell=True" in script:
        raise Stage7ICheckError("observer must not use shell=True")
    if "runtime/stage7i/" not in read(ROOT / ".gitignore"):
        raise Stage7ICheckError("runtime/stage7i must be gitignored")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate W2 Stage7I evidence files.")
    parser.add_argument("archive_json", nargs="?", type=Path)
    parser.add_argument("--evidence-json", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    try:
        validate_static_files()
        start_path = args.archive_json or ROOT / "reports/W2_STAGE7I_OBSERVATION_START.json"
        start = validate_start_report(start_path)
        validate_result_report(ROOT / "reports/W2_STAGE7I_RESULT.md", start)
        if args.evidence_json is not None:
            validate_evidence_file(args.evidence_json)
        validate_runtime(args.runtime_dir)
        status = start.get("status") or start.get("observer_status")
        if status == "BLOCKED_NON_QUALIFYING" and not args.allow_blocked:
            evidence = start.get("evidence_classification") or {}
            print("W2 Stage7I final validation BLOCKED", file=sys.stderr)
            print("forward_complete=false", file=sys.stderr)
            print("gate5_eligible=false", file=sys.stderr)
            if isinstance(evidence, dict):
                print(
                    f"retrospective_allowed={str(evidence.get('retrospective_allowed')).lower()}",
                    file=sys.stderr,
                )
            return 1
    except Stage7ICheckError as exc:
        fail(str(exc))
    if (start.get("status") or start.get("observer_status")) == "BLOCKED_NON_QUALIFYING":
        print("forward_complete=false")
        print("gate5_eligible=false")
    print("W2 Stage7I check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
