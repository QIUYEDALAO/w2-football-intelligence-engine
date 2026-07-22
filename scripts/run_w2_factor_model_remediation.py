#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from w2.factor_model.remediation import (
    FactorModelRemediationConfig,
    FactorModelRemediationService,
    write_remediation_artifacts,
    write_team_identity_authority_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run W2 factor-model remediation with provider-primary team identity."
    )
    parser.add_argument("--competition-id", default="allsvenskan")
    parser.add_argument("--provider-league-id", default="113")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--recent-match-count", type=int, default=5)
    parser.add_argument("--request-budget", type=int, default=100)
    parser.add_argument("--output-dir", default="docs/operations/factor_model_remediation")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call API-Football through request_live(); omitted means seed/report only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = FactorModelRemediationConfig(
        competition_id=args.competition_id,
        provider_league_id=args.provider_league_id,
        season=args.season,
        recent_match_count=args.recent_match_count,
        request_budget=args.request_budget,
        source_revision=os.environ.get("W2_SERVICE_VERSION", "LOCAL_UNDEPLOYED"),
        output_dir=Path(args.output_dir),
    )
    service = FactorModelRemediationService(
        config=config,
        now=datetime.now(UTC),
    )
    result = service.run_controlled_provider_capture(live=bool(args.live))
    write_remediation_artifacts(result, output_dir=config.output_dir)
    write_team_identity_authority_artifacts(
        service.team_identity_authority_payload(),
        output_dir=config.output_dir,
    )
    print(f"final_state={result.as_dict()['final_state']}")
    print(f"provider_call_count={result.provider_call_count}")
    print(f"canonical_team_count={result.canonical_team_count}")
    print(f"fixture_identity_ready_count={result.fixture_identity_ready_count}")
    print(f"canonical_history_rows={result.canonical_history_rows}")
    print(f"rating_snapshot_count={result.rating_snapshot_count}")
    print(f"xg_status={result.xg_status}")
    print(f"report={config.output_dir / 'W2_FACTOR_MODEL_REMEDIATION_RESULT_V1.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
