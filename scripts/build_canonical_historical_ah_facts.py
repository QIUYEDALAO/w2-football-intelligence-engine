#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.historical.formal_ah import build_canonical_ah_facts, write_audit_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline canonical historical AH facts.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--facts-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    result = build_canonical_ah_facts(source_root=args.source_root, registry_path=args.registry)
    args.facts_output.parent.mkdir(parents=True, exist_ok=True)
    args.facts_output.write_text(
        json.dumps(result["facts"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_audit_outputs(
        result["audit"],
        json_path=args.audit_output,
        md_path=args.audit_output.with_suffix(".md"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
