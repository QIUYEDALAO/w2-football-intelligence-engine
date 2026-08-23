"""SQLAlchemy persistence models for the W2 domain."""

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
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
from w2.infrastructure.persistence.factor_shadow_models import (
    FactorShadowForecastCaptureModel,
    FactorShadowForecastOutcomeModel,
    FactorShadowMarketAttemptModel,
    FactorShadowMarketOpportunityModel,
    FactorShadowV2AdmissionModel,
)
from w2.infrastructure.persistence.forward_ops_models import ForwardMarketSnapshotModel
from w2.infrastructure.persistence.future_refresh_models import (
    ExpectedMatchFixtureMaterializationModel,
    ExpectedMatchFixtureObservationModel,
    FreePlanFixtureScopeObservationModel,
    FutureRefreshCheckpointAuditModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawFixtureScopeMembershipModel,
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
    ModelForecastCaptureDataVersionModel,
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
from w2.infrastructure.persistence.outcome_ledger_models import (
    OutcomeLedgerModel,
    OutcomeLedgerRunStateModel,
)
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
)
from w2.infrastructure.persistence.stage7i_lifecycle_models import (
    Stage7ILifecycleEventModel,
    Stage7ILifecycleHeartbeatModel,
    Stage7ILifecycleRunModel,
)

__all__ = [
    "CandidateNotificationOutboxModel",
    "CanonicalHistoricalAhFactModel",
    "CanonicalTeamMatchHistoryModel",
    "CanonicalTeamModel",
    "CompetitionModel",
    "DynamicPrematchEvaluationModel",
    "DynamicPrematchOpportunityModel",
    "DynamicPrematchSupersessionModel",
    "ExpectedMatchFixtureMaterializationModel",
    "ExpectedMatchFixtureObservationModel",
    "FactorShadowForecastCaptureModel",
    "FactorShadowForecastOutcomeModel",
    "FactorShadowMarketAttemptModel",
    "FactorShadowMarketOpportunityModel",
    "FactorShadowV2AdmissionModel",
    "FutureRefreshCheckpointAuditModel",
    "FutureRefreshRunAuditModel",
    "FutureRefreshTaskAuditModel",
    "FreePlanFixtureScopeObservationModel",
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
    "ModelForecastCaptureDataVersionModel",
    "ModelForecastOutcomeModel",
    "OutcomeLedgerModel",
    "OutcomeLedgerRunStateModel",
    "PlayerClubMembershipObservationModel",
    "PredictionModel",
    "ProviderTeamIdentityCrosswalkModel",
    "ProviderQuotaObservationModel",
    "ProviderRequestLogModel",
    "QuotaUsageModel",
    "RegisteredRosterSnapshotModel",
    "RawPayloadModel",
    "RawFixtureScopeMembershipModel",
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
