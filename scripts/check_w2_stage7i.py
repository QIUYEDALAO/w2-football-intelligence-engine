#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN01_ARCHIVE_FIXTURE = "1489401"
GLOBAL_LOCK_PATH = "/opt/w2/shared/runtime/stage7i/observer-global.lock"
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
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage7ICheckError(f"{field} is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise Stage7ICheckError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def require_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise Stage7ICheckError(f"{field} must be a non-empty string")
    return value


def require_bool(payload: dict[str, Any], field: str, expected: bool) -> None:
    if payload.get(field) is not expected:
        raise Stage7ICheckError(f"{field} must be {expected}")


def require_object(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise Stage7ICheckError(f"{field} must be an object")
    return value


def validate_static_files() -> None:
    required = [
        "scripts/run_stage7i_observer.py",
        "scripts/check_w2_stage7i.py",
        "scripts/select_stage7i_successor.py",
        "docs/runbooks/STAGE7I_24H_OBSERVATION.md",
        "reports/W2_STAGE7I_OBSERVATION_START.json",
        "reports/W2_STAGE7I_RESULT.md",
    ]
    for path in required:
        if not (ROOT / path).is_file():
            raise Stage7ICheckError(f"missing {path}")
    observer = read(ROOT / "scripts/run_stage7i_observer.py")
    for token in [
        "observer-global.lock",
        "--fixture-id",
        "--scheduled-kickoff-utc",
        "--baseline-revision",
        "--expected-alembic-head",
        "--selection-json",
        "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE",
    ]:
        if token not in observer:
            raise Stage7ICheckError(f"observer missing token {token}")
    if "shell=True" in observer:
        raise Stage7ICheckError("observer must not use shell=True")
    if "runtime/stage7i/" not in read(ROOT / ".gitignore"):
        raise Stage7ICheckError("runtime/stage7i must be gitignored")


def validate_archive(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise Stage7ICheckError("archive must be an object")
    if payload.get("status") != "BLOCKED_NON_QUALIFYING":
        raise Stage7ICheckError("archive status must be BLOCKED_NON_QUALIFYING")
    if payload.get("observer_status") != "BLOCKED_NON_QUALIFYING":
        raise Stage7ICheckError("observer_status must be BLOCKED_NON_QUALIFYING")
    if str(payload.get("fixture_id")) != RUN01_ARCHIVE_FIXTURE:
        raise Stage7ICheckError("Run 01 archive fixture must remain 1489401")
    if int(payload.get("observer_pid", 0)) != 343187:
        raise Stage7ICheckError("Run 01 archive observer_pid must remain 343187")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    parse_utc(payload.get("captured_at_utc"), "captured_at_utc")
    parse_utc(payload.get("scheduled_kickoff_utc"), "scheduled_kickoff_utc")
    if payload.get("scheduled_kickoff_at") != payload.get("scheduled_kickoff_utc"):
        raise Stage7ICheckError("scheduled_kickoff_at must mirror scheduled_kickoff_utc")
    require_str(payload, "expected_server_revision")
    evidence = require_object(payload, "evidence_classification")
    if evidence.get("forward_complete") is not False:
        raise Stage7ICheckError("forward_complete=false required")
    if evidence.get("gate5_eligible") is not False:
        raise Stage7ICheckError("gate5_eligible=false required")
    if evidence.get("retrospective_allowed") is not True:
        raise Stage7ICheckError("retrospective_allowed=true required")
    recovery = require_object(payload, "recovery_policy")
    if recovery.get("same_fixture_restart_allowed") is not False:
        raise Stage7ICheckError("same_fixture_restart_allowed=false required")
    if recovery.get("successor_fixture_required") is not True:
        raise Stage7ICheckError("successor_fixture_required=true required")
    for field in [
        "actual_kickoff_utc",
        "closing_observation_utc",
        "settlement",
        "evaluation",
        "final_shadow_db_audit",
    ]:
        if field in payload:
            raise Stage7ICheckError(f"archive must not include {field}")
    return payload


def validate_selection(payload: dict[str, Any], *, expected_fixture_id: str | None = None) -> str:
    if payload.get("source") != "W2_STAGING_PROVIDER_DATA":
        raise Stage7ICheckError("selection source must be W2_STAGING_PROVIDER_DATA")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    selected = require_object(payload, "selected_fixture")
    fixture_id = require_str(selected, "fixture_id")
    if fixture_id == RUN01_ARCHIVE_FIXTURE:
        raise Stage7ICheckError("successor fixture must not be 1489401")
    if expected_fixture_id is not None and fixture_id != expected_fixture_id:
        raise Stage7ICheckError("selection fixture_id does not match expected fixture")
    if selected.get("status") not in {"NS", "STARTED", "IN_PROGRESS"}:
        raise Stage7ICheckError("selection fixture status must be NS/STARTED/IN_PROGRESS")
    kickoff = parse_utc(selected.get("scheduled_kickoff_utc"), "selection.scheduled_kickoff_utc")
    generated = parse_utc(payload.get("generated_at_utc"), "selection.generated_at_utc")
    if selected.get("status") == "NS" and kickoff <= generated:
        raise Stage7ICheckError("selected kickoff must be future at selection time")
    mapping = require_object(selected, "provider_mapping")
    if mapping.get("reliable") is not True or mapping.get("conflict") is True:
        raise Stage7ICheckError("provider mapping must be reliable and conflict-free")
    market = require_object(selected, "market_observation")
    captured = parse_utc(market.get("captured_at_utc"), "market_observation.captured_at_utc")
    if captured > generated:
        raise Stage7ICheckError("market captured_at must not be in the future")
    if market.get("fresh") is not True:
        raise Stage7ICheckError("market observation must be fresh")
    if int(market.get("bookmaker_count", 0)) <= 0:
        raise Stage7ICheckError("market observation must include bookmakers")
    return fixture_id


def validate_bootstrap(
    start_path: Path,
    *,
    selection_json: Path | None,
    expected_fixture_id: str | None,
) -> dict[str, Any]:
    payload = load_json(start_path)
    if not isinstance(payload, dict):
        raise Stage7ICheckError("bootstrap start must be an object")
    if payload.get("status") not in {"IN_PROGRESS", "STARTED"}:
        raise Stage7ICheckError("bootstrap status must be IN_PROGRESS or STARTED")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    require_bool(payload, "gate5_eligible", False)
    fixture_id = require_str(payload, "fixture_id")
    if fixture_id == RUN01_ARCHIVE_FIXTURE:
        raise Stage7ICheckError("bootstrap cannot use archived fixture 1489401")
    if expected_fixture_id is not None and fixture_id != expected_fixture_id:
        raise Stage7ICheckError("bootstrap fixture_id does not match expected fixture")
    kickoff = parse_utc(payload.get("scheduled_kickoff_utc"), "scheduled_kickoff_utc")
    started = parse_utc(payload.get("observer_started_at_utc"), "observer_started_at_utc")
    if kickoff <= started:
        raise Stage7ICheckError("bootstrap kickoff must be future at observer start")
    require_str(payload, "baseline_revision")
    require_str(payload, "expected_alembic_head")
    require_str(payload, "observer_id")
    require_str(payload, "runtime_dir")
    if payload.get("global_lock_path") != GLOBAL_LOCK_PATH:
        raise Stage7ICheckError("bootstrap must use global Stage7I lock")
    require_str(payload, "selection_sha256")
    if payload.get("evidence_classification") != "FORWARD_OBSERVATION":
        raise Stage7ICheckError("bootstrap evidence_classification must be FORWARD_OBSERVATION")
    for field in ["actual_kickoff_utc", "closing_observation_utc", "settlement", "evaluation"]:
        if field in payload:
            raise Stage7ICheckError(f"bootstrap must not claim {field}")
    sample = require_object(payload, "initial_sample")
    if sample.get("fixture_id") != fixture_id:
        raise Stage7ICheckError("initial sample fixture mismatch")
    if sample.get("candidate") is not False or sample.get("formal_recommendation") is not False:
        raise Stage7ICheckError("initial sample must keep candidate/formal false")
    sample_time = parse_utc(sample.get("captured_at_utc"), "initial_sample.captured_at_utc")
    if sample_time < started:
        raise Stage7ICheckError("initial sample cannot predate observer start")
    selection_path = selection_json or Path(require_str(payload, "selection_json_path"))
    selection_payload = load_json(selection_path)
    if not isinstance(selection_payload, dict):
        raise Stage7ICheckError("selection JSON must be an object")
    selected_fixture = validate_selection(selection_payload, expected_fixture_id=fixture_id)
    if selected_fixture != fixture_id:
        raise Stage7ICheckError("selection/start fixture mismatch")
    selected = selection_payload["selected_fixture"]
    if selected.get("scheduled_kickoff_utc") != payload.get("scheduled_kickoff_utc"):
        raise Stage7ICheckError("selection/start kickoff mismatch")
    return payload


def validate_evidence_events(payload: dict[str, Any], fixture_id: str) -> None:
    events = payload.get("evidence_events")
    if not isinstance(events, list) or not events:
        raise Stage7ICheckError("evidence_events must be a non-empty list")
    seen: set[str] = set()
    previous: datetime | None = None
    for raw in events:
        if not isinstance(raw, dict):
            raise Stage7ICheckError("each evidence event must be an object")
        event_id = require_str(raw, "event_id")
        if event_id in seen:
            raise Stage7ICheckError(f"duplicate evidence event: {event_id}")
        seen.add(event_id)
        if str(raw.get("fixture_id")) != fixture_id:
            raise Stage7ICheckError(f"fixture_id mismatch for {event_id}")
        category = raw.get("evidence_category")
        if category not in {"FORWARD", "RETROSPECTIVE"}:
            raise Stage7ICheckError(f"invalid evidence category for {event_id}")
        event_time = parse_utc(raw.get("event_time_utc"), f"{event_id}.event_time_utc")
        if previous is not None and event_time < previous:
            raise Stage7ICheckError("evidence events must be chronological")
        previous = event_time
        if raw.get("candidate") is not False or raw.get("formal_recommendation") is not False:
            raise Stage7ICheckError(f"candidate/formal must be false for {event_id}")


def validate_final(path: Path, *, expected_fixture_id: str | None) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise Stage7ICheckError("final evidence must be an object")
    if payload.get("status") != "COMPLETED":
        raise Stage7ICheckError("final status must be COMPLETED")
    require_bool(payload, "candidate", False)
    require_bool(payload, "formal_recommendation", False)
    fixture_id = require_str(payload, "fixture_id")
    if fixture_id == RUN01_ARCHIVE_FIXTURE:
        raise Stage7ICheckError("final cannot use archived fixture 1489401")
    if expected_fixture_id is not None and fixture_id != expected_fixture_id:
        raise Stage7ICheckError("final fixture_id does not match expected fixture")
    started = parse_utc(payload.get("observer_started_at_utc"), "observer_started_at_utc")
    completed = parse_utc(payload.get("completed_at_utc"), "completed_at_utc")
    if completed - started < timedelta(hours=24):
        raise Stage7ICheckError("final observation must cover at least 24 hours")
    if payload.get("stable_revision") is not True:
        raise Stage7ICheckError("final requires stable_revision=true")
    actual = parse_utc(payload.get("actual_kickoff_utc"), "actual_kickoff_utc")
    closing = parse_utc(payload.get("closing_observation_utc"), "closing_observation_utc")
    if closing >= actual:
        raise Stage7ICheckError("closing observation must be before actual kickoff")
    if payload.get("forward_retrospective_separated") is not True:
        raise Stage7ICheckError("final requires forward/retrospective separation")
    if payload.get("settlement_evaluation_legal") is not True:
        raise Stage7ICheckError("final requires legal settlement/evaluation")
    if payload.get("final_shadow_db_audit") != "PASS":
        raise Stage7ICheckError("final Shadow DB audit must PASS")
    validate_evidence_events(payload, fixture_id)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate W2 Stage7I evidence files.")
    parser.add_argument(
        "start_json",
        nargs="?",
        type=Path,
        default=ROOT / "reports/W2_STAGE7I_OBSERVATION_START.json",
    )
    parser.add_argument("--mode", choices=["archive", "bootstrap", "final"], default="final")
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--selection-json", type=Path)
    parser.add_argument("--expected-fixture-id")
    args = parser.parse_args()
    try:
        validate_static_files()
        if args.allow_blocked:
            args.mode = "archive"
        if args.mode == "archive":
            archive = validate_archive(args.start_json)
            print("forward_complete=false")
            print("gate5_eligible=false")
            print(f"fixture_id={archive['fixture_id']}")
        elif args.mode == "bootstrap":
            validate_bootstrap(
                args.start_json,
                selection_json=args.selection_json,
                expected_fixture_id=args.expected_fixture_id,
            )
        else:
            validate_final(args.start_json, expected_fixture_id=args.expected_fixture_id)
    except Stage7ICheckError as exc:
        fail(str(exc))
    print("W2 Stage7I check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
