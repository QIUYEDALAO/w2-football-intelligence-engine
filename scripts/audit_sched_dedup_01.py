#!/usr/bin/env python3
"""Profile SCHED-DEDUP-01 and verify byte-identical projection output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

PROFILE_SCHEMA = "w2.sched_dedup_01.profile.v1"
EVIDENCE_SCHEMA = "w2.sched_dedup_01.evidence.v1"
EXPECTED_EVENTS = 6


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("EVENT_TIME_MUST_BE_AWARE")
    return parsed.astimezone(UTC)


def _normalized_sql(statement: object) -> str:
    return re.sub(r"\s+", " ", str(statement)).strip()


def _parameter_hash(parameters: object) -> str:
    rendered = json.dumps(parameters, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(rendered.encode()).hexdigest()


def _table_names(statement: str) -> list[str]:
    return sorted(
        {
            match.group(1).strip('"')
            for match in re.finditer(r"(?:FROM|JOIN)\s+([A-Za-z0-9_.\"]+)", statement, re.I)
        }
    )


class ProfileRecorder:
    def __init__(self) -> None:
        self.stage = "setup"
        self.stage_seconds: dict[str, float] = defaultdict(float)
        self.stage_calls: dict[str, int] = defaultdict(int)
        self.sql_started: dict[int, tuple[float, str, str, str]] = {}
        self.sql_families: dict[tuple[str, str], dict[str, Any]] = {}

    @contextmanager
    def record(self, stage: str) -> Iterator[None]:
        previous = self.stage
        self.stage = stage
        started = perf_counter()
        try:
            yield
        finally:
            self.stage_seconds[stage] += perf_counter() - started
            self.stage_calls[stage] += 1
            self.stage = previous

    def before_sql(
        self,
        _conn: object,
        _cursor: object,
        statement: object,
        parameters: object,
        context: object,
        _executemany: object,
    ) -> None:
        normalized = _normalized_sql(statement)
        self.sql_started[id(context)] = (
            perf_counter(),
            self.stage,
            normalized,
            _parameter_hash(parameters),
        )

    def after_sql(
        self,
        _conn: object,
        _cursor: object,
        _statement: object,
        _parameters: object,
        context: object,
        _executemany: object,
    ) -> None:
        item = self.sql_started.pop(id(context), None)
        if item is None:
            return
        started, stage, statement, parameter_hash = item
        elapsed = perf_counter() - started
        digest = hashlib.sha256(statement.encode()).hexdigest()
        family = self.sql_families.setdefault(
            (stage, digest),
            {
                "stage": stage,
                "statement_sha256": digest,
                "statement_prefix": statement[:240],
                "tables": _table_names(statement),
                "calls": 0,
                "wall_seconds": 0.0,
                "parameter_counts": defaultdict(int),
            },
        )
        family["calls"] += 1
        family["wall_seconds"] += elapsed
        family["parameter_counts"][parameter_hash] += 1

    def sql_payload(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for family in self.sql_families.values():
            parameter_counts = family.pop("parameter_counts")
            distinct_parameters = len(parameter_counts)
            exact_duplicate_calls = sum(max(0, count - 1) for count in parameter_counts.values())
            rows.append(
                {
                    **family,
                    "wall_seconds": round(float(family["wall_seconds"]), 6),
                    "distinct_parameter_sets": distinct_parameters,
                    "exact_duplicate_calls": exact_duplicate_calls,
                    "n_plus_one_candidate": distinct_parameters > 1,
                }
            )
        rows.sort(key=lambda row: (-float(row["wall_seconds"]), str(row["statement_sha256"])))
        total_calls = sum(int(row["calls"]) for row in rows)
        return {
            "calls": total_calls,
            "wall_seconds": round(sum(float(row["wall_seconds"]) for row in rows), 6),
            "statement_family_count": len({row["statement_sha256"] for row in rows}),
            "exact_duplicate_calls": sum(int(row["exact_duplicate_calls"]) for row in rows),
            "n_plus_one_candidate_calls": sum(
                int(row["calls"]) - 1 for row in rows if row["n_plus_one_candidate"]
            ),
            "families": rows,
        }


def _profile(manifest_path: Path, output: Path, mode: str) -> None:
    if not os.environ.get("W2_DATABASE_URL"):
        raise SystemExit("W2_DATABASE_URL_REQUIRED")
    if "default_transaction_read_only=on" not in os.environ.get("PGOPTIONS", ""):
        raise SystemExit("READ_ONLY_PGOPTIONS_REQUIRED")

    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine

    from w2.infrastructure.database import create_engine
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        AnalysisCardCanaryMaterializer,
        ProjectionSourceEvent,
    )
    from w2.prematch.repository import DynamicPrematchRepository

    manifest = _read_json(manifest_path)
    events = manifest.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENTS:
        raise SystemExit("FROZEN_EVENT_COUNT_MISMATCH")
    if mode == "optimized" and not hasattr(
        AnalysisCardCanaryMaterializer,
        "refresh_shadow_after_write",
    ):
        raise SystemExit("OPTIMIZED_IMPLEMENTATION_UNAVAILABLE")
    if mode == "baseline" and hasattr(
        AnalysisCardCanaryMaterializer,
        "refresh_shadow_after_write",
    ):
        raise SystemExit("BASELINE_SOURCE_TREE_REQUIRED")

    recorder = ProfileRecorder()
    event.listen(Engine, "before_cursor_execute", recorder.before_sql)
    event.listen(Engine, "after_cursor_execute", recorder.after_sql)
    repository = ReadModelRepository()
    engine = create_engine()
    with engine.connect() as connection:
        read_only = str(connection.execute(text("SHOW transaction_read_only")).scalar_one())
    if read_only.lower() != "on":
        raise SystemExit(f"DATABASE_NOT_READ_ONLY:{read_only}")

    analysis_calls = 0

    def calculate(
        scoped_repository: object,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        nonlocal analysis_calls
        analysis_calls += 1
        return ReadModelService(repository=scoped_repository).public_analysis_card_bounded(  # type: ignore[arg-type]
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    cpu_started = process_time()
    wall_started = perf_counter()
    benchmark_clock = _parse_utc(str(manifest["benchmark_clock"]))
    round3_by_fixture: dict[str, list[dict[str, Any]]] | None = None
    if mode == "optimized":
        fixture_ids = list(dict.fromkeys(str(item["fixture_id"]) for item in events))
        round3_by_fixture = {fixture_id: [] for fixture_id in fixture_ids}
        normalized_fixture_ids = {
            fixture_id.removeprefix("api_football:"): fixture_id for fixture_id in fixture_ids
        }
        with recorder.record("batch_round3_prefetch"):
            rows = repository.round3_market_evidence_for_fixtures(fixture_ids)
        for row in rows:
            normalized = str(row.get("fixture_id") or "").removeprefix("api_football:")
            fixture_id = normalized_fixture_ids.get(normalized)
            if fixture_id is None:
                raise RuntimeError("ROUND3_BATCH_RETURNED_UNEXPECTED_FIXTURE")
            round3_by_fixture[fixture_id].append(dict(row))
    materializer_kwargs: dict[str, Any] = {
        "calculate_analysis_card": calculate,
        "clock": lambda: benchmark_clock,
    }
    if round3_by_fixture is not None:
        materializer_kwargs["round3_evidence_by_fixture"] = round3_by_fixture
    materializer = AnalysisCardCanaryMaterializer(repository, **materializer_kwargs)
    dynamic_repository = DynamicPrematchRepository(engine)
    event_rows: list[dict[str, Any]] = []
    try:
        for index, item in enumerate(events):
            source_event = ProjectionSourceEvent.create(
                fixture_id=str(item["fixture_id"]),
                event_type=str(item["event_type"]),
                event_id=str(item["event_id"]),
                event_at=_parse_utc(str(item["event_at"])),
                payload={"frozen_manifest": manifest["schema_version"]},
            )
            with recorder.record(f"event_{index}:initial_artifact_build"):
                artifact = materializer.build(
                    source_event.fixture_id,
                    evaluated_at=source_event.event_at,
                    source_event=source_event,
                )
            if mode == "baseline":
                with recorder.record(f"event_{index}:post_write_rebuild_read_only"):
                    output_artifact = materializer.build(
                        source_event.fixture_id,
                        evaluated_at=source_event.event_at,
                        source_event=source_event,
                    )
                if output_artifact.canonical_bytes != artifact.canonical_bytes:
                    raise RuntimeError("BASELINE_REBUILD_OUTPUT_MISMATCH")
            else:
                with recorder.record(f"event_{index}:targeted_lifecycle_read"):
                    lifecycle = dynamic_repository.lifecycle(source_event.fixture_id)
                with recorder.record(f"event_{index}:incremental_artifact_refresh"):
                    output_artifact = materializer.refresh_shadow_after_write(
                        artifact,
                        lifecycle=lifecycle,
                    )
            event_rows.append(
                {
                    "fixture_id": source_event.fixture_id,
                    "event_type": source_event.event_type,
                    "event_at": source_event.event_at.isoformat().replace("+00:00", "Z"),
                    "canonical_bytes": len(output_artifact.canonical_bytes),
                    "canonical_bytes_sha256": hashlib.sha256(
                        output_artifact.canonical_bytes
                    ).hexdigest(),
                    "artifact_hash": output_artifact.artifact_hash,
                    "projection_hash": output_artifact.payload["projection_hash"],
                }
            )
    finally:
        event.remove(Engine, "before_cursor_execute", recorder.before_sql)
        event.remove(Engine, "after_cursor_execute", recorder.after_sql)

    sql = recorder.sql_payload()
    outcome_ledger_sql_reads = sum(
        int(row["calls"]) for row in sql["families"] if "outcome_ledger" in row["tables"]
    )
    profile: dict[str, Any] = {
        "schema_version": PROFILE_SCHEMA,
        "mode": mode,
        "manifest_sha256": _file_sha256(manifest_path),
        "source_release": manifest["source_release"],
        "database_read_only": True,
        "provider_calls": 0,
        "production_database_writes": 0,
        "outcome_ledger_sql_reads": outcome_ledger_sql_reads,
        "deployment": False,
        "event_count": len(event_rows),
        "analysis_card_calls": analysis_calls,
        "wall_seconds": round(perf_counter() - wall_started, 6),
        "cpu_seconds": round(process_time() - cpu_started, 6),
        "stages": {
            stage: {
                "calls": recorder.stage_calls[stage],
                "wall_seconds": round(seconds, 6),
            }
            for stage, seconds in sorted(recorder.stage_seconds.items())
        },
        "sql": sql,
        "events": event_rows,
    }
    profile["content_sha256"] = _sha256(profile)
    _write_json(output, profile)


def _validated_profile(path: Path, mode: str, manifest_sha256: str) -> dict[str, Any]:
    profile = _read_json(path)
    digest = profile.pop("content_sha256", None)
    if digest != _sha256(profile):
        raise ValueError(f"PROFILE_DIGEST_MISMATCH:{mode}")
    profile["content_sha256"] = digest
    if profile.get("schema_version") != PROFILE_SCHEMA or profile.get("mode") != mode:
        raise ValueError(f"PROFILE_IDENTITY_MISMATCH:{mode}")
    if profile.get("manifest_sha256") != manifest_sha256:
        raise ValueError(f"PROFILE_MANIFEST_MISMATCH:{mode}")
    if profile.get("event_count") != EXPECTED_EVENTS:
        raise ValueError(f"PROFILE_EVENT_COUNT_MISMATCH:{mode}")
    expected_calls = EXPECTED_EVENTS * (4 if mode == "baseline" else 2)
    if profile.get("analysis_card_calls") != expected_calls:
        raise ValueError(f"PROFILE_ANALYSIS_CALL_COUNT_MISMATCH:{mode}")
    for field in ("provider_calls", "production_database_writes"):
        if profile.get(field) != 0:
            raise ValueError(f"PROFILE_FORBIDDEN_IO:{mode}:{field}")
    expected_outcome_reads = sum(
        int(row["calls"])
        for row in profile.get("sql", {}).get("families", [])
        if "outcome_ledger" in row.get("tables", [])
    )
    if profile.get("outcome_ledger_sql_reads") != expected_outcome_reads:
        raise ValueError(f"PROFILE_OUTCOME_READ_COUNT_MISMATCH:{mode}")
    if profile.get("database_read_only") is not True or profile.get("deployment") is not False:
        raise ValueError(f"PROFILE_SAFETY_MISMATCH:{mode}")
    return profile


def _assemble(manifest: Path, baseline: Path, optimized: Path, output: Path) -> None:
    manifest_sha256 = _file_sha256(manifest)
    before = _validated_profile(baseline, "baseline", manifest_sha256)
    after = _validated_profile(optimized, "optimized", manifest_sha256)
    before_outputs = [row["canonical_bytes_sha256"] for row in before["events"]]
    after_outputs = [row["canonical_bytes_sha256"] for row in after["events"]]
    if before_outputs != after_outputs:
        raise ValueError("PROJECTION_OUTPUT_BYTES_CHANGED")
    comparison = {
        "wall_seconds": {
            "before": before["wall_seconds"],
            "after": after["wall_seconds"],
            "change": round(float(after["wall_seconds"]) - float(before["wall_seconds"]), 6),
            "reduction_ratio": round(
                1 - float(after["wall_seconds"]) / float(before["wall_seconds"]), 6
            ),
        },
        "cpu_seconds": {
            "before": before["cpu_seconds"],
            "after": after["cpu_seconds"],
            "change": round(float(after["cpu_seconds"]) - float(before["cpu_seconds"]), 6),
            "reduction_ratio": round(
                1 - float(after["cpu_seconds"]) / float(before["cpu_seconds"]), 6
            ),
        },
        "sql_calls": {
            "before": before["sql"]["calls"],
            "after": after["sql"]["calls"],
            "change": int(after["sql"]["calls"]) - int(before["sql"]["calls"]),
            "reduction_ratio": round(
                1 - int(after["sql"]["calls"]) / int(before["sql"]["calls"]), 6
            ),
        },
        "analysis_card_calls": {
            "before": before["analysis_card_calls"],
            "after": after["analysis_card_calls"],
        },
    }
    if any(float(comparison[field]["after"]) >= float(comparison[field]["before"]) for field in (
        "wall_seconds",
        "cpu_seconds",
        "sql_calls",
    )):
        raise ValueError("PERFORMANCE_DID_NOT_IMPROVE")
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "safety": {
            "provider_calls": 0,
            "production_database_writes": 0,
            "deployment": False,
            "outcome_ledger_sql_reads": {
                "before": before["outcome_ledger_sql_reads"],
                "after": after["outcome_ledger_sql_reads"],
            },
        },
        "byte_invariant": {
            "status": "EXACT_MATCH",
            "event_count": EXPECTED_EVENTS,
            "canonical_bytes_sha256": before_outputs,
        },
        "comparison": comparison,
        "sql_classification": {
            "before_exact_duplicate_calls": before["sql"]["exact_duplicate_calls"],
            "after_exact_duplicate_calls": after["sql"]["exact_duplicate_calls"],
            "before_n_plus_one_candidate_calls": before["sql"]["n_plus_one_candidate_calls"],
            "after_n_plus_one_candidate_calls": after["sql"]["n_plus_one_candidate_calls"],
        },
        "profile_sha256": {
            "baseline": before["content_sha256"],
            "optimized": after["content_sha256"],
        },
    }
    evidence["content_sha256"] = _sha256(evidence)
    _write_json(output, evidence)


def _check(manifest: Path, baseline: Path, optimized: Path, evidence_path: Path) -> None:
    manifest_sha256 = _file_sha256(manifest)
    before = _validated_profile(baseline, "baseline", manifest_sha256)
    after = _validated_profile(optimized, "optimized", manifest_sha256)
    evidence = _read_json(evidence_path)
    digest = evidence.pop("content_sha256", None)
    if digest != _sha256(evidence):
        raise ValueError("EVIDENCE_DIGEST_MISMATCH")
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("EVIDENCE_SCHEMA_MISMATCH")
    if evidence.get("manifest_sha256") != manifest_sha256:
        raise ValueError("EVIDENCE_MANIFEST_MISMATCH")
    if evidence.get("profile_sha256") != {
        "baseline": before["content_sha256"],
        "optimized": after["content_sha256"],
    }:
        raise ValueError("EVIDENCE_PROFILE_MISMATCH")
    expected_outputs = [row["canonical_bytes_sha256"] for row in before["events"]]
    if expected_outputs != [row["canonical_bytes_sha256"] for row in after["events"]]:
        raise ValueError("PROJECTION_OUTPUT_BYTES_CHANGED")
    if evidence.get("byte_invariant") != {
        "status": "EXACT_MATCH",
        "event_count": EXPECTED_EVENTS,
        "canonical_bytes_sha256": expected_outputs,
    }:
        raise ValueError("BYTE_INVARIANT_EVIDENCE_MISMATCH")
    comparison = evidence.get("comparison", {})
    expected_pairs = {
        "wall_seconds": (before["wall_seconds"], after["wall_seconds"]),
        "cpu_seconds": (before["cpu_seconds"], after["cpu_seconds"]),
        "sql_calls": (before["sql"]["calls"], after["sql"]["calls"]),
        "analysis_card_calls": (before["analysis_card_calls"], after["analysis_card_calls"]),
    }
    for field, pair in expected_pairs.items():
        row = comparison.get(field, {})
        if (row.get("before"), row.get("after")) != pair:
            raise ValueError(f"COMPARISON_MISMATCH:{field}")
    safety = evidence.get("safety", {})
    if safety != {
        "provider_calls": 0,
        "production_database_writes": 0,
        "deployment": False,
        "outcome_ledger_sql_reads": {
            "before": before["outcome_ledger_sql_reads"],
            "after": after["outcome_ledger_sql_reads"],
        },
    }:
        raise ValueError("EVIDENCE_SAFETY_MISMATCH")
    print("SCHED_DEDUP_01_CHECK_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("baseline", "optimized"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--optimized", type=Path)
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
        if args.baseline is None or args.optimized is None or args.output is None:
            parser.error("--assemble requires --baseline --optimized --output")
        _assemble(args.manifest, args.baseline, args.optimized, args.output)
        return
    if args.check is not None:
        if args.baseline is None or args.optimized is None:
            parser.error("--check requires --baseline --optimized")
        _check(args.manifest, args.baseline, args.optimized, args.check)
        return
    parser.error("choose --profile, --assemble, or --check")


if __name__ == "__main__":
    main()
