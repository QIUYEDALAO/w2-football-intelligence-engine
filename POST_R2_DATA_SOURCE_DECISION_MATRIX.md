# W2 Post-R2 — Data-Source Decision Matrix

```text
DECISION_DATE = 2026-08-08
ROOT_CAUSE = FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
PREFERRED = API_FOOTBALL_PRO_RENEWAL_AND_BOUNDED_REVALIDATION
FALLBACK = SPORTMONKS_GROWTH_PLUS_PREMIUM_ODDS_AFTER_COVERAGE_TRIAL
PURCHASE_OR_PLAN_CHANGE_EXECUTED = false
PROVIDER_CUTOVER_EXECUTED = false
ROUND_3 = NOT_STARTED
```

## Decision

The preferred path is to renew API-Football at **Pro, USD 19/month**, then run a
separately authorized bounded current-season capability revalidation before any
Round-3 or collection decision. This is the smallest-cost path, preserves W2's
existing identities/client/schema, and directly removes the confirmed Free-plan
season boundary. Pro is a starting tier, not a claim that 7,500 requests/day is
already sufficient for a future collection cadence.

The fallback is **Sportmonks Growth plus Premium Odds**, currently
**EUR 228/month before VAT** (`EUR 99 + EUR 129`), after a trial proves all 17
competition mappings and per-fixture AH/OU/bookmaker depth. If W2 also requires
Sportmonks-provided xG rather than xG-capable raw statistics, budget the xG
bundle from **EUR 24/month**, producing an indicative **EUR 252/month** total.

The Odds API remains a useful low-cost historical-odds pilot or hybrid candidate,
but it is not the fallback recommendation because its own documentation warns
that `spreads` and `totals` are mainly available for US sports/bookmakers. Its
17/17 soccer league keys do not prove 17/17 football AH/OU coverage.

## Evidence legend

```text
VERIFIED_BY_CALL = observed using the current W2 account/key in this task
DOCUMENTED = stated by a current official Provider source
NOT_VERIFIED = not established for every target league/fixture in this task
N/A = Provider is not intended to supply that capability
```

## Option summary

| Path | Current price / quota | Target-17 coverage | Market-data fit | Football enrichment | Engineering effort | Decision |
|---|---|---|---|---|---|---|
| API-Football Free (current) | USD 0; 100/day, 10/min | mappings exist, but current 2025/2026 seasons fail | AH/OU endpoints documented; current season inaccessible | lineups/injuries/statistics documented; inaccessible for required seasons | none | **NOT VIABLE** |
| API-Football paid renewal | Pro USD 19/mo: 7,500/day, 300/min; Ultra USD 29/mo: 75,000/day; Mega USD 39/mo: 150,000/day | 17 W2 mappings retained; paid current-season capability still requires row validation | AH, OU, 15-bookmaker reference list, timestamps; 3-hour refresh; only 7-day retained history | lineups, injuries, statistics documented; xG not separately guaranteed | very low | **PREFERRED: Pro first** |
| Sportmonks full replacement | Growth EUR 99/mo for 30 leagues, 2,500 calls/entity/hour; premium odds +EUR 129/mo; xG bundle from +EUR 24/mo | official catalog covers the 17 identities; per-league feature depth must be trial-verified | Standard odds available; Premium documents AH/OU, 120+ bookmakers, ~1-minute updates, per-odd timestamp and every change retained until 7 days after kickoff | lineups, injuries, statistics documented; xG available with package/add-on and varies by coverage | high | **FALLBACK after trial** |
| The Odds API dedicated odds | USD 30/mo for 20,000 credits; USD 59/100k; USD 119/5m; USD 249/15m | **17/17 league keys documented** | 50+ bookmakers, ISO timestamps, 60s featured-market updates, historical 5-minute snapshots; soccer AH/OU breadth **NOT VERIFIED** | N/A: no lineup/injury/xG role | medium | CONDITIONAL PILOT ONLY |
| Hybrid: API-Football Pro + The Odds API 20K | USD 49/mo combined | core 17 mappings + 17/17 odds league keys documented | historical odds strength, but soccer AH/OU exact coverage still unverified; cross-source identity reconciliation required | API-Football supplies enrichment; xG remains unverified | medium-high | CONDITIONAL, not preferred |

## Capability matrix

| Capability | API-Football Free | API-Football paid | Sportmonks Growth + Premium | The Odds API | Hybrid API-Football + Odds API |
|---|---|---|---|---|---|
| Current fixtures for target 17 | `NOT_VERIFIED`; blocked by season entitlement | `DOCUMENTED`; exact 17 paid audit pending | 17 identities `DOCUMENTED`; exact feed trial pending | event/scores role `DOCUMENTED`, not full football feed | core from API-Football; paid audit pending |
| AH | endpoint/market `DOCUMENTED`, required season blocked | `DOCUMENTED`; exact 17 availability pending | `DOCUMENTED` Premium market; exact 17 depth pending | `spreads` documented but soccer breadth `NOT_VERIFIED` | `NOT_VERIFIED` until odds-provider pilot |
| OU | endpoint/market `DOCUMENTED`, required season blocked | `DOCUMENTED`; exact 17 availability pending | `DOCUMENTED` Premium market; exact 17 depth pending | `totals` documented but soccer breadth `NOT_VERIFIED` | `NOT_VERIFIED` until odds-provider pilot |
| Historical odds | 7-day rolling retention documented, required seasons blocked | 7-day rolling retention; W2 must prospectively persist snapshots | every change available only until 7 days after kickoff; W2 must persist; older football archive is a separate add-on | paid snapshots from league-specific start dates, 10-minute pre-Sep-2022 / 5-minute since; `DOCUMENTED` | best retroactive history, subject to exact market coverage |
| Pre-match timestamps / cadence | Provider update field; ~3-hour updates | same | per-odd bookmaker timestamp; Premium ~1-minute cadence | ISO `last_update`; featured markets ~60 seconds | two timestamp systems require normalization |
| Bookmaker depth | reference endpoint shows 15; per-fixture varies | 15-bookmaker reference list; per-fixture depth pending | Premium 120+ bookmakers / 42 markets | over 50 sources; region/bookmaker selectable | odds depth from The Odds API; exact league/market depth pending |
| Lineups | `DOCUMENTED`, required seasons blocked | `DOCUMENTED` | `DOCUMENTED` | N/A | API-Football |
| Injuries | `DOCUMENTED`, required seasons blocked | `DOCUMENTED` | `DOCUMENTED`; completeness varies | N/A | API-Football |
| Statistics | `DOCUMENTED`, required seasons blocked | `DOCUMENTED`; per-league coverage varies | match/player statistics `DOCUMENTED` | N/A | API-Football |
| xG / xG-capable inputs | raw stats documented; xG `NOT_VERIFIED` | raw stats documented; xG `NOT_VERIFIED` | xG `DOCUMENTED`, package/coverage dependent; bundle from EUR 24/mo | N/A | xG remains `NOT_VERIFIED` unless separately sourced |
| Licensing | terms apply; logos/media need rights review | same; public redistribution/legal review required | commercial applications allowed; direct resale needs approval; per-domain pricing; media rights remain user's responsibility | commercial apps/analytics allowed; standalone resale/redistribution forbidden | must satisfy both vendors and mapping retention terms |

## Target 17 coverage

The target set remains unchanged:

```text
Premier League; La Liga; Bundesliga; Serie A; Ligue 1;
Campeonato Brasileiro Serie A; Liga Profesional de Fútbol; MLS;
Chinese Super League; Allsvenskan; Eliteserien; Eredivisie;
Primeira Liga; Belgian Pro League; Turkish Süper Lig;
Greek Super League; Scottish Premiership
```

- API-Football: W2 already has canonical mappings for all 17, but Round 2 could
  not verify current-season fixtures/markets because identity calls terminated
  at the Free-plan season gate. Paid per-row capability remains `NOT_VERIFIED`.
- Sportmonks: the official catalog/coverage material documents all 17
  competition identities within the 30-league Growth capacity. Exact 17/17
  odds, lineup, injury and statistic depth remains a trial gate because its
  terms explicitly allow coverage gaps.
- The Odds API: the official sports catalog documents an active sport key for
  all 17. This proves competition identity coverage, not AH/OU availability at
  each bookmaker or fixture.

## Cost and implementation detail

| Path | Expected recurring cost | One-time/additional cost | Mapping/schema work | Primary risks |
|---|---:|---:|---|---|
| API-Football Free | USD 0/mo | none | none | cannot access required current seasons |
| API-Football Pro | USD 19/mo | none stated | none beyond bounded revalidation | exact 17 capability still unknown; 7-day odds retention; 3-hour snapshots; future quota may exceed Pro |
| API-Football Ultra/Mega | USD 29/39 mo | none stated | none beyond bounded revalidation | same data-shape/retention risks; paying for unused quota if cadence not modeled |
| Sportmonks Growth standard | EUR 99/mo excl. VAT | historical football data from EUR 29 one-time | full identity, fixture, lineup, market and statistic normalization | migration complexity; per-domain terms; standard odds weaker for market movement |
| Sportmonks Growth + Premium | EUR 228/mo excl. VAT | xG from EUR 24/mo; older historical data from EUR 29 one-time | same full migration | materially higher cost; seven-day vendor retention still requires W2 persistence; availability not guaranteed |
| The Odds API 20K | USD 30/mo | none stated | fixture/team/league/bookmaker reconciliation | soccer AH/OU gaps; no enrichment; credit cost multiplies by region/market; raw resale prohibited |
| Hybrid Pro + Odds API 20K | USD 49/mo | none stated | dual-provider canonical mapping and timestamp reconciliation | two-vendor operations plus unresolved AH/OU coverage |

## Official current sources

### API-Football

- [Pricing and quotas](https://www.api-football.com/pricing)
- [Coverage list and per-season/per-fixture caveat](https://www.api-football.com/coverage)
- [Documentation: odds, bookmakers, markets, timestamps and endpoints](https://www.api-football.com/documentation-v3)
- [2026 guide: three-hour pre-match refresh and seven-day history](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
- [Terms, expiration and media/licensing cautions](https://www.api-football.com/terms)

### Sportmonks

- [Plans and pricing](https://www.sportmonks.com/football-api/plans-pricing/)
- [League and capability coverage](https://www.sportmonks.com/football-api/coverage/)
- [Premium odds feed](https://www.sportmonks.com/football-api/premium-odds-feed/)
- [Odds history, cadence, timestamps and bookmaker depth](https://docs.sportmonks.com/v3/faq/odds)
- [Terms of service and redistribution rules](https://www.sportmonks.com/terms-of-service/)

### The Odds API

- [Current plans and bookmaker overview](https://the-odds-api.com/)
- [17-league sports catalog](https://the-odds-api.com/sports-odds-data/sports-apis.html)
- [V4 markets, timestamps, historical snapshots and credit model](https://the-odds-api.com/liveapi/guides/v4/)
- [Historical coverage start dates](https://the-odds-api.com/historical-odds-data/)
- [Update intervals](https://the-odds-api.com/sports-odds-data/update-intervals.html)
- [Commercial-use and no-resale terms](https://the-odds-api.com/terms-and-conditions.html)

## Owner decision and Round-3 prerequisites

```text
RECOMMENDED_PRIMARY_DATA_SOURCE_PATH = API_FOOTBALL_PRO_RENEWAL
RECOMMENDED_FALLBACK_PATH = SPORTMONKS_GROWTH_PLUS_PREMIUM_ODDS_AFTER_TRIAL
ESTIMATED_PRIMARY_MONTHLY_DATA_COST = USD_19
ESTIMATED_FALLBACK_MONTHLY_DATA_COST = EUR_228_TO_252_EX_VAT
CURRENT_API_FOOTBALL_FREE_PATH_VIABLE = false
CURRENT_API_FOOTBALL_PATH_VIABLE = PAID_ONLY_AFTER_REVALIDATION
ESTIMATED_MONTHLY_DATA_COST = PRIMARY_USD_19__FALLBACK_EUR_228_TO_252_EX_VAT
BLOCKERS_REQUIRING_OWNER_SPEND_OR_ACCOUNT_CHANGE = FREE_PLAN_CURRENT_SEASON_ENTITLEMENT
ROUND_3_DATA_PREREQUISITES = OWNER_SOURCE_SELECTION_AND_SPEND__BOUNDED_17_ROW_REVALIDATION__QUOTA_AND_COLLECTION_AUTHORITY__REAL_TEMPORAL_EVIDENCE
```

Before Round 3 can be authorized:

1. owner selects and funds a plan/source; this task performs neither action;
2. current-season identity, fixtures, AH, OU, bookmaker/timestamp and extended
   capability are revalidated across the fixed 17 without promoting the four
   audit-only candidates;
3. expected collection cadence is costed against quota/credit mechanics;
4. any prospective persistent odds collection receives separate authorization
   and preserves pre-match/close timestamp semantics;
5. temporal evidence gates remain fail-closed until real samples exist.

No plan purchase, Provider switch, Scheduler modification, persistent collection,
league enablement or Round-3 implementation occurred in this task.
