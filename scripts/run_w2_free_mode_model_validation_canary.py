from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.tracking.model_validation_canary import (
    CANARY_TERMINAL,
    free_mode_model_validation_canary,
    write_pro_reopen_owner_decision_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-packet", type=Path)
    args = parser.parse_args()
    report = free_mode_model_validation_canary()
    if args.owner_packet is not None:
        write_pro_reopen_owner_decision_packet(args.owner_packet, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report.get("status") == CANARY_TERMINAL else 2


if __name__ == "__main__":
    raise SystemExit(main())
