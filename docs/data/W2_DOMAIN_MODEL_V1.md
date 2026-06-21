# W2 Domain Model V1

Stage 3 defines the unified football data model only. It does not collect real
data, call Football-API, call DeepSeek, train models, or generate real
recommendations.

```mermaid
erDiagram
    Competition ||--o{ Season : has
    Season ||--o{ Stage : has
    Season ||--o{ Squad : registers
    Team ||--o{ Squad : has
    Player ||--o{ Squad : joins
    Competition ||--o{ Fixture : schedules
    Season ||--o{ Fixture : contains
    Stage ||--o{ Fixture : groups
    Team ||--o{ Fixture : home
    Team ||--o{ Fixture : away
    Venue ||--o{ Fixture : hosts
    Referee ||--o{ Fixture : officiates
    Fixture ||--o{ Market : offers
    Fixture ||--o{ OddsObservation : observes
    Bookmaker ||--o{ OddsObservation : quotes
    Fixture ||--o{ FeatureSnapshot : has
    ModelRun ||--o{ Prediction : emits
    Fixture ||--o{ Prediction : receives
    Fixture ||--o{ Recommendation : may_have
    Recommendation ||--o| RecommendationLock : locks
    Fixture ||--o| Result : finishes
    Result ||--o{ Settlement : settles
    Recommendation ||--o{ Settlement : settled_by
    RawPayloadReference ||--o{ DataProvenance : supports
    ProviderEntityMapping }o--|| Competition : maps
```

Core entities:

- Competition, Season, Stage, Fixture, Team, Player, Squad
- Venue, Referee, Bookmaker, Market, OddsObservation
- Lineup, Injury, Suspension, WeatherObservation, TeamRating
- FeatureSnapshot, ModelRun, Prediction, Recommendation,
  RecommendationLock, Result, Settlement, AuditEvent
- ProviderEntityMapping, RawPayloadReference, DataProvenance

Domain objects are separate from schemas and persistence models. Pydantic
schemas reject unknown fields. SQLAlchemy models define foreign keys, unique
constraints, idempotency keys, and time indexes.

