from __future__ import annotations


def provider_status_label(status: str | None) -> str:
    value = _status(status)
    if value == "READY":
        return "provider 已就绪"
    if value == "PROVIDER_EMPTY":
        return "provider 未返回"
    if value == "PARTIAL":
        return "provider 部分返回"
    if value == "WAITING":
        return "等待 provider 返回"
    return "provider 状态未知"


def lineups_status_label(status: str | None) -> str:
    value = _status(status)
    if value == "READY":
        return "首发已出"
    if value == "PROVIDER_EMPTY":
        return "provider 未返回首发"
    if value == "NOT_REQUESTED":
        return "未到首发请求时点"
    if value == "WAITING":
        return "等待首发"
    return "首发状态未知"


def xg_status_label(status: str | None) -> str:
    value = _status(status)
    if value == "READY":
        return "xG 已就绪"
    if value == "PROVIDER_EMPTY":
        return "xG provider 未返回"
    if value == "INSUFFICIENT_HISTORY":
        return "xG 样本不足"
    if value == "PARTIAL_HISTORY":
        return "xG 历史样本不足"
    if value == "MAPPING_MISSING":
        return "xG 映射缺失"
    if value == "WAITING":
        return "等待 xG"
    return "xG 状态未知"


def _status(status: str | None) -> str:
    return str(status or "UNKNOWN").upper()
