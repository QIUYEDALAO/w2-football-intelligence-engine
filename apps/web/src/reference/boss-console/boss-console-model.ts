import type {
  DashboardV2LeaguePerformanceRow,
  DashboardV2LedgerModel,
  DashboardV2ReleaseModel,
  DashboardV2ScorelineProjection,
} from "../dashboard-v2/dashboard-v2-model";

export type BossDecisionStatus = "pick" | "watch" | "not-ready";
export type BossRiskLevel = "low" | "medium" | "high";

export interface BossDecisionItem {
  id: string;
  priority: string;
  kickoffUtc: string;
  fixtureStatus: string;
  league: string;
  match: string;
  status: BossDecisionStatus;
  decision: string;
  recommendation: string;
  modelProbability: number | null;
  marketProbability: number | null;
  probabilityDelta: number | null;
  expectedValue: number | null;
  uncertainty: number | null;
  scorelineProjection: DashboardV2ScorelineProjection | null;
  candidateRole: "MARKET_MAINLINE" | "ALTERNATE_LINE" | null;
  marketPolicyLabel: string | null;
  marketMainlineLabel: string | null;
  executionQuoteLabel: string | null;
  marketLadder: import("../dashboard-v2/dashboard-v2-model").DashboardV2MarketLadderRow[];
  risk: string;
  riskLevel: BossRiskLevel;
  riskNote: string;
  lineupPending: boolean;
  nextAction: string;
  nextDetail: string;
  snapshotAt: string | null;
  lifecycleState: string | null;
  quoteAgeSeconds: number | null;
  latestCheckpoint: string | null;
  nextCheckpoint: string | null;
  automaticRefreshStatus: string;
  lineupFacts: string[];
  ledgerCode: string;
  ledgerStatus: string;
  ledgerDetail: string;
  reasons: string[];
  risks: string[];
  dataRisk: string;
  marketIdentityRisk: string;
  lineupRisk: string;
}

export interface BossConsoleRuntime {
  schemaStatus: string;
  serviceStatus: string;
  providerStatus: string;
  schedulerStatus: string;
  formalStatus: string;
  lockProductionStatus: string;
}

export interface BossConsoleModel {
  release: DashboardV2ReleaseModel;
  ledger: DashboardV2LedgerModel;
  decisions: BossDecisionItem[];
  selectedDecisionId: string | null;
  leaguePerformance: DashboardV2LeaguePerformanceRow[];
  automaticCollectionPaused: boolean;
  riskExceptionCount: number;
  lineupPendingCount: number;
  lastCheckedAt: string | null;
  runtime: BossConsoleRuntime;
}
