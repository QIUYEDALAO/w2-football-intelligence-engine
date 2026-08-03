from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def workflow(name: str) -> dict[str, object]:
    return yaml.safe_load(text(name))


def triggers(name: str) -> object:
    payload = workflow(name)
    return payload.get("on", payload.get(True))


def test_pr_fast_is_cancelled_by_pr_number_and_never_builds_images() -> None:
    payload = workflow("pr-fast.yml")
    raw = text("pr-fast.yml")
    assert triggers("pr-fast.yml")["pull_request"]["types"] == [
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    ]
    assert payload["concurrency"] == {
        "group": "pr-fast-${{ github.event.pull_request.number }}",
        "cancel-in-progress": True,
    }
    assert payload["jobs"]["pr-fast-required"]["name"] == "PR_FAST_REQUIRED"
    assert "docker/build-push-action" not in raw


def test_release_candidate_uses_exact_head_once_and_has_parallel_lpt_shards() -> None:
    payload = workflow("release-candidate.yml")
    raw = text("release-candidate.yml")
    jobs = payload["jobs"]
    assert triggers("release-candidate.yml").keys() == {"workflow_dispatch"}
    assert payload["concurrency"] == {
        "group": "release-candidate-pr-${{ inputs.pr_number }}",
        "cancel-in-progress": True,
    }
    assert jobs["unit-contract"]["strategy"]["matrix"]["shard"] == [0, 1, 2, 3]
    assert jobs["integration"]["strategy"]["matrix"]["shard"] == [0, 1]
    assert jobs["release-required"]["name"] == "RELEASE_REQUIRED"
    assert payload["permissions"]["statuses"] == "write"
    assert 'statuses/${SOURCE_SHA}' in raw
    assert "-f context=RELEASE_REQUIRED" in raw
    assert raw.count("uses: docker/build-push-action@v6") == 2
    assert 'DOCKER_BUILD_RECORD_UPLOAD: "false"' in raw
    assert "retention-days: 7" in raw
    assert "needs.identity.outputs.images_required == 'true'" in raw
    assert "candidate-cleanup:" in raw
    assert raw.count("file: Dockerfile.python") == 1
    assert raw.count("file: Dockerfile.web") == 1
    assert raw.count("ref: ${{ inputs.expected_head_sha }}") >= 10
    for job in jobs.values():
        for step in job.get("steps", []):
            if step.get("uses") == "actions/checkout@v4":
                assert step["with"] == {
                    "ref": "${{ inputs.expected_head_sha }}",
                    "fetch-depth": 0,
                }
    assert '--network-alias api' in raw
    assert 'docker network create "$smoke_network"' in raw
    assert "merge_group" not in raw
    assert "W2_PROVIDER_CALLS_DISABLED: \"true\"" in raw
    assert "W2_PROVIDER_SCHEDULER_ENABLED: \"false\"" in raw


def test_main_only_promotes_or_dispatches_fail_closed_fallback() -> None:
    raw = text("main-promote.yml")
    payload = workflow("main-promote.yml")
    assert payload["jobs"]["promotion-required"]["name"] == "PROMOTION_REQUIRED"
    assert "pytest" not in raw
    assert "docker/build-push-action" not in raw
    assert "git rev-parse 'HEAD^{tree}'" in raw
    assert "gh workflow run release-candidate.yml" in raw
    assert "pr_number=0" in raw
    assert "force_full=true" in raw
    assert "FALLBACK_PROMOTED" in raw
    assert "ci.yml" not in raw
    assert "W2_RELEASE_PROMOTION_V1_ENABLED" not in raw
    assert "BOOTSTRAP_NOOP" not in raw


def test_legacy_ci_is_deleted_and_required_names_are_unique() -> None:
    assert not (WORKFLOWS / "ci.yml").exists()
    names: list[str] = []
    for filename in ("pr-fast.yml", "release-candidate.yml", "main-promote.yml"):
        for job in workflow(filename)["jobs"].values():
            name = job.get("name")
            required = {
                "PR_FAST_REQUIRED",
                "RELEASE_REQUIRED",
                "PROMOTION_REQUIRED",
            }
            if name in required:
                names.append(name)
    assert sorted(names) == [
        "PROMOTION_REQUIRED",
        "PR_FAST_REQUIRED",
        "RELEASE_REQUIRED",
    ]


def test_finalize_script_reuses_manifest_digests_and_does_not_enable_product_flags() -> None:
    raw = (ROOT / "scripts/release/finalize_pr.sh").read_text(encoding="utf-8")
    assert "relay_immutable_images_via_local.sh" in raw
    assert "deploy_stage7h_staging.sh" in raw
    assert "gh pr merge" in raw
    assert "--merge --delete-branch" in raw
    assert 'manifest_deployable="$(jq -r .deployable "$manifest")"' in raw
    assert "worktree remove --force" in raw
    assert "--auto" not in raw
    assert "mergeStateStatus" in raw
    assert 'merge_state" = CLEAN' in raw
    assert "W2_CANDIDATE" not in raw
    assert "W2_FORMAL" not in raw
    assert "W2_PROVIDER" not in raw


def test_manifest_downloads_are_exact_and_build_records_are_disabled() -> None:
    release = text("release-candidate.yml")
    promote = text("main-promote.yml")
    finalize = (ROOT / "scripts/release/finalize_pr.sh").read_text(encoding="utf-8")
    assert '.dockerbuild' not in release
    assert 'DOCKER_BUILD_RECORD_UPLOAD: "false"' in release
    assert 'release-candidate-${source_sha}' in promote
    assert 'release-candidate-${source_sha}' in finalize
    for raw in (promote, finalize):
        assert "gh run download" in raw
        assert "--name \"release-candidate-${source_sha}\"" in raw
        assert "--pattern" not in raw
        assert "--name '*'" not in raw


def test_context_records_release_candidate_promotion_without_changing_next_action() -> None:
    for filename in (
        "AI_PROJECT_CONTEXT.md",
        "PROJECT_STATE.yaml",
        "NEXT_ACTION.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
    ):
        raw = (ROOT / filename).read_text(encoding="utf-8")
        assert "RELEASE_CANDIDATE_PROMOTION_V1" in raw
        assert "POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS" in raw
    receipt = (
        ROOT / "docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md"
    ).read_text(encoding="utf-8")
    assert "required_approving_review_count: 0" in receipt
    assert "allow_force_pushes: false" in receipt
    assert "allow_deletions: false" in receipt
