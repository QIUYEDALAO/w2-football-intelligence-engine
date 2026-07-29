from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = (
    ROOT
    / "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
SUPERSEDED_PATTERN = re.compile(r"SUPERSEDED_BY:\s*`([^`]+)`")
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
CURRENT_ARCHIVE_CLAIM_PATTERN = re.compile(
    r"(?i)(?:current|next|当前|下一|完整路线图|runbook).*docs/archive/"
    r"|docs/archive/.*(?:current|next|当前|下一|完整路线图|runbook)"
)
ARCHIVE_POLICY_PATTERN = re.compile(
    r'"source_manifest"\s*:\s*"docs/archive/'
)


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end, text.index(start))]


def test_a7_and_b6_done_coordinates_are_authoritative() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    a7 = _section(text, "#### A7. ARCH-P1-08", "#### A8.")
    b6 = _section(text, "#### B6. OPS-01", "#### B7.")

    assert "Status: DONE" in a7
    assert "PR: #423" in a7
    assert "Merge SHA: a607d65b0b71afbc0caa50c44a6e162cf397e4e4" in a7
    assert "CI: 30339386348" in a7
    assert "P1_ARCHITECTURE_CONVERGENCE_PASS = PASS" in a7

    assert "Status: DONE" in b6
    assert "PR: #425" in b6
    assert "Merge SHA: 6aba4ca6e1232d490b0b3c5d5fa40fc09749b3f8" in b6
    assert "FULL CI: 30412412188" in b6
    assert "Main CI: 30414946283" in b6


def test_p2_status_coordinates_and_unstarted_work_are_authoritative() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    b1 = _section(text, "#### B1. EVAL-01A", "#### B2.")
    b2 = _section(text, "#### B2. EVAL-01B", "#### B3.")
    p2 = _section(text, "#### A8. 阶段 P2", "### 阶段 B")

    assert "Status: DONE" in b1
    assert "- [x] PR 合并" in b1
    assert "Status: IMPLEMENTED_PENDING_SECONDARY_REVIEW_AND_STAGING" in b2
    assert "- [ ] PR 合并" in b2

    p2_02 = _section(p2, "**ARCH-P2-02", "**ARCH-P2-03")
    assert "Status: DONE" in p2_02
    assert "PR: #426" in p2_02
    assert "Merge SHA: 49c75521325af46551699b27241c0ef4c6bbb7a0" in p2_02
    assert "CI: 30422145661" in p2_02

    p2_03 = _section(p2, "**ARCH-P2-03", "**ARCH-P2-04")
    assert "Status: DONE" in p2_03
    assert "1853664 KiB（1.77 GiB）" in p2_03

    p2_04 = _section(p2, "**ARCH-P2-04", "**ARCH-P2-06")
    assert "Status: DONE" in p2_04
    assert "PR: #427" in p2_04
    assert "Merge SHA: bf21ddcc495b0c8d041c956734d278c1d611f24e" in p2_04
    assert "CI: 30425831606" in p2_04

    p2_06 = _section(p2, "**ARCH-P2-06", "**ARCH-P2-05")
    assert "Status: DONE" in p2_06
    assert "PR: #428" in p2_06
    assert "Merge SHA: 1a46a9e47a478072d37e4ec4c7a44d914e1a127b" in p2_06
    assert "CI: 30432075563" in p2_06
    assert "- [x] PR 合并" in p2_06

    p2_05 = p2[p2.index("**ARCH-P2-05") :]
    assert "Status: DONE" in p2_05
    assert "PR: #429" in p2_05
    assert "Merge SHA: 86a66ff5c07438b0543d2790165d406d452daedb" in p2_05
    assert "CI: 30435005222" in p2_05
    assert "- [x] exact-head FULL CI、外部验收与 PR 合并" in p2_05


def test_superseded_targets_exist_and_form_no_cycles() -> None:
    graph: dict[Path, Path] = {}
    for source in (ROOT / "docs").rglob("*.md"):
        targets = SUPERSEDED_PATTERN.findall(source.read_text(encoding="utf-8"))
        assert len(targets) <= 1, source
        if not targets:
            continue
        target = ROOT / targets[0]
        assert target.exists(), f"{source.relative_to(ROOT)} -> {targets[0]}"
        graph[source.resolve()] = target.resolve()

    for source in graph:
        seen: set[Path] = set()
        current = source
        while current in graph:
            assert current not in seen, f"SUPERSEDED_BY cycle at {current}"
            seen.add(current)
            current = graph[current]


def test_current_documents_do_not_promote_archived_material() -> None:
    docs = ROOT / "docs"
    for source in docs.rglob("*.md"):
        if "archive" not in source.relative_to(docs).parts:
            for line in source.read_text(encoding="utf-8").splitlines():
                if CURRENT_ARCHIVE_CLAIM_PATTERN.search(line):
                    assert "历史" in line or "不是当前" in line, source
        for raw_target in MARKDOWN_LINK_PATTERN.findall(
            source.read_text(encoding="utf-8")
        ):
            target = raw_target.strip().split()[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_part = target.split("#", 1)[0]
            resolved = (
                ROOT / path_part
                if path_part.startswith("docs/")
                else source.parent / path_part
            )
            assert resolved.exists(), f"{source.relative_to(ROOT)} -> {target}"


def test_active_assets_never_use_archive_as_runtime_storage() -> None:
    for script in (ROOT / "scripts").rglob("*.py"):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            value = node.value
            if any(name.startswith("DEFAULT_OUTPUT") for name in names) and value:
                assert "docs/archive" not in ast.unparse(value), script

    for policy in (ROOT / "config/policies").glob("*.json"):
        assert not ARCHIVE_POLICY_PATTERN.search(
            policy.read_text(encoding="utf-8")
        ), policy


def test_protected_current_authorities_are_not_archived() -> None:
    assert CHECKLIST.is_file()
    assert (ROOT / "docs/runbooks/W2_LEAGUE_EXPANSION_RUNBOOK.md").is_file()
