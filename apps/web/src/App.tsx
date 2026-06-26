import { useCallback, useEffect, useMemo, useState } from "react";
import { DashboardShell } from "./components/DashboardShell";
import { todayShanghai } from "./lib/formatters";
import { API_BASE, COMPETITION_ID } from "./lib/labels";
import {
  asArray,
  cardPayload,
  cardStatus,
  computeStats,
  fixtureId,
  isFixtureOnDate,
  normalizeCards,
} from "./lib/normalize";
import type { DashboardCard, FilterMode, LoadState } from "./types/dashboard";

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

function updatedAtShanghai(): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

export default function App() {
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [filter, setFilter] = useState<FilterMode>("ALL");
  const [date, setDate] = useState<string>(todayShanghai());
  const [updatedAt, setUpdatedAt] = useState<string>("--");
  const [refreshKey, setRefreshKey] = useState(0);

  const loadCards = useCallback(() => {
    let cancelled = false;
    async function load() {
      try {
        setState("loading");
        const list = await getJSON(
          `${API_BASE}/fixtures?competition_id=${COMPETITION_ID}&page_size=80&status=NS&timezone=Asia/Shanghai&operational_date=${date}`,
        );
        const fixtures = asArray(list).filter((fixture) => isFixtureOnDate(fixture, date));
        const ids = fixtures.map(fixtureId).filter(Boolean);
        if (!ids.length) {
          if (!cancelled) {
            setCards([]);
            setState("empty");
          }
          return;
        }
        if (!cancelled) {
          setCards(normalizeCards(fixtures));
          setState("ok");
          setUpdatedAt(updatedAtShanghai());
        }
        ids.forEach((id, index) => {
          getJSON(`${API_BASE}/fixtures/${id}/analysis-card`, 60000)
            .then((payload) => {
              if (cancelled) return;
              const nextCard = cardPayload(payload);
              setCards((current) => current.map((card, cardIndex) => (cardIndex === index ? nextCard : card)));
              setUpdatedAt(updatedAtShanghai());
            })
            .catch(() => {
              if (cancelled) return;
              setCards((current) =>
                current.map((card, cardIndex) =>
                  cardIndex === index
                    ? {
                        ...card,
                        loading: false,
                        bookmaker_intent: { intent: "INSUFFICIENT_DATA", label_cn: "数据暂不可用" },
                        risks_cn: ["分析卡暂不可用，保持 SKIP。"],
                      }
                    : card,
                ),
              );
            });
        });
      } catch {
        if (!cancelled) setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [date]);

  useEffect(() => loadCards(), [loadCards, refreshKey]);

  const visibleCards = useMemo(() => {
    if (filter === "PICK") return cards.filter((card) => cardStatus(card) === "pick");
    if (filter === "SKIP") return cards.filter((card) => cardStatus(card) === "skip" || cardStatus(card) === "loading");
    if (filter === "WATCH") return cards.filter((card) => cardStatus(card) === "watch" || Number(card.watch_level ?? 0) >= 3);
    return cards;
  }, [cards, filter]);

  return (
    <DashboardShell
      cards={visibleCards}
      date={date}
      filter={filter}
      onDateChange={setDate}
      onFilterChange={setFilter}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      state={state}
      stats={computeStats(cards)}
      updatedAt={updatedAt}
    />
  );
}
