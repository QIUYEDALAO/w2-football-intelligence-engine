# W2 League Model Scope V1

Model and calibration scope hierarchy:

`GLOBAL -> COUNTRY -> LEAGUE -> SEASON -> TEAM`

Rules:

- National-team parameters cannot be directly used for clubs.
- Final league parameters are not shared across leagues.
- Each league has independent calibration and Gate state.
- Stage 14A creates registry and policy only.
- Stage 14A does not retrain, recalibrate, promote, or recommend.
