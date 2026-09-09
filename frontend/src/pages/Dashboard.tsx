import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { hasFeature, useAccess } from "../access";
import Executive from "./dashboard/Executive";
import Overview from "./dashboard/Overview";
import Technical from "./dashboard/Technical";

const VIEWS = [
  { key: "overview", label: "Overview", feature: "" },
  { key: "executive", label: "Executive", feature: "dashboard.executive" },
  { key: "technical", label: "Technical", feature: "dashboard.technical" },
] as const;
type ViewKey = typeof VIEWS[number]["key"];
const DEFAULT_DAYS: Record<ViewKey, number> = { overview: 0, executive: 30, technical: 7 };
const REFRESH_KEY = "sorin-dashboard-refresh";

export default function Dashboard() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const [autoRefresh, setAutoRefresh] = useState(() => localStorage.getItem(REFRESH_KEY) !== "off");

  const available = VIEWS.filter(view => !view.feature || hasFeature(access, view.feature));
  const requested = params.get("view") as ViewKey | null;
  const view: ViewKey = available.some(item => item.key === requested) ? (requested as ViewKey) : "overview";
  const parsedDays = Number(params.get("days"));
  const days = Number.isFinite(parsedDays) && parsedDays > 0 ? parsedDays : DEFAULT_DAYS[view];

  const select = (next: ViewKey) => setParams(next === "overview" ? {} : { view: next });
  const setDays = (value: number) => setParams({ view, days: String(value) });
  const toggleRefresh = () => {
    const next = !autoRefresh;
    setAutoRefresh(next);
    localStorage.setItem(REFRESH_KEY, next ? "on" : "off");
  };
  const refreshMs = autoRefresh ? 60_000 : 0;

  return <>
    {available.length > 1 && <div className="tabs hub-tabs dashboard-views">
      {available.map(item => <button key={item.key} className={`tab ${view === item.key ? "active" : ""}`} onClick={() => select(item.key)}>{item.label}</button>)}
      <span className="spacer" />
      <label className="auto-refresh"><input type="checkbox" checked={autoRefresh} onChange={toggleRefresh} /> Auto-refresh (60s)</label>
    </div>}
    {view === "overview" && <Overview refreshMs={refreshMs} />}
    {view === "executive" && <Executive days={days} onDays={setDays} refreshMs={refreshMs} />}
    {view === "technical" && <Technical days={days} onDays={setDays} refreshMs={refreshMs} />}
  </>;
}
