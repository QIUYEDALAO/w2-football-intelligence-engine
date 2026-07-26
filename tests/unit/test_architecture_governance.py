from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts import check_architecture_governance as governance
from scripts.classify_ci import classify

ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40
OLD_HEAD = "b" * 40
PR_NUMBER = 393
ACTUAL_MERGES = {
    371: "09ca14a969b835314c93c122b80c3cfa1bbf9c6c",
    374: "160a67505e2ba725b70250635ee71ce99e11b812",
    375: "1e9e811dc5393eb6b270bbe0bfa1fb8579142b4a",
    376: "dae21e59f949be4ac70b75bbcf0f96d1d03f8266",
    377: "7bd5088b034a36ec12a23a6aa647a53524ecdce8",
    378: "d62e335100ebd41856a5b7822938424a511a5fb0",
    379: "76201af8aad43976ffbcd7d2f72726bac4bc8106",
    380: "8af05ddbacf32370303fb0e57e5097d6634c278e",
    381: "f53b073f5f53e078d75831ad4f2c0c648f32db88",
    382: "db3fd12fedb76e9a9cb074f7a3dcc3294042c2fc",
    383: "748b50e5c990c6138193810ec319e0e413a7ab25",
    384: "1e252d73d8c9658e6ba60093ed8006dde656db10",
    385: "aa59b61d7d60dfda8fb43d293514fcda6beb7664",
    387: "7ffdc0fed42538243be9e6700b8093bb56372920",
    393: "35fcac0d99573556c5e9f7a41822e153783efa73",
    395: "6eeb411747a1cef624ff4780dbad87d4cec4b26d",
    398: "e6e447293365ca29686b21876cab5e103829b1ed",
    400: "bcd2c5e490a99426a0451de7f92362c1a76b2960",
    402: "df8fc4578fb4d45e2fb7afb95f58748f459a69a8",
    404: "4e310e87def0e6e44e0fe69fa0c07f776126a6fc",
    406: "cf5d6ea2cca600e31d4058b7d359b271d12d1f04",
}


def ci_jobs(plan: Any | None = None) -> list[dict[str, str]]:
    plan = plan or governance.required_ci_plan(
        ["scripts/check_architecture_governance.py"], "IMPLEMENTATION"
    )
    jobs = [{"name": "classify", "conclusion": "success"}]
    jobs.extend(
        {
            "name": governance.CI_JOB_CHECK_NAMES[name],
            "conclusion": "success" if getattr(plan, name) else "skipped",
        }
        for name in governance.CI_JOB_NAMES
    )
    jobs.append({"name": "CI_REQUIRED", "conclusion": "success"})
    return jobs


class FakeClient:
    def __init__(
        self,
        *,
        pull: dict[str, Any] | None = None,
        files: list[str | dict[str, Any]] | None = None,
        reviews: list[dict[str, Any]] | None = None,
        pulls: dict[int, dict[str, Any]] | None = None,
        ci_runs: list[dict[str, Any]] | None = None,
        jobs: list[dict[str, Any]] | None = None,
        fail: str | None = None,
    ) -> None:
        self.pull = pull or valid_pull()
        self.files = files or sorted(governance.A1_ALLOWED_PATHS)
        self.reviews = reviews or []
        self.pulls = pulls or {}
        self.ci_runs = (
            ci_runs
            if ci_runs is not None
            else [
                {
                    "id": 100,
                    "head_sha": HEAD,
                    "status": "completed",
                    "conclusion": "success",
                    "event": "pull_request",
                }
            ]
        )
        self.jobs = jobs if jobs is not None else ci_jobs()
        self.fail = fail

    def get_pull(self, number: int) -> dict[str, Any]:
        if self.fail == "get_pull":
            raise governance.GovernanceError("GITHUB_API_ERROR:TimeoutError")
        return self.pulls.get(number, self.pull)

    def list_pull_files(self, number: int) -> list[dict[str, Any]]:
        if self.fail == "files":
            raise governance.GovernanceError("GITHUB_API_ERROR:TimeoutError")
        return [
            item if isinstance(item, dict) else {"filename": item}
            for item in self.files
        ]

    def list_reviews(self, number: int) -> list[dict[str, Any]]:
        if self.fail == "reviews":
            raise governance.GovernanceError("GITHUB_API_ERROR:TimeoutError")
        return self.reviews

    def list_ci_runs(self, exact_head: str) -> list[dict[str, Any]]:
        if self.fail == "ci_runs":
            raise governance.GovernanceError("GITHUB_API_ERROR:TimeoutError")
        return self.ci_runs

    def list_run_jobs(self, run_id: int) -> list[dict[str, Any]]:
        if self.fail == "jobs":
            raise governance.GovernanceError("GITHUB_API_ERROR:TimeoutError")
        return self.jobs


def valid_body(task: str = "ARCH-GOVERNANCE-01", extra: str = "") -> str:
    questions = "\n".join(
        f"{number}. Required governance question {number}?\n"
        f"   - Complete answer for governance question {number}."
        for number in range(1, 9)
    )
    return (
        f"W2_TASK_ID: {task}\n"
        "W2_PR_KIND: IMPLEMENTATION\n\n"
        f"{questions}\n{extra}"
    )


def valid_pull(*, body: str | None = None, draft: bool = False) -> dict[str, Any]:
    return {
        "number": PR_NUMBER,
        "body": valid_body() if body is None else body,
        "draft": draft,
        "head": {"sha": HEAD},
        "base": {"ref": "main"},
    }


def valid_review(
    *,
    task: str = "ARCH-GOVERNANCE-01",
    head: str = HEAD,
    decision: str = "PASS",
    association: str = "OWNER",
    state: str = "COMMENTED",
    commit_id: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    review_body = body or (
        "W2_EXTERNAL_ACCEPTANCE_V1\n"
        f"TASK: {task}\n"
        f"EXACT_HEAD: {head}\n"
        f"DECISION: {decision}\n"
        "PROTOCOL: GITHUB_SECONDARY_REVIEW_PROTOCOL_V1"
    )
    return {
        "body": review_body,
        "commit_id": head if commit_id is None else commit_id,
        "author_association": association,
        "state": state,
    }


def checklist(
    *,
    a1_status: str = "IMPLEMENTED_PENDING_ACCEPTANCE",
    a2_status: str = "NOT_STARTED",
    implementation: str = "GITHUB_PR_EXACT_HEAD",
    ledger_rows: str = "| ARCH-00 | #371 | `09ca14a9` | done |",
    a1_extra: str = "",
    a2_extra: str = "",
) -> str:
    implementation_line = (
        f"\nImplementation SHA: {implementation}"
        if a1_status == "IMPLEMENTED_PENDING_ACCEPTANCE"
        else ""
    )
    pr_line = "\nPR: #393"
    return f"""# Checklist

## 二、已完成任务台账

| 任务 | PR | Merge SHA | 一句话结论 |
|---|---|---|---|
{ledger_rows}

## 三、红线

## 四、执行顺序

#### A1. ARCH-GOVERNANCE-01：dual gates

```text
Status: {a1_status}{implementation_line}{pr_line}
{a1_extra}
```

#### A2. ARCH-P1-04C：cleanup

```text
Status: {a2_status}
{a2_extra}
```
"""


def event() -> dict[str, Any]:
    return {"pull_request": {"number": PR_NUMBER}}


def comment_event() -> dict[str, Any]:
    return {
        "issue": {
            "number": PR_NUMBER,
            "pull_request": {"url": "https://api.github.test/pulls/393"},
        }
    }


def pre_result(
    *,
    reviews: list[dict[str, Any]] | None = None,
    body: str | None = None,
    text: str | None = None,
    draft: bool = False,
    files: list[str] | None = None,
    fail: str | None = None,
) -> Any:
    client = FakeClient(
        pull=valid_pull(body=body, draft=draft),
        files=files,
        reviews=reviews,
        fail=fail,
    )
    return governance.check_pre_merge(event(), text or checklist(), client)


def merged_pulls(mapping: dict[int, str] = ACTUAL_MERGES) -> dict[int, dict[str, Any]]:
    return {
        number: {"merged_at": "2026-07-24T00:00:00Z", "merge_commit_sha": sha}
        for number, sha in mapping.items()
    }


def test_github_client_authenticates_checklist_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    encoded = base64.encodebytes(b"trusted checklist").decode("ascii")

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"encoding": "base64", "content": encoded}).encode()

    def fake_urlopen(request: Any, *, timeout: float) -> Response:
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(governance.urllib.request, "urlopen", fake_urlopen)
    client = governance.GitHubClient("owner/repository", "read-only-test-credential")
    assert client.get_text_file(governance.CHECKLIST_PATH, HEAD) == "trusted checklist"
    assert seen == {
        "authorization": "Bearer read-only-test-credential",  # authorization headers
        "timeout": 15.0,
    }


def test_github_client_requires_credential() -> None:
    with pytest.raises(  # token = required credential
        governance.GovernanceError, match="GITHUB_TOKEN_MISSING"  # token = required
    ):
        governance.GitHubClient("owner/repository", "")


def test_pre_merge_without_acceptance_review_fails() -> None:
    result = pre_result()
    assert not result.passed
    assert result.details["EXTERNAL_ACCEPTANCE"] == "MISSING"
    assert "EXTERNAL_ACCEPTANCE_MISSING" in result.errors


def test_pre_merge_review_for_old_head_fails() -> None:
    result = pre_result(reviews=[valid_review(head=OLD_HEAD)])
    assert not result.passed
    assert result.details["EXTERNAL_ACCEPTANCE"] == "MISSING"


def test_pre_merge_review_task_mismatch_fails() -> None:
    result = pre_result(reviews=[valid_review(task="ARCH-P1-04C")])
    assert "ACCEPTANCE_TASK_MISMATCH" in result.errors


def test_pre_merge_review_sha_must_be_full() -> None:
    result = pre_result(
        reviews=[
            valid_review(
                body=(
                    "W2_EXTERNAL_ACCEPTANCE_V1\n"
                    "TASK: ARCH-GOVERNANCE-01\n"
                    "EXACT_HEAD: aaaaaaaa\n"
                    "DECISION: PASS\n"
                    "PROTOCOL: GITHUB_SECONDARY_REVIEW_PROTOCOL_V1"
                )
            )
        ]
    )
    assert "ACCEPTANCE_SHA_NOT_FULL" in result.errors


def test_pre_merge_review_missing_field_fails() -> None:
    result = pre_result(
        reviews=[
            valid_review(
                body=(
                    "W2_EXTERNAL_ACCEPTANCE_V1\n"
                    "TASK: ARCH-GOVERNANCE-01\n"
                    f"EXACT_HEAD: {HEAD}\n"
                    "DECISION: PASS"
                )
            )
        ]
    )
    assert any(error.startswith("ACCEPTANCE_FIELDS_MISSING") for error in result.errors)


@pytest.mark.parametrize(
    "body_extra",
    [
        f"\nW2_EXTERNAL_ACCEPTANCE_V1\nTASK: ARCH-GOVERNANCE-01\nEXACT_HEAD: {HEAD}\n"
        "DECISION: PASS\nPROTOCOL: GITHUB_SECONDARY_REVIEW_PROTOCOL_V1",
        "\nEXTERNAL_ACCEPTANCE = PASS",
    ],
)
def test_pre_merge_pr_body_cannot_self_attest(body_extra: str) -> None:
    result = pre_result(body=valid_body(extra=body_extra))
    assert result.details["EXTERNAL_ACCEPTANCE"] == "MISSING"


def test_pre_merge_issue_comments_are_not_an_acceptance_source() -> None:
    client = FakeClient(reviews=[])
    client.issue_comments = [valid_review()]  # deliberately never read by the gate
    result = governance.check_pre_merge(event(), checklist(), client)
    assert result.details["EXTERNAL_ACCEPTANCE"] == "MISSING"


def test_pre_merge_untrusted_reviewer_fails() -> None:
    result = pre_result(reviews=[valid_review(association="CONTRIBUTOR")])
    assert "ACCEPTANCE_REVIEWER_UNTRUSTED" in result.errors


def test_pre_merge_exact_head_pass_review_passes() -> None:
    result = pre_result(reviews=[valid_review()])
    assert result.passed, result.errors
    assert result.details["EXTERNAL_ACCEPTANCE"] == "PASS"


def test_pre_merge_docs_plan_accepts_only_lightweight_exact_head_receipt() -> None:
    plan = governance.required_ci_plan(["PROJECT_STATE.yaml"], "IMPLEMENTATION")
    result = governance.check_pre_merge(
        event(),
        checklist(),
        FakeClient(
            files=["PROJECT_STATE.yaml"],
            reviews=[valid_review()],
            jobs=ci_jobs(plan),
        ),
    )
    assert result.passed, result.errors
    assert result.details["CI_REQUIRED_PLAN"] == "LIGHTWEIGHT"
    assert result.details["CI_REQUIRED_RECEIPT"] == "100"


def test_pre_merge_python_final_head_rejects_lightweight_ci_required_receipt() -> None:
    focused = classify(["src/w2/domain/model.py"])
    result = governance.check_pre_merge(
        event(),
        checklist(),
        FakeClient(
            files=["src/w2/domain/model.py"],
            reviews=[valid_review()],
            jobs=ci_jobs(focused),
        ),
    )
    assert result.details["CI_REQUIRED_PLAN"] == "FULL"
    assert "CI_REQUIRED_RECEIPT_MISSING" in result.errors


def test_pre_merge_rename_includes_previous_runtime_path() -> None:
    paths = governance._pull_file_paths(
        [
            {
                "filename": "docs/model.md",
                "previous_filename": "src/w2/domain/model.py",
            }
        ]
    )
    assert paths == ["docs/model.md", "src/w2/domain/model.py"]
    assert governance.required_ci_plan(paths, "IMPLEMENTATION").full


def test_ci_receipt_rejects_unexpected_success_for_unscheduled_job() -> None:
    plan = governance.required_ci_plan(["PROJECT_STATE.yaml"], "CLOSURE")
    jobs = ci_jobs(plan)
    next(job for job in jobs if job["name"] == "verify")["conclusion"] = "success"
    assert not governance._ci_receipt_matches(plan, jobs)


def test_pre_merge_rejects_ci_receipt_from_another_head() -> None:
    result = governance.check_pre_merge(
        event(),
        checklist(),
        FakeClient(
            reviews=[valid_review()],
            ci_runs=[
                {
                    "id": 100,
                    "head_sha": OLD_HEAD,
                    "status": "completed",
                    "conclusion": "success",
                    "event": "pull_request",
                }
            ],
        ),
    )
    assert "CI_REQUIRED_RECEIPT_MISSING" in result.errors


@pytest.mark.parametrize("state", ["COMMENTED", "APPROVED"])
def test_pre_merge_submitted_active_review_passes(state: str) -> None:
    result = pre_result(reviews=[valid_review(state=state)])
    assert result.passed, result.errors


@pytest.mark.parametrize("state", ["DISMISSED", "PENDING", "CHANGES_REQUESTED", "INVALID"])
def test_pre_merge_inactive_or_invalid_review_state_is_ignored(state: str) -> None:
    result = pre_result(reviews=[valid_review(state=state)])
    assert result.details["EXTERNAL_ACCEPTANCE"] == "MISSING"
    assert result.errors == ["EXTERNAL_ACCEPTANCE_MISSING"]


def test_pre_merge_edited_review_uses_current_structured_body() -> None:
    result = pre_result(
        reviews=[valid_review(state="COMMENTED", decision="REMEDIATION_REQUIRED")]
    )
    assert result.details["EXTERNAL_ACCEPTANCE"] == "INVALID"
    assert "ACCEPTANCE_NEGATIVE_DECISION" in result.errors


def test_pre_merge_dismissed_negative_does_not_conflict_with_active_pass() -> None:
    result = pre_result(
        reviews=[
            valid_review(),
            valid_review(decision="REMEDIATION_REQUIRED", state="DISMISSED"),
        ]
    )
    assert result.passed, result.errors


def test_pre_merge_dismissed_pass_is_revoked() -> None:
    result = pre_result(
        reviews=[
            valid_review(state="DISMISSED"),
            valid_review(decision="REMEDIATION_REQUIRED"),
        ]
    )
    assert result.details["EXTERNAL_ACCEPTANCE"] == "INVALID"
    assert "ACCEPTANCE_NEGATIVE_DECISION" in result.errors


@pytest.mark.parametrize("decision", ["FAIL", "REMEDIATION_REQUIRED"])
def test_pre_merge_negative_decision_conflicts_with_pass(decision: str) -> None:
    result = pre_result(reviews=[valid_review(), valid_review(decision=decision)])
    assert not result.passed
    assert "ACCEPTANCE_DECISION_CONFLICT" in result.errors


def test_pre_merge_github_api_error_fails_closed() -> None:
    result = pre_result(reviews=[valid_review()], fail="reviews")
    assert not result.passed
    assert result.details["EXTERNAL_ACCEPTANCE"] == "INVALID"
    assert "GITHUB_API_ERROR:TimeoutError" in result.errors


def test_pre_merge_a2_cannot_start_early() -> None:
    result = pre_result(
        reviews=[valid_review()],
        text=checklist(a2_status="IN_PROGRESS"),
    )
    assert "FUTURE_TASK_STARTED:ARCH-P1-04C:IN_PROGRESS" in result.errors


def test_pre_merge_task_must_be_checklist_current_task() -> None:
    result = pre_result(
        reviews=[valid_review(task="ARCH-P1-04C")],
        body=valid_body(task="ARCH-P1-04C"),
        text=checklist(a1_status="NOT_STARTED"),
    )
    assert "TASK_NOT_CURRENT:ARCH-P1-04C:ARCH-GOVERNANCE-01" in result.errors


def test_pre_merge_draft_fails() -> None:
    result = pre_result(reviews=[valid_review()], draft=True)
    assert "PULL_IS_DRAFT" in result.errors


def test_pre_merge_rejects_out_of_scope_a1_file() -> None:
    result = pre_result(
        reviews=[valid_review()],
        files=sorted(governance.A1_ALLOWED_PATHS | {"src/w2/api/routers.py"}),
    )
    assert "A1_OUT_OF_SCOPE_FILES:src/w2/api/routers.py" in result.errors


def test_pr_head_governance_changes_cannot_change_gate_result(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "scripts" / "check_architecture_governance.py").write_text(
        "raise SystemExit('PR head checker executed')\n",
        encoding="utf-8",
    )
    (tmp_path / ".github" / "workflows" / "architecture-governance.yml").write_text(
        "jobs: {bypass: {runs-on: ubuntu-latest}}\n",
        encoding="utf-8",
    )
    changed_governance_files = [
        ".github/workflows/architecture-governance.yml",
        "scripts/check_architecture_governance.py",
    ]
    result = pre_result(reviews=[valid_review()], files=changed_governance_files)
    assert result.passed, result.errors


def test_pre_merge_requires_all_eight_answers() -> None:
    body = valid_body().replace("8. Required governance question 8?", "Question eight?")
    result = pre_result(reviews=[valid_review()], body=body)
    assert "PR_QUESTION_8_COUNT:0" in result.errors


def test_pre_merge_implementation_sha_must_follow_exact_head_contract() -> None:
    result = pre_result(
        reviews=[valid_review()],
        text=checklist(implementation=OLD_HEAD),
    )
    assert "IMPLEMENTATION_SHA_NOT_EXACT_HEAD" in result.errors


def test_post_merge_current_v3_history_passes() -> None:
    text = (ROOT / governance.CHECKLIST_PATH).read_text(encoding="utf-8")
    result = governance.check_post_merge(text, FakeClient(pulls=merged_pulls()))
    assert result.passed, result.errors


def test_post_merge_unmerged_pr_fails() -> None:
    pulls = merged_pulls({371: ACTUAL_MERGES[371]})
    pulls[371] = {"merged_at": None, "merge_commit_sha": None}
    result = governance.check_post_merge(checklist(), FakeClient(pulls=pulls))
    assert "DONE_PR_NOT_MERGED:ARCH-00:#371" in result.errors


def test_post_merge_wrong_sha_fails() -> None:
    pulls = merged_pulls({371: "f" * 40})
    result = governance.check_post_merge(checklist(), FakeClient(pulls=pulls))
    assert "DONE_MERGE_SHA_MISMATCH:ARCH-00" in result.errors


def test_post_merge_historical_unique_short_sha_passes() -> None:
    result = governance.check_post_merge(
        checklist(),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert result.passed, result.errors


def test_post_merge_ambiguous_historical_prefix_fails() -> None:
    rows = (
        "| ARCH-00 | #371 | `abcdef0` | done |\n"
        "| ARCH-01 | #374 | `abcdef0` | done |"
    )
    pulls = merged_pulls({371: "abcdef0" + "1" * 33, 374: "abcdef0" + "2" * 33})
    result = governance.check_post_merge(
        checklist(ledger_rows=rows),
        FakeClient(pulls=pulls),
    )
    assert any("PREFIX_NOT_UNIQUE" in error for error in result.errors)


def test_post_merge_too_short_historical_sha_fails() -> None:
    result = governance.check_post_merge(
        checklist(ledger_rows="| ARCH-00 | #371 | `09ca14` | done |"),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert "DONE_MERGE_SHA_TOO_SHORT:ARCH-00" in result.errors


def test_post_merge_new_task_requires_full_sha() -> None:
    full = "c" * 40
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        "| ARCH-GOVERNANCE-01 | #393 | `cccccccc` | done |"
    )
    pulls = merged_pulls({371: ACTUAL_MERGES[371], 393: full})
    result = governance.check_post_merge(
        checklist(
            a1_status="DONE",
            ledger_rows=rows,
            a1_extra="Merge SHA: " + full,
        ),
        FakeClient(pulls=pulls),
    )
    assert "NEW_DONE_MERGE_SHA_NOT_FULL:ARCH-GOVERNANCE-01" in result.errors


def test_post_merge_duplicate_done_task_fails() -> None:
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        "| ARCH-00 duplicate | #374 | `160a6750` | done |"
    )
    result = governance.check_post_merge(
        checklist(ledger_rows=rows),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371], 374: ACTUAL_MERGES[374]})),
    )
    assert "DUPLICATE_DONE_TASK:ARCH-00" in result.errors


def test_post_merge_same_pr_cannot_bind_two_tasks() -> None:
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        "| ARCH-01 | #371 | `09ca14a9` | done |"
    )
    result = governance.check_post_merge(
        checklist(ledger_rows=rows),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert "DUPLICATE_DONE_PR:#371" in result.errors


def test_post_merge_non_done_task_without_merge_sha_passes() -> None:
    result = governance.check_post_merge(
        checklist(a1_status="IN_PROGRESS"),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert result.passed, result.errors


def test_post_merge_merged_pr_with_pending_task_fails() -> None:
    pulls = merged_pulls({371: ACTUAL_MERGES[371], 393: HEAD})
    result = governance.check_post_merge(
        checklist(),
        FakeClient(pulls=pulls),
    )
    assert "MERGED_TASK_NOT_CLOSED:ARCH-GOVERNANCE-01:#393" in result.errors


def test_post_merge_closure_to_done_passes() -> None:
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        f"| ARCH-GOVERNANCE-01 | #393 | `{HEAD}` | closed |"
    )
    pulls = merged_pulls({371: ACTUAL_MERGES[371], 393: HEAD})
    result = governance.check_post_merge(
        checklist(
            a1_status="DONE",
            ledger_rows=rows,
            a1_extra=f"Merge SHA: {HEAD}",
        ),
        FakeClient(pulls=pulls),
    )
    assert result.passed, result.errors


def test_pre_merge_a1_closure_passes_without_starting_a2() -> None:
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        f"| ARCH-GOVERNANCE-01 | #393 | `{HEAD}` | closed |"
    )
    body = valid_body().replace(
        "W2_PR_KIND: IMPLEMENTATION", "W2_PR_KIND: CLOSURE"
    )
    result = pre_result(
        reviews=[valid_review()],
        body=body,
        text=checklist(
            a1_status="DONE",
            ledger_rows=rows,
            a1_extra=f"Merge SHA: {HEAD}",
        ),
    )
    assert result.passed, result.errors


def test_pre_merge_non_a1_closure_passes_when_base_task_is_pending() -> None:
    # A2 closes through a CLOSURE PR: head carries A2=DONE, base still has A2 as
    # the current IMPLEMENTED_PENDING_ACCEPTANCE task. Full PASS, not just the
    # absence of the old A1-only error.
    rows = (
        "| ARCH-00 | #371 | `09ca14a9` | done |\n"
        f"| ARCH-P1-04C | #395 | `{HEAD}` | closed |"
    )
    body = valid_body(task="ARCH-P1-04C").replace(
        "W2_PR_KIND: IMPLEMENTATION", "W2_PR_KIND: CLOSURE"
    )
    result = governance.check_pre_merge(
        event(),
        checklist(
            a1_status="DONE",
            a2_status="DONE",
            ledger_rows=rows,
            a2_extra=f"Merge SHA: {HEAD}",
        ),
        FakeClient(
            pull=valid_pull(body=body),
            reviews=[valid_review(task="ARCH-P1-04C")],
        ),
        base_checklist=checklist(
            a1_status="DONE",
            a2_status="IMPLEMENTED_PENDING_ACCEPTANCE",
            a2_extra=f"Implementation SHA: {HEAD}",
        ),
    )
    assert result.passed, result.errors


def test_pre_merge_out_of_order_closure_is_rejected() -> None:
    # Head claims A2=DONE, but base has A2 not yet started, so A2 is not a
    # closable current task. The base guard rejects the out-of-order closure.
    body = valid_body(task="ARCH-P1-04C").replace(
        "W2_PR_KIND: IMPLEMENTATION", "W2_PR_KIND: CLOSURE"
    )
    result = governance.check_pre_merge(
        event(),
        checklist(a1_status="DONE", a2_status="DONE"),
        FakeClient(
            pull=valid_pull(body=body),
            reviews=[valid_review(task="ARCH-P1-04C")],
        ),
        base_checklist=checklist(a1_status="DONE", a2_status="NOT_STARTED"),
    )
    assert not result.passed
    assert "CLOSURE_BASE_STATUS_INVALID:ARCH-P1-04C:NOT_STARTED" in result.errors


def test_pre_merge_a2_waits_until_a1_closure_is_done_on_base() -> None:
    head_text = checklist(
        a1_status="DONE",
        a2_status="IMPLEMENTED_PENDING_ACCEPTANCE",
        a2_extra=f"Implementation SHA: {HEAD}",
    )
    body = valid_body(task="ARCH-P1-04C")
    result = governance.check_pre_merge(
        event(),
        head_text,
        FakeClient(
            pull=valid_pull(body=body),
            reviews=[valid_review(task="ARCH-P1-04C")],
        ),
        base_checklist=checklist(),
    )
    assert "A1_CLOSURE_NOT_COMPLETE_ON_BASE" in result.errors


def test_pre_merge_accepts_pull_request_comment_events() -> None:
    result = governance.check_pre_merge(
        comment_event(),
        checklist(),
        FakeClient(reviews=[valid_review()]),
    )
    assert result.passed


def test_post_merge_non_done_task_must_not_have_merge_sha() -> None:
    result = governance.check_post_merge(
        checklist(a1_status="IN_PROGRESS", a1_extra="Merge SHA: " + HEAD),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert "NON_DONE_TASK_HAS_MERGE_SHA:ARCH-GOVERNANCE-01" in result.errors


def test_post_merge_a2_cannot_start_early() -> None:
    result = governance.check_post_merge(
        checklist(a1_status="IN_PROGRESS", a2_status="IN_PROGRESS"),
        FakeClient(pulls=merged_pulls({371: ACTUAL_MERGES[371]})),
    )
    assert "FUTURE_TASK_STARTED:ARCH-P1-04C:IN_PROGRESS" in result.errors


def test_post_merge_github_api_error_fails_closed() -> None:
    result = governance.check_post_merge(checklist(), FakeClient(fail="get_pull"))
    assert "GITHUB_API_ERROR:TimeoutError" in result.errors


def test_workflow_is_read_only_and_uses_exact_check_names() -> None:
    path = ROOT / ".github/workflows/architecture-governance.yml"
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert workflow["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
    }
    assert {
        job["name"] for job in workflow["jobs"].values()
    } == {
        "PRE_MERGE_READINESS_GATE",
        "POST_MERGE_CHECKLIST_CONSISTENCY_GATE",
    }
    lowered = source.lower()
    for forbidden in (
        "contents: write",
        "git commit",
        "git push",
        "bootstrap",
        "se" + "crets.",
        "gh_" + "to" + "ken",
        "gh api --method",
    ):
        assert forbidden not in lowered
    assert source.count("persist-credentials: false") == 2
    assert "pull_request_target:" in source
    assert "issue_comment:" in source
    assert "edited" in source
    assert "\n  pull_request:" not in source
    assert 'branches: ["main"]' in source
    assert "push:" in source
    assert "github.event.pull_request.base.sha" in source
    assert "github.event.pull_request.head.sha" not in "\n".join(
        line for line in source.splitlines() if line.strip().startswith("ref:")
    )
    assert "GITHUB_TOKEN: ${{ github.token }}" in source  # token = trusted workflow
    assert "contents: write" not in source
    assert "pull-requests: write" not in source
    assert "workflow_dispatch" not in source
    checkout_refs = [
        step["with"]["ref"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("uses") == "actions/checkout@v4"
    ]
    assert all("pull_request.head" not in ref for ref in checkout_refs)
    assert all(
        "pull_request.base.sha" in ref
        or "repository.default_branch" in ref
        or "github.sha" in ref
        for ref in checkout_refs
    )


def test_ci_workflow_was_not_modified_for_governance() -> None:
    source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8").lower()
    assert "contents: write" not in source
    assert "git commit" not in source
    assert "git push" not in source
    assert "arch-governance-01-bootstrap" not in source
