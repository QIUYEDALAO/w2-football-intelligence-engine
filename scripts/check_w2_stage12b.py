from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/W2_STAGE12B_W1_W2_COMPARISON.json"


def main() -> None:
    if not REPORT.exists():
        raise SystemExit("missing Stage12B comparison report")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    if payload.get("mode") != "READ_ONLY_NO_W1_RUNTIME_IMPORT":
        raise SystemExit("Stage12B mode must be W1 read-only")
    if payload.get("w1_modified") is not False:
        raise SystemExit("Stage12B must not modify W1")
    for base in (ROOT / "scripts", ROOT / "src"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = getattr(node, "module", "") or ""
                    names = [alias.name for alias in getattr(node, "names", [])]
                    if module.startswith("w1") or any(name.startswith("w1") for name in names):
                        raise SystemExit(f"W1 runtime import detected in {path}")
    print("W2 Stage12B check PASS")


if __name__ == "__main__":
    main()
