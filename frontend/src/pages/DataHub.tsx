import { useSearchParams } from "react-router-dom";
import Process from "./Process";
import Knowledge from "./Knowledge";
import IoCs from "./IoCs";
import Projects from "./Projects";

const TABS = ["process", "knowledge", "iocs", "projects"] as const;
const LABELS = { process: "Processing", knowledge: "Knowledge", iocs: "IoCs", projects: "Projects" };

export default function DataHub() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") || "process";
  const tab = TABS.includes(raw as any) ? raw as typeof TABS[number] : "process";
  return <>
    <div className="page-intro"><div><h1>Data & IoCs</h1><p>Process evidence, curate knowledge and manage indicators from one workspace.</p></div></div>
    <div className="tabs hub-tabs">{TABS.map(item => <button className={`tab ${tab === item ? "active" : ""}`} key={item} onClick={() => setParams({ tab: item })}>{LABELS[item]}</button>)}</div>
    {tab === "process" && <Process />}
    {tab === "knowledge" && <Knowledge />}
    {tab === "iocs" && <IoCs />}
    {tab === "projects" && <Projects />}
  </>;
}
