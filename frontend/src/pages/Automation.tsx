import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, useToast } from "../lib";

export default function Automation() {
  const [intel, setIntel] = useState<any[] | null>(null);
  const [iocs, setIocs] = useState<any[] | null>(null);
  const [tasks, setTasks] = useState<any[] | null>(null);
  const [busy, setBusy] = useState("");
  const [feed, setFeed] = useState({ name: "", url: "", summarize: false });
  const [task, setTask] = useState({ title: "", workspace: "", prompt: "", mode: "read-only" });
  const toast = useToast();

  async function load() {
    try {
      const [a, b, c] = await Promise.all([
        api.get("/api/automation/intel-sources"),
        api.get("/api/automation/ioc-sources"),
        api.get("/api/automation/claude-tasks"),
      ]);
      setIntel(a); setIocs(b); setTasks(c);
    } catch (e: any) { toast(e.message, "error"); }
  }
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, []);

  async function run(path: string, label: string) {
    setBusy(label);
    try { const out = await api.post(path); toast(JSON.stringify(out), "ok"); await load(); }
    catch (e: any) { toast(e.message, "error"); }
    finally { setBusy(""); }
  }
  async function addFeed() {
    if (!feed.name || !feed.url) return toast("Feed name and URL are required", "error");
    try {
      await api.post("/api/automation/intel-sources", {
        ...feed, source_type: "rss", category: "Threat Intelligence",
        trust_score: 0.75, interval_minutes: 60, enabled: true,
        auto_save_kb: true, auto_extract_iocs: true,
      });
      setFeed({ name: "", url: "", summarize: false }); await load();
      toast("Feed added", "ok");
    } catch (e: any) { toast(e.message, "error"); }
  }
  async function submitTask() {
    if (!task.prompt || !task.workspace) return toast("Workspace and prompt are required", "error");
    try {
      await api.post("/api/automation/claude-tasks", {
        ...task, title: task.title || "Claude Code task", timeout_seconds: 600, max_turns: 10,
      });
      setTask((x) => ({ ...x, title: "", prompt: "" })); await load();
      toast("Claude Code task queued", "ok");
    } catch (e: any) { toast(e.message, "error"); }
  }

  if (!intel || !iocs || !tasks) return <Loading />;
  return <>
    <div className="card mb">
      <div className="card-head"><h3>Intelligence automation</h3>
        <button className="btn-primary btn-sm" disabled={!!busy}
          onClick={() => run("/api/automation/run-all", "all")}>
          {busy === "all" ? "Running…" : "Run all now"}
        </button>
      </div>
      <p className="dim">Accepted security news is saved directly to the Knowledge Base and its IoCs are extracted automatically. Cloud/API security topics are excluded by scope rules.</p>
      <div className="field-row">
        <div><label>Feed name</label><input value={feed.name} onChange={e => setFeed({...feed, name:e.target.value})}/></div>
        <div><label>RSS/Atom URL</label><input className="mono" value={feed.url} onChange={e => setFeed({...feed, url:e.target.value})}/></div>
      </div>
      <div className="row">
        <label className="row"><input type="checkbox" style={{width:"auto"}} checked={feed.summarize}
          onChange={e => setFeed({...feed, summarize:e.target.checked})}/> Claude summaries</label>
        <button className="btn-sm" onClick={addFeed}>+ Add feed</button>
      </div>
      <table className="data"><thead><tr><th>News source</th><th>Trust</th><th>Last success</th><th>Error</th><th/></tr></thead>
        <tbody>{intel.map(x => <tr key={x.id}><td>{x.name}<div className="dim mono">{x.url}</div></td>
          <td>{x.trust_score}</td><td className="dim">{x.last_success_at || "Never"}</td>
          <td className="dim">{x.last_error || "—"}</td><td><button className="btn-sm"
          onClick={() => run(`/api/automation/intel-sources/${x.id}/run`, "intel"+x.id)}>Run</button></td></tr>)}</tbody>
      </table>
    </div>

    <div className="card mb"><div className="card-head"><h3>IoC feeds</h3></div>
      <table className="data"><thead><tr><th>Source</th><th>Adapter</th><th>Trust</th><th>Last success</th><th/></tr></thead>
      <tbody>{iocs.map(x => <tr key={x.id}><td>{x.name}</td><td className="mono">{x.adapter}</td>
        <td>{x.trust_score}</td><td className="dim">{x.last_success_at || "Never"}</td>
        <td><button className="btn-sm" onClick={() => run(`/api/automation/ioc-sources/${x.id}/run`, "ioc"+x.id)}>Run</button></td>
      </tr>)}</tbody></table>
    </div>

    <div className="card"><div className="card-head"><h3>Claude Code tasks</h3></div>
      <div className="field-row"><div><label>Title</label><input value={task.title} onChange={e=>setTask({...task,title:e.target.value})}/></div>
      <div><label>Workspace</label><input className="mono" value={task.workspace} onChange={e=>setTask({...task,workspace:e.target.value})}/></div>
      <div><label>Mode</label><select value={task.mode} onChange={e=>setTask({...task,mode:e.target.value})}>
        <option value="plan">Plan</option><option value="read-only">Read only</option><option value="edit">Edit files</option>
      </select></div></div>
      <label>Prompt</label><textarea style={{minHeight:130}} value={task.prompt} onChange={e=>setTask({...task,prompt:e.target.value})}/>
      <button className="btn-primary btn-sm mb" onClick={submitTask}>Run with Claude Code</button>
      <table className="data"><thead><tr><th>Task</th><th>Mode</th><th>Status</th><th>Changed files</th><th>Result</th></tr></thead>
      <tbody>{tasks.map(x=><tr key={x.id}><td>{x.title}</td><td>{x.mode}</td><td><span className="badge">{x.status}</span></td>
        <td className="mono">{(x.changed_files || []).join(", ") || "—"}</td>
        <td style={{maxWidth:420,whiteSpace:"pre-wrap"}}>{x.error || x.output || "—"}</td></tr>)}</tbody></table>
    </div>
  </>;
}
