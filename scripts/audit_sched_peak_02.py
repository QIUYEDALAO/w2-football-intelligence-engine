#!/usr/bin/env python3
"""Profile the frozen SCHED-PEAK-02 projection batch and verify its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

SCHEMA = "w2.sched_peak_02.profile.v1"
EVIDENCE_SCHEMA = "w2.sched_peak_02.evidence.v1"
EXPECTED_EVENT_COUNT = 6
EXPECTED_ANALYSIS_CALLS = 24


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("EVENT_TIME_MUST_BE_AWARE")
    return parsed.astimezone(UTC)


class Timings:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)

    @contextmanager
    def record(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.seconds[name] += perf_counter() - started
            self.calls[name] += 1

    def wrap(self, name: str, target: Callable[..., Any]) -> Callable[..., Any]:
        def measured(*args: Any, **kwargs: Any) -> Any:
            with self.record(name):
                return target(*args, **kwargs)

        return measured

    def payload(self) -> dict[str, dict[str, float | int]]:
        return {
            name: {"calls": self.calls[name], "wall_seconds": round(seconds, 6)}
            for name, seconds in sorted(self.seconds.items())
        }


def _profile(manifest_path: Path, output: Path, label: str) -> None:
    if not os.environ.get("W2_DATABASE_URL"):
        raise SystemExit("W2_DATABASE_URL_REQUIRED")
    if "default_transaction_read_only=on" not in os.environ.get("PGOPTIONS", ""):
        raise SystemExit("READ_ONLY_PGOPTIONS_REQUIRED")

    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine

    from w2.infrastructure.database import create_engine
    from w2.prematch import analysis_calculator as analysis_module
    from w2.prematch import read_model_projection as projection_module
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        AnalysisCardCanaryMaterializer,
        ProjectionSourceEvent,
        validate_frozen_analysis_payload,
    )
    from w2.strategy import simulate as simulate_module

    manifest = _read_json(manifest_path)
    events = manifest.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENT_COUNT:
        raise SystemExit("FROZEN_EVENT_COUNT_MISMATCH")

    timings = Timings()
    sql_started: dict[int, float] = {}

    def before_cursor_execute(
        _conn: object,
        _cursor: object,
        _statement: object,
        _parameters: object,
        context: object,
        _executemany: object,
    ) -> None:
        sql_started[id(context)] = perf_counter()

    def after_cursor_execute(
        _conn: object,
        _cursor: object,
        _statement: object,
        _parameters: object,
        context: object,
        _executemany: object,
    ) -> None:
        started = sql_started.pop(id(context), None)
        if started is not None:
            timings.seconds["database_driver"] += perf_counter() - started
            timings.calls["database_driver"] += 1

    event.listen(Engine, "before_cursor_execute", before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", after_cursor_execute)

    repository = ReadModelRepository()
    benchmark_engine = create_engine()
    with benchmark_engine.connect() as connection:
        read_only = str(connection.execute(text("SHOW transaction_read_only")).scalar_one())
    if read_only.lower() != "on":
        raise SystemExit(f"DATABASE_NOT_READ_ONLY:{read_only}")

    original_simulation = analysis_module.run_simulation
    original_matrix = simulate_module._exact_score_matrix_with_uncertainty
    original_sampling = simulate_module.sample_score_matrix
    original_json = projection_module.canonical_json_bytes
    original_hash = projection_module.canonical_sha256
    original_dynamic_evaluations = projection_module._dynamic_evaluations
    analysis_module.run_simulation = timings.wrap("simulation_total", original_simulation)
    simulate_module._exact_score_matrix_with_uncertainty = timings.wrap(
        "exact_score_matrix_13x13", original_matrix
    )
    simulate_module.sample_score_matrix = timings.wrap(
        "deterministic_sampling_10000", original_sampling
    )
    projection_module.canonical_json_bytes = timings.wrap("canonical_serialization", original_json)
    projection_module.canonical_sha256 = timings.wrap("canonical_hashing", original_hash)
    projection_module._dynamic_evaluations = timings.wrap(
        "dynamic_evaluation_projection", original_dynamic_evaluations
    )

    def calculate(
        scoped_repository: object,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        with timings.record("analysis_card"):
            return ReadModelService(repository=scoped_repository).public_analysis_card_bounded(  # type: ignore[arg-type]
                fixture_id,
                evaluation_time=evaluated_at,
                use_frozen_canary=False,
            )

    benchmark_clock = _parse_utc(str(manifest["benchmark_clock"]))
    materializer = AnalysisCardCanaryMaterializer(
        repository,
        calculate_analysis_card=calculate,
        clock=lambda: benchmark_clock,
    )
    event_rows: list[dict[str, Any]] = []
    cpu_started = process_time()
    wall_started = perf_counter()
    try:
        for item in events:
            source_event = ProjectionSourceEvent.create(
                fixture_id=str(item["fixture_id"]),
                event_type=str(item["event_type"]),
                event_id=str(item["event_id"]),
                event_at=_parse_utc(str(item["event_at"])),
                payload={"frozen_manifest": manifest["schema_version"]},
            )
            started = perf_counter()
            with timings.record("initial_artifact_build"):
                artifact = materializer.build(
                    source_event.fixture_id,
                    evaluated_at=source_event.event_at,
                    source_event=source_event,
                )
            with timings.record("artifact_validation"):
                validate_frozen_analysis_payload(source_event.fixture_id, artifact.payload)
            with timings.record("post_write_rebuild_read_only"):
                rebuilt = materializer.build(
                    source_event.fixture_id,
                    evaluated_at=source_event.event_at,
                    source_event=source_event,
                )
            with timings.record("artifact_validation"):
                validate_frozen_analysis_payload(source_event.fixture_id, rebuilt.payload)
            if rebuilt.artifact_hash != artifact.artifact_hash:
                raise RuntimeError("READ_ONLY_REBUILD_HASH_MISMATCH")
            event_rows.append(
                {
                    "fixture_id": source_event.fixture_id,
                    "event_type": source_event.event_type,
                    "event_at": source_event.event_at.isoformat().replace("+00:00", "Z"),
                    "wall_seconds": round(perf_counter() - started, 6),
                    "artifact_bytes": len(artifact.canonical_bytes),
                    "artifact_hash": artifact.artifact_hash,
                }
            )
    finally:
        analysis_module.run_simulation = original_simulation
        simulate_module._exact_score_matrix_with_uncertainty = original_matrix
        simulate_module.sample_score_matrix = original_sampling
        projection_module.canonical_json_bytes = original_json
        projection_module.canonical_sha256 = original_hash
        projection_module._dynamic_evaluations = original_dynamic_evaluations
        event.remove(Engine, "before_cursor_execute", before_cursor_execute)
        event.remove(Engine, "after_cursor_execute", after_cursor_execute)

    total_wall = perf_counter() - wall_started
    total_cpu = process_time() - cpu_started
    profile = {
        "schema_version": SCHEMA,
        "label": label,
        "coverage_trace_active": sys.gettrace() is not None,
        "manifest_sha256": _sha256(manifest),
        "source_release": manifest["source_release"],
        "source_image_digest": manifest["source_image_digest"],
        "database_read_only": True,
        "provider_calls": 0,
        "outcomes_reads": 0,
        "event_count": len(event_rows),
        "analysis_call_count": timings.calls["analysis_card"],
        "projection_pass_contract": manifest["projection_pass_contract"],
        "total_wall_seconds": round(total_wall, 6),
        "total_cpu_seconds": round(total_cpu, 6),
        "stages": timings.payload(),
        "events": event_rows,
    }
    profile["content_sha256"] = _sha256(profile)
    _write_json(output, profile)


def _validated_profile(path: Path, *, label: str, manifest_sha256: str) -> dict[str, Any]:
    profile = _read_json(path)
    digest = profile.pop("content_sha256", None)
    if digest != _sha256(profile):
        raise ValueError(f"PROFILE_DIGEST_MISMATCH:{label}")
    profile["content_sha256"] = digest
    if profile.get("schema_version") != SCHEMA or profile.get("label") != label:
        raise ValueError(f"PROFILE_IDENTITY_MISMATCH:{label}")
    if profile.get("manifest_sha256") != manifest_sha256:
        raise ValueError(f"PROFILE_MANIFEST_MISMATCH:{label}")
    if profile.get("event_count") != EXPECTED_EVENT_COUNT:
        raise ValueError(f"PROFILE_EVENT_COUNT_MISMATCH:{label}")
    if profile.get("analysis_call_count") != EXPECTED_ANALYSIS_CALLS:
        raise ValueError(f"PROFILE_ANALYSIS_CALL_COUNT_MISMATCH:{label}")
    if profile.get("provider_calls") != 0 or profile.get("outcomes_reads") != 0:
        raise ValueError(f"PROFILE_FORBIDDEN_IO:{label}")
    if profile.get("database_read_only") is not True:
        raise ValueError(f"PROFILE_DATABASE_NOT_READ_ONLY:{label}")
    return profile


def _stage(profile: dict[str, Any], name: str) -> float:
    return float(profile.get("stages", {}).get(name, {}).get("wall_seconds", 0.0))


def _assemble(manifest_path: Path, plain_path: Path, covered_path: Path, output: Path) -> None:
    manifest = _read_json(manifest_path)
    manifest_sha = _sha256(manifest)
    plain = _validated_profile(plain_path, label="plain", manifest_sha256=manifest_sha)
    covered = _validated_profile(covered_path, label="coverage", manifest_sha256=manifest_sha)
    if plain.get("coverage_trace_active") is not False:
        raise ValueError("PLAIN_PROFILE_HAS_TRACE")
    if covered.get("coverage_trace_active") is not True:
        raise ValueError("COVERAGE_PROFILE_HAS_NO_TRACE")
    plain_hashes = [row["artifact_hash"] for row in plain["events"]]
    covered_hashes = [row["artifact_hash"] for row in covered["events"]]
    if plain_hashes != covered_hashes:
        raise ValueError("FROZEN_OUTPUT_HASH_MISMATCH")
    plain_wall = float(plain["total_wall_seconds"])
    covered_wall = float(covered["total_wall_seconds"])
    if plain_wall <= 0 or covered_wall <= 0:
        raise ValueError("PROFILE_DURATION_INVALID")

    stage_names = (
        "exact_score_matrix_13x13",
        "deterministic_sampling_10000",
        "database_driver",
        "canonical_serialization",
        "canonical_hashing",
        "dynamic_evaluation_projection",
        "initial_artifact_build",
        "artifact_validation",
        "post_write_rebuild_read_only",
        "analysis_card",
        "simulation_total",
    )
    stage_comparison = {
        name: {
            "plain_seconds": round(_stage(plain, name), 6),
            "coverage_seconds": round(_stage(covered, name), 6),
            "multiplier": round(_stage(covered, name) / _stage(plain, name), 6)
            if _stage(plain, name) > 0
            else None,
            "calls": int(plain.get("stages", {}).get(name, {}).get("calls", 0)),
        }
        for name in stage_names
    }
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "frozen_manifest": {
            "sha256": manifest_sha,
            "source_release": manifest["source_release"],
            "source_image_digest": manifest["source_image_digest"],
            "competition_id": manifest["competition_id"],
            "plan_count": manifest["plan_count"],
            "event_count": len(manifest["events"]),
            "analysis_call_count": EXPECTED_ANALYSIS_CALLS,
        },
        "safety": {
            "provider_calls": 0,
            "production_database_writes": 0,
            "outcomes_reads": 0,
            "deployment": False,
            "benchmark_database": "isolated_clone_read_only",
        },
        "coverage_ab": {
            "plain_wall_seconds": round(plain_wall, 6),
            "coverage_wall_seconds": round(covered_wall, 6),
            "coverage_overhead_seconds": round(covered_wall - plain_wall, 6),
            "coverage_multiplier": round(covered_wall / plain_wall, 6),
            "plain_cpu_seconds": round(float(plain["total_cpu_seconds"]), 6),
            "coverage_cpu_seconds": round(float(covered["total_cpu_seconds"]), 6),
            "coverage_cpu_overhead_seconds": round(
                float(covered["total_cpu_seconds"]) - float(plain["total_cpu_seconds"]), 6
            ),
            "coverage_cpu_multiplier": round(
                float(covered["total_cpu_seconds"]) / float(plain["total_cpu_seconds"]), 6
            ),
            "plain_seconds_per_plan": round(plain_wall / int(manifest["plan_count"]), 6),
            "coverage_seconds_per_plan": round(covered_wall / int(manifest["plan_count"]), 6),
            "production_observed_seconds_per_plan": round(
                float(manifest["observed_task_wall_seconds"]) / int(manifest["plan_count"]), 6
            ),
            "production_observed_task_wall_seconds": round(
                float(manifest["observed_task_wall_seconds"]), 6
            ),
            "coverage_rehearsal_minus_production_seconds": round(
                covered_wall - float(manifest["observed_task_wall_seconds"]), 6
            ),
            "production_wall_explained_ratio": round(
                covered_wall / float(manifest["observed_task_wall_seconds"]), 6
            ),
        },
        "stage_comparison": stage_comparison,
        "profile_sha256": {
            "plain": plain["content_sha256"],
            "coverage": covered["content_sha256"],
        },
        "plain_event_timings": plain["events"],
        "coverage_event_timings": covered["events"],
        "capacity_retest_contract": {
            "not_before": "2026-08-28T04:37:34Z",
            "same_1830z_slot_shape_required": True,
            "coverage_must_be_absent": True,
            "measurements": [
                "queue_seconds",
                "claim_to_finish_seconds",
                "task_wall_seconds",
                "per_plan_seconds",
                "worker_cpu_and_rss",
                "database_connections_and_query_time",
                "provider_call_count_and_max_elapsed_ms",
                "window_margin_seconds",
            ],
            "temporary_capacity_until_retest": 2,
            "long_term_capacity_baseline": None,
        },
    }
    evidence["content_sha256"] = _sha256(evidence)
    _write_json(output, evidence)


def _check(manifest_path: Path, plain_path: Path, covered_path: Path, evidence_path: Path) -> None:
    manifest = _read_json(manifest_path)
    manifest_sha = _sha256(manifest)
    plain = _validated_profile(plain_path, label="plain", manifest_sha256=manifest_sha)
    covered = _validated_profile(covered_path, label="coverage", manifest_sha256=manifest_sha)
    evidence = _read_json(evidence_path)
    digest = evidence.pop("content_sha256", None)
    if digest != _sha256(evidence):
        raise ValueError("EVIDENCE_DIGEST_MISMATCH")
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("EVIDENCE_SCHEMA_MISMATCH")
    if evidence.get("frozen_manifest", {}).get("sha256") != manifest_sha:
        raise ValueError("EVIDENCE_MANIFEST_MISMATCH")
    if evidence.get("profile_sha256") != {
        "plain": plain["content_sha256"],
        "coverage": covered["content_sha256"],
    }:
        raise ValueError("EVIDENCE_PROFILE_MISMATCH")
    safety = evidence.get("safety", {})
    if safety.get("provider_calls") != 0 or safety.get("production_database_writes") != 0:
        raise ValueError("EVIDENCE_SAFETY_MISMATCH")
    if evidence.get("capacity_retest_contract", {}).get("long_term_capacity_baseline") is not None:
        raise ValueError("LONG_TERM_CAPACITY_PREMATURELY_SET")
    print("SCHED_PEAK_02_CHECK_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("plain", "coverage"))
    parser.add_argument("--plain", type=Path)
    parser.add_argument("--covered", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--assemble", action="store_true")
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.profile:
        if args.output is None:
            parser.error("--profile requires --output")
        _profile(args.manifest, args.output, args.profile)
        return
    if args.assemble:
        if args.plain is None or args.covered is None or args.output is None:
            parser.error("--assemble requires --plain --covered --output")
        _assemble(args.manifest, args.plain, args.covered, args.output)
        return
    if args.check:
        if args.plain is None or args.covered is None:
            parser.error("--check requires --plain --covered")
        _check(args.manifest, args.plain, args.covered, args.check)
        return
    parser.error("choose --profile, --assemble, or --check")


if __name__ == "__main__":
    main()
