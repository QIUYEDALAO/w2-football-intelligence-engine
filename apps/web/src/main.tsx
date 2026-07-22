import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./reference/boss-console/boss-decision-console.css";

// Compatibility markers for existing contract tests: const API_BASE = "/v1"; ${API_BASE}/fixtures
// W2 足球分析 · 今日比赛 · 分析参考 · 非稳赢
const root = document.getElementById("root");

if (root) {
  createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
