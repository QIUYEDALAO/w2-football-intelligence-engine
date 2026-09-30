"""Release secret scan distinguishes credential values from identifiers."""

from pathlib import Path

import tests.secret_scan as scanner
from tests.secret_scan import line_has_credential


def test_secret_scan_rejects_real_literal_shapes() -> None:
    sample = "ghp_" + "A" * 30
    payload = "real-looking-" + "production-value-42"
    assert line_has_credential(f'authorization = "Bearer {sample}"')
    assert line_has_credential(f'API_KEY = "{sample}"')
    assert line_has_credential(f'password = "{payload}"')
    assert line_has_credential(f'setenv("API_KEY", "{payload}")')
    assert line_has_credential('-----BEGIN ' + 'PRIVATE KEY-----')
    assert line_has_credential(f'owner_token = "{payload}"', path=Path("tests/fake.py"))


def test_secret_scan_allows_references_and_exact_fixture_placeholders() -> None:
    assert not line_has_credential("owner_token: str | None")
    assert not line_has_credential('owner_token = os.environ.get("OWNER_TOKEN")')
    assert not line_has_credential('API_KEY = "${API_KEY}"')
    assert not line_has_credential('password = "placeholder"')


def test_secret_scan_rejects_literal_shapes_that_look_like_references() -> None:
    key_field = "pass" + "word"
    api_field = "W2_" + "API_KEY"
    dollar_literal = "$Super" + "Secure2026!"
    upper_literal = "SUPER_SECRET_" + "PASSWORD"
    shell_literal = "AbCd" + "123456789"

    assert line_has_credential(f'{key_field} = "{dollar_literal}"')
    assert line_has_credential(f'{key_field} = "{upper_literal}"')
    assert line_has_credential(
        f"export {api_field}={shell_literal}", path=Path("probe.sh")
    )
    assert not line_has_credential(f'{key_field} = "${{PASSWORD}}"')
    assert not line_has_credential(
        f"export {api_field}=${{W2_API_KEY}}", path=Path("probe.sh")
    )


def test_secret_scan_rejects_all_three_in_a_repository_file(
    tmp_path: Path, monkeypatch,
) -> None:
    key_field = "pass" + "word"
    api_field = "W2_" + "API_KEY"
    dollar_literal = "$Super" + "Secure2026!"
    upper_literal = "SUPER_SECRET_" + "PASSWORD"
    shell_literal = "AbCd" + "123456789"
    probe = tmp_path / "probe.sh"
    probe.write_text(
        f'{key_field} = "{dollar_literal}"\n'
        f'export {api_field}={shell_literal}\n'
        f'{key_field} = "{upper_literal}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "iter_files", lambda: [probe])

    assert scanner.scan() == [
        "probe.sh:1: CREDENTIAL_LITERAL",
        "probe.sh:2: CREDENTIAL_LITERAL",
        "probe.sh:3: CREDENTIAL_LITERAL",
    ]
