"""API-Football 凭据池：主号优先，失效/超额自动切备用号。

背景（指令书 I 任务 B）：Pro 账号 2026-10-16 到期，过渡期用 ``Pro + 免费号``
双 key 承载，Pro 失效或超额时自动切到免费号，到期后由免费号独立承载。

设计要点：

* **明文永不出这个模块。** ``ProviderCredential`` 的 ``repr`` 一律打码，
  日志/异常/报表里只会出现 slot 序号与不可逆指纹，不出现 key 本身。
* **只对凭据类失败切换。** 401/403（无效或过期）、429（限流/超额）、以及
  payload 里点名的 key/subscription/quota 类错误才切下一把；网络错误、
  超时、5xx、参数错误一律**不切换**——换一把 key 解决不了，重试只会放大故障、
  把「我们的 bug」伪装成「凭据问题」。
* **失败必须留痕。** 每次切换都把 slot 序号写进该次失败的 error 描述
  （``PROVIDER_HTTP_401:CREDENTIAL_SLOT_0``），因此「主号被拒 → 备用号接管」
  在 ``provider_request_logs`` 里是可查的持久证据，不需要新表。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: 有序凭据列表，逗号分隔，**第一个是主号**。例：``pro_key,free_key``。
CREDENTIALS_ENV = "W2_APIFOOTBALL_KEYS"
#: 单凭据的历史变量，仅在 CREDENTIALS_ENV 未设置时回退使用。
LEGACY_CREDENTIALS_ENV = "W2_API_FOOTBALL_API_KEY"

#: 只有这些状态码代表「这把凭据不可用」，才允许切换。
CREDENTIAL_STATUS_CODES = frozenset({401, 403, 429})

#: payload.errors 里出现这些词才判定为凭据类失败。
_CREDENTIAL_ERROR_KEYWORDS = (
    "token",
    "key",
    "subscription",
    "plan",
    "suspend",
    "expired",
    "quota",
    "rate",
    "limit",
    "requests",
)

REASON_REJECTED = "CREDENTIAL_REJECTED"
REASON_RATE_LIMITED = "CREDENTIAL_RATE_LIMITED"
REASON_POOL_EXHAUSTED = "CREDENTIAL_POOL_EXHAUSTED"


class ProviderCredentialPoolExhausted(RuntimeError):
    """池内所有凭据都不可用。失败关闭：不降级、不重试、不静默放行。"""


@dataclass(frozen=True)
class ProviderCredential:
    slot: int
    secret: str

    @property
    def fingerprint(self) -> str:
        """不可逆指纹，仅用于跨日志比对同一把 key。"""
        return hashlib.sha256(self.secret.encode("utf-8")).hexdigest()[:12]

    def __repr__(self) -> str:
        return (
            f"ProviderCredential(slot={self.slot}, "
            f"fingerprint={self.fingerprint}, secret=<redacted>)"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class ProviderCredentialPool:
    credentials: tuple[ProviderCredential, ...]

    @property
    def size(self) -> int:
        return len(self.credentials)

    def __bool__(self) -> bool:
        return bool(self.credentials)

    def __iter__(self):
        return iter(self.credentials)

    def __repr__(self) -> str:
        slots = [credential.slot for credential in self.credentials]
        return f"ProviderCredentialPool(size={self.size}, slots={slots})"

    __str__ = __repr__


def parse_credentials(raw: str) -> tuple[str, ...]:
    """解析逗号分隔凭据串。

    **重复的 key 会被丢弃**：同一把 key 占两个 slot 是「假切换」——切过去仍然
    是同一个账号、同一份配额，会让超额诊断彻底失真。
    """
    seen: set[str] = set()
    parsed: list[str] = []
    for chunk in raw.split(","):
        secret = chunk.strip()
        if not secret or secret in seen:
            continue
        seen.add(secret)
        parsed.append(secret)
    return tuple(parsed)


def credential_pool_from_env(
    env: Mapping[str, str] | None = None,
) -> ProviderCredentialPool:
    """从环境变量构造凭据池。

    变量存在但解析后为空（例如 ``W2_APIFOOTBALL_KEYS=","``）时**不静默回退**
    到历史单凭据变量：那会让「池配错了」表现成「池是好的」，属于把配置错误
    悄悄放行。此处直接返回空池，由调用方失败关闭。
    """
    source = os.environ if env is None else env
    if CREDENTIALS_ENV in source:
        secrets = parse_credentials(str(source.get(CREDENTIALS_ENV) or ""))
    else:
        legacy = str(source.get(LEGACY_CREDENTIALS_ENV) or "").strip()
        secrets = (legacy,) if legacy else ()
    return ProviderCredentialPool(
        credentials=tuple(
            ProviderCredential(slot=index, secret=secret)
            for index, secret in enumerate(secrets)
        )
    )


def primary_credential(env: Mapping[str, str] | None = None) -> str | None:
    """当前应当用于「单次探测 / 就绪判断」的主凭据。

    池化之后，只看历史单变量会在只配了 ``W2_APIFOOTBALL_KEYS`` 的部署里
    报出「凭据不可见」，把就绪检查挡死在假阴性上。这里给出唯一权威：
    池内第一把优先，没有池才回退历史单变量。
    """
    pool = credential_pool_from_env(env)
    if pool.size:
        return pool.credentials[0].secret
    source = os.environ if env is None else env
    legacy = str(source.get(LEGACY_CREDENTIALS_ENV) or "").strip()
    return legacy or None


def _payload_credential_reason(payload: Any) -> str | None:
    """从 ``payload.errors`` 判定凭据类失败。

    **键名也要查**：API-Football 把类别放在键上、把说明放在值上
    （``{"token": "Invalid API key"}``、``{"requests": "reached the limit"}``）。
    只看值会漏掉 ``{"token": "invalid"}`` 这类写法——类别在键、值里没有任何关键词。
    """
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if isinstance(errors, dict):
        texts = [str(key) for key in errors if key]
        texts.extend(str(value) for value in errors.values() if value)
    elif isinstance(errors, list):
        texts = [str(value) for value in errors if value]
    else:
        texts = []
    for text in texts:
        lowered = text.lower()
        if any(keyword in lowered for keyword in _CREDENTIAL_ERROR_KEYWORDS):
            return REASON_REJECTED
    return None


def failover_reason(*, status_code: int | None, payload: Any) -> str | None:
    """判定这次响应是否属于「换下一把凭据就能改善」的失败。

    返回原因字符串表示应当切换；返回 ``None`` 表示**不得切换**——
    此时调用方应按原样把失败暴露出去。
    """
    if status_code in CREDENTIAL_STATUS_CODES:
        if status_code == 429:
            return REASON_RATE_LIMITED
        return REASON_REJECTED
    if status_code is not None and status_code >= 400:
        # 400/404/422 等是我们的请求有问题，换 key 无意义。
        return None
    return _payload_credential_reason(payload)


def credential_failure_error(*, status_code: int | None, reason: str, slot: int) -> str:
    """把 slot 写进失败描述，作为「主号被拒 → 备用号接管」的持久证据。"""
    prefix = f"PROVIDER_HTTP_{status_code}" if status_code is not None else "PROVIDER_ERROR"
    return f"{prefix}:{reason}:CREDENTIAL_SLOT_{slot}"
