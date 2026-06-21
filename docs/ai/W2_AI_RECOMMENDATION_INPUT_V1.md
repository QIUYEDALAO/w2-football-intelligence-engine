# W2 AI Recommendation Input V1

The AI input contains schema_version, request_id, execution_mode, project_gate, fixture, analysis_context, data_quality, market_snapshot, model_snapshot, legal_candidates, evidence_catalog, invalidation_catalog, reference_score_catalog, data_limitation_catalog, and hard_rules.

Market snapshots use First Seen Odds language unless verified opening data exists; `opening_odds` must not appear without real opening data. Legal candidates are system-created and reference actual market/line availability. AH and Totals require line; 1X2 and BTTS line is null. AI may only reference candidate_id, evidence_id, condition_id, and score_id.
