import { useSearchParams } from "react-router-dom";
import Jobs from "./Jobs";
import Notifications from "./Notifications";

export default function OperationsHub() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "notifications" ? "notifications" : "jobs";
  return <>
    <div className="page-intro"><div><h1>Operations</h1><p>Monitor background work and outbound notifications.</p></div></div>
    <div className="tabs hub-tabs">
      <button className={`tab ${tab === "jobs" ? "active" : ""}`} onClick={() => setParams({ tab: "jobs" })}>Jobs</button>
      <button className={`tab ${tab === "notifications" ? "active" : ""}`} onClick={() => setParams({ tab: "notifications" })}>Notifications</button>
    </div>
    {tab === "jobs" ? <Jobs /> : <Notifications />}
  </>;
}
