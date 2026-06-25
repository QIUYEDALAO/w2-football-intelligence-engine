import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

const API_BASE = "/v1";
const COMPETITION_ID = "1";

const MARKET_LABEL: Record<string, string> = {
  ASIAN_HANDICAP: "让球",
  TOTALS: "大小球",
  FIRST_HALF_GOALS: "半场进球",
  SCORE: "比分",
};
const MARKET_ORDER = ["ASIAN_HANDICAP", "TOTALS", "FIRST_HALF_GOALS", "SCORE"];
const LEAN_COLOR: Record<string, string> = {
  ASIAN_HANDICAP: "#185FA5",
  TOTALS: "#3B6D11",
  FIRST_HALF_GOALS: "#5F5E5A",
  SCORE: "#5F5E5A",
};
const LEAN_BG: Record<string, string> = {
  ASIAN_HANDICAP: "#E6F1FB",
  TOTALS: "#EAF3DE",
  FIRST_HALF_GOALS: "#F1EFE8",
  SCORE: "#F1EFE8",
};

function todayShanghai(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function isFixtureOnDate(fixture: unknown, selectedDate: string): boolean {
  const record = asRecord(fixture);
  const operationalDate = record.operational_date_beijing;
  if (typeof operationalDate === "string" && operationalDate) {
    return operationalDate === selectedDate;
  }
  const kickoffBeijing = record.kickoff_beijing;
  if (typeof kickoffBeijing === "string" && kickoffBeijing) {
    return kickoffBeijing.startsWith(selectedDate);
  }
  return false;
}

async function getJSON(url: string, timeoutMs = 20000): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal }).finally(() => {
    window.clearTimeout(timeout);
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  const record = asRecord(value);
  for (const key of ["items", "fixtures", "data", "results"]) {
    const nested = record[key];
    if (Array.isArray(nested)) {
      return nested;
    }
  }
  return [];
}

function fxId(item: unknown): string {
  const record = asRecord(item);
  const fixture = asRecord(record.fixture);
  return String(record.fixture_id ?? record.id ?? fixture.id ?? "");
}

function fmtTime(iso?: unknown): string {
  if (typeof iso !== "string" || !iso) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(iso));
  } catch {
    return "";
  }
}

function cardPayload(payload: unknown): Record<string, unknown> {
  const record = asRecord(payload);
  return asRecord(record.card ?? payload);
}

function marketPayload(market: unknown): Record<string, unknown> {
  return asRecord(market);
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value ? value : fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function Dots({ value }: { value?: unknown }) {
  const n = Math.max(0, Math.min(5, Math.round(numberValue(value) * 5)));
  return (
    <span style={{ display: "inline-flex", gap: 3, verticalAlign: "middle" }}>
      {[0, 1, 2, 3, 4].map((index) => (
        <span
          key={index}
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: index < n ? "#185FA5" : "transparent",
            border: index < n ? "none" : "1px solid #cfcfcf",
          }}
        />
      ))}
    </span>
  );
}

function scoreLabels(market: Record<string, unknown>): string[] {
  const scores = market.scores;
  if (Array.isArray(scores)) {
    return scores.map((score) => String(score)).filter(Boolean);
  }
  const references = market.reference_scores;
  if (!Array.isArray(references)) {
    return [];
  }
  return references
    .map((score) => {
      const record = asRecord(score);
      return String(record.scoreline ?? score ?? "");
    })
    .filter(Boolean);
}

function MarketRow({ market }: { market: unknown }) {
  const m = marketPayload(market);
  const code = textValue(m.market);
  const label = MARKET_LABEL[code] ?? code;
  const skip = textValue(m.decision, "SKIP") === "SKIP";
  const scores = scoreLabels(m);
  const reason = textValue(m.reason ?? m.reason_cn);
  return (
    <div style={{ borderTop: "0.5px solid #e7e5df", padding: "9px 0" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 13, color: "#444" }}>{label}</span>
        {skip ? (
          <span style={{ fontSize: 12, color: "#8a8a8a", border: "0.5px solid #e0ded7", padding: "3px 9px", borderRadius: 8 }}>
            SKIP
          </span>
        ) : (
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {code === "SCORE" ? (
              scores.slice(0, 2).map((score, index) => (
                <span key={`${score}-${index}`} style={{ fontSize: 12, color: "#444", background: "#f4f3ee", padding: "3px 9px", borderRadius: 8 }}>
                  {score}
                </span>
              ))
            ) : (
              <span
                style={{
                  fontSize: 12,
                  color: LEAN_COLOR[code] ?? "#444",
                  background: LEAN_BG[code] ?? "#f1efe8",
                  padding: "3px 9px",
                  borderRadius: 8,
                }}
              >
                {textValue(m.lean ?? m.lean_cn, "倾向")}
              </span>
            )}
            {code !== "SCORE" ? <Dots value={m.confidence} /> : null}
          </span>
        )}
      </div>
      {!skip && reason ? <div style={{ fontSize: 12, color: "#9a978d", marginTop: 4 }}>理由：{reason}</div> : null}
      {code === "SCORE" && !skip ? <div style={{ fontSize: 12, color: "#9a978d", marginTop: 4 }}>方向一致的条件概率 · 非精确比分预测</div> : null}
    </div>
  );
}

function Card({ card }: { card: unknown }) {
  const c = cardPayload(card);
  const skip = textValue(c.decision, "SKIP") === "SKIP";
  const intent = asRecord(c.bookmaker_intent);
  const marketList = Array.isArray(c.markets) ? c.markets : [];
  const markets = MARKET_ORDER.map((code) => marketList.find((market) => marketPayload(market).market === code)).filter(Boolean);
  const watch = Math.max(0, Math.min(4, Number(c.watch_level ?? 0)));
  const risks = Array.isArray(c.risks_cn) ? c.risks_cn : Array.isArray(c.risks) ? c.risks : ["—"];
  const intentLabel = textValue(intent.label_cn, textValue(intent.intent) === "INSUFFICIENT_DATA" ? "数据不足" : textValue(intent.intent, "—"));
  const openingLine = textValue(intent.opening_line);
  const currentLine = textValue(intent.current_line);
  return (
    <div style={{ background: "#fff", border: "0.5px solid #e7e5df", borderRadius: 12, padding: "1rem 1.25rem", marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span
          style={{
            fontSize: 12,
            color: skip ? "#6b6b6b" : "#185FA5",
            background: skip ? "#f1efe8" : "#E6F1FB",
            padding: "3px 9px",
            borderRadius: 8,
          }}
        >
          {skip ? "数据不足" : "有分析"}
        </span>
        <span style={{ fontSize: 12, color: "#9a978d" }}>
          {fmtTime(c.kickoff_utc)} · {textValue(c.competition_cn, "世界杯")}
        </span>
      </div>
      <div style={{ fontSize: 17, fontWeight: 500, marginBottom: 10 }}>
        {textValue(c.home_cn, "主队")} <span style={{ color: "#b3b1a8", fontWeight: 400 }}>vs</span> {textValue(c.away_cn, "客队")}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#f6f5f0", padding: "8px 12px", borderRadius: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 13, color: "#666" }}>
          庄家意图：{intentLabel}
          {openingLine && currentLine ? ` · 盘口 ${openingLine} → ${currentLine}` : ""}
        </span>
      </div>
      {skip ? (
        <div style={{ fontSize: 12, color: "#9a978d", paddingTop: 8 }}>暂不推荐：等盘口快照与 xG 富集到位后自动更新。</div>
      ) : (
        <>
          {markets.map((market, index) => (
            <MarketRow key={index} market={market} />
          ))}
          <div style={{ borderTop: "0.5px solid #e7e5df", paddingTop: 10, marginTop: 2, display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 12, color: "#a3322d" }}>风险：{risks.map((risk) => String(risk)).join("；")}</span>
            <span style={{ fontSize: 12, color: "#9a978d" }}>
              关注度 <span style={{ color: "#BA7517" }}>{"★".repeat(watch)}</span>
              {"☆".repeat(4 - watch)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function Dashboard() {
  const [cards, setCards] = useState<Record<string, unknown>[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error" | "empty">("loading");
  const date = todayShanghai();

  useEffect(() => {
    (async () => {
      try {
        setState("loading");
        const list = await getJSON(`${API_BASE}/fixtures?competition_id=${COMPETITION_ID}&page_size=80&status=NS&timezone=Asia/Shanghai&operational_date=${date}`);
        const ids = asArray(list).filter((fixture) => isFixtureOnDate(fixture, date)).map(fxId).filter(Boolean);
        if (ids.length === 0) {
          setState("empty");
          return;
        }
        const results = await Promise.all(ids.map((id) => getJSON(`${API_BASE}/fixtures/${id}/analysis-card`, 60000).catch(() => null)));
        const ok = results.filter(Boolean).map(cardPayload);
        setCards(ok);
        setState(ok.length ? "ok" : "empty");
      } catch {
        setState("error");
      }
    })();
  }, [date]);

  return (
    <div
      style={{
        maxWidth: 760,
        margin: "0 auto",
        padding: "20px 16px",
        fontFamily: "system-ui, -apple-system, 'PingFang SC', sans-serif",
        color: "#222",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontSize: 18, fontWeight: 500 }}>W2 足球分析 · 今日比赛</span>
        <span style={{ fontSize: 12, color: "#854F0B", background: "#FAEEDA", padding: "4px 10px", borderRadius: 8 }}>分析参考 · 非稳赢</span>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 13, padding: "5px 12px", borderRadius: 8, background: "#f1efe8" }}>今日</span>
        <span style={{ fontSize: 13, padding: "5px 12px", borderRadius: 8, border: "0.5px solid #e7e5df", color: "#666" }}>世界杯</span>
        <span style={{ fontSize: 13, padding: "5px 12px", borderRadius: 8, border: "0.5px solid #e7e5df", color: "#666" }}>{date}</span>
      </div>
      {state === "loading" ? <div style={{ color: "#9a978d", fontSize: 14, padding: "2rem 0", textAlign: "center" }}>加载中…</div> : null}
      {state === "error" ? <div style={{ color: "#a3322d", fontSize: 14, padding: "2rem 0", textAlign: "center" }}>加载失败，请稍后重试。</div> : null}
      {state === "empty" ? <div style={{ color: "#9a978d", fontSize: 14, padding: "2rem 0", textAlign: "center" }}>今日暂无白名单比赛或数据未就绪。</div> : null}
      {state === "ok" ? cards.map((card, index) => <Card key={index} card={card} />) : null}
      <div style={{ fontSize: 11, color: "#9a978d", textAlign: "center", marginTop: 14, lineHeight: 1.6 }}>
        本页为分析参考，非投注建议，不保证盈利 · 数据不足时一律 SKIP，不强出推荐
      </div>
    </div>
  );
}

const el = document.getElementById("root");
if (el) {
  createRoot(el).render(<Dashboard />);
}
