#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ingestion_models import ProviderRequestLogModel
from w2.infrastructure.persistence.models import (
    PlayerIdentityMappingModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.providers.api_football import ApiFootballClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual bounded ARCH-P1-03B player-profile canary."
    )
    parser.add_argument("--fixture", action="append", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--max-calls", required=True, type=int)
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("--live is required for the explicitly authorized one-shot")

    repository = FutureRefreshDbRepository()
    fixtures = list(dict.fromkeys(str(value) for value in args.fixture if str(value)))
    targets: dict[str, str] = {}
    with Session(repository.engine) as session:
        snapshots = list(
            session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(StructuredLineupSnapshotModel.fixture_id.in_(fixtures))
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            )
        )
        latest: dict[tuple[str, str], StructuredLineupSnapshotModel] = {}
        for snapshot in snapshots:
            latest.setdefault((snapshot.fixture_id, snapshot.team_external_id), snapshot)
        for snapshot in latest.values():
            players = list(
                session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id,
                        StructuredLineupPlayerModel.starter.is_(True),
                    )
                )
            )
            for player in players:
                mapping = session.scalar(
                    select(PlayerIdentityMappingModel)
                    .where(
                        PlayerIdentityMappingModel.api_football_player_id
                        == player.api_football_player_id,
                        PlayerIdentityMappingModel.team_external_id
                        == snapshot.team_external_id,
                    )
                    .order_by(PlayerIdentityMappingModel.valid_from.desc())
                    .limit(1)
                )
                if mapping is not None and mapping.mapping_status == "CANDIDATE":
                    continue
                prior_team = targets.setdefault(
                    player.api_football_player_id,
                    snapshot.team_external_id,
                )
                if prior_team != snapshot.team_external_id:
                    raise SystemExit(
                        f"player {player.api_football_player_id} has multiple target teams"
                    )
    if not targets or len(targets) > args.max_calls:
        raise SystemExit(
            f"target count {len(targets)} must be between 1 and --max-calls"
        )

    endpoint = "player_profiles" if args.profiles else "players"
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({endpoint}),
    )
    started_at = datetime.now(UTC)
    actual_calls = 0
    raw_payloads = 0
    failures: list[dict[str, str]] = []
    for player_id, team_id in sorted(targets.items()):
        actual_calls += 1
        try:
            params = (
                {"player": player_id}
                if args.profiles
                else {"id": player_id, "season": str(args.season)}
            )
            response = client.request_live(endpoint, params)
        except Exception as exc:  # ledger records the bounded transport failure first
            failures.append({"player_id": player_id, "error_type": type(exc).__name__})
            continue
        stored_payload = {
            **response.payload,
            "endpoint": endpoint,
            "parameters": params,
            "w2_scope": {"expected_team_id": team_id, "fixture_ids": fixtures},
        }
        source_sha256 = hashlib.sha256(
            json.dumps(
                stored_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        repository.save_raw_payload(
            sha256=source_sha256,
            endpoint=endpoint,
            captured_at=response.captured_at,
            payload=stored_payload,
        )
        raw_payloads += 1

    with Session(repository.engine) as session:
        ledger_rows = list(
            session.scalars(
                select(ProviderRequestLogModel).where(
                    ProviderRequestLogModel.provider == "api_football",
                    ProviderRequestLogModel.endpoint == endpoint,
                    ProviderRequestLogModel.requested_at >= started_at,
                )
            )
        )
    success_rows = sum(
        row.error is None and row.status_code is not None and row.status_code < 400
        for row in ledger_rows
    )
    failure_rows = len(ledger_rows) - success_rows
    equation_passed = actual_calls == success_rows + failure_rows
    print(
        json.dumps(
            {
                "schema_version": "w2.arch_p1_03b_player_profiles.v1",
                "fixture_ids": fixtures,
                "target_player_count": len(targets),
                "actual_calls": actual_calls,
                "success_ledger_rows": success_rows,
                "failure_ledger_rows": failure_rows,
                "ledger_equation_passed": equation_passed,
                "raw_payloads_written": raw_payloads,
                "failures": failures,
                "scheduler_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if equation_passed and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
