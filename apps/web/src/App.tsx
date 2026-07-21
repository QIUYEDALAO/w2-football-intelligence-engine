import { lazy, Suspense } from "react";
import { DashboardPage } from "./components/DashboardPage";

const DashboardV2VisualFixturePage = import.meta.env.DEV
  ? lazy(async () => {
      const modulePath = "/src/reference/dashboard-v2/DashboardV2VisualFixturePage.tsx";
      const module = (await import(
        /* @vite-ignore */ modulePath
      )) as typeof import("./reference/dashboard-v2/DashboardV2VisualFixturePage");
      return { default: module.DashboardV2VisualFixturePage };
    })
  : null;

export default function App() {
  if (DashboardV2VisualFixturePage && window.location.pathname === "/__visual/dashboard-v2") {
    return (
      <Suspense fallback={null}>
        <DashboardV2VisualFixturePage />
      </Suspense>
    );
  }
  return <DashboardPage />;
}
