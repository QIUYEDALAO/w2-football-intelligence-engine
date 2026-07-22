import type {
  DashboardDayView,
  DashboardMatchCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../../types/dashboard";
import { adaptDashboardV2 } from "./dashboard-v2-adapter";
import { DashboardV2Reference } from "./DashboardV2Reference";

export interface DashboardV2Props {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  performance?: DashboardPerformance;
  release?: ReleaseSyncState;
}

/**
 * Production wrapper.
 *
 * The presentational DOM/CSS lives in DashboardV2Reference and is protected by
 * visual-regression tests. Backend/API changes belong in dashboard-v2-adapter.ts.
 * legacyMatches remains accepted for the current DashboardPage call signature,
 * but the public V2 view deliberately uses one forward-ledger accounting model.
 */
export function DashboardV2({ dayView, performance, release }: DashboardV2Props) {
  const model = adaptDashboardV2(dayView, performance, release);
  return <DashboardV2Reference model={model} />;
}
