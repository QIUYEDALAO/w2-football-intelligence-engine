import type { BossConsoleModel, BossDecisionItem } from "./boss-console-model";

function readyScoreline(
  decisionHash: string,
  evidenceHash: string,
  consistencyLabel: string,
  rows: Array<{
    scoreline: string;
    sampleCount: number;
    primarySettlement: "WIN" | "HALF_WIN";
  }>,
): NonNullable<BossDecisionItem["scorelineProjection"]> {
  const consistentSampleCount = 6417;
  return {
    status: "READY",
    simulationsRequested: 10_000,
    simulationsCompleted: 10_000,
    consistentSampleCount,
    consistencyLabel,
    decisionHash,
    evidenceHash,
    blocker: null,
    top3: rows.map((row) => ({
      ...row,
      unconditionalProbability: row.sampleCount / 10_000,
      conditionalProbability: row.sampleCount / consistentSampleCount,
    })),
  };
}

function item(
  value: Partial<BossDecisionItem> & Pick<BossDecisionItem, "id" | "priority" | "kickoffUtc" | "match" | "status" | "recommendation">,
): BossDecisionItem {
  const pick = value.status === "pick";
  const watch = value.status === "watch";
  return {
    fixtureStatus: "NS",
    league: "瑞典超 · 常规赛第14轮",
    decision: pick ? "分析建议" : watch ? "继续观察" : "暂不可判断",
    modelProbability: null,
    marketProbability: null,
    probabilityDelta: null,
    expectedValue: null,
    uncertainty: null,
    scorelineProjection: null,
    candidateRole: null,
    marketPolicyLabel: null,
    marketMainlineLabel: null,
    executionQuoteLabel: null,
    marketLadder: [],
    risk: "中",
    riskLevel: "medium",
    riskNote: pick ? "首发未确认" : watch ? "NO_EDGE" : "未到采集时点",
    lineupPending: pick,
    nextAction: pick ? "赛前30分钟" : watch ? "等待新盘口" : "待安排",
    nextDetail: pick ? "新盘口 / 首发 / 阵容异常" : watch ? "下一次受控采集" : "受控采集窗口",
    snapshotAt: pick || watch ? "2026-07-21T10:59:00Z" : null,
    lifecycleState: pick ? "ANALYSIS_PICK_ACTIVE" : watch ? "NO_EDGE_CURRENT" : "NOT_READY_SOURCE_ABSENT",
    quoteAgeSeconds: pick || watch ? 0 : null,
    latestCheckpoint: pick || watch ? "T-1h" : null,
    nextCheckpoint: pick || watch ? "LINEUP_CONFIRMED" : "opening",
    automaticRefreshStatus: pick || watch ? "已评估当前快照" : "等待评估快照",
    lineupFacts: [pick ? "首发尚未确认" : "尚未到公布窗口或确认首发尚未取得", "模型影响：仅 advisory · 数值调整关闭"],
    ledgerCode: pick ? "8aab83c" : "—",
    ledgerStatus: pick ? "验证 ledger 已记录" : watch ? "仅保留观察证据" : "尚未进入验证 ledger",
    ledgerDetail: pick ? "待完场结算 · 不产生假赛果" : watch ? "不计入推荐命中率" : "待形成完整赛前决策",
    reasons: pick
      ? ["模型与同盘口市场概率差达到分析门槛", "真实 xG 与球队评级方向一致", "执行报价与推荐方向、盘口线完全绑定"]
      : watch
        ? ["模型和市场接近，不足以形成分析方向", "模型 EV 未达到门槛", "保持 NO_EDGE 比强行推荐更可信"]
        : ["比赛尚未进入完整评估窗口", "当前不展示虚假概率或推荐", "达到采集条件后进入决策队列"],
    risks: pick
      ? ["首发尚未公布，阵容变化可能影响结论", "盘口变化后必须重新计算", "正式推荐能力仍未开放"]
      : watch
        ? ["暂无可执行方向", "临场盘口变化后结论可能改变", "当前不进入统一前向验证账本分母"]
        : ["盘口或首发数据尚不完整", "不可用历史快照替代当前执行报价", "保持 NOT_READY"],
    dataRisk: pick || watch ? "READY" : "阻断",
    marketIdentityRisk: pick || watch ? "主线身份完整" : "盘口身份待确认",
    lineupRisk: pick ? "首发待确认" : "首发证据未进入建议门",
    ...value,
  };
}

export const bossConsoleFixture: BossConsoleModel = {
  release: {
    environment: "staging",
    apiSha: "d2a7980",
    webSha: "d2a7980",
    pageUpdatedAt: "2026-07-21T12:33:00Z",
    oddsConfirmedAt: "2026-07-21T10:59:00Z",
    nextRefreshAt: null,
  },
  ledger: {
    rangeLabel: "07-07 至 07-21",
    validationCount: 28,
    settledCount: 23,
    pendingCount: 5,
    eligibleCount: 16,
    evidenceRepairPendingCount: 7,
    hitCount: 11,
    missCount: 3,
    pushCount: 2,
    voidCount: 0,
    decisiveCount: 14,
    hitRate: 11 / 14,
    clvMedian: 0.01,
    clvSampleCount: 2,
  },
  selectedDecisionId: "1494218",
  automaticCollectionPaused: true,
  riskExceptionCount: 2,
  lineupPendingCount: 2,
  lastCheckedAt: "2026-07-21T12:31:00Z",
  runtime: {
    schemaStatus: "PASS",
    serviceStatus: "HEALTHY",
    providerStatus: "DISABLED",
    schedulerStatus: "STOPPED",
    formalStatus: "DISABLED",
    lockProductionStatus: "DISABLED",
  },
  decisions: [
    item({ id: "1494218", priority: "P1", kickoffUtc: "2026-07-25T13:00:00Z", match: "代格福什 vs 尤尔加登", status: "pick", recommendation: "客队 -0.75 @1.90", modelProbability: .568, marketProbability: .497, probabilityDelta: .071, expectedValue: .074, uncertainty: .044, ledgerCode: "8aab83c", scorelineProjection: readyScoreline("10ad2a2dec", "e04aa5d8ef", "全部符合：客队 -0.75", [{ scoreline: "0-1", sampleCount: 1130, primarySettlement: "HALF_WIN" }, { scoreline: "0-2", sampleCount: 980, primarySettlement: "WIN" }, { scoreline: "1-2", sampleCount: 870, primarySettlement: "HALF_WIN" }]), reasons: ["模型与同盘口市场概率差达到 +7.1pp", "真实 xG 与球队评级方向一致", "执行报价与推荐方向、盘口线完全绑定"], risks: ["首发尚未公布，阵容变化可能影响结论", "盘口若由 -0.75 跳到 -1.0 需重新计算", "EV 标准误 ±4.4%，正式推荐能力仍未开放"] }),
    item({ id: "1494223", priority: "P2", kickoffUtc: "2026-07-26T12:00:00Z", match: "天狼星 vs 哥德堡", status: "pick", recommendation: "小 3.5 @1.98", modelProbability: .62, marketProbability: .55, probabilityDelta: .07, expectedValue: .061, uncertainty: .038, risk: "低", riskLevel: "low", riskNote: "盘口稳定", nextAction: "首发公布后", nextDetail: "首发 / 伤停 / 总进球线变化", ledgerCode: "d4c81b2", scorelineProjection: readyScoreline("22be819dec", "f18ca4e1ef", "全部符合：小 3.5", [{ scoreline: "1-1", sampleCount: 1060, primarySettlement: "WIN" }, { scoreline: "1-0", sampleCount: 930, primarySettlement: "WIN" }, { scoreline: "0-1", sampleCount: 850, primarySettlement: "WIN" }]) }),
    item({ id: "1494222", priority: "P3", kickoffUtc: "2026-07-26T12:00:00Z", match: "布洛马波卡纳 vs 哈马比", status: "pick", recommendation: "客队 -1.25 @1.92", modelProbability: .583, marketProbability: .495, probabilityDelta: .088, expectedValue: .094, uncertainty: .052, risk: "高", riskLevel: "high", riskNote: "深盘波动", nextAction: "盘口变动即重评", nextDetail: "盘口 / 首发 / 伤停", ledgerCode: "b37f20a", scorelineProjection: readyScoreline("33cf920dec", "a29db5f2ef", "全部符合：客队 -1.25", [{ scoreline: "0-2", sampleCount: 1010, primarySettlement: "WIN" }, { scoreline: "1-3", sampleCount: 890, primarySettlement: "WIN" }, { scoreline: "0-3", sampleCount: 740, primarySettlement: "WIN" }]) }),
    item({ id: "1494217", priority: "P4", kickoffUtc: "2026-07-26T14:30:00Z", match: "马尔默 vs 埃尔夫斯堡", status: "pick", recommendation: "大 2.5 @1.85", modelProbability: .602, marketProbability: .541, probabilityDelta: .061, expectedValue: .056, uncertainty: .041, riskNote: "阵容待定", nextAction: "赛前60分钟", nextDetail: "首发 / 天气 / 总进球线", ledgerCode: "9ae41dd", scorelineProjection: readyScoreline("44da031dec", "b30ec6a3ef", "全部符合：大 2.5", [{ scoreline: "2-1", sampleCount: 1080, primarySettlement: "WIN" }, { scoreline: "2-2", sampleCount: 920, primarySettlement: "WIN" }, { scoreline: "3-1", sampleCount: 810, primarySettlement: "WIN" }]) }),
    item({ id: "1494220", priority: "P5", kickoffUtc: "2026-07-26T17:00:00Z", match: "赫根 vs AIK Stockholm", status: "pick", recommendation: "小 3.5 @1.91", modelProbability: .624, marketProbability: .567, probabilityDelta: .057, expectedValue: .049, uncertainty: .036, risk: "低", riskLevel: "low", riskNote: "优势较窄", nextAction: "赛前30分钟", nextDetail: "临场总进球线 / 首发", ledgerCode: "1f6de40", scorelineProjection: readyScoreline("55eb142dec", "c41fd7b4ef", "全部符合：小 3.5", [{ scoreline: "1-1", sampleCount: 1110, primarySettlement: "WIN" }, { scoreline: "1-0", sampleCount: 900, primarySettlement: "WIN" }, { scoreline: "0-1", sampleCount: 820, primarySettlement: "WIN" }]) }),
    item({ id: "1494224", priority: "W1", kickoffUtc: "2026-07-23T17:00:00Z", match: "北雪平 vs 瓦尔贝里", status: "watch", recommendation: "优势不足 · 暂不选方向", modelProbability: .514, marketProbability: .499, probabilityDelta: .015, expectedValue: .008, uncertainty: .049, riskNote: "分歧不足" }),
    item({ id: "1494221", priority: "W2", kickoffUtc: "2026-07-25T15:30:00Z", match: "米亚尔比 vs 厄斯特松德", status: "watch", recommendation: "模型优势不足", modelProbability: .526, marketProbability: .504, probabilityDelta: .022, expectedValue: .013, uncertainty: .042, risk: "低", riskLevel: "low" }),
    item({ id: "1494219", priority: "W3", kickoffUtc: "2026-07-26T14:00:00Z", match: "卡尔马 vs 哈尔姆斯塔德", status: "watch", recommendation: "NO_EDGE · 不操作", modelProbability: .498, marketProbability: .492, probabilityDelta: .006, expectedValue: .002, uncertainty: .039, risk: "低", riskLevel: "low", riskNote: "无优势", nextAction: "等待临场", nextDetail: "新报价或阵容变化" }),
    ...[
      ["future-1", "N1", "2026-07-27T11:00:00Z", "韦纳穆 vs 北雪平", "尚未进入临场窗口"],
      ["future-2", "N2", "2026-07-28T12:30:00Z", "哥德堡盖斯 vs 天狼星", "等待首轮盘口"],
      ["future-3", "N3", "2026-07-29T13:00:00Z", "尤尔加登 vs 马尔默", "尚未进入临场窗口"],
      ["future-4", "N4", "2026-07-30T14:00:00Z", "AIK vs 哈马比", "等待首轮盘口"],
      ["future-5", "N5", "2026-07-31T15:00:00Z", "赫根 vs 代格福什", "尚未进入临场窗口"],
      ["future-6", "N6", "2026-08-01T16:30:00Z", "埃尔夫斯堡 vs 米亚尔比", "等待首轮盘口"],
    ].map(([id, priority, kickoffUtc, match, recommendation]) => item({ id, priority, kickoffUtc, match, status: "not-ready", recommendation, league: "瑞典超 · 未来赛程" })),
  ],
  leaguePerformance: [
    { competitionKey: "eliteserien", league: "挪威超", eligibleCount: 6, hitCount: 4, missCount: 1, pushCount: 1, clvMedian: .04, clvSampleCount: 1, statusLabel: "样本不足" },
    { competitionKey: "allsvenskan", league: "瑞典超", eligibleCount: 4, hitCount: 3, missCount: 1, pushCount: 0, clvMedian: -.02, clvSampleCount: 1, statusLabel: "样本不足" },
    { competitionKey: "brasileirao_serie_a", league: "巴甲", eligibleCount: 4, hitCount: 2, missCount: 1, pushCount: 1, clvMedian: null, clvSampleCount: 0, statusLabel: "样本不足" },
    { competitionKey: "chinese_super_league", league: "中超", eligibleCount: 2, hitCount: 2, missCount: 0, pushCount: 0, clvMedian: null, clvSampleCount: 0, statusLabel: "样本不足" },
  ],
};
