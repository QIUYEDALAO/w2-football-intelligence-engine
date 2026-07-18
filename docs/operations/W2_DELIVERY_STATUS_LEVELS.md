# W2 Delivery Status Levels

W2 uses exactly four delivery states. A later state includes the earlier ones,
but no document may skip evidence or use a stronger synonym.

| State | Meaning | Required evidence |
|---|---|---|
| `implemented` | Code or documentation exists in the current local candidate. | Local commit or working-tree diff. |
| `locally_verified` | The candidate passed its focused contracts and the required local gates. | Test/build output and evidence paths. |
| `staging_accepted` | The exact local candidate passed isolated predeploy and formal staging canary gates. | Release/image/schema/artifact identity, before/after invariants and rollback evidence. |
| `production_approved` | The user explicitly approved production after a separate R4 review. | Recorded approval and production release manifest. |

Rules:

- `implemented` never means tested or deployed.
- `locally_verified` never means staging was changed.
- `staging_accepted` never means GitHub or production was updated.
- `production_approved` cannot be inferred from champion or RECOMMEND approval.
- Historical PRs #333–#347 are requirement and failure-case clues only. Their
  existence, CI, merge state or staging history is not current-tree delivery evidence.
- GitHub synchronization is recorded separately and remains false unless explicitly
  performed at the user's request.
