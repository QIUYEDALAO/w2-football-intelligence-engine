#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from w2.historical.formal_ah import audit_formal_ah_sources, write_audit_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit formal AH historical source eligibility.")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = audit_formal_ah_sources(source_root=args.source_root, registry_path=args.registry)
    json_path = args.output
    md_path = args.output.with_suffix(".md")
    write_audit_outputs(payload, json_path=json_path, md_path=md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
