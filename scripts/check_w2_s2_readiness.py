from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a W2 S2 readiness report.")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    errors: list[str] = []
    if "data_source" not in payload:
        errors.append("missing data_source")
    if "authoritative" not in payload:
        errors.append("missing authoritative")
    if payload.get("beats_market") is not False:
        errors.append("beats_market must remain false")
    if payload.get("formal_enabled") is not False:
        errors.append("formal_enabled must remain false")
    if payload.get("candidate_enabled") is not False:
        errors.append("candidate_enabled must remain false")
    data_source = str(payload.get("data_source") or "")
    if ("fixtures/stage5_demo" in data_source or "stage5_demo" in data_source) and (
        payload.get("authoritative") is not False
    ):
        errors.append("stage5 demo reports must be non-authoritative")
    if payload.get("authoritative") is False:
        gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
        if gate.get("beats_market") is not False:
            errors.append("non-authoritative report cannot drive beats_market")
        if payload.get("dashboard_publishable") is not False:
            errors.append("non-authoritative report cannot enter dashboard")
        if payload.get("card_publishable") is not False:
            errors.append("non-authoritative report cannot enter cards")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("s2 readiness report PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
