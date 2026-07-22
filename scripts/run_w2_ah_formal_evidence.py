from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.ah_formal_evidence import (  # noqa: E402
    AhFormalEvidenceProtocol,
    evaluate_ah_formal_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate frozen AH formal evidence offline.")
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--protocol-json", type=Path, required=True)
    parser.add_argument("--data-source", required=True)
    parser.add_argument("--output-report", type=Path)
    args = parser.parse_args()
    protocol_data = json.loads(args.protocol_json.read_text(encoding="utf-8"))
    protocol = AhFormalEvidenceProtocol(**protocol_data["protocol"])
    rows = _read_rows(args.input_jsonl)
    report = evaluate_ah_formal_evidence(rows, protocol=protocol, data_source=args.data_source)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output_report is not None:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            return [row for row in payload["records"] if isinstance(row, dict)]
        raise ValueError("AH evidence JSON input must contain a records list")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("AH evidence JSONL rows must be objects")
            rows.append(payload)
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
