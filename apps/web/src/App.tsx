import { lazy, Suspense } from "react";
import { DashboardPage } from "./components/DashboardPage";

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
  return BossConsoleVisualFixturePage && window.location.pathname === "/__visual/boss-console"
    ? (
      <Suspense fallback={null}>
        <BossConsoleVisualFixturePage />
      </Suspense>
    )
    : <DashboardPage />;
}
