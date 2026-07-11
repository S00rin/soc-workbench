import { useEffect, useState } from "react";
import { api } from "../api";
import { Markdown, Modal, useToast } from "../lib";

type Issue = {
  key: string;
  summary: string;
  status: string;
  assignee: string;
  priority: string;
  updated: string;
};

export default function Jira() {
  const [jql, setJql] = useState("assignee = currentUser() ORDER BY updated DESC");
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [instruction, setInstruction] = useState("Summarize activity, list risks, action items, and unassigned/overdue issues.");
  const [analysis, setAnalysis] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);
  const [openIssue, setOpenIssue] = useState<string | null>(null);
  const [writeOpen, setWriteOpen] = useState(false);
  const toast = useToast();

  async function testConn() {
    try {
      const res = await api.post("/api/jira/test");
      toast(`Connected: ${res.user || res.displayName || JSON.stringify(res).slice(0, 60)}`, "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function search() {
    setBusy(true);
    setAnalysis("");
    try {
      const res = await api.post("/api/jira/search", { jql, max_results: 50 });
      setIssues(res.issues);
      setSummary(res.summary);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setAnalyzing(true);
    try {
      const res = await api.post("/api/jira/analyze", { jql, instruction, max_results: 100 });
      setAnalysis(res.result);
      setSummary(res.summary);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <>
      <div className="card mb">
        <div className="card-head">
          <h3>JQL search</h3>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn-sm" onClick={testConn}>Test connection</button>
            <button className="btn-sm" onClick={() => setWriteOpen(true)}>✎ Write…</button>
          </div>
        </div>
        <textarea value={jql} onChange={(e) => setJql(e.target.value)} style={{ minHeight: 60 }} />
        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={search} disabled={busy}>{busy ? <span className="spin" /> : "Search"}</button>
          <span className="faint" style={{ fontSize: 12 }}>Configure Jira URL & token in Settings → Jira.</span>
        </div>
      </div>

      {summary && (
        <div className="row mb" style={{ gap: 8 }}>
          {Object.entries(summary).slice(0, 8).map(([k, v]: any) => (
            <span key={k} className="badge">{k}: {typeof v === "object" ? Object.keys(v).length : String(v)}</span>
          ))}
        </div>
      )}

      {issues && (
        <div className="card mb">
          <div className="card-head"><h3>{issues.length} issue(s)</h3></div>
          {issues.length === 0 ? <div className="empty">No issues matched.</div> : (
            <table className="data">
              <thead><tr><th>Key</th><th>Summary</th><th>Status</th><th>Assignee</th><th>Priority</th></tr></thead>
              <tbody>
                {issues.map((i) => (
                  <tr key={i.key} style={{ cursor: "pointer" }} onClick={() => setOpenIssue(i.key)}>
                    <td className="mono">{i.key}</td>
                    <td>{i.summary}</td>
                    <td><span className="badge">{i.status}</span></td>
                    <td className="dim">{i.assignee || "unassigned"}</td>
                    <td className="dim">{i.priority || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>AI analysis</h3></div>
        <label>Instruction</label>
        <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} style={{ minHeight: 60, fontFamily: "inherit" }} />
        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={analyze} disabled={analyzing}>{analyzing ? <span className="spin" /> : "Analyze issues"}</button>
        </div>
        {analysis && (<><hr className="hr" /><Markdown text={analysis} /></>)}
      </div>

      {openIssue && <IssueModal key0={openIssue} onClose={() => setOpenIssue(null)} />}
      {writeOpen && <WriteModal onClose={() => setWriteOpen(false)} />}
    </>
  );
}

function IssueModal({ key0, onClose }: { key0: string; onClose: () => void }) {
  const [issue, setIssue] = useState<any | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/api/jira/issue/${key0}`).then(setIssue).catch((e) => setErr(e.message));
  }, [key0]);
  return (
    <Modal title={key0} onClose={onClose} wide>
      {err && <div className="badge red" style={{ display: "block", padding: 10 }}>{err}</div>}
      {!issue && !err && <div className="dim">Loading…</div>}
      {issue && (
        <>
          <h3>{issue.fields?.summary}</h3>
          <div className="row mb">
            <span className="badge">{issue.fields?.status?.name}</span>
            <span className="dim">{issue.fields?.assignee?.displayName || "unassigned"}</span>
          </div>
          <Markdown text={typeof issue.fields?.description === "string" ? issue.fields.description : "_No description._"} />
        </>
      )}
    </Modal>
  );
}

function WriteModal({ onClose }: { onClose: () => void }) {
  const [action, setAction] = useState("comment");
  const [target, setTarget] = useState("");
  const [body, setBody] = useState("");
  const [transitionId, setTransitionId] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  function payload(confirm: boolean) {
    return { action, target, body, transition_id: transitionId, fields: {}, confirm };
  }

  async function doPreview() {
    if (!target.trim()) return toast("Issue key is required", "error");
    setBusy(true);
    try {
      const res = await api.post("/api/jira/write", payload(false));
      setPreview(res.preview);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      await api.post("/api/jira/write", payload(true));
      toast("Write applied", "ok");
      onClose();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Jira write (preview required)" onClose={onClose}
      footer={
        preview ? (
          <>
            <button className="btn-sm" onClick={() => setPreview(null)}>Back</button>
            <button className="btn-primary btn-sm" onClick={confirm} disabled={busy}>{busy ? <span className="spin" /> : "Confirm & apply"}</button>
          </>
        ) : (
          <>
            <button className="btn-sm" onClick={onClose}>Cancel</button>
            <button className="btn-primary btn-sm" onClick={doPreview} disabled={busy}>{busy ? <span className="spin" /> : "Preview"}</button>
          </>
        )
      }
    >
      {preview ? (
        <>
          <p className="dim" style={{ marginTop: 0 }}>Review this change before it is written to Jira:</p>
          <pre className="md" style={{ background: "var(--bg)", padding: 12, borderRadius: 7, overflowX: "auto", fontSize: 12.5 }}>
            {JSON.stringify(preview, null, 2)}
          </pre>
        </>
      ) : (
        <>
          <div className="field-row">
            <div>
              <label>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="comment">comment</option>
                <option value="transition">transition</option>
              </select>
            </div>
            <div><label>Issue key</label><input value={target} onChange={(e) => setTarget(e.target.value)} className="mono" placeholder="PROJ-123" /></div>
          </div>
          {action === "comment" && (<><label>Comment</label><textarea value={body} onChange={(e) => setBody(e.target.value)} style={{ minHeight: 100, fontFamily: "inherit" }} /></>)}
          {action === "transition" && (<><label>Transition id</label><input value={transitionId} onChange={(e) => setTransitionId(e.target.value)} className="mono" /></>)}
        </>
      )}
    </Modal>
  );
}
