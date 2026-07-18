# W2 Next Action

## Current gate

R3 is `staging_accepted` and remains the active delivery phase. LMM0-LMM8 is
the authorized in-progress correction workstream on local branch
`codex/w2-lmm-lineup-multimarket`, based on local `main@8e171dc`.

The currently accepted staging implementation is `01f8a75`; the LMM candidate
has not been deployed. Existing read-only cycles must be restarted from `0/3`
only after the single LMM staging canary succeeds. No GitHub synchronization is
authorized.

R4 is authorized for approval-package preparation only. Champion,
RECOMMEND/lock, OFFICIAL and write-enabled production state changes are not
authorized.

## Next execution

1. Complete LMM0 coverage evidence from local Transfermarkt data and redacted,
   read-only staging lineup exports with provider delta zero.
2. Complete LMM1-LMM7 code, migration, deterministic offline evaluation and all
   local/isolated gates. Markets whose evaluation gate fails keep lineup weight
   zero.
3. Deploy the exact local candidate to staging once, after freezing rollback
   evidence and stopping scheduler with queue zero.
4. On staging acceptance, restore scheduler exactly and restart the consecutive
   Beijing 09:00 read-only count at `0/3` on the same SHA and images.
5. After `3/3` PASS, record read-only production approval under the user's
   existing conditional authorization.

R3 is `staging_accepted`; R4 is authorized for preparation only. No GitHub
fetch, pull, push or PR is authorized.
