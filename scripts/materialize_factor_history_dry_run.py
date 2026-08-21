#!/usr/bin/env python3
"""Build the Gate 1 factor-history corpus from persisted fixture raw JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.history import (
    API_FOOTBALL_TEAM_ID_NAMESPACE,
    RAW_HISTORY_CORPUS_SCHEMA_VERSION,
    materialize_factor_history_from_persisted_raw,
)
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIRS = (
    ROOT / "config/competitions/top_five",
    ROOT / "config/competitions/national_leagues",
)
METRICS = (
    "selected_fixture_count",
    "eligible_finished_fixture_count",
    "history_row_count",
    "identity_missing_fixture_count",
    "unfinished_fixture_count",
    "result_missing_fixture_count",
    "late_result_fixture_count",
    "conflict_fixture_count",
    "out_of_window_fixture_count",
)
PIT_REASONS = {
    "IDENTITY_MISSING_AT_LATEST_VISIBLE_CAPTURE": "identity_missing_fixture_count",
    "LATEST_VISIBLE_CAPTURE_CONFLICT": "conflict_fixture_count",
    "KICKOFF_OUTSIDE_HALF_OPEN_HISTORY_WINDOW": "out_of_window_fixture_count",
    "LATEST_VISIBLE_STATUS_NOT_FINISHED": "unfinished_fixture_count",
    "LATEST_VISIBLE_TERMINAL_RESULT_MISSING": "result_missing_fixture_count",
}


class _RawRepository:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        if endpoint != "fixtures":
            raise ValueError(f"UNEXPECTED_RAW_ENDPOINT:{endpoint}")
        return self.rows


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("DATETIME_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(UTC)


def _hash(identity_type: str, payload: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **payload},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _profiles() -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    for path in sorted(file for directory in PROFILE_DIRS for file in directory.glob("*.v1.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        competition_id = str(payload.get("competition_id") or "")
        if competition_id not in REQUIRED_MATCHDAY_COMPETITIONS:
            continue
        league_id = str((payload.get("provider_mapping") or {}).get("api_football_league_id") or "")
        if not league_id:
            raise ValueError(f"PROVIDER_LEAGUE_ID_MISSING:{competition_id}")
        profiles.append({"competition_id": competition_id, "provider_league_id": league_id})
    if {row["competition_id"] for row in profiles} != set(REQUIRED_MATCHDAY_COMPETITIONS):
        raise ValueError("EXACT_13_COMPETITION_SCOPE_MISMATCH")
    if len({row["provider_league_id"] for row in profiles}) != len(profiles):
        raise ValueError("EXACT_13_PROVIDER_LEAGUE_ID_CONFLICT")
    return sorted(profiles, key=lambda row: row["competition_id"])


def read_jsonl(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in lines if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("RAW_JSONL_ROW_INVALID")
    return rows


def build_report(
    raw_rows: list[dict[str, Any]],
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    as_of: datetime,
    seasons: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    batch = materialize_factor_history_from_persisted_raw(
        _RawRepository(raw_rows),
        kickoff_from=kickoff_from,
        kickoff_to=kickoff_to,
        as_of=as_of,
    )
    profiles = _profiles()
    scopes = {
        (row["provider_league_id"], season): row["competition_id"]
        for row in profiles
        for season in seasons
    }
    source_scope = {
        (str(row["provider_league_id"]), str(row["season"])): row
        for row in batch.coverage_report["by_league_season"]
    }
    by_scope: list[dict[str, Any]] = []
    for (league_id, season), competition_id in sorted(
        scopes.items(), key=lambda item: (item[1], item[0][1])
    ):
        source = source_scope.get((league_id, season), {})
        counts = {metric: int(source.get(metric, 0)) for metric in METRICS}
        by_scope.append(
            {
                "competition_id": competition_id,
                "provider_league_id": league_id,
                "season": season,
                **counts,
                "point_in_time_exclusion_reasons": {
                    reason: counts[metric] for reason, metric in PIT_REASONS.items()
                },
            }
        )

    history_rows = [
        row
        for row in batch.history_rows
        if (str(row["provider_league_id"]), str(row["season"])) in scopes
    ]
    corpus_body = {
        "schema_version": RAW_HISTORY_CORPUS_SCHEMA_VERSION,
        "provider": "api_football",
        "team_identity_namespace": API_FOOTBALL_TEAM_ID_NAMESPACE,
        "snapshot_as_of": as_of,
        "kickoff_from": kickoff_from,
        "kickoff_to": min(kickoff_to, as_of),
        "seasons": list(seasons),
        "history_rows": history_rows,
    }
    corpus = {
        **corpus_body,
        "corpus_sha256": _hash("FACTOR_MODEL_GATE1_RAW_HISTORY_CORPUS", corpus_body),
    }
    totals = {metric: sum(int(row[metric]) for row in by_scope) for metric in METRICS}
    input_totals = dict(batch.coverage_report["totals"])
    report_body = {
        "schema_version": "w2.factor_model.gate1_history_dry_run.v1",
        "source": {
            "provider": "api_football",
            "database_table": "raw_payload",
            "endpoint": "fixtures",
            "snapshot_as_of": as_of,
            "raw_payload_count": len(raw_rows),
            "raw_payload_sha256_set_hash": _hash(
                "FACTOR_MODEL_GATE1_RAW_PAYLOAD_SET",
                {"sha256": sorted(str(row.get("sha256") or "") for row in raw_rows)},
            ),
        },
        "scope": {
            "competition_count": len(profiles),
            "league_season_count": len(scopes),
            "seasons": list(seasons),
            "kickoff_from": kickoff_from,
            "kickoff_to": min(kickoff_to, as_of),
        },
        "contracts": {
            "selection_policy": "LATEST_RAW_CAPTURE_STRICTLY_BEFORE_FEATURE_AS_OF",
            "team_identity_namespace": API_FOOTBALL_TEAM_ID_NAMESPACE,
            "provider_calls": 0,
            "database_writes": 0,
            "split_frozen": False,
            "training_executed": False,
            "deployment_executed": False,
        },
        "corpus": {
            "eligible_finished_fixture_count": totals["eligible_finished_fixture_count"],
            "history_row_count": len(history_rows),
            "corpus_sha256": corpus["corpus_sha256"],
        },
        "totals": totals,
        "input_diagnostics": {
            key: int(input_totals.get(key, 0))
            for key in (
                "malformed_raw_payload_count",
                "malformed_fixture_item_count",
                "identity_missing_item_count",
                "not_known_at_as_of_fixture_count",
                "equivalent_latest_duplicate_count",
            )
        },
        "point_in_time_exclusion_reasons": {
            reason: totals[metric] for reason, metric in PIT_REASONS.items()
        }
        | {
            "NO_RAW_CAPTURE_STRICTLY_BEFORE_AS_OF": int(
                input_totals.get("not_known_at_as_of_fixture_count", 0)
            )
        },
        "by_league_season": by_scope,
    }
    return corpus, {
        **report_body,
        "report_sha256": _hash("FACTOR_MODEL_GATE1_HISTORY_DRY_RUN", report_body),
    }


def _json(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise TypeError(f"JSON_VALUE_UNSUPPORTED:{type(value).__name__}")


def _markdown(report: Mapping[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "# Gate 1 saved-raw 历史物化 dry-run",
        "",
        f"- Snapshot as-of: `{report['source']['snapshot_as_of']}`",
        f"- Scope: `{report['scope']['competition_count']}` leagues × "
        f"`{len(report['scope']['seasons'])}` seasons = "
        f"`{report['scope']['league_season_count']}`",
        f"- Eligible fixtures/history rows: "
        f"`{totals['eligible_finished_fixture_count']}` / "
        f"`{report['corpus']['history_row_count']}`",
        "- Provider calls / database writes / split / training / deployment: "
        "`0 / 0 / false / false / false`",
        "",
        "| competition | season | selected | eligible | identity missing | unfinished | "
        "result missing | >36h late | conflict | PIT out-of-window |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["by_league_season"]:
        lines.append(
            f"| {row['competition_id']} | {row['season']} | "
            f"{row['selected_fixture_count']} | {row['eligible_finished_fixture_count']} | "
            f"{row['identity_missing_fixture_count']} | {row['unfinished_fixture_count']} | "
            f"{row['result_missing_fixture_count']} | {row['late_result_fixture_count']} | "
            f"{row['conflict_fixture_count']} | {row['out_of_window_fixture_count']} |"
        )
    lines.extend(("", "## Point-in-time exclusions", ""))
    for reason, count in report["point_in_time_exclusion_reasons"].items():
        lines.append(f"- `{reason}`: `{count}`")
    return "\n".join(lines) + "\n"


def write_artifacts(output_dir: Path, corpus: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "factor_history_corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2, sort_keys=True, default=_json) + "\n",
        encoding="utf-8",
    )
    (output_dir / "factor_history_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json) + "\n",
        encoding="utf-8",
    )
    (output_dir / "factor_history_coverage.md").write_text(
        _markdown(report), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--kickoff-from", default="2024-01-01T00:00:00Z")
    parser.add_argument("--kickoff-to", default="2027-01-01T00:00:00Z")
    parser.add_argument("--seasons", default="2024,2025,2026")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    seasons = tuple(value.strip() for value in args.seasons.split(",") if value.strip())
    corpus, report = build_report(
        read_jsonl(sys.stdin),
        kickoff_from=_utc(args.kickoff_from),
        kickoff_to=_utc(args.kickoff_to),
        as_of=_utc(args.as_of),
        seasons=seasons,
    )
    write_artifacts(args.output_dir, corpus, report)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "eligible_finished_fixture_count": report["corpus"][
                    "eligible_finished_fixture_count"
                ],
                "history_row_count": report["corpus"]["history_row_count"],
                "report_sha256": report["report_sha256"],
                "provider_calls": 0,
                "database_writes": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
