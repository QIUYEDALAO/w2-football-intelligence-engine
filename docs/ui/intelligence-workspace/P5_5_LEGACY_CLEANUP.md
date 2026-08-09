# P5.5 Controlled Legacy Cleanup

## Authority and boundary

- Starting main: `f931702f617f432ba66c90f08828090f094d8ba5`
- Public route: `/`
- Public read model: `GET /v1/dashboard/intelligence-workspace`
- Public authority: `NEW_INTELLIGENCE_WORKSPACE_ONLY`
- Product/runtime changes: none
- Provider calls, Scheduler/cadence, whitelist, model/factor/threshold, Phase 0.5, Round 4, Candidate, Formal, Lock, Production, P6 and real-money authority: unchanged or not started as required.

## Non-reachability proof

The public entrypoint graph is `main.tsx -> App.tsx -> DashboardPage.tsx -> IntelligenceConsole.tsx`. The only public API client imported by that graph is `intelligenceWorkspaceApi.ts`; it reads the unified endpoint and has no legacy fallback.

Repository route, import, entrypoint, runtime, build, test, config, workflow and reference searches found no public or production consumer for the removed Boss L1/L2, Recommendation or Performance presentations. Their remaining references were historical source-text tests, which were replaced with fail-closed absence and unified-authority assertions.

The Boss visual fixture is not a public product route: it is guarded by `import.meta.env.DEV` and exists solely at `/__visual/boss-console` for the protected acceptance contract. Its legacy CSS is now loaded only by that development fixture; the production bundle loads only `base.css` and `intelligence.css`.

## Hygiene classification

| Asset group | Classification | Evidence |
| --- | --- | --- |
| Unified workspace component, API client, types and scoped CSS | `KEEP` | Direct public entrypoint/import/runtime chain. |
| Unified truth, negative, responsive and fail-closed E2E | `KEEP` | Current P3-P5 acceptance and CI. |
| Old Boss L1/L2, Recommendation and Performance product components | `DELETE` | No public route/import/entrypoint/runtime/build/workflow consumer. |
| Old dashboard and performance API clients, supporting presentation-only modules and performance CSS | `DELETE` | No current caller; unified API client is the only public read. |
| Obsolete product-source tests for deleted presentations | `DELETE` | Tested removed code rather than current authority. |
| Protected Boss manifest, fixture route, pixel E2E, reference sources and golden images | `RETAIN_FOR_EVIDENCE` | `check_boss_console_baseline.py` and Web E2E remain live acceptance contracts. |
| Dashboard V2 reference adapter/model/fixture and legacy styles | `RETAIN_FOR_EVIDENCE` | Transitive protected Boss visual-contract dependencies; loaded only by the development fixture. |
| Database migrations, replay/settlement evidence and backend projection authorities | `KEEP` | Historical/runtime contracts; outside presentation cleanup. |

## Acceptance evidence

```text
BOSS_PROTECTED_BASELINE = PASS
TYPESCRIPT = PASS
WEB_BUILD = PASS
WEB_E2E = 44_PASS
FOCUSED_UNIT_CONTRACT = 53_PASS
PUBLIC_PRODUCTION_BUNDLE_EXCLUDES_LEGACY_CSS = PASS
LEGACY_PUBLIC_FALLBACK = NONE
```

Final full unit/contract/integration, exact-head CI, `RELEASE_REQUIRED`, and clean-worktree identities are recorded in the terminal context receipt after the immutable PR head passes.

## Repository hygiene

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 44
DEAD_ASSETS_DELETED = 44
OBSOLETE_TRACKED_LINES_REMOVED = 6229
RETAINED_FOR_EVIDENCE = protected Boss baseline chain + transitive Dashboard V2 reference dependencies
UNRESOLVED_HYGIENE_ITEMS = 0
```
