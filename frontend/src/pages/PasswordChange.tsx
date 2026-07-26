import { useState } from "react";
import { api } from "../api";
import { useToast } from "../lib";

export default function PasswordChange({ onChanged, onLogout }: { onChanged: () => void | Promise<void>; onLogout: () => void }) {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (next.length < 12) return toast("New password must contain at least 12 characters", "error");
    if (next !== confirm) return toast("Password confirmation does not match", "error");
    setBusy(true);
    try {
      await api.post("/api/auth/change-password", { current_password: current, new_password: next });
      toast("Password changed", "ok");
      await onChanged();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  return <div className="login-wrap"><form className="card login-card" onSubmit={submit}>
    <div className="login-brand"><img src="/brand/soorin-mark.png" alt="Soorin" /></div>
    <h1 style={{ textAlign: "center" }}>Change temporary password</h1>
    <p className="dim" style={{ textAlign: "center" }}>Set a private password before entering your workspace.</p>
    <label>Current password</label><input type="password" autoComplete="current-password" value={current} onChange={event => setCurrent(event.target.value)} autoFocus />
    <label>New password</label><input type="password" autoComplete="new-password" value={next} onChange={event => setNext(event.target.value)} />
    <label>Confirm new password</label><input type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} />
    <button className="btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: 18 }} disabled={busy}>{busy ? <span className="spin" /> : "Change password"}</button>
    <button type="button" className="btn-ghost" style={{ width: "100%", justifyContent: "center", marginTop: 8 }} onClick={onLogout}>Sign out</button>
  </form></div>;
}
