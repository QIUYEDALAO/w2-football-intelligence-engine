from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.providers.quota import parse_api_football_quota


class ProviderRequestLedger(Protocol):
    def record_request(
        self,
        *,
        provider: str,
        endpoint: str,
        params: dict[str, str],
        live: bool,
        status_code: int | None,
        requested_at: datetime,
        completed_at: datetime,
        headers: dict[str, str],
        payload: dict[str, Any],
        error: str | None = None,
    ) -> None:
        pass


def provider_request_hash(
    *,
    endpoint: str,
    params: dict[str, str],
    requested_at: datetime | None = None,
) -> str:
    payload = json.dumps(
        {
            "endpoint": endpoint,
            "params": params,
            "requested_at": (
                requested_at.astimezone(UTC).isoformat()
                if requested_at is not None
                else None
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DbProviderRequestLedger:
    def record_request(
        self,
        *,
        provider: str,
        endpoint: str,
        params: dict[str, str],
        live: bool,
        status_code: int | None,
        requested_at: datetime,
        completed_at: datetime,
        headers: dict[str, str],
        payload: dict[str, Any],
        error: str | None = None,
    ) -> None:
        engine = create_engine()
        request_hash = provider_request_hash(
            endpoint=endpoint,
            params=params,
            requested_at=requested_at,
        )
        with Session(engine) as session:
            session.add(
                ProviderRequestLogModel(
                    ingestion_run_id=None,
                    provider=provider,
                    endpoint=endpoint,
                    request_hash=request_hash,
                    live=live,
                    status_code=status_code,
                    requested_at=requested_at.astimezone(UTC),
                    completed_at=completed_at.astimezone(UTC),
                    error=error,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            except Exception:
                session.rollback()
                raise
        quota = parse_api_football_quota(
            headers=headers,
            payload=payload,
            observed_at=completed_at,
        )
        if quota.daily_remaining is not None and quota.daily_limit is not None:
            window_start = completed_at.astimezone(UTC).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            window_end = window_start + timedelta(days=1)
            used = max(quota.daily_limit - quota.daily_remaining, 0)
            with Session(engine) as session:
                existing = session.scalar(
                    select(QuotaUsageModel).where(
                        QuotaUsageModel.provider == provider,
                        QuotaUsageModel.endpoint == endpoint,
                        QuotaUsageModel.window_start == window_start,
                    )
                )
                if existing is None:
                    session.add(
                        QuotaUsageModel(
                            provider=provider,
                            endpoint=endpoint,
                            used=used,
                            limit=quota.daily_limit,
                            window_start=window_start,
                            window_end=window_end,
                        )
                    )
                else:
                    existing.used = max(existing.used, used)
                    existing.limit = quota.daily_limit
                    existing.window_end = window_end
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                    raise


def provider_request_ledger_from_env() -> ProviderRequestLedger | None:
    if os.environ.get("W2_PROVIDER_REQUEST_LEDGER_ENABLED", "false").lower() != "true":
        return None
    return DbProviderRequestLedger()
