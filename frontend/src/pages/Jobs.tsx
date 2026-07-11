import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Loading, Modal, statusBadge, timeAgo, useToast } from "../lib";

type Job = {
  id: number;
  name: string;
  kind: string;
  status: string;
  progress: number;
  result: string;
  error: string;
  ref_type: string;
  ref_id: number | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

const STATUSES = ["", "pending", "running", "completed", "failed"];

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<Job | null>(null);
  const [auto, setAuto] = useState(true);
  const toast = useToast();
  const timer = useRef<number | null>(null);

  async function load() {
    try {
      const qs = status ? `?status=${status}` : "";
      setJobs(await api.get(`/api/jobs${qs}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (!auto) return;
    timer.current = window.setInterval(load, 3000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, status]);

  async function retry(j: Job) {
    try {
      await api.post(`/api/jobs/${j.id}/retry`);
      toast("Job re-queued", "ok");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!jobs) return <Loading />;

  return (
    <>
      <div className="row mb">
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 180 }}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s ? s : "All statuses"}</option>
          ))}
        </select>
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} style={{ width: "auto" }} />
          <span className="dim">Auto-refresh</span>
        </label>
        <span className="spacer" />
        <button className="btn-sm" onClick={load}>↻ Refresh</button>
      </div>

      <div className="card">
        {jobs.length === 0 ? (
          <div className="empty">No jobs yet. Background work (LLM analysis, etc.) shows up here.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Job</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} style={{ cursor: "pointer" }} onClick={() => setDetail(j)}>
                  <td>{j.name}</td>
                  <td><span className="badge">{j.kind}</span></td>
                  <td>{statusBadge(j.status)}</td>
                  <td>{j.attempts}</td>
                  <td className="dim">{timeAgo(j.created_at)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {j.status === "failed" && (
                      <button className="btn-sm" onClick={() => retry(j)}>Retry</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <Modal title={detail.name} onClose={() => setDetail(null)}>
          <div className="row mb">
            {statusBadge(detail.status)}
            <span className="badge">{detail.kind}</span>
            {detail.ref_type && <span className="dim">{detail.ref_type} #{detail.ref_id}</span>}
          </div>
          <div className="field-row mb">
            <div><label>Created</label><div className="dim">{timeAgo(detail.created_at)}</div></div>
            <div><label>Started</label><div className="dim">{detail.started_at ? timeAgo(detail.started_at) : "—"}</div></div>
            <div><label>Finished</label><div className="dim">{detail.finished_at ? timeAgo(detail.finished_at) : "—"}</div></div>
          </div>
          {detail.result && (
            <>
              <label>Result</label>
              <div className="mono" style={{ whiteSpace: "pre-wrap" }}>{detail.result}</div>
            </>
          )}
          {detail.error && (
            <>
              <label>Error</label>
              <div className="badge red" style={{ display: "block", whiteSpace: "pre-wrap", padding: 10 }}>{detail.error}</div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
