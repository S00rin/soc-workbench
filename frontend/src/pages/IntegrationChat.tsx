import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { hasFeature, useAccess } from "../access";
import { Loading, Markdown, useToast } from "../lib";

type Provider = "jira" | "confluence" | "wikijs" | "splunk";
type Connection = {
  connection_id: number; provider: Provider; display_name: string; enabled: boolean;
  ai_enabled?: boolean; base_url?: string;
};
type Session = {
  id: number; provider: Provider; connection_id: number; title: string; message_count: number;
  updated_at: string; turns?: Turn[];
};
type Turn = {
  id: number; prompt_redacted: string; generated_query: string; query_language: string;
  response_markdown: string; status: string; duration_ms: number; error_code?: string;
  error_summary?: string; result_data?: { count?: number }; created_at: string;
};

export default function IntegrationChat() {
  const access = useAccess();
  const toast = useToast();
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [connectionKey, setConnectionKey] = useState("");
  const [prompt, setPrompt] = useState("");
  const [queryOverride, setQueryOverride] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);

  const available = useMemo(() => (connections || []).filter(item =>
    item.enabled !== false && hasFeature(access, `integration.${item.provider}`)
  ), [connections, access]);

  async function loadSessions() {
    const value = await api.get("/api/integrations/chat/sessions?page_size=100");
    setSessions(value.items || []);
  }
  async function loadSession(id: number) {
    const value = await api.get(`/api/integrations/chat/sessions/${id}`);
    setSession(value);
    setConnectionKey(`${value.provider}:${value.connection_id}`);
  }
  useEffect(() => {
    Promise.all([api.get("/api/integrations/connections"), api.get("/api/integrations/chat/sessions?page_size=100")])
      .then(([connectionRows, sessionRows]) => {
        setConnections(connectionRows);
        setSessions(sessionRows.items || []);
        const first = connectionRows.find((item: Connection) => item.enabled !== false && hasFeature(access, `integration.${item.provider}`));
        if (first) setConnectionKey(`${first.provider}:${first.connection_id}`);
      }).catch((error) => toast(error.message, "error"));
  }, []);

  function newChat() {
    setSession(null);
    setPrompt("");
    setQueryOverride("");
  }

  async function send() {
    const clean = prompt.trim();
    if (!clean) return;
    const [provider, connectionRaw] = connectionKey.split(":") as [Provider, string];
    if (!provider || !connectionRaw) return toast("Choose an integration connection first", "info");
    setBusy(true);
    try {
      let active = session;
      if (!active) {
        active = await api.post("/api/integrations/chat/sessions", {
          provider, connection_id: Number(connectionRaw), title: "New integration chat",
        });
        setSession(active);
      }
      await api.post(`/api/integrations/chat/sessions/${active.id}/turns`, { prompt: clean, query_override: queryOverride.trim() });
      await loadSession(active.id);
      await loadSessions();
      setPrompt("");
      setQueryOverride("");
    } catch (error: any) {
      toast(error.message, "error");
      if (session?.id) loadSession(session.id).catch(() => undefined);
    } finally { setBusy(false); }
  }

  async function removeSession(row: Session) {
    if (!confirm(`Delete chat history “${row.title}”?`)) return;
    try {
      await api.del(`/api/integrations/chat/sessions/${row.id}`);
      if (session?.id === row.id) newChat();
      await loadSessions();
    } catch (error: any) { toast(error.message, "error"); }
  }

  if (!connections) return <Loading label="Loading integration chat…" />;
  const selected = available.find(item => `${item.provider}:${item.connection_id}` === connectionKey);
  const turns = session?.turns || [];
  return <div className={`chat-shell ${historyOpen ? "with-history" : ""}`}>
    <aside className="chat-history card">
      <div className="card-head"><h3>Prompt history</h3><button className="btn-sm btn-primary" onClick={newChat}>+ New</button></div>
      {sessions.length === 0 && <div className="empty">Your Jira, Confluence, Wiki.js and Splunk conversations will appear here.</div>}
      <div className="chat-session-list">{sessions.map(row => <div key={row.id} className={`chat-session ${session?.id === row.id ? "active" : ""}`}>
        <button className="chat-session-main" onClick={() => loadSession(row.id)}>
          <b>{row.title || "Untitled chat"}</b><span>{row.provider} · {row.message_count} prompt(s)</span>
        </button>
        <button className="btn-ghost chat-delete" title="Delete history" onClick={() => removeSession(row)}>×</button>
      </div>)}</div>
    </aside>
    <section className="chat-main">
      <div className="chat-toolbar card">
        <div><h2>Ask your integrations</h2><p>Write naturally. The workbench creates a read-only query, retrieves evidence and keeps the full conversation.</p></div>
        <div className="row"><button className="btn-sm history-toggle" onClick={() => setHistoryOpen(value => !value)}>{historyOpen ? "Hide history" : "Show history"}</button>
          <select aria-label="Integration connection" value={connectionKey} disabled={Boolean(session)} onChange={event => setConnectionKey(event.target.value)}>
            <option value="">Select connection</option>
            {available.map(item => <option key={`${item.provider}:${item.connection_id}`} value={`${item.provider}:${item.connection_id}`}>{item.display_name}</option>)}
          </select>
        </div>
      </div>
      {!selected && available.length === 0 && <div className="card empty integration-empty">No enabled integration is available. Ask an admin to configure Jira, Confluence, Wiki.js or Splunk.</div>}
      <div className="chat-transcript">
        {turns.length === 0 && <div className="chat-welcome"><img src="/brand/soorin-mark.png" alt="Soorin" /><h2>What would you like to know?</h2><p>Examples: “Show critical open Jira incidents”, “Summarize recent Confluence runbooks”, or “Find Wiki.js pages about incident response”.</p></div>}
        {turns.map(turn => <div className="chat-turn" key={turn.id}>
          <div className="chat-bubble user"><div className="bubble-label">You</div>{turn.prompt_redacted}</div>
          <div className={`chat-bubble assistant ${turn.status === "failed" ? "failed" : ""}`}>
            <div className="bubble-label"><span>Soorin Workbench</span><span>{turn.duration_ms} ms</span></div>
            {turn.status === "failed" ? <div className="action-error"><b>{turn.error_code}</b>{turn.error_summary}</div> : <Markdown text={turn.response_markdown} />}
            {turn.generated_query && <details className="query-detail"><summary>{turn.query_language} used · {turn.result_data?.count ?? 0} result(s)</summary><code>{turn.generated_query}</code></details>}
            <button className="btn-sm btn-ghost" onClick={() => { setPrompt(turn.prompt_redacted); setQueryOverride(turn.generated_query || ""); setAdvanced(Boolean(turn.generated_query)); }}>Edit & run again</button>
          </div>
        </div>)}
      </div>
      <div className="chat-composer card">
        <textarea value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={session ? "Ask a follow-up…" : "Ask Jira, Confluence, Wiki.js or Splunk in natural language…"} />
        {advanced && <div className="query-override"><label>Optional query override</label><textarea className="mono" value={queryOverride} onChange={event => setQueryOverride(event.target.value)} placeholder="Leave empty to generate from the prompt" /></div>}
        <div className="row"><button className="btn-sm btn-ghost" onClick={() => setAdvanced(value => !value)}>{advanced ? "Hide query editor" : "Edit generated query"}</button><span className="spacer" /><span className="faint">Enter to send · Shift+Enter for a new line</span><button className="btn-primary" disabled={busy || !prompt.trim() || !connectionKey} onClick={send}>{busy ? <span className="spin" /> : "Send"}</button></div>
      </div>
    </section>
  </div>;
}
