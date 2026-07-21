import { BossDecisionConsoleReference } from "./BossDecisionConsoleReference";
import { bossConsoleFixture } from "./boss-console.fixture";

const FIXED_NOW = new Date("2026-07-21T12:33:00Z");

export function BossConsoleVisualFixturePage() {
  return <BossDecisionConsoleReference model={bossConsoleFixture} fixedNow={FIXED_NOW} prototypeCopy />;
}
