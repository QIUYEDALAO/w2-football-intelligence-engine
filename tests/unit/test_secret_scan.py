"""Release secret scan distinguishes credential values from identifiers."""

from pathlib import Path

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
