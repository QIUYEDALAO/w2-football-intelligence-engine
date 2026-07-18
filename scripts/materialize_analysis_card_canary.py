from __future__ import annotations

import argparse
import json
from datetime import datetime

from w2.api.frozen_analysis import (
    AnalysisCardCanaryMaterializer,
    write_frozen_analysis_artifacts,
)
from w2.api.repository import ReadModelRepository
from w2.infrastructure.database import create_engine

CANARY_FIXTURES = ("1576804", "1494701", "1494210")


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--evaluated-at must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize deterministic analysis-card canaries."
    )
    parser.add_argument("--fixture-id", action="append", dest="fixture_ids")
    parser.add_argument("--evaluated-at", required=True, type=parse_datetime)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    fixture_ids = tuple(args.fixture_ids or CANARY_FIXTURES)
    materializer = AnalysisCardCanaryMaterializer(ReadModelRepository())
    artifacts = [
        materializer.build(fixture_id, evaluated_at=args.evaluated_at) for fixture_id in fixture_ids
    ]
    if args.write:
        write_frozen_analysis_artifacts(create_engine(), artifacts)
    print(
        json.dumps(
            {
                "status": "MATERIALIZED" if args.write else "DRY_RUN",
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
                    for fixture_id, artifact in zip(fixture_ids, artifacts, strict=True)
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
