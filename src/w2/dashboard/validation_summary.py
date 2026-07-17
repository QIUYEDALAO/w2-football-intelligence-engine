from __future__ import annotations

from typing import Any


def validation_summary(performance: dict[str, Any]) -> dict[str, Any]:
    official = _bucket(performance.get("official"))
    analysis_shadow = _bucket(performance.get("analysis_shadow"))
    return {
        "status": "ANALYSIS_ONLY",
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "official": {
            **official,
            "label": _sample_label("official", official["sample_size"]),
        },
        "analysis_shadow": {
            **analysis_shadow,
            "label": _sample_label("analysis_shadow", analysis_shadow["sample_size"]),
        },
        "score_exact": {
            "sample_size": _int(performance.get("score_exact", {}).get("sample_size")),
            "hit_count": _int(performance.get("score_exact", {}).get("hit_count")),
            "hit_rate": performance.get("score_exact", {}).get("hit_rate"),
            "label": _sample_label(
                "score_exact",
                _int(performance.get("score_exact", {}).get("sample_size")),
            ),
        },
        "policy": {
            "sample_minimum": 200,
            "push_counts_as_win": False,
            "void_included_in_sample": False,
            "runtime_beats_market_must_remain_false": True,
        },
    }


def _bucket(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return {
        "sample_size": _int(row.get("sample_size")),
        "hit_count": _int(row.get("hit_count")),
        "miss_count": _int(row.get("miss_count")),
        "push_count": _int(row.get("push_count")),
        "void_count": _int(row.get("void_count")),
        "hit_rate": row.get("hit_rate"),
    }


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _sample_label(scope: str, sample_size: int) -> str:
    if sample_size:
        return f"{scope}: {sample_size} settled sample(s)"
    if scope == "official":
        return "official 样本不足，暂不计算命中率"
    if scope == "analysis_shadow":
        return "analysis_shadow 样本不足，暂不计算命中率"
    return "分析参考样本不足，暂不计算命中率"
