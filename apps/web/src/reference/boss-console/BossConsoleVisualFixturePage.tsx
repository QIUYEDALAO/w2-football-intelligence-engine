import { BossDecisionConsoleReference } from "./BossDecisionConsoleReference";
import { bossConsoleFixture } from "./boss-console.fixture";
import type { BossConsoleModel, BossDecisionItem } from "./boss-console-model";

const FIXED_NOW = new Date("2026-07-21T12:33:00Z");

function decisionCount(model: BossConsoleModel, count: number): BossConsoleModel {
  const decisions: BossDecisionItem[] = Array.from({ length: count }, (_, index) => {
    const source = model.decisions[index % model.decisions.length];
    return index < model.decisions.length
      ? source
      : {
          ...source,
          id: `${source.id}-copy-${index}`,
          priority: `N${index + 1}`,
          status: "not-ready",
          decision: "暂不可判断",
          recommendation: "尚未进入完整评估窗口",
          modelProbability: null,
          marketProbability: null,
          probabilityDelta: null,
          expectedValue: null,
          uncertainty: null,
          scorelineProjection: null,
          ledgerCode: "—",
        };
  });
  return { ...model, decisions };
}

export function BossConsoleVisualFixturePage() {
  const params = new URLSearchParams(window.location.search);
  const requestedCount = Number(params.get("count") || bossConsoleFixture.decisions.length);
  let model = decisionCount(
    bossConsoleFixture,
    Number.isFinite(requestedCount) ? Math.max(1, Math.min(30, requestedCount)) : bossConsoleFixture.decisions.length,
  );
  if (params.has("timeAnomaly")) {
    model = {
      ...model,
      release: {
        ...model.release,
        oddsConfirmedAt: "2026-07-21T13:00:00Z",
        pageUpdatedAt: "2026-07-21T12:33:00Z",
      },
    };
  }
  if (params.has("scorelineNotReady")) {
    model = {
      ...model,
      decisions: model.decisions.map((item, index) => index === 0 ? {
        ...item,
        scorelineProjection: {
          status: "NOT_READY",
          simulationsRequested: 10_000,
          simulationsCompleted: 0,
          consistentSampleCount: 0,
          consistencyLabel: "",
          decisionHash: "",
          evidenceHash: "",
          blocker: "SCORELINE_CONSTRAINT_EMPTY",
          top3: [],
        },
      } : item),
    };
  }
  if (params.has("nearKickoff")) {
    model = {
      ...model,
      decisions: model.decisions.map((item, index) => index === 0
        ? { ...item, kickoffUtc: "2026-07-21T13:16:00Z" }
        : item),
    };
  }
  return (
    <BossDecisionConsoleReference
      model={model}
      fixedNow={params.has("liveClock") ? undefined : FIXED_NOW}
      prototypeCopy
    />
  );
}
