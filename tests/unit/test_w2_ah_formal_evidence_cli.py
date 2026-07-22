from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_ah_formal_evidence_cli_writes_machine_readable_report(tmp_path: Path) -> None:
    source = tmp_path / "evidence.jsonl"
    source.write_text("", encoding="utf-8")
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_ah_formal_evidence.py",
            "--input-jsonl",
            str(source),
            "--protocol-json",
            "config/evaluations/ah_formal_evidence.v1.json",
            "--data-source",
            "empty-frozen-export",
            "--output-report",
            str(report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload == json.loads(report.read_text(encoding="utf-8"))
    assert payload["conclusion"] == "INSUFFICIENT_EVIDENCE"
    assert payload["frozen_input_sha256"]
    assert payload["formal_ah_enabled"] is False


def test_frozen_v3_07_report_is_reproducible(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_ah_formal_evidence.py",
            "--input-jsonl",
            "docs/operations/W2_V3_07_AH_FORMAL_EVIDENCE_INPUT_20260720.json",
            "--protocol-json",
            "config/evaluations/ah_formal_evidence.v1.json",
            "--data-source",
            "V3-00-frozen-canonical-cohort",
            "--output-report",
            str(report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    frozen = Path("docs/operations/W2_V3_07_AH_FORMAL_EVIDENCE_20260720.json")
    assert result.stdout == frozen.read_text(encoding="utf-8")
    assert report.read_text(encoding="utf-8") == result.stdout
