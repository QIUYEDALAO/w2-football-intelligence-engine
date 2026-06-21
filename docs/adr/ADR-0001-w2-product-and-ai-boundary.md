# ADR-0001 W2 Product And AI Boundary

Status: Accepted for Stage 1 contract.

W2 is rebuilt rather than extended from W1 because W1 is frozen as Legacy, uses local JSON/static Dashboard architecture, mixes runtime concerns, and carries historical coupling that should not become production architecture. Stage 1 freezes product boundaries first so later engineering work does not accidentally encode ambiguous recommendation, state, or AI authority rules.

Decision, Lifecycle, and Data state are separate because LOCKED/SETTLED are not recommendation decisions, and data readiness must gate recommendations independently. A match can have at most one official primary recommendation to preserve auditability. WATCH and SKIP still receive full cards so absence of a recommendation remains explainable rather than hidden.

Exact score is only a reference scenario because W2 Stage 1 supports 1X2, Asian Handicap, and Totals as formal markets. DeepSeek may only choose legal candidates; it may not create lines, odds, probabilities, facts, or candidates. Reasons must cite evidence IDs so AI language remains tied to system facts. Gate 4 is required before real RECOMMEND in shadow, and Gate 5 before production publishing.

W2 does not initialize Git or dependencies in this stage because this package is contract-only. W2 does not inherit W1 `independent_edge`, default AGREE-market behavior, or W1 runtime code. W1 is read-only reference.
