# W2 Market Mainline Ladder Audit

- Source SHA: `ea81f9cf6ff23b763564ca044b3f80a7e736c5ed`
- Fixtures: `14` (`8` source ready, `6` source absent)
- Observations: `33999`
- Mode: `READ_ONLY_NO_PROVIDER_NO_DB_WRITE`

| Fixture | Pre-fix V3 | Pre-fix selected | New AH mainline | New OU mainline |
|---|---|---|---:|---:|
| 1494217 | ANALYSIS_PICK | TOTALS UNDER 3.5 @1.7 | 1.25 | 3.25 |
| 1494218 | ANALYSIS_PICK | TOTALS OVER 2.5 @1.7 | 0.75 | 2.75 |
| 1494219 | NOT_READY | - | -1.5 | 3.0 |
| 1494220 | ANALYSIS_PICK | TOTALS UNDER 3.5 @1.67 | -0.5 | 3.0 |
| 1494221 | NO_EDGE | - | -0.25 | 2.5 |
| 1494222 | ANALYSIS_PICK | TOTALS OVER 2.5 @1.68 | -0.5 | 2.75 |
| 1494223 | ANALYSIS_PICK | TOTALS UNDER 3.5 @1.68 | -1.0 | 3.25 |
| 1494224 | NO_EDGE | - | -1.0 | 3.0 |
| 1494225 | NOT_READY | - | - | - |
| 1494226 | NOT_READY | - | - | - |
| 1494227 | NOT_READY | - | - | - |
| 1494230 | NOT_READY | - | - | - |
| 1494231 | NOT_READY | - | - | - |
| 1494232 | NOT_READY | - | - | - |

## Frozen Findings

- `1494218` contains a complete `2.75` line from 6 bookmakers: median O/U `1.875/1.865`, devig `0.498663/0.501337`, balance distance `0.001337`.
- Its old `2.5` line had 8 complete pairs but median O/U `1.70/2.11`, balance distance `0.053806`.
- The old line was selected by strict max complete-pair count. The new one-book-one-vote authority selects `2.75`.
- The five old TOTALS picks require fresh recomputation; this audit does not preserve a target pick count.

Audit hash: `bab9671cf2fb780798dd36fdfcd6110d128703c09f6c497aa18f269192ab49c0`
