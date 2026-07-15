from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.tracking.ah_evidence_review import build_ah_evidence_review
from w2.tracking.forward_ledger_performance import forward_ledger_performance


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the read-only W2 AH evidence review")
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime"))
    args = parser.parse_args()
    performance = forward_ledger_performance(args.runtime_root)
    report = performance.get("ah_evidence_review") or build_ah_evidence_review([])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
