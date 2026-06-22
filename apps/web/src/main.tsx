import React from "react";
import { createRoot } from "react-dom/client";
import { DashboardShell } from "./product-dashboard";
import "./styles.css";

export const stage10CompatibilityAnchors = {
  notice: "正式推荐尚未启用，当前仅为研究与前瞻验证。",
  fixtureEndpoint: "/api/v1/fixtures",
  operationsEndpointPrefix: "/api/ops/",
};

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <DashboardShell />
  </React.StrictMode>,
);
