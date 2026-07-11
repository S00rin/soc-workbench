import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, Markdown, Modal, statusBadge, timeAgo, useToast } from "../lib";

type ReportRow = {
  id: number;
  title: string;
  report_type: string;
  language: string;
  status: string;
  created_at: string;
};

const SOURCES = ["knowledge", "intel", "iocs", "analyses"];

export default function Reports() {
  const [reports, setReports] = useState<ReportRow[] | null>(null);
  const [types, setTypes] = useState<string[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [f, setF] = useState({
    title: "", report_type: "weekly_soc", language: "en", detail_level: "balanced",
    date_from: "", date_to: "", customer: "", notes: "",
    data_sources: ["knowledge", "intel", "iocs", "analyses"] as string[], use_llm: true,
  });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));

  async function load() {
    try {
      const [r, t] = await Promise.all([api.get("/api/reports"), api.get("/api/reports/types")]);
      setReports(r);
      setTypes(t);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleSource(s: string) {
    set("data_sources", f.data_sources.includes(s) ? f.data_sources.filter((x) => x !== s) : [...f.data_sources, s]);
  }

  async function generate() {
    if (!f.title.trim()) return toast("Title is required", "error");
    setBusy(true);
    try {
      const res = await api.post("/api/reports/generate", f);
      toast("Report generated", "ok");
      await load();
      setOpen(res.id);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this report?")) return;
    try {
      await api.del(`/api/reports/${id}`);
      toast("Deleted", "ok");
      setReports((prev) => prev?.filter((r) => r.id !== id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  return (
    <div className="grid cols-2">
      <div className="card" style={{ alignSelf: "start" }}>
        <div className="card-head"><h3>Generate report</h3></div>
        <label>Title</label>
        <input value={f.title} onChange={(e) => set("title", e.target.value)} placeholder="Weekly SOC report — week 28" />
        <div className="field-row">
          <div>
            <label>Type</label>
            <select value={f.report_type} onChange={(e) => set("report_type", e.target.value)}>
              {types.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div style={{ maxWidth: 110 }}>
            <label>Language</label>
            <select value={f.language} onChange={(e) => set("language", e.target.value)}><option value="en">en</option><option value="fa">fa</option></select>
          </div>
          <div style={{ maxWidth: 140 }}>
            <label>Detail</label>
            <select value={f.detail_level} onChange={(e) => set("detail_level", e.target.value)}>
              {["minimal", "balanced", "detailed"].map((d) => <option key={d}>{d}</option>)}
            </select>
          </div>
        </div>
        <div className="field-row">
          <div><label>Date from</label><input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} /></div>
          <div><label>Date to</label><input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} /></div>
          <div><label>Customer</label><input value={f.customer} onChange={(e) => set("customer", e.target.value)} /></div>
        </div>
        <label>Data sources</label>
        <div className="row" style={{ gap: 12 }}>
          {SOURCES.map((s) => (
            <label key={s} className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
              <input type="checkbox" checked={f.data_sources.includes(s)} onChange={() => toggleSource(s)} style={{ width: "auto" }} />
              <span className="dim">{s}</span>
            </label>
          ))}
        </div>
        <label>Manual notes</label>
        <textarea value={f.notes} onChange={(e) => set("notes", e.target.value)} style={{ minHeight: 70, fontFamily: "inherit" }} />
        <div className="row mt">
          <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={f.use_llm} onChange={(e) => set("use_llm", e.target.checked)} style={{ width: "auto" }} />
            <span className="dim">Use LLM (else skeleton only)</span>
          </label>
          <span className="spacer" />
          <button className="btn-primary btn-sm" onClick={generate} disabled={busy}>{busy ? <span className="spin" /> : "Generate"}</button>
        </div>
      </div>

      <div className="card" style={{ alignSelf: "start" }}>
        <div className="card-head"><h3>Reports</h3><button className="btn-sm" onClick={load}>↻</button></div>
        {!reports ? <Loading /> : reports.length === 0 ? (
          <div className="empty">No reports yet.</div>
        ) : (
          <div className="list">
            {reports.map((r) => (
              <div className="list-row" key={r.id}>
                <div style={{ cursor: "pointer" }} onClick={() => setOpen(r.id)}>
                  <div>{r.title}</div>
                  <div className="meta">{r.report_type.replace(/_/g, " ")} · {r.language} · {timeAgo(r.created_at)}</div>
                </div>
                <span className="row" style={{ gap: 6 }}>
                  {statusBadge(r.status)}
                  <button className="btn-sm" onClick={() => setOpen(r.id)}>Open</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(r.id)}>✕</button>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {open !== null && <ReportModal id={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}

function ReportModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [report, setReport] = useState<any | null>(null);
  const [content, setContent] = useState("");
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function load() {
    try {
      const r = await api.get(`/api/reports/${id}`);
      setReport(r);
      setContent(r.content || "");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function save() {
    setBusy(true);
    try {
      await api.put(`/api/reports/${id}`, { content });
      toast("Saved (previous version kept)", "ok");
      setEdit(false);
      load();
      onChanged();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function download(fmt: string) {
    try {
      const ext = fmt === "pdf" ? "html" : fmt; // pdf export returns print-ready html
      await api.download(`/api/reports/${id}/export?fmt=${fmt}`, `report-${id}.${ext}`);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!report) return <Modal title="Report" onClose={onClose}><Loading /></Modal>;

  return (
    <Modal title={report.title} onClose={onClose} wide
      footer={
        <>
          <span className="row" style={{ gap: 6, marginRight: "auto" }}>
            {["md", "html", "docx", "pdf"].map((fmt) => (
              <button key={fmt} className="btn-sm" onClick={() => download(fmt)}>↓ {fmt.toUpperCase()}</button>
            ))}
          </span>
          {edit ? (
            <>
              <button className="btn-sm" onClick={() => { setEdit(false); setContent(report.content || ""); }}>Cancel</button>
              <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save"}</button>
            </>
          ) : (
            <button className="btn-sm" onClick={() => setEdit(true)}>Edit</button>
          )}
        </>
      }
    >
      <div className="row mb">
        <span className="badge">{report.report_type?.replace(/_/g, " ")}</span>
        <span className="badge">{report.language}</span>
        {(report.versions?.length ?? 0) > 0 && <span className="badge purple">{report.versions.length} prior version(s)</span>}
      </div>
      {edit ? (
        <textarea value={content} onChange={(e) => setContent(e.target.value)} style={{ minHeight: 420 }} />
      ) : (
        <Markdown text={content || "_Empty report._"} />
      )}
    </Modal>
  );
}
