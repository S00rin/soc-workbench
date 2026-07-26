import { useSearchParams } from "react-router-dom";
import IntegrationChat from "./IntegrationChat";
import Atlassian from "./Atlassian";
import WikiJS from "./WikiJS";
import Splunk from "./Splunk";

const TABS = ["chat", "atlassian", "wikijs", "splunk"] as const;
const LABELS = { chat: "Prompt Chat", atlassian: "Jira & Confluence", wikijs: "Wiki.js", splunk: "Splunk" };

export default function IntegrationHub() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") || "chat";
  const tab = TABS.includes(raw as any) ? raw as typeof TABS[number] : "chat";
  return <>
    <div className="page-intro"><div><h1>Integration Hub</h1><p>One place for connections, permissions, natural-language analysis and complete history.</p></div></div>
    <div className="tabs hub-tabs">{TABS.map(item => <button className={`tab ${tab === item ? "active" : ""}`} key={item} onClick={() => setParams({ tab: item })}>{LABELS[item]}</button>)}</div>
    {tab === "chat" && <IntegrationChat />}
    {tab === "atlassian" && <Atlassian />}
    {tab === "wikijs" && <WikiJS />}
    {tab === "splunk" && <Splunk />}
  </>;
}
