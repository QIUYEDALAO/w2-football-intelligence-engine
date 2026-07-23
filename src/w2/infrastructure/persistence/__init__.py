"""SQLAlchemy persistence models for the W2 domain."""

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
    T30ValidationSnapshotModel,
)
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
    TeamRatingSnapshotModel,
)
from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.future_refresh_models import (
    FutureRefreshCheckpointAuditModel,
    FutureRefreshCheckpointPlanModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    IngestionRunModel,
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.infrastructure.persistence.league_models import (
    LeagueProfileModel,
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)
from w2.infrastructure.persistence.market_projection_view import (
    PROJECTION_VIEW_NAME,
    current_market_projection,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEvidenceManifestModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import (
    CanonicalHistoricalAhFactModel,
    CompetitionModel,
    FixtureModel,
    HistoricalMarketSourceSnapshotModel,
    ModelRunModel,
    PlayerClubMembershipObservationModel,
    PlayerIdentityCrosswalkModel,
    PredictionModel,
    RecommendationLockModel,
    RecommendationModel,
    RefereeModel,
    RegisteredRosterSnapshotModel,
    ResultModel,
    SeasonModel,
    SettlementModel,
    StageModel,
    TeamIdentityCrosswalkModel,
    TeamModel,
    TeamValueAsOfArtifactModel,
    VenueModel,
)
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
)
from w2.infrastructure.persistence.shadow_strategy_models import (
    ShadowStrategyEvaluationModel,
    ShadowStrategyLockModel,
    ShadowStrategyRunModel,
)
from w2.infrastructure.persistence.stage7i_lifecycle_models import (
    Stage7ILifecycleEventModel,
    Stage7ILifecycleHeartbeatModel,
    Stage7ILifecycleRunModel,
)

__all__ = [
    "CanonicalHistoricalAhFactModel",
    "CanonicalTeamMatchHistoryModel",
    "CanonicalTeamModel",
    "CompetitionModel",
    "DynamicPrematchEvaluationModel",
    "DynamicPrematchSupersessionModel",
    "FutureRefreshCheckpointAuditModel",
    "FutureRefreshCheckpointPlanModel",
    "FutureRefreshRunAuditModel",
    "FutureRefreshTaskAuditModel",
    "Gate5RecommendationLockEventModel",
    "ForwardMarketSnapshotModel",
    "PROJECTION_VIEW_NAME",
    "current_market_projection",
    "FixtureModel",
    "HistoricalMarketSourceSnapshotModel",
    "IngestionRunModel",
    "LineupConfirmedEventModel",
    "LeagueProfileModel",
    "LeagueReadinessAuditModel",
    "LeagueSeasonModel",
    "MatchdayCheckpointPlanModel",
    "MatchdayEndpointCaptureModel",
    "MatchdayEvidenceManifestModel",
    "MatchdayFixtureIdentityModel",
    "MatchdayMarketObservationModel",
    "ModelRunModel",
    "PlayerClubMembershipObservationModel",
    "PlayerIdentityCrosswalkModel",
    "PredictionModel",
    "ProviderTeamIdentityCrosswalkModel",
    "ProviderRequestLogModel",
    "QuotaUsageModel",
    "RegisteredRosterSnapshotModel",
    "RawPayloadModel",
    "ReadModelCheckpointModel",
    "RecommendationLockModel",
    "RecommendationModel",
    "RefereeModel",
    "ResultModel",
    "SeasonModel",
    "SettlementModel",
    "ShadowStrategyEvaluationModel",
    "ShadowStrategyLockModel",
    "ShadowStrategyRunModel",
    "Stage7ILifecycleEventModel",
    "Stage7ILifecycleHeartbeatModel",
    "Stage7ILifecycleRunModel",
    "StageModel",
    "TeamModel",
    "T30ValidationSnapshotModel",
    "TeamIdentityCrosswalkModel",
    "TeamRatingSnapshotModel",
    "TeamValueAsOfArtifactModel",
    "TeamXgMatchModel",
    "TeamXgRollingSnapshotModel",
    "VenueModel",
]
