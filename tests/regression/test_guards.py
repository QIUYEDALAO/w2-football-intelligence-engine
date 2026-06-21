from __future__ import annotations

from pathlib import Path

from tests.secret_scan import scan

ROOT = Path(__file__).resolve().parents[2]


def test_secret_patterns_are_guarded() -> None:
    assert scan() == []


def test_no_w1_or_legacy_runtime_path_dependency() -> None:
    forbidden = ["/w1_world_cup_engine", "/v2_football_quant/.env", "Football-API"]
    scanned = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or ".venv" in path.parts
            or path.suffix in {".pyc", ".db"}
        ):
            continue
        if path.parts[-1] == "README.md" or "docs" in path.parts or "reports" in path.parts:
            continue
        if path.as_posix().endswith("scripts/check_w2_stage1_contracts.py"):
            continue
        if path.as_posix().endswith("scripts/check_w2_stage3_data_model.py"):
            continue
        if path.as_posix().endswith("tests/regression/test_guards.py"):
            continue
        if path.as_posix().endswith("tests/secret_scan.py"):
            continue
        if path.as_posix().endswith("tests/unit/test_config.py"):
            continue
        if path.as_posix().endswith("src/w2/config.py"):
            continue
        scanned.append((path, path.read_text(encoding="utf-8", errors="ignore")))
    offenders = [
        f"{path.relative_to(ROOT)}:{needle}"
        for path, text in scanned
        for needle in forbidden
        if needle in text
        and path.name not in {"W2_STAGE2_RESULT.md", "SECRETS_AND_ENVIRONMENTS.md"}
    ]
    assert offenders == []


def test_scripts_do_not_contain_core_business_logic() -> None:
    forbidden_terms = [
        "candidate scoring",
        "recommendation engine",
        "market model",
        "football entity",
    ]
    offenders = []
    for path in (ROOT / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in forbidden_terms:
            if term in text:
                offenders.append(f"{path.name}:{term}")
    assert offenders == []
