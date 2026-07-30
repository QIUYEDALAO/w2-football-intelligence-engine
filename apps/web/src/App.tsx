import { lazy, Suspense } from "react";
import { DashboardPage } from "./components/DashboardPage";
import { PerformancePage } from "./components/PerformancePage";

function PrimaryNavigation() {
  return (
    <nav className="primary-navigation" aria-label="主导航">
      <a className={window.location.pathname === "/" ? "is-active" : ""} href="/">比赛决策</a>
      <a className={window.location.pathname === "/performance" ? "is-active" : ""} href="/performance">表现复盘</a>
    </nav>
  );
}

const BossConsoleVisualFixturePage = import.meta.env.DEV
  ? lazy(async () => {
      const modulePath = "/src/reference/boss-console/BossConsoleVisualFixturePage.tsx";
      const module = (await import(
        /* @vite-ignore */ modulePath
      )) as typeof import("./reference/boss-console/BossConsoleVisualFixturePage");
      return { default: module.BossConsoleVisualFixturePage };
    })
  : null;

export default function App() {
  if (BossConsoleVisualFixturePage && window.location.pathname === "/__visual/boss-console") {
    return (
      <Suspense fallback={null}>
        <BossConsoleVisualFixturePage />
      </Suspense>
    );
  }
  return (
    <>
      <PrimaryNavigation />
      {window.location.pathname === "/performance" ? <PerformancePage /> : <DashboardPage />}
    </>
  );
}
