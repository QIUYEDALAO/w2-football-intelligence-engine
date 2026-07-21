import { DashboardPage } from "../../components/DashboardPage";
import { DashboardV2VisualFixturePage } from "./DashboardV2VisualFixturePage";

export default function App() {
  if (window.location.pathname === "/__visual/dashboard-v2") {
    return <DashboardV2VisualFixturePage />;
  }
  return <DashboardPage />;
}
