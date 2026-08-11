# SC20 single public authority cutover

Base: `f2b82c7d59341e8ecc98ccb34130b983c51664fc`.

The fresh-base inventory found the old public authority in backend projection,
API schema, TypeScript types, primary UI branches, CSS, tests, examples and
current visual references. Every live/current consumer was migrated to
`WorkspacePublicSemantics` plus factual context. One frontend converter,
`apps/web/src/lib/publicPresentation.ts`, owns public copy and tone.

The old status fields, focus enum, date-strip presentation field, frontend team
dictionary and its helper were physically removed. The old real-shape fixture
was preserved only as isolated historical evidence under `docs/archive/sc19/`.
The Dashboard V2 adapter remains only because the protected Boss Console visual
authority still imports it; its frontend team-translation dependency was
removed rather than migrated.
The canonical public team-label config is the only successful Chinese-label
authority; gaps fail closed with explicit identity/label causes.

`CONSUMER_INVENTORY.json` records the exact pre-cutover counts and consumer
classes. `TEAM_LABEL_PARITY.json` accounts for all 118 legacy label entries.
