from __future__ import annotations

from dataclasses import asdict, dataclass

FACTOR_SCALE_VERSION = "w2.factor_scale.v1"


@dataclass(frozen=True, kw_only=True)
class FactorScaleParams:
    version: str = FACTOR_SCALE_VERSION
    f3_rest_diff_divisor: float = 4.0
    f6_h2h_diff_divisor: float = 2.0
    f7_elo_diff_divisor: float = 300.0
    supremacy_deadband: float = 0.04
    supremacy_score_per_quarter_line: float = 0.16
    factor_sigma_default: float = 0.10
    factor_sigma_neutral: float = 0.14
    factor_sigma_proxy: float = 0.20
    factor_sigma_unknown: float = 0.25

    def snapshot(self) -> dict[str, float | str]:
        return asdict(self)


DEFAULT_FACTOR_SCALE_PARAMS = FactorScaleParams()
