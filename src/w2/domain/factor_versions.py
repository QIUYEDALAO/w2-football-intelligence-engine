"""Per-factor computation version authority for the four AH scoring factors.

One business fact has one versioned computation authority. Before this module
the AH factor builders had none. `config/factors/factor_registry.v1.json`
carries a governance `version` used for lifecycle decisions, but it says
nothing about which algorithm produced a score, so a consumer recording a
factor observation had no way to name the computation it was recording and no
way to notice when that computation changed underneath it.

The version names the algorithm the builder actually runs, not the release it
shipped in. It is deliberately not a commit SHA, a deploy SHA, a build
timestamp or a bare ``v1``: none of those changes when -- and only when -- the
computation changes, which is the one property a computation version needs.

Each declaration is pinned to two facts about its builder:

* ``ready_reason`` -- the reason code the builder emits when it actually
  computes, so the version and the executed algorithm demonstrably name the
  same thing;
* ``builder_source_sha256`` -- SHA-256 of that builder function's own source
  text, so editing the algorithm without revising the version fails a lock
  test rather than silently reusing a stale version.

The pin is per function, not per file, so a change to one factor does not
force a spurious version bump on the others that share a module.

This module holds pure data and imports nothing from `w2.features`; the lock
test does the importing. It is the single mapping -- consumers read it through
``factor_computation_version`` and nobody may keep a second copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

SCHEMA_VERSION: Final = "w2.factor_computation_version.v1"


@dataclass(frozen=True, kw_only=True)
class FactorBuilderBinding:
    """What computation a factor version names, and where that computation is."""

    version: str
    module: str
    builder: str
    ready_reason: str
    builder_source_sha256: str


_BINDINGS: Final = MappingProxyType(
    {
        "F3_REST_FITNESS": FactorBuilderBinding(
            version="w2.factor.f3_rest_fitness.rest_days_diff.v1",
            module="w2.features.team_factors",
            builder="rest_fitness_factor",
            ready_reason="REST_DAYS_DIFF_COMPUTED",
            builder_source_sha256=(
                "6eadf9e79a762cc3e13ee72c30ad5d15948333df0240089e84c5c11a82615e0a"
            ),
        ),
        "F5_RECENT_AH_COVER": FactorBuilderBinding(
            version="w2.factor.f5_recent_ah_cover.settled_cover_rate_diff.v1",
            module="w2.features.team_factors",
            builder="recent_ah_cover_factor",
            ready_reason="SETTLED_AH_COVER_RATE_DIFF",
            builder_source_sha256=(
                "5401ae40553db5bdc356bbbe1c068c87e08f656fb457d88ff472d3bb8664da4a"
            ),
        ),
        "F6_H2H": FactorBuilderBinding(
            version="w2.factor.f6_h2h.mean_goal_diff.v1",
            module="w2.features.team_factors",
            builder="h2h_factor",
            ready_reason="INTERNAL_FIXTURE_H2H_DIFF",
            builder_source_sha256=(
                "fe5c64d6311f3448b3af168c01e11e1964dfe43b6a122984817004adf65c6a5a"
            ),
        ),
        "F9_TRUE_XG": FactorBuilderBinding(
            version="w2.factor.f9_true_xg.rolling_net_xg_diff.v1",
            module="w2.features.live_factors",
            builder="true_xg_factor",
            ready_reason="AS_OF_ROLLING_XG_DIFF",
            builder_source_sha256=(
                "07b2a645092b0ac93b3ebbeb80fd24637ae2cbb2dd8b1a0c406a0dddf2c1873a"
            ),
        ),
    }
)

FACTOR_BUILDER_BINDINGS: Final = _BINDINGS
FACTOR_COMPUTATION_VERSIONS: Final = MappingProxyType(
    {factor_id: binding.version for factor_id, binding in _BINDINGS.items()}
)


class FactorVersionError(KeyError):
    """A factor with no declared computation version. Never defaulted."""


def factor_builder_binding(factor_id: str) -> FactorBuilderBinding:
    """The declared binding, or a refusal."""
    try:
        return _BINDINGS[factor_id]
    except KeyError as exc:
        raise FactorVersionError(f"FACTOR_COMPUTATION_VERSION_UNKNOWN:{factor_id}") from exc


def factor_computation_version(factor_id: str) -> str:
    """The declared computation version, or a refusal.

    Unknown fails closed. A caller that cannot name the computation it ran must
    not be able to fall back to a plausible-looking string.
    """
    return factor_builder_binding(factor_id).version
