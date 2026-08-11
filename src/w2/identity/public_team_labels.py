from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class PublicTeamLabelAuthorityError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def reviewed_public_team_labels() -> dict[str, str]:
    path = (
        Path(__file__).resolve().parents[3]
        / "config"
        / "identity"
        / "public_team_labels.zh-CN.v1.json"
    )
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        "w2.public-team-labels.zh-CN.v1"
    ):
        raise PublicTeamLabelAuthorityError("PUBLIC_TEAM_LABEL_SCHEMA_INVALID")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise PublicTeamLabelAuthorityError("PUBLIC_TEAM_LABEL_ENTRIES_INVALID")
    labels: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("review_status") != "APPROVED":
            raise PublicTeamLabelAuthorityError("PUBLIC_TEAM_LABEL_REVIEW_INVALID")
        team_id = str(entry.get("w2_team_id") or "").strip()
        label = str(entry.get("public_name") or "").strip()
        if (
            team_id.split(":")[:2] != ["w2", "team"]
            or not any("\u4e00" <= character <= "\u9fff" for character in label)
            or team_id in labels
        ):
            raise PublicTeamLabelAuthorityError("PUBLIC_TEAM_LABEL_ENTRY_INVALID")
        labels[team_id] = label
    return labels
