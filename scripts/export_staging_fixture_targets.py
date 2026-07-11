from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from w2.features.offline_materialization import sanitized_target_fixture_payload
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

TMP_ROOT = Path("/tmp").resolve()  # noqa: S108 - deliberate non-repository export boundary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sanitized staging fixture targets")
    parser.add_argument("--kickoff-from", type=_datetime, required=True)
    parser.add_argument("--kickoff-to", type=_datetime, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    args = parser.parse_args()
    if os.getenv("W2_ENVIRONMENT", "").casefold() != "staging":
        raise SystemExit("STAGING_ENVIRONMENT_REQUIRED")
    out_file = args.out_file.resolve()
    if not out_file.is_relative_to(TMP_ROOT):
        raise SystemExit("OUT_FILE_MUST_BE_UNDER_TMP")
    payload = sanitized_target_fixture_payload(
        FutureRefreshDbRepository().fixture_payloads(),
        kickoff_from=args.kickoff_from,
        kickoff_to=args.kickoff_to,
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "fixture_count": len(payload["fixtures"]),
                "content_hash": payload["content_hash"],
                "out_file": str(out_file),
                "provider_calls": 0,
                "db_writes": 0,
            },
            sort_keys=True,
        )
    )
    return 0


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
