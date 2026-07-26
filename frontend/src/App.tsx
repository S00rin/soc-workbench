import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, clearToken, getToken } from "./api";
import { Loading } from "./lib";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Process from "./pages/Process";
import Knowledge from "./pages/Knowledge";
import Projects from "./pages/Projects";
import IoCs from "./pages/IoCs";
import Jobs from "./pages/Jobs";
import Settings from "./pages/Settings";
import Jira from "./pages/Jira";
import Splunk from "./pages/Splunk";
import Intel from "./pages/Intel";
import Reports from "./pages/Reports";
import Notifications from "./pages/Notifications";
import Prompts from "./pages/Prompts";
import Automation from "./pages/Automation";
import AttackLab from "./pages/AttackLab";
import AttackScenario from "./pages/AttackScenario";

type AuthState = "checking" | "in" | "out";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("checking");
  const loc = useLocation();
  useEffect(() => {
    if (!getToken()) { setAuth("out"); return; }
    api.get("/api/auth/me").then(() => setAuth("in")).catch(() => {
      clearToken(); setAuth("out");
    });
  }, []);
  if (auth === "checking") return <Loading label="Starting SOC Workbench…" />;
  if (auth === "out") {
    if (loc.pathname === "/login") return <Login onLogin={() => setAuth("in")} />;
    return <Navigate to="/login" replace />;
  }
  if (loc.pathname === "/login") return <Navigate to="/" replace />;
  return <Layout onLogout={() => { clearToken(); setAuth("out"); }}>
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/process" element={<Process />} />
      <Route path="/knowledge" element={<Knowledge />} />
      <Route path="/projects" element={<Projects />} />
      <Route path="/iocs" element={<IoCs />} />
      <Route path="/jobs" element={<Jobs />} />
      <Route path="/jira" element={<Jira />} />
      <Route path="/splunk" element={<Splunk />} />
      <Route path="/intel" element={<Intel />} />
      <Route path="/automation" element={<Automation />} />
      <Route path="/attack-lab" element={<AttackLab />} />
      <Route path="/attack-lab/:scenarioId" element={<AttackScenario />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/notifications" element={<Notifications />} />
      <Route path="/prompts" element={<Prompts />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </Layout>;
}
