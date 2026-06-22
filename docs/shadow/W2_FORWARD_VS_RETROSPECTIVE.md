# W2 Forward vs Retrospective Shadow Evidence

Forward shadow evidence is created before kickoff from legal captured snapshots
and append-only locks. Retrospective replay is marked `RETROSPECTIVE_REPLAY` and
is used for reproducibility, hard-gate, settlement, and threshold sensitivity
checks only.

Gate5 review requires the pre-registered forward target sample count from
`config/policies/gate5_shadow_acceptance.v1.json`. Retrospective rows never
increase that forward sample count.
