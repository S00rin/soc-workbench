import { ReactNode, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

const NAV = [
  { group: "Workspace", items: [
    { to: "/", icon: "▚", label: "Dashboard" },
    { to: "/process", icon: "⇪", label: "Input & Processing" },
    { to: "/knowledge", icon: "❏", label: "Knowledge Base" },
    { to: "/iocs", icon: "⌖", label: "IoCs" },
    { to: "/projects", icon: "◈", label: "Projects" },
    { to: "/jobs", icon: "⚙", label: "Jobs" },
  ]},
  { group: "Integrations", items: [
    { to: "/jira", icon: "◔", label: "Jira" },
    { to: "/splunk", icon: "◱", label: "Splunk & MCP" },
    { to: "/intel", icon: "◎", label: "Internet Intel" },
    { to: "/automation", icon: "↻", label: "Automation" },
    { to: "/reports", icon: "▤", label: "Reports" },
    { to: "/notifications", icon: "✉", label: "Notifications" },
    { to: "/prompts", icon: "❯", label: "Prompt Library" },
  ]},
  { group: "Training", items: [
    { to: "/attack-lab", icon: "⌁", label: "Attack Simulation Lab" },
  ]},
  { group: "System", items: [{ to: "/settings", icon: "⚙", label: "Settings" }]},
];
const TITLES: Record<string,string> = {
  "/":"Dashboard", "/process":"Input & Data Processing", "/knowledge":"SOC Knowledge Base",
  "/iocs":"IoC Repository", "/projects":"Projects", "/jobs":"Background Jobs",
  "/jira":"Jira", "/splunk":"Splunk & MCP", "/intel":"Internet Intelligence",
  "/automation":"Intelligence & Claude Automation", "/reports":"Reports",
  "/notifications":"Notifications", "/prompts":"Prompt Library", "/settings":"Settings",
  "/attack-lab":"Attack Simulation Lab",
};
export default function Layout({ children, onLogout }: { children: ReactNode; onLogout: () => void }) {
  const [open,setOpen]=useState(false); const loc=useLocation();
  return <div className="app">
    <aside className={`sidebar ${open ? "open" : ""}`} onClick={()=>setOpen(false)}>
      <div className="brand"><span className="logo">◆</span> SOC Workbench</div>
      {NAV.map(g=><div key={g.group}><div className="nav-group-label">{g.group}</div>
        {g.items.map(it=><NavLink key={it.to} to={it.to} end={it.to==="/"}
          className={({isActive})=>`nav-item ${isActive ? "active" : ""}`}>
          <span className="ic">{it.icon}</span><span>{it.label}</span></NavLink>)}</div>)}
    </aside>
    <div className="main"><header className="topbar"><div className="row">
      <button className="btn-ghost btn-sm" onClick={()=>setOpen(o=>!o)} style={{display:"none"}} id="menuBtn">☰</button>
      <span className="title">{TITLES[loc.pathname] || (loc.pathname.startsWith("/attack-lab/") ? "Attack Scenario" : "SOC Workbench")}</span></div>
      <div className="row"><span className="dim" style={{fontSize:12.5}}>admin</span>
      <button className="btn-sm btn-ghost" onClick={onLogout}>Sign out</button></div></header>
      <main className="content">{children}</main></div>
  </div>;
}
