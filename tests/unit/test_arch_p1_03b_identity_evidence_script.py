from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import scripts.arch_p1_03b_identity_evidence as evidence


class _Result:
    def scalar_one(self) -> str:
        return "0043_drop_legacy_identity_crosswalks"


class _Session:
    def __init__(self, _engine: object) -> None:
        pass

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def scalar(self, _statement: object) -> int:
        return 312

    def execute(self, _statement: object) -> _Result:
        return _Result()


class _Repository:
    def __init__(self) -> None:
        self.engine = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            url=SimpleNamespace(host="staging-db", database="w2"),
        )

    def player_identity_candidate_audit(self, **_kwargs: object) -> list[dict[str, int]]:
        return [{"provider_player_id": 1}]

    def player_identity_fixture_matrix(self, **_kwargs: object) -> list[dict[str, int]]:
        return [{"fixture_id": 1494212}]

    def player_identity_join_evidence(self, **_kwargs: object) -> dict[str, object]:
        return {"rows": [{"provider_player_id": 1}], "business_hash": "a" * 64, "status": "PASS"}


@pytest.fixture
def invocation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[list[str], list[str]]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"mappings":[]}', encoding="utf-8")
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    read_only_statements: list[str] = []

    def listen(_engine: object, name: str, callback: object) -> None:
        if name == "begin":
            callback(
                SimpleNamespace(
                    dialect=SimpleNamespace(name="postgresql"),
                    exec_driver_sql=read_only_statements.append,
                )
            )

    monkeypatch.setattr(evidence, "FutureRefreshDbRepository", _Repository)
    monkeypatch.setattr(evidence, "Session", _Session)
    monkeypatch.setattr(evidence, "approved_player_identity_manifest_rows", lambda _payload: [])
    monkeypatch.setattr(evidence.event, "listen", listen)
    monkeypatch.setattr(evidence.event, "remove", lambda *_args: None)
    monkeypatch.setattr(
        evidence.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="a" * 40 + "\n"),
    )
    return (
        [
            "--as-of",
            "2026-04-04T13:00:00Z",
            "--fixtures",
            "1494212",
            "--m3-fixtures",
            "1494212",
            "--manifest",
            str(manifest),
            "--review-package-sha256",
            manifest_hash,
            "--approval-artifact-sha256",
            "b" * 64,
            "--reviewed-by",
            "operator:liudehua",
        ],
        read_only_statements,
    )


def test_stdout_remains_backward_compatible(
    invocation: tuple[list[str], list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv, read_only_statements = invocation
    assert evidence.main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "w2.arch_p1_03b_identity_acceptance.v1"
    assert payload["provider_call_delta"] == payload["db_write_delta"] == 0
    assert "artifact_kind" not in payload
    assert read_only_statements == ["SET TRANSACTION READ ONLY"]


def test_output_is_canonical_hashed_and_replayable(
    invocation: tuple[list[str], list[str]], tmp_path: Path
) -> None:
    argv, _read_only_statements = invocation
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert evidence.main([*argv, "--output", str(first)]) == 0
    assert evidence.main([*argv, "--output", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_bytes())
    assert set(payload) == {
        "schema_version",
        "schema_path",
        "artifact_kind",
        "task_id",
        "subject_head",
        "generator",
        "replay",
        "migration_head",
        "captured_at",
        "source_identity",
        "row_count",
        "result_fingerprint",
        "provider_call_delta",
        "db_write_delta",
        "artifact_sha256",
    }
    expected_hash = evidence._canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"}
    )
    assert payload["artifact_sha256"] == expected_hash
    assert payload["provider_call_delta"] == payload["db_write_delta"] == 0
    assert payload["replay"]["output_flag"] == "--output"
    assert payload["replay"]["command_sha256"] == evidence._canonical_sha256(
        payload["replay"]["argv"]
    )
    assert first.read_bytes() == evidence._canonical_bytes(payload) + b"\n"


def test_missing_or_invalid_arguments_fail_closed(
    invocation: tuple[list[str], list[str]], tmp_path: Path
) -> None:
    argv, _read_only_statements = invocation
    with pytest.raises(SystemExit):
        evidence.main([])
    with pytest.raises(ValueError, match="timezone"):
        evidence.main([*argv, "--as-of", "2026-04-04"])
    output = tmp_path / "bad.json"
    wrong_hash = [*argv]
    wrong_hash[wrong_hash.index("--review-package-sha256") + 1] = "0" * 64
    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        evidence.main([*wrong_hash, "--output", str(output)])
    assert not output.exists()
