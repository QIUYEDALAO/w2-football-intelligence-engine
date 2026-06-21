# W2 Season Rollover V1

Season rollover is generated from local historical fixtures. The dry-run reports
latest completed season, next season, retained teams, removed teams, new teams,
unresolved mappings, provider ID conflicts, season dates, calibration reset
policy, and team-prior carry-forward policy.

Promotion and relegation are never guessed. If the local data cannot confirm
membership changes, the rollover status is `MANUAL_REVIEW_REQUIRED`.
