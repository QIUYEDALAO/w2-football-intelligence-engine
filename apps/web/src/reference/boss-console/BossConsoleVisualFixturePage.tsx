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
          priority: `A${index + 1}`,
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
  if (params.has("marketContract")) {
    model = {
      ...model,
      decisions: model.decisions.map((item, index) => index === 0
        ? {
            ...item,
            priority: "A1",
            candidateRole: "MARKET_MAINLINE",
            marketPolicyLabel: "canonical_bookmaker_mainline_consensus_v1",
            marketMainlineLabel: "市场主线：2.75 · 6家完整双边 · 6票 · 大1.88 / 小1.86",
            executionQuoteLabel: "分析选择：大小球 · 大 2.75 @1.91 · 市场主线 · Betano",
            marketLadder: [
              {
                line: "2.75",
                completePairBookmakerCount: 6,
                bookmakerVoteCount: 6,
                leftPrice: 1.875,
                rightPrice: 1.865,
                status: "SELECTED_MARKET_MAINLINE",
                reason: null,
                modelProbability: 0.58,
                marketProbability: 0.499,
                probabilityDelta: 0.081,
                expectedValue: 0.074,
                uncertainty: 0.044,
              },
              {
                line: "2.5",
                completePairBookmakerCount: 8,
                bookmakerVoteCount: 2,
                leftPrice: 1.7,
                rightPrice: 2.11,
                status: "REJECTED",
                reason: "LOWER_BOOKMAKER_CONSENSUS",
                modelProbability: 0.63,
                marketProbability: 0.554,
                probabilityDelta: 0.076,
                expectedValue: 0.071,
                uncertainty: 0.08,
              },
            ],
            dataRisk: "READY",
            marketIdentityRisk: "主线身份完整",
            lineupRisk: "首发待确认",
            nextAction: "计划复核：赛前30分钟",
            nextDetail: "状态：受控采集尚未安排",
          }
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
