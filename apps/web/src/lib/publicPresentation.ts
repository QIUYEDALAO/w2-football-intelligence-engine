import type { PublicStatusSemantics } from "../types/intelligenceWorkspace";

export type PublicTone = "neutral" | "warning" | "critical";

export interface PublicFacts {
  dayNoun?: "今日" | "所选比赛日";
  fixtureCount?: number;
  competitionCount?: number;
  marketReadyCount?: number;
  priorityCount?: number;
  finishedCount?: number;
  selectedFixture?: boolean;
  subject?: string;
}

export interface PublicPresentation {
  label: string;
  tone: PublicTone;
  className: "neutral" | "warn" | "critical";
  headline: string;
  summary: string;
  detail: string;
}

const causeCopy: Record<Exclude<PublicStatusSemantics["cause"], null>, Pick<PublicPresentation, "label" | "tone">> = {
  NOT_YET_DUE: { label: "未进入市场采集窗口", tone: "neutral" },
  AWAITING_COLLECTION: { label: "已到采集时点，证据待采集", tone: "warning" },
  INSUFFICIENT: { label: "已采集，证据量不足", tone: "warning" },
  UNAVAILABLE: { label: "来源不可用", tone: "critical" },
  UNASSESSED: { label: "尚未评估", tone: "neutral" },
  LABEL_MISSING: { label: "中文译名待映射", tone: "neutral" },
  IDENTITY_UNRESOLVED: { label: "身份待确认", tone: "warning" },
  AMBIGUOUS: { label: "身份存在歧义", tone: "warning" },
};

function result(
  label: string,
  tone: PublicTone,
  headline: string,
  summary: string,
  detail: string,
): PublicPresentation {
  return {
    label,
    tone,
    className: tone === "warning" ? "warn" : tone,
    headline,
    summary,
    detail,
  };
}

export function publicPresentation(
  semantics: PublicStatusSemantics,
  facts: PublicFacts = {},
): PublicPresentation {
  const day = facts.dayNoun || "所选比赛日";
  const fixtures = facts.fixtureCount || 0;
  const competitions = facts.competitionCount || 0;
  const ready = facts.marketReadyCount || 0;
  const subject = facts.subject || "当前对象";
  const cause = semantics.cause;
  const scopeSubject = semantics.scope === "MATCH"
    ? "本场比赛"
    : semantics.scope === "CROSS_DAY_CUMULATIVE"
      ? "跨比赛日累计证据"
      : semantics.scope === "GLOBAL"
        ? "全局证据"
        : `${day}比赛`;

  if (cause === "LABEL_MISSING") {
    return result(causeCopy[cause].label, causeCopy[cause].tone, subject, `${subject} 已识别，中文译名尚未映射。`, "保留可读原名；不会用占位符替换已知身份。");
  }
  if (cause === "IDENTITY_UNRESOLVED" || cause === "AMBIGUOUS") {
    const copy = causeCopy[cause];
    return result(copy.label, copy.tone, subject, `${subject} 的球队身份尚不能唯一确认。`, "身份确认前不生成中文译名。");
  }
  if (facts.subject === "赛果" && cause === "NOT_YET_DUE") {
    return result("赛果尚未产生", "neutral", "比赛尚未结束", "赛果尚未产生。", "这不是赛果采集缺口。");
  }
  if (facts.subject === "赛果" && cause === "AWAITING_COLLECTION") {
    return result("赛果待采集", "warning", "已完场，赛果待采集", "比赛已经结束，赛果仍待既有流程采集。", "只陈述已持久化的赛果事实。");
  }
  if (cause) {
    const copy = causeCopy[cause];
    const headline = semantics.scope === "SELECTED_DAY"
      ? `${scopeSubject}可查看，${cause === "NOT_YET_DUE" ? "尚未进入市场采集窗口" : copy.label}`
      : `${scopeSubject}：${copy.label}`;
    const summary = fixtures && semantics.scope === "SELECTED_DAY"
      ? `${day} ${fixtures} 场比赛可查看；${copy.label}，暂不生成市场分析。`
      : `${scopeSubject}：${copy.label}。`;
    const detail = cause === "NOT_YET_DUE"
      ? "赛程正常展示；等待既有采集窗口，不把正常等待渲染为故障。"
      : "只展示已持久化事实，不用缺失数据补算。";
    return result(copy.label, copy.tone, headline, summary, detail);
  }

  if (fixtures === 0) {
    return result("空比赛日", "neutral", "所选比赛日没有纳入观察池的比赛", "本比赛日观察池内没有比赛。", "不会用其他日期的比赛填充本页；空比赛日不代表系统异常。");
  }
  if (facts.finishedCount === fixtures) {
    return result("已完场", "neutral", `${day}比赛已完场`, `${fixtures} 场比赛已完场。`, "赛果与验证状态按各自证据作用域展示。");
  }
  if (facts.selectedFixture) {
    return result("市场证据可用", "neutral", "比赛级市场证据可用", `${ready || 1} 场比赛具备当前市场证据。`, "公开判断只来自持久化证据。");
  }
  if (ready > 0) {
    return result("市场证据可用", "neutral", `${day}已有市场证据`, `${ready} 场比赛具备持久化市场证据。`, "公开判断只来自持久化证据。");
  }
  if (facts.priorityCount === undefined) {
    return result("赛程可查看", "neutral", `${day}赛程可查看`, `${fixtures} 场比赛已持久化。`, "当前标签不推断市场或模型状态。");
  }
  return result("无需优先复核", "neutral", `${day}未发现需优先排查的比赛`, `${fixtures} 场比赛均未触发优先复核。`, `${competitions} 个联赛的持久化证据未达到关注阈值。`);
}
