import type { DashboardMode } from "../types/dashboard";

const TABS: Array<{ value: DashboardMode; label: string }> = [
  { value: "today", label: "今日推荐" },
  { value: "next36", label: "未来赛程" },
  { value: "results", label: "完场复盘" },
  { value: "all", label: "全部比赛" },
];

export function SegmentTabs({ mode, onModeChange }: { mode: DashboardMode; onModeChange: (mode: DashboardMode) => void }) {
  return (
    <nav className="segment-tabs" aria-label="Dashboard sections">
      {TABS.map((tab) => (
        <button className={mode === tab.value ? "toolbar-button is-active" : "toolbar-button"} key={tab.value} onClick={() => onModeChange(tab.value)} type="button">
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
