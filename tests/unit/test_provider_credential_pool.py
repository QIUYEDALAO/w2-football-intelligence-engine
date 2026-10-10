"""指令书 I 任务 B：API-Football 凭据池（Pro 优先 / 失效自动切备用号）。

覆盖三类证据：

1. **轮换正例**：主号健康时只用主号；主号 401/403/429 时自动切备用号并成功；
2. **反例攻击**：400 参数错、500、传输错误、payload 非凭据类错误**都不得切换**
   ——换 key 解决不了这些，切换只会浪费配额并把「我们的 bug」伪装成凭据问题；
3. **配置与泄密攻击**：空池失败关闭、显式空池不回退历史变量、重复 key 去重、
   任何 repr / 异常消息里不得出现 key 明文。
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError
from w2.providers.key_pool import (
    CREDENTIALS_ENV,
    LEGACY_CREDENTIALS_ENV,
    ProviderCredential,
    ProviderCredentialPool,
    ProviderCredentialPoolExhausted,
    credential_pool_from_env,
    failover_reason,
    parse_credentials,
)

PRO_KEY = "pro-secret-aaa"
FREE_KEY = "free-secret-bbb"


class _FakeResponse:
    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
        self.status = status
        self.headers = headers or {}
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(code: int, payload: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.invalid",
        code=code,
        msg="error",
        hdrs={},
        fp=io.BytesIO(json.dumps(payload).encode()),
    )


class _Recorder:
    """按调用序返回预置响应，并记录每次请求用的凭据。"""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.secrets: list[str] = []
        self.records: list[dict[str, object]] = []

    def urlopen(self, request: urllib.request.Request, timeout: int) -> object:
        self.secrets.append(request.get_header("X-apisports-key") or "")
        outcome = self.outcomes[min(len(self.secrets) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def ledger(self) -> _Recorder:
        return self

    def record_request(self, **kwargs: object) -> None:
        self.records.append(kwargs)


def _client(
    recorder: _Recorder, monkeypatch, keys: str = f"{PRO_KEY},{FREE_KEY}"
) -> ApiFootballClient:
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "odds")
    monkeypatch.delenv("W2_PROVIDER_REQUEST_LEDGER_ENABLED", raising=False)
    monkeypatch.setenv(CREDENTIALS_ENV, keys)
    monkeypatch.setattr(urllib.request, "urlopen", recorder.urlopen)
    return ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"odds"}),
        request_ledger=recorder,
    )


def _ok() -> _FakeResponse:
    return _FakeResponse(200, {"response": []})


# ── 正例：主号优先与自动接管 ────────────────────────────────────────────────
def test_primary_credential_used_when_healthy(monkeypatch) -> None:
    recorder = _Recorder([_ok()])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "1"})

    assert response.status_code == 200
    assert recorder.secrets == [PRO_KEY], "主号健康时不得动用备用号"


def test_primary_rejected_falls_over_to_backup(monkeypatch) -> None:
    """Pro 停用模拟：主号 403 → 免费号自动接管。"""
    recorder = _Recorder([_http_error(403, {"response": []}), _ok()])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "2"})

    assert response.status_code == 200
    assert recorder.secrets == [PRO_KEY, FREE_KEY], "必须换到备用凭据"
    failed = [row for row in recorder.records if row["status_code"] == 403]
    assert len(failed) == 1
    assert "CREDENTIAL_SLOT_0" in str(failed[0]["error"]), (
        "失败尝试必须把 slot 写进 error，作为接管的持久证据"
    )
    succeeded = [row for row in recorder.records if row["status_code"] == 200]
    assert len(succeeded) == 1


def test_rate_limited_primary_falls_over(monkeypatch) -> None:
    recorder = _Recorder([_http_error(429, {"response": []}), _ok()])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "3"})

    assert response.status_code == 200
    assert recorder.secrets == [PRO_KEY, FREE_KEY]


def test_payload_credential_error_falls_over(monkeypatch) -> None:
    """HTTP 200 但 payload 点名 token 失效，同样属于凭据类失败。"""
    recorder = _Recorder(
        [_FakeResponse(200, {"response": [], "errors": {"token": "invalid"}}), _ok()]
    )
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "4"})

    assert response.status_code == 200
    assert recorder.secrets == [PRO_KEY, FREE_KEY]


def test_pool_exhausted_raises_with_all_slots_named(monkeypatch) -> None:
    recorder = _Recorder([_http_error(401, {}), _http_error(401, {})])
    client = _client(recorder, monkeypatch)

    with pytest.raises(ProviderCredentialPoolExhausted) as excinfo:
        client.request_live("odds", {"fixture": "5"})

    message = str(excinfo.value)
    assert "slot=0" in message and "slot=1" in message
    assert PRO_KEY not in message and FREE_KEY not in message, "异常不得泄露 key 明文"


# ── 反例攻击：这些情况一律不得切换 ─────────────────────────────────────────
def test_bad_request_does_not_fail_over(monkeypatch) -> None:
    """400 是我们的参数/用法有问题，换 key 只会掩盖 bug 并浪费配额。"""
    recorder = _Recorder([_http_error(400, {"response": []})])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "bad"})

    assert response.status_code == 400
    assert recorder.secrets == [PRO_KEY], "400 不得触发备用凭据"


def test_server_error_does_not_fail_over(monkeypatch) -> None:
    recorder = _Recorder([_http_error(503, {"response": []})])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "6"})

    assert response.status_code == 503
    assert recorder.secrets == [PRO_KEY]


def test_transport_error_does_not_fail_over_and_propagates(monkeypatch) -> None:
    recorder = _Recorder([urllib.error.URLError("boom")])
    client = _client(recorder, monkeypatch)

    with pytest.raises(urllib.error.URLError):
        client.request_live("odds", {"fixture": "7"})

    assert recorder.secrets == [PRO_KEY], "传输故障不是凭据问题，不得切换"


def test_non_credential_payload_error_does_not_fail_over(monkeypatch) -> None:
    recorder = _Recorder([_FakeResponse(200, {"response": [], "errors": {"param": "bad"}})])
    client = _client(recorder, monkeypatch)

    response = client.request_live("odds", {"fixture": "8"})

    assert response.status_code == 200
    assert recorder.secrets == [PRO_KEY]
    assert failover_reason(
        status_code=200, payload={"response": [], "errors": {"param": "bad"}}
    ) is None


# ── 配置与泄密攻击 ─────────────────────────────────────────────────────────
def test_duplicate_keys_collapse_to_one_slot() -> None:
    """同一把 key 占两个 slot 是「假切换」：切过去还是同一份配额。"""
    assert parse_credentials(f"{PRO_KEY},{PRO_KEY},{FREE_KEY}") == (PRO_KEY, FREE_KEY)


def test_legacy_single_key_used_when_pool_env_absent(monkeypatch) -> None:
    monkeypatch.delenv(CREDENTIALS_ENV, raising=False)
    monkeypatch.setenv(LEGACY_CREDENTIALS_ENV, PRO_KEY)

    pool = credential_pool_from_env()

    assert pool.size == 1
    assert pool.credentials[0].secret == PRO_KEY


def test_explicit_empty_pool_does_not_fall_back_to_legacy(monkeypatch) -> None:
    """池变量存在但解析为空 = 配置错误，必须失败关闭，不得静默用历史单 key。"""
    monkeypatch.setenv(CREDENTIALS_ENV, " , ")
    monkeypatch.setenv(LEGACY_CREDENTIALS_ENV, PRO_KEY)

    assert credential_pool_from_env().size == 0


def test_empty_pool_fails_closed_before_transport(monkeypatch) -> None:
    recorder = _Recorder([_ok()])
    client = _client(recorder, monkeypatch, keys="")
    monkeypatch.delenv(LEGACY_CREDENTIALS_ENV, raising=False)

    with pytest.raises(LiveNetworkDisabledError, match="credential is not visible"):
        client.request_live("odds", {"fixture": "9"})

    assert recorder.secrets == [], "空池不得发起任何请求"


def test_credentials_never_render_in_plain_text() -> None:
    credential = ProviderCredential(slot=0, secret=PRO_KEY)
    pool = ProviderCredentialPool(credentials=(credential,))

    for rendered in (repr(credential), str(credential), repr(pool), str(pool)):
        assert PRO_KEY not in rendered, f"渲染结果泄露了 key: {rendered}"
    # 凭据本身渲染时给出指纹用于跨日志比对；池渲染只暴露 slot 序号。
    assert "<redacted>" in repr(credential)
    assert credential.fingerprint != PRO_KEY
    assert credential.fingerprint in repr(credential)
    assert "slots=[0]" in repr(pool)
