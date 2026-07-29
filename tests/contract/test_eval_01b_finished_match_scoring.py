from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = (
    ROOT
    / "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)


def test_scoring_is_write_side_checkpoint_projection_without_new_table() -> None:
    source = (
        ROOT / "src/w2/tracking/finished_match_scoring_projection.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    table_names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "__tablename__"
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    }

    assert table_names == set()
    assert "ReadModelCheckpointModel" in source
    assert "performance:fixture:" in source
    assert "performance:cohort:" in source
    assert not list((ROOT / "migrations/versions").glob("*eval_01b*"))


def test_api_and_web_do_not_import_or_recompute_scoring() -> None:
    for root in (ROOT / "src/w2/api", ROOT / "apps/web"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert "finished_match_scoring_projection" not in text
            assert "model_minus_market_log_loss" not in text


def test_eval_01b_authority_status_and_safety_contract() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")
    section = checklist[
        checklist.index("#### B2. EVAL-01B") : checklist.index("#### B3.")
    ]
    state = yaml.safe_load((ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"))

    assert "B2_RESULT_AUTHORITY = results" in section
    assert (
        "B2_1X2_PROBABILITY_AUTHORITY = "
        "outcome_ledger.capture.probability_identity"
    ) in section
    assert (
        "B2_DYNAMIC_EVALUATION_ROLE = AH_OU_LIFECYCLE_METADATA_ONLY" in section
    )
    assert "B2_SCORING_TABLE_COUNT = 0" in section
    assert "- [ ] PR 合并。" in section
    assert state["current_task"] == "EVAL-01B"
    assert (
        state["current_status"]
        == "IMPLEMENTED_PENDING_SECONDARY_REVIEW_AND_STAGING"
    )
    assert state["current_pr"] == 430
    assert state["next_task"] == "EVAL-01C"
    assert (
        state["tasks"]["EVAL-01B"]["status"]
        == "IMPLEMENTED_PENDING_SECONDARY_REVIEW_AND_STAGING"
    )
    assert state["tasks"]["EVAL-01B"]["blockers"] == [
        "OUTCOME_LEDGER_ENVELOPE_PAYLOAD_PARITY_REQUIRED",
        "LATEST_GROUP_MISSING_IDENTITY_MASKS_REAL_CONFLICT",
        "STAGING_FAIL_CLOSED_REMEDIATION_REQUIRED",
    ]
    assert (
        state["staging"]["eval_01b_exact_head_acceptance"]
        == "STAGING_FAIL_CLOSED_REMEDIATION_REQUIRED"
    )
    assert state["tasks"]["EVAL-01C"]["status"] == "NOT_STARTED"
    assert state["safety"]["provider_calls"] == 0
    assert state["safety"]["scheduler_started"] is False
    assert state["safety"]["production_started"] is False


def test_cli_requires_explicit_write_confirmation_and_has_no_provider_import() -> None:
    source = (
        ROOT / "src/w2/tracking/finished_match_scoring_cli.py"
    ).read_text(encoding="utf-8")
    wrapper = (
        ROOT / "scripts/run_w2_finished_match_scoring_projection.py"
    ).read_text(encoding="utf-8")

    assert "--write-db" in source
    assert "--confirm-write" in source
    assert "WRITE_CONFIRMATION_PHRASE" in source
    assert "finished_match_scoring_cli import main" in wrapper
    assert (
        'w2-finished-match-scoring = "w2.tracking.finished_match_scoring_cli:main"'
        in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert "provider" not in "\n".join(
        line for line in source.splitlines() if line.lstrip().startswith(("from ", "import "))
    )
