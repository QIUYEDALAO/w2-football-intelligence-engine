from __future__ import annotations

import csv
import gzip
import hashlib
import io
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.lineups.intelligence import normalize_player_name

TRANSFERMARKT_R2_ROOT = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"


@dataclass(frozen=True, kw_only=True)
class TransfermarktSnapshot:
    source_url: str
    source_sha256: str
    observed_at: datetime
    rows: tuple[dict[str, Any], ...]


def load_player_snapshot(
    *,
    observed_at: datetime,
    compressed: bytes | None = None,
    allow_network: bool = False,
) -> TransfermarktSnapshot:
    source_url = f"{TRANSFERMARKT_R2_ROOT}/players.csv.gz"
    if compressed is None and not allow_network:
        raise ValueError("TRANSFERMARKT_NETWORK_REQUIRES_EXPLICIT_--live")
    payload = compressed if compressed is not None else _download(source_url)
    reader = csv.DictReader(
        io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(payload)), encoding="utf-8")
    )
    source_hash = hashlib.sha256(payload).hexdigest()
    rows: list[dict[str, Any]] = []
    for row in reader:
        player_id = str(row.get("player_id") or "")
        name = str(row.get("name") or "")
        if not player_id or not name:
            continue
        rows.append(
            {
                "transfermarkt_player_id": player_id,
                "player_name": name,
                "normalized_name": normalize_player_name(name),
                "current_club_id": _optional_text(row.get("current_club_id")),
                "current_club_name": _optional_text(row.get("current_club_name")),
                "competition_code": _optional_text(row.get("current_club_domestic_competition_id")),
                "position": _optional_text(row.get("position")),
                "sub_position": _optional_text(row.get("sub_position")),
                "market_value_eur": _decimal(row.get("market_value_in_eur")),
                "source_sha256": source_hash,
                "observed_at": observed_at.astimezone(UTC),
            }
        )
    return TransfermarktSnapshot(
        source_url=source_url,
        source_sha256=source_hash,
        observed_at=observed_at.astimezone(UTC),
        rows=tuple(rows),
    )


def _download(url: str) -> bytes:
    if not url.startswith(f"{TRANSFERMARKT_R2_ROOT}/"):
        raise ValueError("TRANSFERMARKT_SOURCE_URL_NOT_ALLOWED")
    request = urllib.request.Request(  # noqa: S310 - fixed HTTPS host checked above
        url,
        headers={"User-Agent": "W2-offline-transfermarkt-import/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - checked
        payload = response.read()
    if not isinstance(payload, bytes):
        raise ValueError("TRANSFERMARKT_SOURCE_RESPONSE_INVALID")
    return payload


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if str(value or "").strip() else None
    except InvalidOperation:
        return None
