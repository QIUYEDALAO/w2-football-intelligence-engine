import type {
  DashboardDayView,
  DashboardMatchCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../../types/dashboard";
import { adaptBossDecisionConsole } from "./boss-console-adapter";
import { BossDecisionConsoleReference } from "./BossDecisionConsoleReference";

export interface BossDecisionConsoleProps {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  performance?: DashboardPerformance;
  release?: ReleaseSyncState;
}

export function BossDecisionConsole(props: BossDecisionConsoleProps) {
  return <BossDecisionConsoleReference model={adaptBossDecisionConsole(props.dayView, props.legacyMatches, props.performance, props.release)} />;
}
