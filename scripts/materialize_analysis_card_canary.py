from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import cast

from w2.api.repository import ReadModelRepository, ReadModelService
from w2.infrastructure.database import create_engine
from w2.prematch.read_model_projection import (
    MAX_PUBLIC_FIXTURES,
    AnalysisCardCanaryMaterializer,
    FrozenAnalysisError,
    ScopedAnalysisRepository,
    write_frozen_analysis_artifacts,
)

CANARY_FIXTURES = ("1576804", "1494701", "1494210")


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--evaluated-at must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize deterministic frozen analysis-card artifacts."
    )
    parser.add_argument("--fixture-id", action="append", dest="fixture_ids")
    parser.add_argument(
        "--all-public",
        action="store_true",
        help="Materialize the bounded public fixture inventory.",
    )
    parser.add_argument("--evaluated-at", required=True, type=parse_datetime)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.all_public and args.fixture_ids:
        parser.error("--all-public and --fixture-id are mutually exclusive")
    repository = ReadModelRepository()
    if args.all_public:
        fixture_ids = tuple(
            dict.fromkeys(
                str(payload.get("fixture", {}).get("id") or "")
                for payload in repository.public_fixture_payloads(limit=MAX_PUBLIC_FIXTURES)
                if payload.get("fixture", {}).get("id")
            )
        )
    else:
        fixture_ids = tuple(args.fixture_ids or CANARY_FIXTURES)
    def calculate_analysis_card(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, object] | None:
        return ReadModelService(
            repository=cast(ReadModelRepository, scoped_repository)
        ).public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    materializer = AnalysisCardCanaryMaterializer(
        repository,
        calculate_analysis_card=calculate_analysis_card,
    )
    artifacts = []
    unavailable = []
    for fixture_id in fixture_ids:
        try:
            artifacts.append(
                materializer.build(fixture_id, evaluated_at=args.evaluated_at)
            )
        except FrozenAnalysisError as exc:
            if not args.all_public:
                raise
            unavailable.append({"fixture_id": fixture_id, "reason": str(exc)})
    if args.write:
        write_frozen_analysis_artifacts(create_engine(), artifacts)
    print(
        json.dumps(
            {
                "status": "MATERIALIZED" if args.write else "DRY_RUN",
                "requested_fixture_count": len(fixture_ids),
                "materialized_fixture_count": len(artifacts),
                "unavailable_fixture_count": len(unavailable),
                "unavailable": unavailable,
                "schema_versions": sorted(
                    {str(artifact.payload["schema_version"]) for artifact in artifacts}
                ),
                "artifacts": [
                    {
                        "fixture_id": fixture_id,
                        "checkpoint_key": artifact.checkpoint_key,
                        "source_hash": artifact.source_hash,
                        "artifact_hash": artifact.artifact_hash,
                    }
                    for artifact in artifacts
                    for fixture_id in [
                        str(artifact.payload["fixture_identity"]["fixture_id"])
                    ]
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
