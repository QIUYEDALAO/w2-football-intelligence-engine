export type DashboardV2DecisionTier =
  | "ANALYSIS_PICK"
  | "NO_EDGE"
  | "WATCH"
  | "NOT_READY"
  | "SKIP";

export type DashboardV2DataStatus = "READY" | "PARTIAL" | "STALE" | "BLOCKED";

export interface DashboardV2ReleaseModel {
  environment: string;
  apiSha: string;
  webSha: string;
  pageUpdatedAt: string;
  oddsConfirmedAt: string | null;
  nextRefreshAt: string | null;
}

export interface DashboardV2LedgerModel {
  rangeLabel: string;
  validationCount: number;
  settledCount: number;
  pendingCount: number;
  eligibleCount: number;
  evidenceRepairPendingCount: number;
  hitCount: number;
  missCount: number;
  pushCount: number;
  voidCount: number;
  decisiveCount: number;
  hitRate: number | null;
  clvMedian: number | null;
  clvSampleCount: number;
}

export interface DashboardV2HealthModel {
  automaticCollectionPaused: boolean;
  competitionCount: number;
  upcomingCount: number;
  description: string;
}

export interface DashboardV2ScorelineRow {
  scoreline: string;
  sampleCount: number;
  unconditionalProbability: number;
  conditionalProbability: number;
  primarySettlement: "WIN" | "HALF_WIN";
}

export interface DashboardV2ScorelineProjection {
  status: "READY" | "NOT_READY";
  simulationsRequested: number;
  simulationsCompleted: number;
  consistentSampleCount: number;
  consistencyLabel: string;
  decisionHash: string;
  evidenceHash: string;
  blocker?: string | null;
  top3: DashboardV2ScorelineRow[];
}

export interface DashboardV2QuoteModel {
  marketPolicyLabel: string;
  candidateRole?: "MARKET_MAINLINE" | "ALTERNATE_LINE";
  marketMainlineLine?: string;
  marketMainlineBookmakerCount?: number;
  marketMainlineVoteCount?: number;
  marketMainlineOverPrice?: number | null;
  marketMainlineUnderPrice?: number | null;
  marketMainlineHomePrice?: number | null;
  marketMainlineAwayPrice?: number | null;
  bookmaker: string;
  capturedAt: string;
  marketLabel: string;
  selectionLabel: string;
  line: string;
  odds: number;
  marketProbability: number | null;
  modelProbability: number | null;
  probabilityDelta: number | null;
  expectedValue: number | null;
  uncertainty: number | null;
  ladder?: DashboardV2MarketLadderRow[];
}

export interface DashboardV2MarketLadderRow {
  line: string;
  completePairBookmakerCount: number;
  bookmakerVoteCount: number;
  leftPrice: number | null;
  rightPrice: number | null;
  status: string;
  reason: string | null;
  modelProbability: number | null;
  marketProbability: number | null;
  probabilityDelta: number | null;
  expectedValue: number | null;
  uncertainty: number | null;
}

export interface DashboardV2TrackingModel {
  status: "CAPTURED_PENDING" | "NOT_CAPTURED" | "SETTLED" | "EXCLUDED";
  label: string;
  detail: string;
  captureHash?: string | null;
}

export interface DashboardV2FixtureModel {
  fixtureId: string;
  kickoffUtc: string;
  status: string;
  competition: string;
  homeTeam: string;
  awayTeam: string;
  decisionTier: DashboardV2DecisionTier;
  dataStatus: DashboardV2DataStatus;
  reasonLabel: string | null;
  nextEvaluationAt: string | null;
  primaryMarketLabel: string;
  secondaryMarketLabel: string | null;
  scorelineSummary: string | null;
  quote: DashboardV2QuoteModel | null;
  scorelineProjection: DashboardV2ScorelineProjection | null;
  modelLabel: string;
  calibrationLabel: string;
  dataFacts: string[];
  tracking: DashboardV2TrackingModel;
}

export interface DashboardV2LeaguePerformanceRow {
  competitionKey?: string;
  league: string;
  eligibleCount: number;
  hitCount: number;
  missCount: number;
  pushCount: number;
  clvMedian: number | null;
  clvSampleCount: number;
  statusLabel: string;
}

export interface DashboardV2ViewModel {
  observedFootballDay: string;
  release: DashboardV2ReleaseModel;
  ledger: DashboardV2LedgerModel;
  health: DashboardV2HealthModel;
  fixtures: DashboardV2FixtureModel[];
  selectedFixtureId: string | null;
  leaguePerformance: DashboardV2LeaguePerformanceRow[];
}
