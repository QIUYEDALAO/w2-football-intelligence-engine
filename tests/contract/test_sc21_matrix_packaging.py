"""The SC21 role authority matrix has to survive being installed as a wheel.

``factor_checklist`` used to find the matrix by guessing: ``Path.cwd()/docs/...``
and ``Path(__file__).parents[3]/docs/...``. Both hold in a source checkout and
neither holds in the released image, which installs the project with
``--no-editable`` and never copies ``docs/``. Every dashboard request in that image
raised SC21_FACTOR_ROLE_AUTHORITY_MATRIX_NOT_FOUND while every test everywhere
passed, because every test ran from a checkout.

So these tests build the wheel and read the matrix the way an installed package
must: from package data, from a process whose working directory is not the project
and whose import path does not include the repository.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from w2.dashboard import factor_checklist

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MATRIX = (
    ROOT / "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"
)
WHEEL_RESOURCE = "w2/dashboard/data/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"


@pytest.fixture(autouse=True)
def _clear_authority_cache() -> Iterator[None]:
    factor_checklist._role_authority.cache_clear()
    yield
    factor_checklist._role_authority.cache_clear()


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    built = sorted(out.glob("*.whl"))
    assert len(built) == 1, built
    return built[0]


def test_source_checkout_loads_the_matrix() -> None:
    payload = factor_checklist._role_authority()

    assert payload["schema_version"] == "w2.sc21-factor-coverage.v2"
    assert payload == json.loads(SOURCE_MATRIX.read_text(encoding="utf-8"))


def test_wheel_ships_the_matrix_byte_for_byte(wheel: Path) -> None:
    """One source document, copied -- not a second authority that can drift."""
    with zipfile.ZipFile(wheel) as archive:
        assert WHEEL_RESOURCE in archive.namelist()
        shipped = archive.read(WHEEL_RESOURCE)

    source = SOURCE_MATRIX.read_bytes()
    assert hashlib.sha256(shipped).hexdigest() == hashlib.sha256(source).hexdigest()
    assert shipped == source


_INSTALLED_LOOKUP = (
    "import json, pathlib, sys;"
    "import w2;"
    "from w2.dashboard.factor_checklist import _role_authority;"
    "root = pathlib.Path(sys.prefix).resolve();"
    "assert root in pathlib.Path(w2.__file__).resolve().parents, w2.__file__;"
    "sys.stdout.write(json.dumps(_role_authority()))"
)


def test_installed_wheel_loads_the_matrix_from_a_clean_venv_outside_the_repository(
    wheel: Path, tmp_path: Path
) -> None:
    """The case the released image hit and no existing test covered.

    A fresh virtual environment is created away from the repository, the wheel is
    installed into it, and the lookup runs from a third directory with nothing
    from the checkout on the import path. Nothing is monkeypatched: the assertion
    that ``w2`` resolved out of that venv's own site-packages is what stops the
    editable install in the development environment from answering instead, which
    is how "the matrix loads" could otherwise be true for the wrong reason.
    """
    venv = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--python", "3.12", str(venv)],
        check=True,
        capture_output=True,
        text=True,
    )
    python = venv / "bin/python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = subprocess.run(
        [str(python), "-c", _INSTALLED_LOOKUP],
        cwd=elsewhere,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads(SOURCE_MATRIX.read_text(encoding="utf-8"))


def test_missing_resource_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def absent() -> str:
        raise FileNotFoundError("SC21_FACTOR_ROLE_AUTHORITY_MATRIX_NOT_FOUND")

    monkeypatch.setattr(factor_checklist, "_role_authority_text", absent)

    with pytest.raises(FileNotFoundError, match="SC21_FACTOR_ROLE_AUTHORITY_MATRIX_NOT_FOUND"):
        factor_checklist._role_authority()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[]", "SC21_FACTOR_ROLE_AUTHORITY_INVALID"),
        ('"a string"', "SC21_FACTOR_ROLE_AUTHORITY_INVALID"),
    ],
)
def test_wrong_top_level_type_fails_closed(
    monkeypatch: pytest.MonkeyPatch, text: str, expected: str
) -> None:
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: text)

    with pytest.raises(ValueError, match=expected):
        factor_checklist._role_authority()


def test_malformed_json_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: "{not json")

    with pytest.raises(json.JSONDecodeError):
        factor_checklist._role_authority()


def _mutated(mutate: Any) -> str:
    payload = json.loads(SOURCE_MATRIX.read_text(encoding="utf-8"))
    mutate(payload)
    return json.dumps(payload)


def test_missing_roles_section_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    text = _mutated(lambda payload: payload.pop("fixture_factor_roles"))
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: text)

    with pytest.raises(ValueError, match="SC21_FIXTURE_FACTOR_ROLES_INVALID"):
        factor_checklist._role_authority()


def test_dropped_role_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def drop(payload: dict[str, Any]) -> None:
        roles = payload["fixture_factor_roles"]
        roles.pop(next(iter(roles)))

    text = _mutated(drop)
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: text)

    with pytest.raises(ValueError, match="SC21_FIXTURE_FACTOR_ROLES_INVALID"):
        factor_checklist._role_authority()


def test_unknown_role_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def add(payload: dict[str, Any]) -> None:
        roles = payload["fixture_factor_roles"]
        roles["F99_NOT_A_FACTOR"] = dict(roles[next(iter(roles))])

    text = _mutated(add)
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: text)

    with pytest.raises(ValueError, match="SC21_FIXTURE_FACTOR_ROLES_INVALID"):
        factor_checklist._role_authority()


def test_invalid_role_value_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def corrupt(payload: dict[str, Any]) -> None:
        roles = payload["fixture_factor_roles"]
        first = next(iter(roles))
        roles[first] = dict(roles[first]) | {"role_model_forecast": "NOT_A_ROLE"}

    text = _mutated(corrupt)
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: text)

    with pytest.raises(ValueError, match="SC21_FIXTURE_FACTOR_ROLE_INVALID"):
        factor_checklist._role_authority()


def test_lookup_does_not_search_the_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stray docs/ tree next to the process must not satisfy the lookup.

    The old code read ``Path.cwd()/docs/...``, so whatever the working directory
    happened to contain could answer for the authority. It cannot now.
    """
    decoy = tmp_path / "docs/review_packages/SC21_FACTOR_INPUT_CHAIN"
    decoy.mkdir(parents=True)
    (decoy / "SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    payload = factor_checklist._role_authority()

    assert payload["schema_version"] == "w2.sc21-factor-coverage.v2"


def test_both_image_build_paths_ship_the_one_tracked_file() -> None:
    """An image must carry the tracked document, not a copy that can drift.

    The formal Dockerfile and the offline local-release overlay build the image by
    different routes. Both have to take the matrix from the same repository path
    and deliver it to the same package-data location, so the bytes in either
    image are the bytes in git. Copying ``docs/`` wholesale is what this replaced.
    """
    dockerfile = (ROOT / "Dockerfile.python").read_text(encoding="utf-8")
    overlay = (ROOT / "infra/local-release/Dockerfile.python-overlay").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    source = (
        "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"
    )
    resource = WHEEL_RESOURCE

    assert source in dockerfile
    assert source in overlay
    assert f'"{source}" = "{resource}"' in pyproject
    for build_file in (dockerfile, overlay):
        assert "COPY docs " not in build_file
        assert "COPY docs\n" not in build_file
    # The formal image installs the wheel and then removes the build input, so
    # nothing at runtime can quietly satisfy a path-based fallback.
    assert "rm -rf /app/docs" in dockerfile


def test_a_cached_failure_does_not_leak_into_the_next_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``lru_cache`` holds a failure too, so each case must clear it.

    Two different invalid payloads are read in one process; the second only
    raises if the first exception was not cached in place of a result.
    """
    original = factor_checklist._role_authority_text
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: "{not json")
    with pytest.raises(json.JSONDecodeError):
        factor_checklist._role_authority()

    factor_checklist._role_authority.cache_clear()
    monkeypatch.setattr(factor_checklist, "_role_authority_text", lambda: "[]")
    with pytest.raises(ValueError, match="SC21_FACTOR_ROLE_AUTHORITY_INVALID"):
        factor_checklist._role_authority()

    factor_checklist._role_authority.cache_clear()
    monkeypatch.setattr(factor_checklist, "_role_authority_text", original)
    assert factor_checklist._role_authority()["schema_version"] == "w2.sc21-factor-coverage.v2"
