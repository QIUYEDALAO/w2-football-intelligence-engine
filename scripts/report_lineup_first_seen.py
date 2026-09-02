from __future__ import annotations

import json

from w2.ingestion.lineup_first_seen import LineupFirstSeenRepository


def main() -> int:
    print(
        json.dumps(
            LineupFirstSeenRepository().distribution_summary(),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
