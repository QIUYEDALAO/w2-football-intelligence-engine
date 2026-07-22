from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from w2.operations.release_evidence import build_release_gate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a verified W2 release-gate manifest.")
    parser.add_argument("--gate-results", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.gate_results.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("gate results must be a JSON list")
    manifest = build_release_gate_manifest(
        cast(list[dict[str, Any]], payload), evidence_root=args.evidence_root
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = manifest.model_dump_json(indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=args.output.parent, delete=False
    ) as stream:
        stream.write(serialized)
        temporary = Path(stream.name)
    os.replace(temporary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
