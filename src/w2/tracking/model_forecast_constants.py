"""Model forecast ledger 的跨模块共享常量。

这些常量被 ``w2.tracking.forward_evidence`` 与 ``w2.tracking.model_forecast_ledger``
共用。它们只依赖 ``w2.domain``（canonical authority），不依赖 ``w2.ingestion``，
因此 API 入口可安全 import 而不把 read-time computation 包带进传递 import 图。
"""
from __future__ import annotations

from w2.domain.canonical_serialization import HashDomain

MODEL_FAMILY = "EXACT_DC_POISSON"
MODEL_FORECAST_CAPTURE_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
MODEL_FORECAST_OUTCOME_HASH_DOMAIN = HashDomain.OUTCOME_LEDGER_PAYLOAD
MODEL_FORECAST_XG_IDENTITY_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY
MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
