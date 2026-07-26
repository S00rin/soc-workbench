import { ReactNode, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { hasFeature, hasModule, useAccess } from "../access";

type NavItem = { to: string; icon: string; label: string; module?: string; feature?: string; admin?: boolean };
const NAV: { group: string; items: NavItem[] }[] = [
  { group: "Overview", items: [{ to: "/", icon: "01", label: "Dashboard", module: "dashboard" }] },
  { group: "Workspace", items: [
    { to: "/data", icon: "02", label: "Data & IoCs", module: "data" },
    { to: "/integrations", icon: "03", label: "Integration Hub", module: "integrations" },
    { to: "/intelligence", icon: "04", label: "Intelligence", module: "intelligence" },
    { to: "/reports", icon: "05", label: "Reports", module: "reports" },
    { to: "/price-analyzer", icon: "06", label: "Price Analyzer", module: "price_analyzer" },
    { to: "/sensors", icon: "07", label: "Sensor Library", module: "sensors" },
  ] },
  { group: "Manage", items: [
    { to: "/operations", icon: "08", label: "Operations", module: "operations" },
    { to: "/prompts", icon: "09", label: "Prompt Library", module: "prompts" },
    { to: "/admin/access", icon: "10", label: "Access & Features", admin: true },
    { to: "/settings", icon: "11", label: "Settings", module: "settings" },
    { to: "/help", icon: "?", label: "Help Guides" },
  ] },
  { group: "Training", items: [
    { to: "/attack-lab", icon: "12", label: "Attack Simulation Lab" },
  ] },
  { group: "Soorin", items: [{ to: "/about-sorin", icon: "S", label: "معرفی سورین" }] },
];

const TITLES: Record<string, string> = {
  "/": "Dashboard", "/data": "Data & IoCs", "/integrations": "Integration Hub",
  "/intelligence": "Intelligence", "/reports": "Reports", "/price-analyzer": "Price Analyzer",
  "/sensors": "Equipment & Sensor Library",
  "/operations": "Operations", "/prompts": "Prompt Library", "/settings": "Settings",
  "/admin/access": "Access & Feature Control", "/help": "Help Guides",
  "/about-sorin": "معرفی سورین", "/attack-lab": "Attack Simulation Lab",
};

export default function Layout({ children, onLogout }: { children: ReactNode; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const access = useAccess();
  const title = TITLES[loc.pathname] || (loc.pathname.startsWith("/attack-lab/") ? "Attack Scenario" : "Soorin SOC Workbench");
  const visibleGroups = NAV.map(group => ({
    ...group,
    items: group.items.filter(item =>
      (!item.admin || access.user.role === "admin") &&
      (!item.module || hasModule(access, item.module)) &&
      (!item.feature || hasFeature(access, item.feature))
    ),
  })).filter(group => group.items.length > 0);

  return <div className="app">
    {open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <div className="brand">
        <img src="/brand/soorin-mark.png" alt="Soorin logo" />
        <div><b>Soorin</b><span>SOC Workbench</span></div>
      </div>
      <nav>{visibleGroups.map(group => <div key={group.group}><div className="nav-group-label">{group.group}</div>
        {group.items.map(item => <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={() => setOpen(false)}
          className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
          <span className="ic">{item.icon}</span><span>{item.label}</span>
        </NavLink>)}</div>)}</nav>
      <div className="sidebar-foot"><span className="brand-dot" /> Secure workspace</div>
    </aside>
    <div className="main">
      <header className="topbar"><div className="row">
        <button className="btn-ghost btn-sm menu-btn" onClick={() => setOpen(value => !value)} aria-label="Open navigation">☰</button>
        <span className="title">{title}</span></div>
        <div className="row user-menu"><div className="user-avatar">{(access.user.display_name || access.user.username).slice(0, 1).toUpperCase()}</div><div className="user-meta"><b>{access.user.display_name || access.user.username}</b><span>{access.user.role}</span></div>
          <button className="btn-sm btn-ghost" onClick={onLogout}>Sign out</button></div>
      </header>
      <main className="content">{children}</main>
    </div>
  </div>;
}
