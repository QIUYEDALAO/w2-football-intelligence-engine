"""Football-API ``/status`` 免费只读查询——Dashboard「采集额度」实时显示的唯一豁免点。

架构边界（红线，禁止放松）：
- api 后端【只允许】调用 Football-API ``/status``（免费只读），绝不允许调用任何数据采集
  端点（fixtures / statistics / odds / lineups / players 等）。本模块是该豁免的**唯一**实现：
  它**不复用** ``ApiFootballClient.request_live``（那条链受采集闸门 ``allow_live`` /
  ``W2_PROVIDER_CALLS_DISABLED`` / ``W2_PROVIDER_ENDPOINT_ALLOWLIST`` 约束，且会写入
  Provider 请求账本、计入 billable 统计），而是独立、硬编码只请求 ``/status`` 的最小
  只读实现——从代码层面杜绝越界调用任何采集端点。
- 「只读·不调用 Provider」语义保留：本查询**不触发任何数据采集**，只读账号额度状态。
  api-sports.io 明确 ``/status`` 免费，实测连续两次查询 ``requests.current`` 不变
  （不消耗额度）。因此本查询也不写 Provider 请求账本。
- fail-closed：超时 / 网络 / HTTP / 解析错误一律返回 ``degraded=True`` 且额度字段全
  ``None``，绝不伪造额度数字；由调用方回退读 ``read_model_checkpoint`` 的 provider_status
  缓存并打「缓存」标记。

真实响应结构（2026-10-08 实测）：:

    {"response": {"account": {...},
                  "subscription": {"plan": "Pro",
                                   "end": "2026-10-16T16:10:05+00:00",
                                   "active": true},
                  "requests": {"current": 3128, "limit_day": 7500}}}

注意：真实字段是 ``requests.current``（已用）与 ``requests.limit_day``（日限），
**没有** ``requests.remaining``——这正是旧口径 ``parse_api_football_quota`` 读
``response.requests.remaining`` 恒为 ``None`` 导致 QUOTA_UNKNOWN 的根因。
本模块用 ``remaining = limit_day - current`` 计算剩余额度。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from w2.providers.key_pool import primary_credential

STATUS_BASE_URL = "https://v3.football.api-sports.io"
STATUS_PATH = "status"
# 凭据来源的权威在 w2.providers.key_pool（池内第一把优先，否则回退历史单变量）。
STATUS_AUTH_HEADER = "x-apisports-key"
# Dashboard 刷新路径上的只读查询，短超时避免拖垮面板；失败即降级缓存。
STATUS_TIMEOUT_SECONDS = 8.0
# /status 免费只读查询的进程内缓存 TTL（秒）——system_health 与 /v1/provider/quota
# 共用同一缓存，避免每次请求都同步外呼 /status（免费，但外呼仍有网络延迟）。
STATUS_QUOTA_TTL_SECONDS = 60.0
_status_quota_cache: dict[str, Any] = {}


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _transport_error(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "PROVIDER_TIMEOUT"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            return "PROVIDER_TIMEOUT"
        return "PROVIDER_URL_ERROR"
    return "PROVIDER_CONNECTION_ERROR"


def parse_status_quota(payload: dict[str, Any]) -> dict[str, Any]:
    """从 ``/status`` 响应解析额度字段；缺失/类型不符一律 ``None``（不造假）。"""
    if not isinstance(payload, dict):
        return {
            "current": None,
            "limit_day": None,
            "remaining": None,
            "plan": None,
            "plan_end": None,
        }
    response = payload.get("response")
    response = response if isinstance(response, dict) else {}
    requests = response.get("requests")
    requests = requests if isinstance(requests, dict) else {}
    subscription = response.get("subscription")
    subscription = subscription if isinstance(subscription, dict) else {}
    current = _parse_int(requests.get("current"))
    limit_day = _parse_int(requests.get("limit_day"))
    remaining = (
        limit_day - current
        if current is not None and limit_day is not None
        else None
    )
    plan = subscription.get("plan")
    plan_end = subscription.get("end")
    return {
        "current": current,
        "limit_day": limit_day,
        "remaining": remaining,
        "plan": plan if isinstance(plan, str) else None,
        "plan_end": plan_end if isinstance(plan_end, str) else None,
    }


def fetch_provider_quota_live() -> dict[str, Any]:
    """实时查询 Football-API ``/status`` 额度；失败返回 ``degraded=True`` + 空字段。"""
    observed_at = datetime.now(UTC)
    degraded_base: dict[str, Any] = {
        "source": "cache",
        "degraded": True,
        "error": None,
        "current": None,
        "limit_day": None,
        "remaining": None,
        "plan": None,
        "plan_end": None,
        "observed_at": observed_at.isoformat(),
    }
    api_key = primary_credential()
    if not api_key:
        degraded_base["error"] = "PROVIDER_CREDENTIAL_MISSING"
        return degraded_base

    request = urllib.request.Request(  # noqa: S310
        f"{STATUS_BASE_URL}/{STATUS_PATH}",
        headers={STATUS_AUTH_HEADER: api_key},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            request,
            timeout=STATUS_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read()
            status_code = response.status
    except urllib.error.HTTPError as exc:
        degraded_base["error"] = f"PROVIDER_HTTP_{exc.code}"
        return degraded_base
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        degraded_base["error"] = _transport_error(exc)
        return degraded_base

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        degraded_base["error"] = "PROVIDER_RESPONSE_DECODE_ERROR"
        return degraded_base

    if status_code >= 400:
        degraded_base["error"] = f"PROVIDER_HTTP_{status_code}"
        return degraded_base

    parsed = parse_status_quota(payload)
    # 关键字段解析不到（结构漂移）→ 视为 degraded，不返回半真数据。
    if parsed["current"] is None or parsed["limit_day"] is None:
        degraded_base["error"] = "PROVIDER_STATUS_SCHEMA_DRIFT"
        return degraded_base

    return {
        "source": "live",
        "degraded": False,
        "error": None,
        **parsed,
        "observed_at": observed_at.isoformat(),
    }


def fetch_provider_quota_live_cached() -> dict[str, Any]:
    """实时 /status 查询加短 TTL（60s）——进程内共享缓存，避免重复外呼。

    system_health 与 /v1/provider/quota 两处统一复用此函数：TTL 内互相命中缓存，
    不重复外呼 /status；缓存过期后重新外呼。
    """
    now = time.monotonic()
    cached_ts = _status_quota_cache.get("ts")
    if cached_ts is not None and now - cached_ts < STATUS_QUOTA_TTL_SECONDS:
        return _status_quota_cache["result"]
    result = fetch_provider_quota_live()
    _status_quota_cache["ts"] = now
    _status_quota_cache["result"] = result
    return result
