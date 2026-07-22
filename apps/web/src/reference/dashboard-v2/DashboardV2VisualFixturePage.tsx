import { DashboardV2Reference } from "./DashboardV2Reference";
import { dashboardV2ReferenceFixture } from "./dashboard-v2-reference.fixture";

const FIXED_NOW = new Date("2026-07-21T12:33:00Z");

export function DashboardV2VisualFixturePage() {
  return (
    <DashboardV2Reference
      model={dashboardV2ReferenceFixture}
      fixedNow={FIXED_NOW}
    />
  );
}
