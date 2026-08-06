# 《W2 竞彩足球量化 · 研究与迭代协议》 v2.3.1

## Repository copy

The project-supplied protocol is preserved verbatim in four ordered parts because the source
is a large context authority:

1. [Part 01 — facts, positioning, sharp markets and system layers](W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1/part-01.md)
2. [Part 02 — data sources, time contracts, metrics and Track 1 gates](W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1/part-02.md)
3. [Part 03 — Phase A/B, statistics and Freeze A/B checklists](W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1/part-03.md)
4. [Part 04 — exclusions, signatures and engineering-boundary inventory](W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1/part-04.md)

```text
PROTOCOL_VERSION = v2.3.1
SOURCE_DATE = 2026-08-05
SOURCE_SHA256 = b724bd3daf37d395966f78514ed1011e1ae95f6507ed959cd7d9d03f584142eb
STATUS_IN_SOURCE = FREEZE_A_CANDIDATE
HHAD_DECISION = OPTION_B
```

## Binding priority

The protocol is the research specification. Repository and runtime facts corrected after
its drafting are governed by:

- [W2 Quant Freeze A0 Binding](../operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md)
- [Quant program machine state](../../QUANT_PROJECT_STATE.yaml)
- [Quant program master checklist](../operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md)

Where the source protocol conflicts with Binding Errata A, the binding has priority.
Freeze A0 authorises offline engineering only. Freeze A1 live collection, Track 1, strategy,
Shadow, risk, portfolio, 2×1 and real-money execution remain unauthorised.
