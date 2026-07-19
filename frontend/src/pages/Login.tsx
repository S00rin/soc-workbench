import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";

export default function Login({ onLogin }: { onLogin: () => void | Promise<void> }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.login(username, password);
      await onLogin();
      nav("/");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="login-brand"><img src="/brand/soorin-mark.png" alt="Soorin" /></div>
        <h1 style={{ textAlign: "center", marginBottom: 4 }}>Soorin SOC Workbench</h1>
        <p className="dim" style={{ textAlign: "center", marginTop: 0 }}>Sign in to your secure workspace</p>
        <label>Username</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {err && <div className="badge red" style={{ display: "block", marginTop: 12, padding: "8px 10px" }}>{err}</div>}
        <button className="btn-primary" style={{ width: "100%", marginTop: 18, justifyContent: "center" }} disabled={busy}>
          {busy ? <span className="spin" /> : "Sign in"}
        </button>
        <p className="faint" style={{ fontSize: 11.5, textAlign: "center", marginTop: 14 }}>
          Access is managed by your Soorin Workbench administrator.
        </p>
      </form>
    </div>
  );
}
