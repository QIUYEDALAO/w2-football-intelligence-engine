from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.ci_shards import DEDICATED, candidates, collected_files, lpt_plan, plan


def _durations(tmp_path: Path) -> Path:
    files = candidates("unit-contract") + candidates("integration")
    path = tmp_path / "durations.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "w2.pytest-durations.v1",
                "default_seconds": 1,
                "files": {name: index + 1 for index, name in enumerate(files)},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_lpt_is_deterministic_and_balances_by_duration() -> None:
    files = ["a", "b", "c", "d"]
    durations = {"a": 8.0, "b": 7.0, "c": 2.0, "d": 1.0}
    assert lpt_plan(files, durations, 1.0, 2) == [["a", "d"], ["b", "c"]]


def test_every_generic_test_file_is_assigned_once_and_dedicated_files_are_excluded(
    tmp_path: Path,
) -> None:
    durations = _durations(tmp_path)
    assigned: list[str] = []
    for kind, count in (("unit-contract", 4), ("integration", 2)):
        shards = plan(kind, count, durations)
        flattened = [path for shard in shards for path in shard]
        assert sorted(flattened) == candidates(kind)
        assert len(flattened) == len(set(flattened))
        assigned.extend(flattened)
    assert not DEDICATED.intersection(assigned)
    assert sorted(assigned + list(DEDICATED)) == collected_files()


def test_invalid_or_empty_duration_manifest_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "durations.json"
    path.write_text('{"schema_version":"wrong","files":{}}', encoding="utf-8")
    with pytest.raises(ValueError):
        plan("unit-contract", 4, path)


def test_checked_in_duration_manifest_covers_the_current_suite() -> None:
    assigned = [
        path
        for kind, count in (("unit-contract", 4), ("integration", 2))
        for shard in plan(kind, count)
        for path in shard
    ]
    assert sorted(assigned + list(DEDICATED)) == collected_files()
