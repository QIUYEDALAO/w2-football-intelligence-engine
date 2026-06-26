import type { FilterMode } from "../types/dashboard";

const FILTERS: Array<{ value: FilterMode; label: string }> = [
  { value: "ALL", label: "全部" },
  { value: "PICK", label: "有分析" },
  { value: "SKIP", label: "跳过" },
  { value: "WATCH", label: "关注" },
];

export function DashboardToolbar({
  date,
  filter,
  onDateChange,
  onFilterChange,
  onRefresh,
}: {
  date: string;
  filter: FilterMode;
  onDateChange: (value: string) => void;
  onFilterChange: (value: FilterMode) => void;
  onRefresh: () => void;
}) {
  return (
    <nav className="dashboard-toolbar" aria-label="Dashboard controls">
      <div className="filter-row">
        {FILTERS.map((item) => (
          <button
            className={filter === item.value ? "toolbar-button is-active" : "toolbar-button"}
            key={item.value}
            onClick={() => onFilterChange(item.value)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="date-refresh">
        <label>
          日期
          <input type="date" value={date} onChange={(event) => onDateChange(event.target.value)} />
        </label>
        <button className="toolbar-button refresh-button" onClick={onRefresh} type="button">
          刷新
        </button>
      </div>
    </nav>
  );
}
