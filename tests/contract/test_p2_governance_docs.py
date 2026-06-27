from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_p2_governance_documents_exist_and_preserve_analysis_only_boundary() -> None:
    documents = [
        "docs/runbooks/W2_AUGUST_LEAGUE_VALIDATION_PLAN.md",
        "docs/runbooks/W2_FORMAL_DECISION_REVIEW_TEMPLATE.md",
        "docs/runbooks/W2_API_FOOTBALL_QUOTA_UPGRADE_PLAN.md",
        "docs/runbooks/W2_P2_RELEASE_GOVERNANCE.md",
        ".github/pull_request_template.md",
    ]

    combined = "\n".join(read(document) for document in documents)

    assert "FORMAL/CANDIDATE" in combined
    assert "beats_market" in combined
    assert "production" in combined.lower()
    for document in documents:
        assert read(document).strip()


def test_august_validation_plan_keeps_runtime_whitelist_disabled() -> None:
    text = read("docs/runbooks/W2_AUGUST_LEAGUE_VALIDATION_PLAN.md")
    competitions_readme = read("config/competitions/README.md")

    assert "No runtime whitelist expansion in this PR" in text
    assert "A later runtime PR may propose enabling" in text
    assert "Changing" in competitions_readme
    assert "`enabled` from `false` to `true`" in competitions_readme
    assert "separate approved runtime PR" in competitions_readme


def test_formal_decision_template_defaults_to_keep_analysis_only() -> None:
    text = read("docs/runbooks/W2_FORMAL_DECISION_REVIEW_TEMPLATE.md")

    assert "Default decision: `KEEP_ANALYSIS_ONLY`" in text
    assert "Do not approve FORMAL/CANDIDATE unless all S2 gate checks pass" in text
    assert "A separate implementation PR is required for any unlock" in text


def test_quota_upgrade_plan_does_not_default_enable_75000() -> None:
    text = read("docs/runbooks/W2_API_FOOTBALL_QUOTA_UPGRADE_PLAN.md")

    assert "Default daily budget: `7500`" in text
    assert "Reserve bucket: `1500`" in text
    assert "Do not default-enable `75000/day`" in text
    assert "does not authorize payment" in text


def test_pr_template_contains_release_safety_gates() -> None:
    text = read(".github/pull_request_template.md")

    required = [
        "Did not read or print `.env`",
        "FORMAL/CANDIDATE remain disabled",
        "Runtime `beats_market` remains false",
        "No fake odds, scores, EV, xG, or hit rates",
        "No provider credential, payment, or quota-plan change",
    ]
    for item in required:
        assert item in text
