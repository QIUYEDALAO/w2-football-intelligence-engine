from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from w2.tracking.finished_match_scoring_projection import (
    WRITE_CONFIRMATION_PHRASE,
    run_finished_match_scoring_projection,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project finished-match scoring into read_model_checkpoint."
    )
    parser.add_argument("--fixture-id", action="append")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.write_db and args.dry_run:
        parser.error("--write-db requires --no-dry-run")
    if args.write_db and args.confirm_write != WRITE_CONFIRMATION_PHRASE:
        parser.error(f"--confirm-write {WRITE_CONFIRMATION_PHRASE} is required")
    payload = run_finished_match_scoring_projection(
        fixture_ids=args.fixture_id,
        dry_run=args.dry_run,
        write_db=args.write_db,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "status={status} finished={finished_result_count} "
            "fixture_checkpoints={fixture_checkpoint_count} "
            "cohort_checkpoints={cohort_checkpoint_count} scored={scored_count} "
            "not_scorable={not_scorable_count} blocked={blocked_count} "
            "db_writes={db_writes} provider_calls={provider_calls}".format(**payload)
        )
    return 0 if payload["status"] in {"PASS", "NO_DUE_WORK"} else 1
