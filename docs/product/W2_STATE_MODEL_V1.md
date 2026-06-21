# W2 State Model V1

W2 uses three orthogonal statuses.

DecisionStatus: NOT_READY, SKIP, WATCH, CANDIDATE, RECOMMEND. New matches start NOT_READY. Evaluated matches with no valid candidate become SKIP. CANDIDATE is a system state; DeepSeek cannot invent it. DeepSeek may choose only RECOMMEND, WATCH, or SKIP.

LifecycleStatus: DRAFT, ACTIVE, LOCKED, SUPERSEDED, VOID, SETTLED. LOCKED and SETTLED are not DecisionStatus. LOCKED content is immutable; updates create new versions and SUPERSEDED events. SETTLED appends result/evaluation only.

DataStatus: READY, PARTIAL, STALE, BLOCKED. BLOCKED cannot RECOMMEND. STALE cannot lock RECOMMEND. RECOMMEND+LOCKED requires READY.

DisplayGrade: A for RECOMMEND, B for CANDIDATE, C for WATCH, NA for SKIP/NOT_READY. B and C are not official recommendations.
