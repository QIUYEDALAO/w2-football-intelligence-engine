"""FootyStats Provider 适配器（指令书 I 任务 A）。

只做三件事：发请求、按 canonical sha256 留档原始响应、记配额账。

边界：

* 这是 FootyStats **专用**适配器，不是通用 HTTP 传输层（AGENTS.md 禁止造第二个）；
* 全部序列化/hash 走 ``w2.domain.canonical_serialization``，本模块没有
  ``json.dumps``、没有 ``hashlib``——canonical authority 静态守卫据此判定；
* API key 只从进程环境读，绝不落库、绝不进入 ``RequestLog.request_params``，
  也绝不出现在异常文本里。

配额：FootyStats 回传 ``metadata.request_limit`` / ``request_remaining``。
调用前用**上一次观测到的** remaining 做闸门，保留 ``QUOTA_RESERVE_RATIO``
余量；剩余不足时拒绝发请求而不是把额度打空。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)
from w2.quant_research.footystats_shadow_models import (
    SHADOW_CONTRACT_VERSION,
    FsRawPayloadModel,
    FsRequestLogModel,
)

#: F1R-B 的同一条理由：quant 域尚不存在，新增一个就要改生产模块。
#: 域字符串显式写进 preimage，将来引入 quant 域是一次可见的身份变更。
HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
SERIALIZER_VERSION = str(CURRENT_SERIALIZER_VERSION)

FOOTYSTATS_BASE_URL = "https://api.football-data-api.com"
FOOTYSTATS_KEY_ENV = "W2_FOOTYSTATS_API_KEY"
RAW_PAYLOAD_CONTRACT = "w2.footystats_raw_payload.v1"

#: 只允许这四个端点：不在白名单里的端点 fail closed，而不是拼个 URL 就打出去。
ALLOWED_ENDPOINTS = frozenset(
    {"league-list", "league-matches", "todays-matches", "match"}
)
#: 留 20% 余量（1800/小时 ⇒ 触线 1440 即停）。
QUOTA_RESERVE_RATIO = 0.2


class FootyStatsError(RuntimeError):
    """带机器可读 code 的拒绝。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class FootyStatsCredentialMissing(FootyStatsError):
    def __init__(self, env_name: str) -> None:
        super().__init__("FOOTYSTATS_CREDENTIAL_NOT_VISIBLE", env_name)


class FootyStatsQuotaExhausted(FootyStatsError):
    def __init__(self, remaining: int, limit: int, floor: int) -> None:
        super().__init__(
            "FOOTYSTATS_QUOTA_RESERVE_REACHED",
            f"remaining={remaining} limit={limit} floor={floor}",
        )


def raw_payload_sha256(payload: Any) -> str:
    """一份原始响应的 canonical 内容哈希（去重键）。"""
    return canonical_sha256(
        {
            "contract": RAW_PAYLOAD_CONTRACT,
            "hash_domain": str(HASH_DOMAIN),
            "serializer_version": SERIALIZER_VERSION,
            "payload": payload,
        },
        domain=HASH_DOMAIN,
    )


@dataclass(frozen=True)
class FootyStatsResponse:
    endpoint: str
    params: dict[str, str]
    payload: dict[str, Any]
    status_code: int
    payload_sha256: str
    body: str
    byte_size: int
    request_limit: int | None
    request_remaining: int | None

    @property
    def rows(self) -> list[dict[str, Any]]:
        data = self.payload.get("data")
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


class FootyStatsClient:
    """FootyStats 只读采集客户端。

    ``engine`` 是旁路表所在库；本类只写 ``fs_request_log`` / ``fs_raw_payload``。
    """

    def __init__(
        self,
        engine: Engine,
        *,
        key_env: str = FOOTYSTATS_KEY_ENV,
        base_url: str = FOOTYSTATS_BASE_URL,
        timeout_seconds: float = 60.0,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._key_env = key_env
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._opener = opener
        self._now = now or (lambda: datetime.now(UTC))

    # ── 配额 ────────────────────────────────────────────────────────────────
    def quota_state(self) -> tuple[int | None, int | None]:
        """返回 (limit, remaining)：最近一次观测到的 Provider 配额。"""
        with Session(self._engine) as session:
            row = session.execute(
                select(FsRequestLogModel.request_limit, FsRequestLogModel.request_remaining)
                .where(FsRequestLogModel.payload_sha256.is_not(None))
                .order_by(FsRequestLogModel.requested_at.desc())
                .limit(1)
            ).first()
        return (row[0], row[1]) if row else (None, None)

    def _assert_quota_headroom(self) -> None:
        limit, remaining = self.quota_state()
        if limit is None or remaining is None:
            return
        floor = int(limit * QUOTA_RESERVE_RATIO)
        if remaining <= floor:
            raise FootyStatsQuotaExhausted(remaining, limit, floor)

    # ── 请求 ────────────────────────────────────────────────────────────────
    def _api_key(self) -> str:
        key = os.environ.get(self._key_env, "").strip()
        if not key:
            raise FootyStatsCredentialMissing(self._key_env)
        return key

    def _fetch(self, url: str) -> tuple[int, str]:
        # URL 由本类用固定 base_url 拼成，不接受调用方传入；scheme 仍然显式限定，
        # 免得 base_url 被改成一个 file:/ 自定义 scheme 时静默生效。
        if not url.startswith("https://"):
            raise FootyStatsError("FOOTYSTATS_URL_SCHEME_NOT_HTTPS", url.split("?", 1)[0])
        request = urllib.request.Request(  # noqa: S310
            url, headers={"Accept": "application/json"}
        )
        if self._opener is not None:
            with self._opener(request, self._timeout) as response:
                raw = response.read()
                return int(getattr(response, "status", 200)), raw.decode("utf-8", "replace")
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            return int(response.status), response.read().decode("utf-8", "replace")

    def request(self, endpoint: str, params: dict[str, str] | None = None) -> FootyStatsResponse:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise FootyStatsError("FOOTYSTATS_ENDPOINT_NOT_ALLOWED", endpoint)
        resolved_params = {str(k): str(v) for k, v in (params or {}).items()}
        # 先做配额闸门再做凭证读取：没有余量就不该把 key 拿出来用。
        self._assert_quota_headroom()
        key = self._api_key()
        query = urllib.parse.urlencode({**resolved_params, "key": key})
        url = f"{self._base_url}/{endpoint}?{query}"
        requested_at = self._now()

        try:
            status_code, body = self._fetch(url)
        except urllib.error.HTTPError as error:
            self._record_failure(
                endpoint, resolved_params, requested_at, int(error.code), "HTTP_ERROR"
            )
            raise FootyStatsError("FOOTYSTATS_HTTP_ERROR", f"{endpoint}:{error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self._record_failure(
                endpoint, resolved_params, requested_at, 0, type(error).__name__
            )
            raise FootyStatsError("FOOTYSTATS_TRANSPORT_ERROR", endpoint) from error

        try:
            payload = json.loads(body)
        except ValueError as error:
            self._record_failure(
                endpoint, resolved_params, requested_at, status_code, "NON_JSON_BODY"
            )
            raise FootyStatsError("FOOTYSTATS_BODY_NOT_JSON", endpoint) from error
        if not isinstance(payload, dict):
            self._record_failure(
                endpoint, resolved_params, requested_at, status_code, "NON_OBJECT_BODY"
            )
            raise FootyStatsError("FOOTYSTATS_BODY_NOT_OBJECT", endpoint)

        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        limit = _as_int(metadata.get("request_limit"))
        remaining = _as_int(metadata.get("request_remaining"))
        digest = raw_payload_sha256(payload)
        response = FootyStatsResponse(
            endpoint=endpoint,
            params=resolved_params,
            payload=payload,
            status_code=status_code,
            payload_sha256=digest,
            body=body,
            byte_size=len(body.encode("utf-8")),
            request_limit=limit,
            request_remaining=remaining,
        )
        self._record_success(response, requested_at)
        return response

    # ── 落档 ────────────────────────────────────────────────────────────────
    def _record_failure(
        self,
        endpoint: str,
        params: dict[str, str],
        requested_at: datetime,
        status_code: int,
        error_code: str,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                FsRequestLogModel(
                    endpoint=endpoint,
                    request_params=params,
                    requested_at=requested_at,
                    http_status=status_code,
                    payload_sha256=None,
                    byte_size=0,
                    error_code=error_code,
                    contract_version=SHADOW_CONTRACT_VERSION,
                )
            )

    def _record_success(self, response: FootyStatsResponse, requested_at: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                FsRequestLogModel(
                    endpoint=response.endpoint,
                    request_params=response.params,
                    requested_at=requested_at,
                    http_status=response.status_code,
                    request_limit=response.request_limit,
                    request_remaining=response.request_remaining,
                    payload_sha256=response.payload_sha256,
                    byte_size=response.byte_size,
                    error_code=None,
                    contract_version=SHADOW_CONTRACT_VERSION,
                )
            )
            existing = session.get(FsRawPayloadModel, response.payload_sha256)
            if existing is None:
                session.add(
                    FsRawPayloadModel(
                        payload_sha256=response.payload_sha256,
                        endpoint=response.endpoint,
                        body=response.body,
                        byte_size=response.byte_size,
                        first_seen_at=requested_at,
                        last_seen_at=requested_at,
                        observation_count=1,
                    )
                )
            else:
                existing.last_seen_at = requested_at
                existing.observation_count += 1
