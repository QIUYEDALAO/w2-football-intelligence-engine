# W2 Tournament Operations V1

Core objects:

- `TournamentProfile`
- `TournamentStage`
- `GroupDefinition`
- `KnockoutRound`
- `QualificationRule`
- `MatchContext`
- `MatchImportanceContext`
- `OperationsSchedule`

The model is configuration-driven. Runtime code loads competition profiles from
`config/competitions/*.json` and produces per-fixture operations plans.

Result semantics:

- Group matches use 90-minute result semantics.
- Knockout matches separate 90-minute, extra-time, and penalty information.
- Settlement and model evaluation must preserve that separation.

Context policy:

- group standings context
- qualification state
- must-win / draw-sufficient
- eliminated / qualified
- knockout path
- rest days
- host context

All Stage 13A context is `EXPLANATORY_ONLY_UNVALIDATED` and
`model_feature_enabled=false`.
