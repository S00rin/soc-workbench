import { ReactNode, useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AccessProvider, AccessState, hasModule, useAccess } from "./access";
import { api, clearToken, getToken } from "./api";
import { Loading } from "./lib";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import DataHub from "./pages/DataHub";
import IntegrationHub from "./pages/IntegrationHub";
import IntelligenceHub from "./pages/IntelligenceHub";
import OperationsHub from "./pages/OperationsHub";
import Settings from "./pages/Settings";
import Reports from "./pages/Reports";
import Prompts from "./pages/Prompts";
import AccessAdmin from "./pages/AccessAdmin";
import AboutSorin from "./pages/AboutSorin";
import PasswordChange from "./pages/PasswordChange";

type AuthState = "checking" | "in" | "out";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("checking");
  const [access, setAccess] = useState<AccessState | null>(null);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const loc = useLocation();

  const loadAuth = useCallback(async () => {
    if (!getToken()) { setAccess(null); setAuth("out"); return; }
    setAuth("checking");
    try {
      const me = await api.get("/api/auth/me");
      setMustChangePassword(Boolean(me.must_change_password));
      setAccess(await api.get("/api/access/effective"));
      setAuth("in");
    } catch {
      clearToken(); setAccess(null); setMustChangePassword(false); setAuth("out");
    }
  }, []);

  useEffect(() => { loadAuth(); }, [loadAuth]);
  if (auth === "checking") return <Loading label="Starting Soorin SOC Workbench…" />;
  if (auth === "out") {
    if (loc.pathname === "/login") return <Login onLogin={loadAuth} />;
    return <Navigate to="/login" replace />;
  }
  if (!access) return <Loading />;
  if (loc.pathname === "/login") return <Navigate to="/" replace />;
  if (mustChangePassword) return <AccessProvider value={access}><PasswordChange onChanged={loadAuth} onLogout={() => { clearToken(); setAccess(null); setMustChangePassword(false); setAuth("out"); }} /></AccessProvider>;

  return <AccessProvider value={access}>
    <Layout onLogout={() => { clearToken(); setAccess(null); setMustChangePassword(false); setAuth("out"); }}>
      <Routes>
        <Route path="/" element={<Allowed module="dashboard"><Dashboard /></Allowed>} />
        <Route path="/data" element={<Allowed module="data"><DataHub /></Allowed>} />
        <Route path="/integrations" element={<Allowed module="integrations"><IntegrationHub /></Allowed>} />
        <Route path="/intelligence" element={<Allowed module="intelligence"><IntelligenceHub /></Allowed>} />
        <Route path="/reports" element={<Allowed module="reports"><Reports /></Allowed>} />
        <Route path="/operations" element={<Allowed module="operations"><OperationsHub /></Allowed>} />
        <Route path="/prompts" element={<Allowed module="prompts"><Prompts /></Allowed>} />
        <Route path="/settings" element={<Allowed module="settings"><Settings /></Allowed>} />
        <Route path="/admin/access" element={access.user.role === "admin" ? <AccessAdmin /> : <Navigate to="/" replace />} />
        <Route path="/about-sorin" element={<AboutSorin />} />

        {/* Backward-compatible URLs now land in the compact hubs. */}
        <Route path="/process" element={<Navigate to="/data?tab=process" replace />} />
        <Route path="/knowledge" element={<Navigate to="/data?tab=knowledge" replace />} />
        <Route path="/iocs" element={<Navigate to="/data?tab=iocs" replace />} />
        <Route path="/projects" element={<Navigate to="/data?tab=projects" replace />} />
        <Route path="/jira" element={<Navigate to="/integrations?tab=chat" replace />} />
        <Route path="/atlassian" element={<Navigate to="/integrations?tab=atlassian" replace />} />
        <Route path="/splunk" element={<Navigate to="/integrations?tab=splunk" replace />} />
        <Route path="/intel" element={<Navigate to="/intelligence?tab=intel" replace />} />
        <Route path="/automation" element={<Navigate to="/intelligence?tab=automation" replace />} />
        <Route path="/jobs" element={<Navigate to="/operations?tab=jobs" replace />} />
        <Route path="/notifications" element={<Navigate to="/operations?tab=notifications" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  </AccessProvider>;
}

function Allowed({ module, children }: { module: string; children: ReactNode }) {
  const access = useAccess();
  return hasModule(access, module) ? <>{children}</> : <Navigate to="/" replace />;
}
