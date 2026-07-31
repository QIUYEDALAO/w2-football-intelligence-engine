#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/scripts/run_predeploy_e2e_smoke.sh"

python3 - "${TARGET}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
required = 'assert event_types == {"FIXTURE_CHANGED", "LINEUP_CHANGED", "ODDS_CHANGED"}'
if required not in source:
    raise SystemExit(
        "C9_PREDEPLOY_REQUIRED_EVENT_SET_MISSING: "
        "the strict FIXTURE_CHANGED/LINEUP_CHANGED/ODDS_CHANGED assertion must not be weakened"
    )
print("c9_predeploy_event_contract PASS")
PY
