import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, statusBadge, timeAgo, useToast } from "../lib";

type Notif = {
  id: number;
  channel: string;
  subject: string;
  recipients: string;
  status: string;
  error: string;
  created_at: string;
};

const CHANNELS = ["email", "webhook", "telegram"];

export default function Notifications() {
  const [history, setHistory] = useState<Notif[] | null>(null);
  const [templates, setTemplates] = useState<string[]>([]);
  const [f, setF] = useState({ channel: "email", subject: "", body: "", recipients: "", template: "" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));

  async function load() {
    try {
      const [h, t] = await Promise.all([api.get("/api/notifications"), api.get("/api/notifications/templates")]);
      setHistory(h);
      setTemplates(t);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send() {
    if (!f.body.trim()) return toast("Message body is required", "error");
    if (!f.recipients.trim()) return toast(f.channel === "telegram" ? "Chat id (or leave blank to use default)" : "Recipient is required", f.recipients.trim() ? "info" : "error");
    setBusy(true);
    try {
      const res = await api.post("/api/notifications/send", f);
      toast(`Notification ${res.status}`, res.status === "sent" ? "ok" : "info");
      setF((p) => ({ ...p, subject: "", body: "" }));
      load();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const recipientLabel =
    f.channel === "email" ? "Recipient email(s), comma separated"
    : f.channel === "webhook" ? "Webhook URL"
    : "Telegram chat id (blank = default from Settings)";

  return (
    <div className="grid cols-2">
      <div className="card" style={{ alignSelf: "start" }}>
        <div className="card-head"><h3>Send notification</h3></div>
        <div className="field-row">
          <div>
            <label>Channel</label>
            <select value={f.channel} onChange={(e) => set("channel", e.target.value)}>
              {CHANNELS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label>Template (optional)</label>
            <select value={f.template} onChange={(e) => set("template", e.target.value)}>
              <option value="">— none —</option>
              {templates.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </div>
        </div>
        <label>{recipientLabel}</label>
        <input value={f.recipients} onChange={(e) => set("recipients", e.target.value)} className={f.channel !== "telegram" ? "mono" : ""} />
        {f.channel !== "webhook" && (<><label>Subject</label><input value={f.subject} onChange={(e) => set("subject", e.target.value)} /></>)}
        <label>Message</label>
        <textarea value={f.body} onChange={(e) => set("body", e.target.value)} style={{ minHeight: 140, fontFamily: "inherit" }} />
        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={send} disabled={busy}>{busy ? <span className="spin" /> : "Send"}</button>
          <span className="faint" style={{ fontSize: 12 }}>Channel credentials come from Settings.</span>
        </div>
      </div>

      <div className="card" style={{ alignSelf: "start" }}>
        <div className="card-head"><h3>History</h3><button className="btn-sm" onClick={load}>↻</button></div>
        {!history ? <Loading /> : history.length === 0 ? (
          <div className="empty">No notifications sent yet.</div>
        ) : (
          <div className="list">
            {history.map((n) => (
              <div className="list-row" key={n.id} style={{ alignItems: "flex-start" }}>
                <div>
                  <div>{n.subject || <span className="dim">(no subject)</span>}</div>
                  <div className="meta">
                    <span className="badge">{n.channel}</span> {n.recipients} · {timeAgo(n.created_at)}
                    {n.error && <span className="badge red" style={{ marginLeft: 6 }} title={n.error}>error</span>}
                  </div>
                </div>
                {statusBadge(n.status)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
