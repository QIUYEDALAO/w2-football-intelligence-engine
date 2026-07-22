# W2 Matchday Context Sync Rule - 2026-07-21

## User Instruction

Every time Codex receives a new instruction for this W2 task, Codex must update a GitHub-visible context file.

## Operating Rule

- Context updates do not need a new pull request.
- Context updates do not need CI.
- Context-only commits must use `[skip ci]`.
- The current PR branch remains the GitHub synchronization surface.
- Context files must not include auth material, private keys, or raw provider payloads.

## Current Synchronization Surface

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Branch: `codex/w2-matchday-live-intake-recovery`
- Pull request: `#369`

## Status

This rule is now recorded as GitHub-visible task context and applies to subsequent instructions in this thread.
