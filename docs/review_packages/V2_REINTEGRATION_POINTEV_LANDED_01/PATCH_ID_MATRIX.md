# POINT-EV patch equivalence

`git patch-id --stable` was computed independently for each commit in each pair.

| V2-side commit | deployed commit | stable patch id | result |
|---|---|---|---|
| `1f0a689f` | `6fccdfaa` | `2bb28bd9259a3c7c14aecce6a2e3430ac25d5818` | EQUIVALENT |
| `19c6bd2c` | `b97acfed` | `29efda2f9f08e605e9a2e8f20faa6edc1134fd45` | EQUIVALENT |
| `238d04b1` | `eba0d9e1` | `668049e389faee1d6fb67ccd882d76a16d4151f9` | EQUIVALENT |
| `2b4751c6` | `9f672f8a` | `730359e91afc2dfcda3f1bfad5e24c7fe02b6321` | EQUIVALENT |

The merge retained the deployed first-parent implementation. The final tree has no
second calibration authority or duplicated POINT-EV implementation. The only
post-baseline POINT-EV-area source changes restrict legacy identity construction to
frozen-read compatibility and add direct safety tests.
