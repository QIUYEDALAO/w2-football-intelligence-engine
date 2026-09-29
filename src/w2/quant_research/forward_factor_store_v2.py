"""Runtime AH source port for the unchanged historical F1R-C store contract.

The v2 sink inherits the frozen sink's identity, retry and atomic batch logic.
Only F5's source reference port is extended to the actual settlement table.
"""
from sqlalchemy import select
from w2.infrastructure.persistence.models import RuntimeAhSettlementFactModel


def runtime_source_store(legacy, source_capture_contract):
    class RuntimeSourceStore(legacy.ForwardFactorObservationStore):
        @staticmethod
        def _assert_source_capture_ids_self_consistent(session, payloads):
            runtime, historic = [], []
            for payload in payloads:
                (runtime if payload["factor_id"] == "F5_RECENT_AH_COVER" and
                 payload["participated"] else historic).append(payload)
            if historic:
                legacy.ForwardFactorObservationStore._assert_source_capture_ids_self_consistent(session, historic)
            for payload in runtime:
                ids = sorted(filter(None, str(payload["factor_inputs"].get("source_record_ids", "")).split(",")))
                expected = legacy.contract.canonical_sha256({"contract": source_capture_contract,
                    "factor_id": payload["factor_id"], "record_ids": ids}, domain=legacy.contract.HASH_DOMAIN)
                if payload["source_capture_id"] != "w2.consumed_source_set.v1:" + expected:
                    raise legacy.StoreError("SOURCE_CAPTURE_ID_MISMATCH", payload["factor_id"])
                rows = list(session.scalars(select(RuntimeAhSettlementFactModel).where(
                    RuntimeAhSettlementFactModel.fact_id.in_(ids))))
                if not ids or {row.fact_id for row in rows} != set(ids):
                    raise legacy.StoreError("SOURCE_RECORD_NOT_FOUND", ",".join(ids))
                for row in rows:
                    if not all((row.fact_hash, row.source_set_hash, row.settlement_capture_id,
                                row.settlement_payload_sha256, row.quote_capture_ids, row.quote_payload_sha256s)):
                        raise legacy.StoreError("SOURCE_RECORD_PROVENANCE_INCOMPLETE", row.fact_id)
                    if row.settlement_observed_at is None:
                        raise legacy.StoreError("SOURCE_RECORD_CONTENT_INCOMPLETE", row.fact_id)
    return RuntimeSourceStore
