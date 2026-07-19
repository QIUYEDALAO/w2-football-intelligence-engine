# W2 Next Action

## Current gate

R3 is `staging_accepted`. LMM0–LMM8 and the Dashboard ledger-authority repair
are `staging_accepted` on exact local implementation
`438ac07e8ad3b30dbe1c4107b759100e1cae7418`. GitHub was not accessed or
synchronized.

The 2026-07-19 10:00 patrol exposed a real runtime-path regression and does not
count. The correction resets the consecutive natural-day read-only count to
`0/3`. The next eligible patrols are 2026-07-20, 2026-07-21 and 2026-07-22 at
09:00 Asia/Shanghai on the same implementation SHA, images and data contract.

Current Swedish fixtures have only early odds captured around 2026-07-17 22:48
Beijing. The hard missing input is an AH/OU quote captured within the executable
30-minute freshness window. The next scheduled collection is 2026-07-19 16:30.
After that collection, a pick forms only if a quote is complete and fresh and
the market decision score passes; otherwise the Dashboard must state the next
failed gate. These non-top-five fixtures do not have a hard lineup gate.

## Next execution

1. At 16:30, allow the existing controlled scheduler to perform its normal
   collection; do not issue an extra provider request from acceptance work.
2. Confirm that the Dashboard shows the latest captured time and either a
   qualified AH/OU pick or a precise remaining blocker.
3. Run the real staging read-only patrol at 09:00 on 2026-07-20, 2026-07-21 and
   2026-07-22. Count at most one PASS per natural day.
4. UNKNOWN and hard failures do not count. A data-contract, decision or runtime
   correction resets the sequence; pure wording changes do not.
5. After `3/3`, record the conditionally authorized read-only production state
   without rebuilding or changing the candidate.

Champion switching, formal RECOMMEND, lock, OFFICIAL and write-enabled
production remain unauthorized. No GitHub fetch, pull, push or PR is authorized.
R4 is authorized for approval-package preparation only; no R4 switch is
implicitly approved.
