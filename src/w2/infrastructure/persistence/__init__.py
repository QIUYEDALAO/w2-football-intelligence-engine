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
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
    RawStatisticsRetentionModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    IngestionRunModel,
    ProviderQuotaObservationModel,
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
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.infrastructure.persistence.models import (
    CanonicalHistoricalAhFactModel,
    CompetitionModel,
    FixtureModel,
    HistoricalMarketSourceSnapshotModel,
    ModelRunModel,
    PlayerClubMembershipObservationModel,
    PredictionModel,
    RecommendationLockModel,
    RecommendationModel,
    RefereeModel,
    RegisteredRosterSnapshotModel,
    ResultModel,
    SeasonModel,
    SettlementModel,
    StageModel,
    TeamModel,
    TeamValueAsOfArtifactModel,
    VenueModel,
)
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
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
    "ModelForecastCaptureModel",
    "ModelForecastOutcomeModel",
    "OutcomeLedgerModel",
    "PlayerClubMembershipObservationModel",
    "PredictionModel",
    "ProviderTeamIdentityCrosswalkModel",
    "ProviderQuotaObservationModel",
    "ProviderRequestLogModel",
    "QuotaUsageModel",
    "RegisteredRosterSnapshotModel",
    "RawPayloadModel",
    "RawStatisticsRetentionModel",
    "ReadModelCheckpointModel",
    "RecommendationLockModel",
    "RecommendationModel",
    "RefereeModel",
    "ResultModel",
    "SeasonModel",
    "SettlementModel",
    "Stage7ILifecycleEventModel",
    "Stage7ILifecycleHeartbeatModel",
    "Stage7ILifecycleRunModel",
    "StageModel",
    "TeamModel",
    "T30ValidationSnapshotModel",
    "TeamRatingSnapshotModel",
    "TeamValueAsOfArtifactModel",
    "TeamXgMatchModel",
    "TeamXgRollingSnapshotModel",
    "VenueModel",
]
