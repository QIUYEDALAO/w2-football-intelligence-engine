# W2 AI Recommendation Output V1

DeepSeek output contains decision, selected_candidate_id, confidence_score, risk_level, market_relation, Chinese headline/summary/match read/market read, supporting reasons, counterarguments, rejected alternatives, reference score IDs, invalidation condition IDs, data limitation IDs, watch reason, and skip reason.

RECOMMEND requires an ELIGIBLE selected candidate, at least two supporting reasons, at least one counterargument, at least one rejected alternative when available, at least two invalidation conditions including price/line and data/lineup/market status. WATCH cannot create an official recommendation. SKIP must have no selected candidate.

AI free text cannot introduce new odds, lines, probabilities, expected goals, bookmaker counts, scorelines, timestamps, or player facts. Those are copied later by system card projection.
