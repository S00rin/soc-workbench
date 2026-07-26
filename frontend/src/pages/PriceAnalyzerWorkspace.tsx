import { useEffect, useState } from "react";
import "@fontsource-variable/vazirmatn/wght.css";
import { api } from "../api";
import { Loading, useToast } from "../lib";
import type { Contract } from "./PriceAnalyzer";

type Section = {
  id: number; contract_id: number; order_index: number; title: string; category: string;
  role: string; excerpt: string; estimated_hours: number; adjusted_hours: number;
  hourly_rate_override: number | null; notes: string;
};
type WBSItem = {
  id: number; contract_id: number; parent_id: number | null; section_id: number | null;
  level: number; code: string; title: string; order_index: number;
  start_date: string; end_date: string; duration_days: number; percent_complete: number; assignee: string;
};
type RaciEntry = { id: number; wbs_item_id: number; participant: string; raci: string };
type Cost = {
  currency: string; total_hours: number; subtotal: number; overhead_amount: number;
  contingency_amount: number; discount_amount: number; tax_amount: number; total: number;
  rows: { section_id: number; title: string; category: string; role: string; hours: number; rate: number; cost: number }[];
};
type Detail = { contract: Contract; sections: Section[]; wbs: WBSItem[]; raci: RaciEntry[]; cost: Cost };

const CATEGORIES = [
  "initiation", "requirements", "design", "development", "testing",
  "deployment", "training", "project_management", "support", "other",
];

type Tab = "sections" | "wbs" | "gantt" | "raci" | "settings";

export default function PriceAnalyzerWorkspace({ contractId, onBack, onDeleted }: { contractId: number; onBack: () => void; onDeleted: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [tab, setTab] = useState<Tab>("sections");
  const [busy, setBusy] = useState(false);
  const [lastMethod, setLastMethod] = useState<"ai" | "heuristic" | null>(null);
  const toast = useToast();

  async function load() {
    try {
      setDetail(await api.get(`/api/price-analyzer/contracts/${contractId}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contractId]);

  useEffect(() => {
    api.get("/api/projects").then(setProjects).catch(() => setProjects([]));
  }, []);

  if (!detail) return <Loading />;
  const { contract, sections, wbs, raci, cost } = detail;
  const isFa = contract.language === "fa";

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const analyze = () => withBusy(async () => {
    const res = await api.post(`/api/price-analyzer/contracts/${contractId}/analyze`, {});
    setLastMethod(res?.method === "ai" ? "ai" : "heuristic");
    toast("Contract analyzed", "ok");
    await load();
  });

  const generateWbs = (scheduleStart: string) => withBusy(async () => {
    await api.post(`/api/price-analyzer/contracts/${contractId}/wbs/generate`, scheduleStart ? { schedule_start: scheduleStart } : {});
    toast("WBS & Gantt generated", "ok");
    await load();
  });

  const updateSection = (s: Section, patch: Partial<Section>) => withBusy(async () => {
    await api.put(`/api/price-analyzer/contracts/${contractId}/sections/${s.id}`, patch);
    await load();
  });

  const addSection = () => withBusy(async () => {
    await api.post(`/api/price-analyzer/contracts/${contractId}/sections`, {
      title: "New section", category: "other",
      role: Object.keys(contract.coefficients?.rates || {})[0] || "unassigned",
      estimated_hours: 0, adjusted_hours: 0,
    });
    await load();
  });

  const deleteSection = (s: Section) => withBusy(async () => {
    await api.del(`/api/price-analyzer/contracts/${contractId}/sections/${s.id}`);
    await load();
  });

  const updateWbsItem = (item: WBSItem, patch: Partial<WBSItem>) => withBusy(async () => {
    await api.put(`/api/price-analyzer/contracts/${contractId}/wbs/${item.id}`, patch);
    await load();
  });

  const saveRaci = (entries: { wbs_item_id: number; participant: string; raci: string }[]) => withBusy(async () => {
    await api.put(`/api/price-analyzer/contracts/${contractId}/raci`, { entries });
    toast("RACI matrix saved", "ok");
    await load();
  });

  const updateContract = (patch: Record<string, any>) => withBusy(async () => {
    await api.put(`/api/price-analyzer/contracts/${contractId}`, patch);
    await load();
  });

  const exportFile = (fmt: "pdf" | "xlsx") => withBusy(async () => {
    await api.download(`/api/price-analyzer/contracts/${contractId}/export?fmt=${fmt}`, `price-analysis-${contractId}.${fmt}`);
  });

  const pushToReport = () => withBusy(async () => {
    const r = await api.post(`/api/price-analyzer/contracts/${contractId}/push-to-report`, {});
    toast(`Report #${r.report_id} created`, "ok");
  });

  const syncMilestones = () => withBusy(async () => {
    const r = await api.post(`/api/price-analyzer/contracts/${contractId}/sync-milestones`, {});
    toast(`${r.milestones} milestone(s) on the linked project`, "ok");
  });

  const saveToKnowledge = () => withBusy(async () => {
    const r = await api.post(`/api/price-analyzer/contracts/${contractId}/to-knowledge`, {});
    toast(r.created ? "Saved to the knowledge base (Data → Knowledge)" : "Knowledge base entry updated", "ok");
    await load();
  });

  const removeContract = () => {
    if (!confirm(`Delete "${contract.title}"? This cannot be undone.`)) return;
    withBusy(async () => {
      await api.del(`/api/price-analyzer/contracts/${contractId}`);
      onDeleted();
    });
  };

  return (
    <div dir={isFa ? "rtl" : "ltr"} lang={contract.language} className={isFa ? "fa" : undefined}>
      <div className="page-intro">
        <div>
          <button className="btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: 6 }}>← Back to contracts</button>
          <h1>{contract.title}</h1>
          <p>{contract.customer || "—"} · {cost.currency} · {sections.length} section(s) · {cost.total_hours}h total</p>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn-sm" disabled={busy} onClick={() => exportFile("xlsx")}>Export Excel</button>
          <button className="btn-sm" disabled={busy} onClick={() => exportFile("pdf")}>Export PDF</button>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "sections" ? "active" : ""}`} onClick={() => setTab("sections")}>Sections & Cost</button>
        <button className={`tab ${tab === "wbs" ? "active" : ""}`} onClick={() => setTab("wbs")}>WBS</button>
        <button className={`tab ${tab === "gantt" ? "active" : ""}`} onClick={() => setTab("gantt")}>Gantt</button>
        <button className={`tab ${tab === "raci" ? "active" : ""}`} onClick={() => setTab("raci")}>RACI</button>
        <button className={`tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>Settings</button>
      </div>

      {tab === "sections" && (
        <SectionsTab contract={contract} sections={sections} cost={cost} busy={busy} lastMethod={lastMethod} isFa={isFa}
          onAnalyze={analyze} onUpdate={updateSection} onDelete={deleteSection} onAdd={addSection} />
      )}
      {tab === "wbs" && (
        <WbsTab wbs={wbs} hasSections={sections.length > 0} busy={busy} scheduleStart={contract.schedule_start}
          onGenerate={generateWbs} onUpdate={updateWbsItem} />
      )}
      {tab === "gantt" && <GanttTab wbs={wbs} isFa={isFa} />}
      {tab === "raci" && <RaciTab wbs={wbs} raci={raci} busy={busy} onSave={saveRaci} />}
      {tab === "settings" && (
        <SettingsTab contract={contract} projects={projects} busy={busy}
          onUpdate={updateContract} onPushReport={pushToReport} onSyncMilestones={syncMilestones}
          onSaveToKnowledge={saveToKnowledge} onDelete={removeContract} />
      )}
    </div>
  );
}

// --- Sections & Cost ---------------------------------------------------------

function SectionsTab({ contract, sections, cost, busy, lastMethod, isFa, onAnalyze, onUpdate, onDelete, onAdd }: {
  contract: Contract; sections: Section[]; cost: Cost; busy: boolean;
  lastMethod: "ai" | "heuristic" | null; isFa: boolean;
  onAnalyze: () => void; onUpdate: (s: Section, patch: Partial<Section>) => void; onDelete: (s: Section) => void; onAdd: () => void;
}) {
  const roles = Object.keys(contract.coefficients?.rates || {});
  const heuristicHint = isFa
    ? "این تحلیل بدون مدل زبانی و به‌صورت خودکار انجام شد (تقسیم بر اساس ساختار قرارداد). برای استخراج دقیق‌تر بخش‌ها و تعهدات فنی، یک مدل زبانی را در «تنظیمات ← LLM» پیکربندی کنید. برآوردها یک نقطه شروع قابل‌ویرایش هستند."
    : "This analysis ran offline without an LLM (structure-based split). For sharper section and technical-obligation extraction, configure an LLM under Settings → LLM. The estimates are an editable starting point.";

  return (
    <>
      {lastMethod === "heuristic" && (
        <div className="notice compact mb" style={{ border: "1px solid var(--border-strong)", borderRadius: 8, padding: "10px 12px", color: "var(--text-dim)", fontSize: 12.5 }}>
          {heuristicHint}
        </div>
      )}
      <div className="card mb">
        <div className="card-head">
          <h3>Cost summary</h3>
          <span className="row" style={{ gap: 6 }}>
            <button className="btn-sm" disabled={busy} onClick={onAdd}>+ Add section</button>
            <button className="btn-primary btn-sm" disabled={busy} onClick={onAnalyze}>
              {sections.length > 0 ? "Re-analyze contract" : "Analyze contract"}
            </button>
          </span>
        </div>
        <div className="grid cols-4">
          <Stat label="Total hours" value={`${cost.total_hours}h`} />
          <Stat label="Subtotal" value={`${cost.subtotal} ${cost.currency}`} />
          <Stat label="Overhead + contingency" value={`${(cost.overhead_amount + cost.contingency_amount).toFixed(2)} ${cost.currency}`} />
          <Stat label="Total" value={`${cost.total} ${cost.currency}`} />
        </div>
      </div>

      {sections.length === 0 ? (
        <div className="card"><div className="empty">No sections yet. Click "Analyze contract" to split it into scope sections, or add one manually.</div></div>
      ) : (
        <div className="card table-card">
          <table className="data">
            <thead>
              <tr><th>Title</th><th>Category</th><th>Role</th><th>Hours</th><th>Rate override</th><th>Cost</th><th /></tr>
            </thead>
            <tbody>
              {sections.map((s) => {
                const row = cost.rows.find((r) => r.section_id === s.id);
                return (
                  <tr key={s.id}>
                    <td style={{ minWidth: 200 }}>
                      <input defaultValue={s.title} onBlur={(e) => e.target.value !== s.title && onUpdate(s, { title: e.target.value })} />
                    </td>
                    <td>
                      <select defaultValue={s.category} onChange={(e) => onUpdate(s, { category: e.target.value })}>
                        {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
                      </select>
                    </td>
                    <td>
                      <select defaultValue={s.role} onChange={(e) => onUpdate(s, { role: e.target.value })}>
                        {roles.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
                      </select>
                    </td>
                    <td style={{ width: 90 }}>
                      <input type="number" min={0} step={0.5} defaultValue={s.adjusted_hours}
                        onBlur={(e) => Number(e.target.value) !== s.adjusted_hours && onUpdate(s, { adjusted_hours: Number(e.target.value) })} />
                    </td>
                    <td style={{ width: 130 }}>
                      <input type="number" min={0} step={10000} dir="ltr" placeholder="role rate" defaultValue={s.hourly_rate_override ?? ""}
                        style={{ fontVariantNumeric: "tabular-nums" }}
                        onBlur={(e) => onUpdate(s, { hourly_rate_override: e.target.value === "" ? null : Number(e.target.value) })} />
                    </td>
                    <td className="dim">{row ? `${row.cost} ${cost.currency}` : "—"}</td>
                    <td><button className="btn-sm btn-danger" onClick={() => onDelete(s)}>✕</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="stat"><div className="num">{value}</div><div className="label">{label}</div></div>;
}

// --- WBS ----------------------------------------------------------------------

function WbsTab({ wbs, hasSections, busy, scheduleStart, onGenerate, onUpdate }: {
  wbs: WBSItem[]; hasSections: boolean; busy: boolean; scheduleStart: string;
  onGenerate: (start: string) => void; onUpdate: (item: WBSItem, patch: Partial<WBSItem>) => void;
}) {
  const [start, setStart] = useState(scheduleStart || new Date().toISOString().slice(0, 10));

  return (
    <>
      <div className="card mb">
        <div className="row">
          <div><label>Schedule start</label><input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <span className="spacer" />
          <button className="btn-primary btn-sm" disabled={busy || !hasSections}
            onClick={() => { if (wbs.length === 0 || confirm("Regenerate the WBS & Gantt? This replaces the current schedule and RACI matrix.")) onGenerate(start); }}>
            {wbs.length > 0 ? "Regenerate WBS & Gantt" : "Generate WBS & Gantt"}
          </button>
        </div>
        {!hasSections && <p className="dim" style={{ fontSize: 12.5, marginBottom: 0 }}>Analyze the contract into sections first.</p>}
      </div>

      {wbs.length === 0 ? (
        <div className="card"><div className="empty">No work breakdown structure yet.</div></div>
      ) : (
        <div className="card table-card">
          <table className="data">
            <thead><tr><th>Code</th><th>Title</th><th>Start</th><th>End</th><th>Days</th><th>%</th><th>Assignee</th></tr></thead>
            <tbody>
              {wbs.map((item) => (
                <tr key={item.id}>
                  <td className="dim">{item.code}</td>
                  <td style={{ paddingInlineStart: (item.level - 1) * 18 + 10 }}>
                    <input defaultValue={item.title} style={{ fontWeight: item.level < 3 ? 650 : 400 }}
                      onBlur={(e) => e.target.value !== item.title && onUpdate(item, { title: e.target.value })} />
                  </td>
                  <td style={{ width: 130 }}><input type="date" defaultValue={item.start_date}
                    onBlur={(e) => e.target.value !== item.start_date && onUpdate(item, { start_date: e.target.value })} /></td>
                  <td style={{ width: 130 }}><input type="date" defaultValue={item.end_date}
                    onBlur={(e) => e.target.value !== item.end_date && onUpdate(item, { end_date: e.target.value })} /></td>
                  <td className="dim">{item.duration_days}</td>
                  <td style={{ width: 70 }}><input type="number" min={0} max={100} defaultValue={item.percent_complete}
                    onBlur={(e) => Number(e.target.value) !== item.percent_complete && onUpdate(item, { percent_complete: Number(e.target.value) })} /></td>
                  <td style={{ width: 140 }}><input defaultValue={item.assignee}
                    onBlur={(e) => e.target.value !== item.assignee && onUpdate(item, { assignee: e.target.value })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// --- Gantt ---------------------------------------------------------------------

function GanttTab({ wbs, isFa }: { wbs: WBSItem[]; isFa: boolean }) {
  if (wbs.length === 0) return <div className="card"><div className="empty">Generate a WBS first to see the Gantt chart.</div></div>;

  const starts = wbs.map((w) => new Date(w.start_date).getTime()).filter((n) => !Number.isNaN(n));
  const ends = wbs.map((w) => new Date(w.end_date || w.start_date).getTime()).filter((n) => !Number.isNaN(n));
  const min = Math.min(...starts);
  const max = Math.max(...ends);
  const totalMs = Math.max(1, max - min);
  const dayMs = 86400000;
  const totalDays = Math.max(1, Math.round(totalMs / dayMs) + 1);

  const levelClass: Record<number, string> = { 1: "gantt-bar l1", 2: "gantt-bar l2", 3: "gantt-bar l3" };

  return (
    <div className="card">
      <div className="gantt-chart" dir="ltr">
        {wbs.map((item) => {
          const s = new Date(item.start_date).getTime();
          const e = new Date(item.end_date || item.start_date).getTime();
          const offsetPct = Number.isNaN(s) ? 0 : ((s - min) / totalMs) * 100;
          const widthPct = Math.max(1.5, Number.isNaN(e) ? 1.5 : ((e - s + dayMs) / totalMs) * 100);
          const sidePosition: any = isFa ? { right: `${offsetPct}%` } : { left: `${offsetPct}%` };
          return (
            <div className="gantt-row" key={item.id}>
              <div className="gantt-label" style={{ paddingInlineStart: (item.level - 1) * 14, fontWeight: item.level < 3 ? 650 : 400 }} dir={isFa ? "rtl" : "ltr"}>
                {item.code} {item.title}
              </div>
              <div className="gantt-track">
                <div className={levelClass[item.level] || "gantt-bar"} style={{ ...sidePosition, width: `${widthPct}%` }}
                  title={`${item.start_date} → ${item.end_date} (${item.duration_days}d, ${item.percent_complete}%)`}>
                  {item.percent_complete > 0 && <span className="gantt-progress" style={{ width: `${item.percent_complete}%` }} />}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="faint" style={{ fontSize: 12, marginTop: 10 }}>{totalDays} day span · darker bars are phases, lightest bars are tasks.</p>
    </div>
  );
}

// --- RACI ------------------------------------------------------------------------

const RACI_CODES = ["", "R", "A", "C", "I"];

function RaciTab({ wbs, raci, busy, onSave }: { wbs: WBSItem[]; raci: RaciEntry[]; busy: boolean; onSave: (entries: { wbs_item_id: number; participant: string; raci: string }[]) => void }) {
  const tasks = wbs.filter((w) => w.level === 3);
  const [participants, setParticipants] = useState<string[]>(() => {
    const seen = Array.from(new Set(raci.map((r) => r.participant)));
    return seen.length ? seen : ["Project Manager"];
  });
  const [grid, setGrid] = useState<Record<string, string>>(() => {
    const g: Record<string, string> = {};
    for (const r of raci) g[`${r.wbs_item_id}::${r.participant}`] = r.raci;
    return g;
  });
  const [newParticipant, setNewParticipant] = useState("");

  function setCell(wbsItemId: number, participant: string, value: string) {
    setGrid((g) => ({ ...g, [`${wbsItemId}::${participant}`]: value }));
  }

  function addParticipant() {
    const name = newParticipant.trim();
    if (!name || participants.includes(name)) return;
    setParticipants((p) => [...p, name]);
    setNewParticipant("");
  }

  function removeParticipant(name: string) {
    setParticipants((p) => p.filter((n) => n !== name));
    setGrid((g) => {
      const next = { ...g };
      for (const key of Object.keys(next)) if (key.endsWith(`::${name}`)) delete next[key];
      return next;
    });
  }

  function save() {
    const entries: { wbs_item_id: number; participant: string; raci: string }[] = [];
    for (const task of tasks) {
      for (const participant of participants) {
        const value = grid[`${task.id}::${participant}`];
        if (value) entries.push({ wbs_item_id: task.id, participant, raci: value });
      }
    }
    onSave(entries);
  }

  if (tasks.length === 0) return <div className="card"><div className="empty">Generate a WBS first to build the RACI matrix.</div></div>;

  return (
    <div className="card table-card">
      <div className="row mb">
        <input placeholder="Add participant…" value={newParticipant} onChange={(e) => setNewParticipant(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addParticipant()} style={{ maxWidth: 220 }} />
        <button className="btn-sm" onClick={addParticipant}>+ Add</button>
        <span className="spacer" />
        <button className="btn-primary btn-sm" disabled={busy} onClick={save}>Save RACI matrix</button>
      </div>
      <table className="data">
        <thead>
          <tr>
            <th>Task</th>
            {participants.map((p) => (
              <th key={p}>
                {p} <button className="btn-ghost btn-sm" title="Remove participant" onClick={() => removeParticipant(p)}>✕</button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id}>
              <td className="dim">{task.code} {task.title}</td>
              {participants.map((p) => (
                <td key={p} style={{ width: 90 }}>
                  <select value={grid[`${task.id}::${p}`] || ""} onChange={(e) => setCell(task.id, p, e.target.value)}>
                    {RACI_CODES.map((code) => <option key={code} value={code}>{code || "—"}</option>)}
                  </select>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Settings --------------------------------------------------------------------

function SettingsTab({ contract, projects, busy, onUpdate, onPushReport, onSyncMilestones, onSaveToKnowledge, onDelete }: {
  contract: Contract; projects: any[]; busy: boolean;
  onUpdate: (patch: Record<string, any>) => void; onPushReport: () => void; onSyncMilestones: () => void;
  onSaveToKnowledge: () => void; onDelete: () => void;
}) {
  const coeff = contract.coefficients || {};
  const [rates, setRates] = useState<Record<string, number>>(coeff.rates || {});
  const [newRole, setNewRole] = useState("");

  function saveCoefficients(patch: Record<string, any>) {
    onUpdate({ coefficients: { ...coeff, ...patch } });
  }

  function addRole() {
    const role = newRole.trim().toLowerCase().replace(/\s+/g, "_");
    if (!role || rates[role] !== undefined) return;
    const next = { ...rates, [role]: 40 };
    setRates(next);
    saveCoefficients({ rates: next });
    setNewRole("");
  }

  function removeRole(role: string) {
    const next = { ...rates };
    delete next[role];
    setRates(next);
    saveCoefficients({ rates: next });
  }

  function updateRate(role: string, value: number) {
    const next = { ...rates, [role]: value };
    setRates(next);
    saveCoefficients({ rates: next });
  }

  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Contract</h3>
        <div className="field-row">
          <div><label>Title</label><input defaultValue={contract.title} onBlur={(e) => e.target.value !== contract.title && onUpdate({ title: e.target.value })} /></div>
          <div><label>Customer</label><input defaultValue={contract.customer} onBlur={(e) => e.target.value !== contract.customer && onUpdate({ customer: e.target.value })} /></div>
        </div>
        <div className="field-row">
          <div>
            <label>Language</label>
            <select defaultValue={contract.language} onChange={(e) => onUpdate({ language: e.target.value })}>
              <option value="fa">فارسی</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label>Linked project</label>
            <select defaultValue={contract.project_id ?? ""} onChange={(e) => onUpdate({ project_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">— none —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        </div>
        <label>Notes</label>
        <textarea defaultValue={contract.notes} style={{ minHeight: 90 }} onBlur={(e) => e.target.value !== contract.notes && onUpdate({ notes: e.target.value })} />

        <div className="row" style={{ marginTop: 14, gap: 6, flexWrap: "wrap" }}>
          <button className="btn-sm" disabled={busy} onClick={onSaveToKnowledge}>
            {contract.knowledge_item_id ? "Update knowledge base entry" : "Save to knowledge base"}
          </button>
          <button className="btn-sm" disabled={busy || !contract.project_id} onClick={onSyncMilestones}>Sync phase milestones to project</button>
          <button className="btn-sm" disabled={busy} onClick={onPushReport}>Push cost summary to Reports</button>
          <span className="spacer" />
          <button className="btn-danger btn-sm" disabled={busy} onClick={onDelete}>Delete contract</button>
        </div>
        {contract.knowledge_item_id && (
          <p className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>
            {contract.language === "fa"
              ? "این قرارداد در پایگاه دانش ذخیره شده و از «داده‌ها ← دانش» قابل بازبینی و ویرایش است."
              : "Saved in the knowledge base — review and edit it under Data → Knowledge."}
          </p>
        )}
      </div>

      <div className="card">
        <h3>Cost coefficients</h3>
        <div className="field-row">
          <div><label>Currency</label><input defaultValue={coeff.currency || "USD"} onBlur={(e) => saveCoefficients({ currency: e.target.value })} /></div>
          <div><label>Hours per day</label><input type="number" min={1} max={24} defaultValue={coeff.hours_per_day ?? 8}
            onBlur={(e) => saveCoefficients({ hours_per_day: Number(e.target.value) })} /></div>
        </div>
        <div className="field-row">
          <div><label>Overhead %</label><input type="number" min={0} defaultValue={coeff.overhead_percent ?? 0}
            onBlur={(e) => saveCoefficients({ overhead_percent: Number(e.target.value) })} /></div>
          <div><label>Contingency %</label><input type="number" min={0} defaultValue={coeff.contingency_percent ?? 0}
            onBlur={(e) => saveCoefficients({ contingency_percent: Number(e.target.value) })} /></div>
        </div>
        <div className="field-row">
          <div><label>Tax %</label><input type="number" min={0} defaultValue={coeff.tax_percent ?? 0}
            onBlur={(e) => saveCoefficients({ tax_percent: Number(e.target.value) })} /></div>
          <div><label>Discount %</label><input type="number" min={0} defaultValue={coeff.discount_percent ?? 0}
            onBlur={(e) => saveCoefficients({ discount_percent: Number(e.target.value) })} /></div>
        </div>

        <label>Hourly rates by role</label>
        <table className="data">
          <tbody>
            {Object.entries(rates).map(([role, rate]) => (
              <tr key={role}>
                <td className="dim">{role.replace("_", " ")}</td>
                <td style={{ width: 140 }}><input type="number" min={0} step={10000} dir="ltr" value={rate}
                  style={{ width: "100%", fontVariantNumeric: "tabular-nums" }}
                  onChange={(e) => updateRate(role, Number(e.target.value))} /></td>
                <td><button className="btn-sm btn-danger" onClick={() => removeRole(role)}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 8 }}>
          <input placeholder="New role name…" value={newRole} onChange={(e) => setNewRole(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRole()} style={{ maxWidth: 200 }} />
          <button className="btn-sm" onClick={addRole}>+ Add role</button>
        </div>
      </div>
    </div>
  );
}
