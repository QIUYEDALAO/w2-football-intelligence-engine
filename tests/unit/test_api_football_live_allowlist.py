from __future__ import annotations

import pytest

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError


def test_api_football_live_endpoint_allowlist_blocks_unapproved_endpoint() -> None:
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics", "lineups", "injuries"}),
    )

    with pytest.raises(LiveNetworkDisabledError, match="live endpoint not approved: odds"):
        client.request_live("odds", {"fixture": "1489404"})
