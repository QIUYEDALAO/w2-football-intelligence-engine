"""F6 H2H 补采 — 第 1 步：查询 API-Football 今日剩余配额（只读 status 调用）。

只读键名，不打印 API key。fail-closed：任何失败即非零退出，不自动重试。
"""
from __future__ import annotations

import json
import sys

from w2.providers.api_football import ApiFootballClient
from w2.providers.quota import parse_api_football_quota


def main() -> int:
    client = ApiFootballClient(allow_live=True)
    response = client.request_live("status", {})
    if response.status_code >= 400:
        print(json.dumps({"status": "error", "http": response.status_code}, ensure_ascii=False))
        return 1
    quota = parse_api_football_quota(
        headers=response.headers,
        payload=response.payload,
        observed_at=response.captured_at,
    )
    requests = {}
    resp = response.payload.get("response")
    if isinstance(resp, dict) and isinstance(resp.get("requests"), dict):
        requests = resp["requests"]
    print(
        json.dumps(
            {
                "status": "ok",
                "daily_remaining": quota.daily_remaining,
                "daily_limit": quota.daily_limit,
                "daily_source": quota.daily_source,
                "daily_limit_source": quota.daily_limit_source,
                "burst_remaining": quota.burst_remaining,
                "burst_limit": quota.burst_limit,
                "requests_body": requests,
            },
            ensure_ascii=False,
        )
    )
    return 0 if quota.daily_remaining is not None else 1


if __name__ == "__main__":
    sys.exit(main())
