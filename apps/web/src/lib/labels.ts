import type { MarketCode } from "../types/dashboard";

export const API_BASE = "/v1";
export const COMPETITION_ID = "1";

export const MARKET_ORDER: MarketCode[] = ["ASIAN_HANDICAP", "TOTALS", "FIRST_HALF_GOALS", "SCORE"];

export const MARKET_META: Record<MarketCode, { label: string; short: string; className: string }> = {
  ASIAN_HANDICAP: { label: "让球", short: "让球", className: "market-ah" },
  TOTALS: { label: "大小球", short: "大小", className: "market-ou" },
  FIRST_HALF_GOALS: { label: "半场进球", short: "半场", className: "market-half" },
  SCORE: { label: "比分", short: "比分", className: "market-score" },
};

export const INTENT_LABELS: Record<string, string> = {
  HOME_LEAN: "偏主队",
  AWAY_LEAN: "偏客队",
  OVER_LEAN: "偏大球",
  UNDER_LEAN: "偏小球",
  CONFLICTED: "信号分歧",
  INSUFFICIENT_DATA: "数据不足",
  LEAKAGE_BLOCKED: "as-of 拦截",
};

export const TENDENCY_LABELS: Record<string, string> = {
  HOME_AH: "主队方向",
  AWAY_AH: "客队方向",
  NO_SIDE_EDGE: "暂无边向",
  OVER: "大球",
  UNDER: "小球",
  "1H_OVER": "半场有球",
  "1H_UNDER": "半场谨慎",
  HOME: "主胜方向",
  AWAY: "客胜方向",
  DRAW: "平局方向",
};

export const COMPETITION_TRANSLATIONS: Array<[RegExp, string]> = [
  [/World Cup/i, "世界杯"],
  [/Group Stage/i, "小组赛"],
  [/Round of 16/i, "16 强"],
  [/Quarter[- ]final/i, "四分之一决赛"],
  [/Semi[- ]final/i, "半决赛"],
  [/Final/i, "决赛"],
];

export const REASON_TRANSLATIONS: Array<[RegExp, string]> = [
  [/^F9_TRUE_XG:/, "滚动 xG 已纳入对比"],
  [/^F1_MARKET_MOVEMENT:/, "盘口从初盘到当前有可用变化"],
  [/^F2_BOOKMAKER_DISAGREEMENT:/, "多家庄家分歧已纳入"],
  [/^F3_REST:/, "体能与休息差已纳入"],
  [/^F4_MATCH_IMPORTANCE:/, "赛事阶段重要性已纳入"],
  [/^F5_SETTLED_AH_FORM:/, "近期赢盘表现已纳入"],
  [/^F6_H2H:/, "历史交锋已纳入"],
  [/^F7_STRENGTH_FORM:/, "球队强度与近期状态已纳入"],
  [/^F8_SQUAD_VALUE:/, "球队身价差异已纳入"],
  [/^FEATURES_INSUFFICIENT$/, "多因素输入不足"],
  [/^AH_ANALYSIS_INPUT_UNAVAILABLE$/, "让球分析输入不足"],
  [/^AH_MARKET_UNAVAILABLE$/, "让球盘口暂未覆盖"],
  [/^OU_ANALYSIS_INPUT_UNAVAILABLE$/, "大小球分析输入不足"],
  [/^OU_MARKET_UNAVAILABLE$/, "大小球盘口暂未覆盖"],
  [/^HALF_GOAL_INPUT_UNAVAILABLE$/, "半场进球模型输入不足"],
  [/^SCORE_MATRIX_UNAVAILABLE$/, "比分矩阵暂不可用"],
  [/^BOOKMAKER_INTENT_INPUT_UNAVAILABLE$/, "庄家意图输入不足"],
  [/^INSUFFICIENT_DATA$/, "数据点不足，暂不输出倾向"],
  [/^CONFLICTED$/, "盘口信号互相冲突，暂不强出方向"],
  [/^LEAKAGE_BLOCKED$/, "as-of 防泄漏规则拦截"],
  [/^大小球意图: OVER_LEAN$/, "大小球盘口倾向偏大"],
  [/^大小球意图: UNDER_LEAN$/, "大小球盘口倾向偏小"],
  [/^大小球意图: CONFLICTED$/, "大小球盘口方向存在分歧"],
  [/^庄家意图: HOME_LEAN$/, "庄家意图偏主队方向"],
  [/^庄家意图: AWAY_LEAN$/, "庄家意图偏客队方向"],
  [/^半场 Poisson 拆分 P\(1H>0\.5\)=/, "半场进球使用 1H Poisson 拆分估计"],
  [/^比分使用方向一致条件概率/, "比分只展示与主方向一致的条件概率"],
];
