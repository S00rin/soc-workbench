import { useSearchParams } from "react-router-dom";
import Intel from "./Intel";
import Automation from "./Automation";

export default function IntelligenceHub() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "automation" ? "automation" : "intel";
  return <>
    <div className="page-intro"><div><h1>Intelligence</h1><p>Collect, review and automate threat-intelligence workflows.</p></div></div>
    <div className="tabs hub-tabs">
      <button className={`tab ${tab === "intel" ? "active" : ""}`} onClick={() => setParams({ tab: "intel" })}>Internet Intel</button>
      <button className={`tab ${tab === "automation" ? "active" : ""}`} onClick={() => setParams({ tab: "automation" })}>Automation</button>
    </div>
    {tab === "intel" ? <Intel /> : <Automation />}
  </>;
}
