from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from w2.config import get_settings


class PublicCompetitionLabelAuthorityError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def public_competition_labels() -> dict[str, str]:
    """The single authority for public Chinese competition names.

    Mirrors the Dashboard's ``CANONICAL_COMPETITION_LABELS`` so the notification
    flows render the same Chinese league names the Dashboard shows, without each
    flow maintaining its own name table.
    """
    path = (
        get_settings().readiness_config_path
        / "identity"
        / "public_competition_labels.zh-CN.v1.json"
    )
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        "w2.public-competition-labels.zh-CN.v1"
    ):
        raise PublicCompetitionLabelAuthorityError("PUBLIC_COMPETITION_LABEL_SCHEMA_INVALID")
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        raise PublicCompetitionLabelAuthorityError("PUBLIC_COMPETITION_LABEL_ENTRIES_INVALID")
    labels: dict[str, str] = {}
    for key, value in entries.items():
        competition_id = str(key).strip()
        label = str(value).strip()
        if competition_id and label:
            labels[competition_id] = label
    return labels
