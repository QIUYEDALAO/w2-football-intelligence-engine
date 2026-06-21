from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from w2.operations.observability import redact


class Role(StrEnum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


RBAC_PERMISSIONS = {
    Role.VIEWER: {"read:public"},
    Role.OPERATOR: {"read:public", "read:operations"},
    Role.ADMIN: {"read:public", "read:operations", "read:audit"},
}


ALLOWED_ENV_KEYS = {
    "W2_ENVIRONMENT",
    "W2_DATABASE_URL",
    "W2_REDIS_URL",
    "W2_FORWARD_HOLDOUT_AUTORUN",
    "W2_FORWARD_HOLDOUT_NETWORK",
}


@dataclass(frozen=True, kw_only=True)
class SecurityPolicy:
    roles: dict[str, set[str]]
    production_ops_enabled: bool = False
    external_notifications_enabled: bool = False
    deepseek_enabled: bool = False
    recommendation_enabled: bool = False
    cors_allowlist: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://staging.w2.local",
    )
    rate_limit_policy: str = "LOCAL_STAGING_ABSTRACTION_ONLY"
    security_headers: tuple[str, ...] = (
        "X-Content-Type-Options: nosniff",
        "X-Frame-Options: DENY",
        "Referrer-Policy: no-referrer",
    )

    def can(self, role: Role, permission: str) -> bool:
        return permission in self.roles[role.value]


def default_security_policy() -> SecurityPolicy:
    return SecurityPolicy(roles={role.value: RBAC_PERMISSIONS[role] for role in Role})


def sanitize_audit_payload(payload: dict[str, str]) -> dict[str, str]:
    return {key: redact(value) for key, value in payload.items() if key in ALLOWED_ENV_KEYS}


def dependency_scan_summary() -> dict[str, str | bool]:
    return {
        "scanner": "static_placeholder",
        "network_used": False,
        "status": "LOCAL_REVIEW_REQUIRED",
    }
