# W2 Product Charter V2

W2 is a multi-league football analysis system for match screening, multi-factor
analysis, and analysis-grade recommendations.

The product position is:

- combine as-of market movement, team form, goal-rate strength, fitness,
  historical context, model-vs-market comparison, and data-quality checks;
- explain why a match is `SKIP`, `WATCH`, or `ANALYSIS_PICK`;
- show risks, missing data, and invalidation conditions next to every analysis
  lean;
- keep outputs useful for research and operator review without claiming stable
  market-beating edge.

W2 does not claim guaranteed profit, certain wins, daily picks, or stable
outperformance over efficient betting markets. Professional quantitative
operators struggle to beat mature odds consistently; W2 therefore treats market
prices as strong information, not as an easy opponent.

Public output levels are:

- `NOT_READY`: required data or lifecycle state is not ready.
- `SKIP`: default state; no clear analysis lean or insufficient evidence.
- `WATCH`: enough signal to monitor, but below analysis-pick threshold.
- `ANALYSIS_PICK`: an explainable analysis lean with reasons, risk notes, and
  attention level. It is analysis reference only, not a profit guarantee.
- `RECOMMEND`: reserved for separately proven positive expected value. It is
  disabled by default and may remain unused indefinitely.

`candidate=true` and `formal_recommendation=true` remain reserved for a future
market-beating proof path. Analysis cards do not set those flags; an
`ANALYSIS_PICK` is an independent, honest output tier.

Every analysis card must explicitly include: `分析参考，非保证盈利`.
