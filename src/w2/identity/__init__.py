"""Canonical team/player identity authority (ARCH-P1-03).

The single public entry for resolving canonical W2 identities. Runtime code must
resolve identity through :class:`CanonicalIdentityRepository` rather than reading
the legacy crosswalk tables or constructing canonical IDs from provider IDs.
"""

from __future__ import annotations

from w2.identity.canonical_identity_repository import CanonicalIdentityRepository

__all__ = ["CanonicalIdentityRepository"]
