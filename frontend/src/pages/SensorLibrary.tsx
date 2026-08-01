import { useEffect, useMemo, useState } from "react";
import "@fontsource-variable/vazirmatn/wght.css";
import { api } from "../api";
import { useAccess } from "../access";
import { Loading, Markdown, Modal, useToast } from "../lib";

// --- types ---------------------------------------------------------------
type Capability = { name: string; category: string; description: string };
type LogSource = {
  id: number; sensor_id: number; name: string; log_type: string; format: string; sample: string;
  key_fields: string[]; siem_sourcetype: string; siem_index: string; mitre_data_source: string;
  eps_estimate: number; retention_days: number; order_index: number;
};
type SensorDoc = {
  id: number; sensor_id: number; kind: string; title: string; summary: string; content: string;
  severity: string; trigger: string; mitre_techniques: string[]; tags: string[]; order_index: number;
  updated_by: string; confluence_page_id: string; confluence_url: string; confluence_synced_at: string | null;
};
type SensorSummary = {
  id: number; slug: string; name: string; vendor: string; product_model: string; category: string;
  status: string; criticality: string; environment: string; log_format: string; collection_methods: string[];
  tags: string[]; mitre_tactics: string[]; owner: string; is_builtin: boolean;
  log_source_count: number; document_count: number; confluence_page_id: string; confluence_url: string;
  updated_at: string;
};
type SensorDetail = SensorSummary & {
  description: string; capabilities: Capability[]; deployment_notes: string; vendor_url: string;
  doc_url: string; updated_by: string; log_sources: LogSource[]; documents: SensorDoc[];
};
type Catalog = {
  categories: string[]; log_formats: string[]; collection_methods: string[]; doc_kinds: string[];
  doc_kind_labels: Record<string, string>; statuses: string[]; criticalities: string[];
  environments: string[]; mitre_tactics: string[];
};
type Summary = {
  total_sensors: number; log_sources: number; documents: number; playbooks: number; runbooks: number;
  by_category: Record<string, number>; by_criticality: Record<string, number>; by_status: Record<string, number>;
  tactic_coverage: Record<string, number>; tactics_covered: number; tactics_total: number;
};

// --- i18n ----------------------------------------------------------------
const T = {
  en: {
    heading: "Equipment & Sensor Library",
    intro: "Every device and sensor the SOC operates — capabilities, log sources, collection guides, runbooks and playbooks. Publish any of it to Confluence.",
    sensors: "sensors", logSources: "log sources", runbooks: "runbooks", playbooks: "playbooks",
    coverage: "ATT&CK tactics", search: "Search name, vendor…", allCategories: "All categories",
    allStatus: "All statuses", newSensor: "+ New sensor", empty: "No sensors match your filters.",
    noneSelected: "Select a sensor to see its profile.", overview: "Overview", capabilities: "Capabilities",
    deployment: "Deployment notes", logSourcesH: "Log sources", exportMd: "Export .md", exportJson: "Export .json",
    publish: "Publish to Confluence", edit: "Edit", delete: "Delete", addLog: "+ Log source", addDoc: "+ Document",
    vendor: "Vendor", model: "Model", owner: "Owner", format: "Log format", collection: "Collection",
    sample: "Sample", keyFields: "Key fields", sourcetype: "SIEM sourcetype", index: "Index", eps: "~EPS",
    retention: "Retention (days)", dataSource: "MITRE data source", severity: "Severity", trigger: "Trigger",
    techniques: "Techniques", builtin: "Built-in", synced: "Synced to Confluence", save: "Save", cancel: "Cancel",
    confirmDel: "Delete this? This cannot be undone.", name: "Name", category: "Category", description: "Description (Markdown)",
    title: "Title", summary: "Summary", content: "Content (Markdown)", kind: "Type", tags: "Tags (comma-separated)",
    tactics: "ATT&CK tactics (comma-separated)", methods: "Collection methods (comma-separated)",
    status: "Status", criticality: "Criticality", environment: "Environment", vendorUrl: "Vendor URL", docUrl: "Docs URL",
    capName: "Capability name", capCat: "Category", capDesc: "Description", addCap: "+ Add capability",
    connection: "Confluence connection", space: "Space", parent: "Parent page ID (optional)", publishBtn: "Publish",
    publishScope: "Publishing", wholeProfile: "Full sensor profile", pickConn: "Select a connection…", pickSpace: "Select a space…",
    open: "Open", noTargets: "No Confluence-enabled connections. Configure one in the Analyzer Hub first.",
  },
  fa: {
    heading: "کتابخانه تجهیزات و سنسورها",
    intro: "همه تجهیزات و سنسورهای مرکز عملیات امنیت — قابلیت‌ها، منابع لاگ، دستورالعمل‌های لاگ‌گیری، Runbook و Playbook. امکان انتشار در کانفلوئنس.",
    sensors: "تجهیز", logSources: "منبع لاگ", runbooks: "رانبوک", playbooks: "پلی‌بوک",
    coverage: "تاکتیک ATT&CK", search: "جستجوی نام، سازنده…", allCategories: "همه دسته‌ها",
    allStatus: "همه وضعیت‌ها", newSensor: "+ تجهیز جدید", empty: "تجهیزی با این فیلترها یافت نشد.",
    noneSelected: "یک تجهیز را برای دیدن مشخصات انتخاب کنید.", overview: "معرفی", capabilities: "قابلیت‌ها",
    deployment: "نکات استقرار", logSourcesH: "منابع لاگ", exportMd: "خروجی md.", exportJson: "خروجی json.",
    publish: "انتشار در کانفلوئنس", edit: "ویرایش", delete: "حذف", addLog: "+ منبع لاگ", addDoc: "+ سند",
    vendor: "سازنده", model: "مدل", owner: "مالک", format: "قالب لاگ", collection: "روش جمع‌آوری",
    sample: "نمونه", keyFields: "فیلدهای کلیدی", sourcetype: "sourcetype سیم", index: "ایندکس", eps: "تقریب EPS",
    retention: "نگهداشت (روز)", dataSource: "منبع داده MITRE", severity: "شدت", trigger: "محرک",
    techniques: "تکنیک‌ها", builtin: "پیش‌فرض", synced: "همگام با کانفلوئنس", save: "ذخیره", cancel: "انصراف",
    confirmDel: "حذف شود؟ این عمل بازگشت‌پذیر نیست.", name: "نام", category: "دسته", description: "معرفی (Markdown)",
    title: "عنوان", summary: "خلاصه", content: "محتوا (Markdown)", kind: "نوع", tags: "برچسب‌ها (با کاما)",
    tactics: "تاکتیک‌های ATT&CK (با کاما)", methods: "روش‌های جمع‌آوری (با کاما)",
    status: "وضعیت", criticality: "بحرانیت", environment: "محیط", vendorUrl: "آدرس سازنده", docUrl: "آدرس مستندات",
    capName: "نام قابلیت", capCat: "دسته", capDesc: "توضیح", addCap: "+ افزودن قابلیت",
    connection: "اتصال کانفلوئنس", space: "فضا", parent: "شناسه صفحه والد (اختیاری)", publishBtn: "انتشار",
    publishScope: "انتشار", wholeProfile: "مشخصات کامل تجهیز", pickConn: "یک اتصال انتخاب کنید…", pickSpace: "یک فضا انتخاب کنید…",
    open: "باز کردن", noTargets: "هیچ اتصال دارای کانفلوئنس وجود ندارد. ابتدا در مرکز یکپارچه‌سازی یکی بسازید.",
  },
};

const CRIT_BADGE: Record<string, string> = { low: "green", medium: "blue", high: "yellow", critical: "red" };
const STATUS_BADGE: Record<string, string> = { active: "green", evaluation: "yellow", deprecated: "red" };
const csv = (v: string): string[] => v.split(",").map((s) => s.trim()).filter(Boolean);

export default function SensorLibrary() {
  const access = useAccess();
  const isAdmin = access.user.role === "admin";
  const toast = useToast();
  const [lang, setLang] = useState<"en" | "fa">("en");
  const t = T[lang];

  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [list, setList] = useState<SensorSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SensorDetail | null>(null);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");

  const [editSensor, setEditSensor] = useState<any | null>(null);
  const [editLog, setEditLog] = useState<any | null>(null);
  const [editDoc, setEditDoc] = useState<any | null>(null);
  const [publishing, setPublishing] = useState<{ document_id: number | null } | null>(null);

  useEffect(() => { api.get("/api/sensors/catalog").then(setCatalog).catch((e) => toast(e.message, "error")); }, []); // eslint-disable-line

  async function loadList() {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    try {
      const [res, sum] = await Promise.all([
        api.get(`/api/sensors?${params.toString()}`),
        api.get("/api/sensors/summary"),
      ]);
      setList(res.items);
      setSummary(sum);
      setSelectedId((prev) => (res.items.some((r: SensorSummary) => r.id === prev) ? prev : res.items[0]?.id ?? null));
    } catch (e: any) { toast(e.message, "error"); }
  }

  useEffect(() => { loadList(); }, [category, status, q]); // eslint-disable-line

  async function loadDetail(id: number) {
    try { setDetail(await api.get(`/api/sensors/${id}`)); }
    catch (e: any) { toast(e.message, "error"); }
  }
  useEffect(() => { if (selectedId != null) { setDetail(null); loadDetail(selectedId); } else setDetail(null); }, [selectedId]);

  async function refreshAll() { await loadList(); if (selectedId != null) await loadDetail(selectedId); }

  async function removeSensor(id: number) {
    if (!confirm(t.confirmDel)) return;
    try { await api.del(`/api/sensors/${id}`); toast("Deleted", "ok"); setSelectedId(null); loadList(); }
    catch (e: any) { toast(e.message, "error"); }
  }
  async function removeLog(id: number) {
    if (!confirm(t.confirmDel)) return;
    try { await api.del(`/api/sensors/log-sources/${id}`); toast("Deleted", "ok"); refreshAll(); }
    catch (e: any) { toast(e.message, "error"); }
  }
  async function removeDoc(id: number) {
    if (!confirm(t.confirmDel)) return;
    try { await api.del(`/api/sensors/documents/${id}`); toast("Deleted", "ok"); refreshAll(); }
    catch (e: any) { toast(e.message, "error"); }
  }

  const catLabel = (c: string) => c.replace(/_/g, "/").toUpperCase();
  const docsByKind = useMemo(() => {
    const map = new Map<string, SensorDoc[]>();
    for (const d of detail?.documents || []) { if (!map.has(d.kind)) map.set(d.kind, []); map.get(d.kind)!.push(d); }
    return map;
  }, [detail]);

  if (!catalog || list === null) return <Loading />;

  return (
    <div dir={lang === "fa" ? "rtl" : "ltr"} lang={lang} className={lang === "fa" ? "fa" : undefined}>
      <div className="page-intro">
        <div><h1>{t.heading}</h1><p>{t.intro}</p></div>
        <div className="pill-toggle">
          <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>EN</button>
          <button className={lang === "fa" ? "active" : ""} onClick={() => setLang("fa")}>فا</button>
        </div>
      </div>

      {summary && (
        <div className="grid cols-4 mb">
          <div className="card stat"><div className="num">{summary.total_sensors}</div><div className="label">{t.sensors}</div></div>
          <div className="card stat"><div className="num">{summary.log_sources}</div><div className="label">{t.logSources}</div></div>
          <div className="card stat"><div className="num">{summary.runbooks} / {summary.playbooks}</div><div className="label">{t.runbooks} / {t.playbooks}</div></div>
          <div className="card stat"><div className="num">{summary.tactics_covered}/{summary.tactics_total}</div><div className="label">{t.coverage}</div></div>
        </div>
      )}

      <div className="row mb" style={{ gap: 8, flexWrap: "wrap" }}>
        <input placeholder={t.search} value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">{t.allCategories}</option>
          {catalog.categories.map((c) => <option key={c} value={c}>{catLabel(c)}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t.allStatus}</option>
          {catalog.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="spacer" />
        {isAdmin && <button className="btn-primary btn-sm" onClick={() => setEditSensor(blankSensor())}>{t.newSensor}</button>}
      </div>

      <div className="grid help-layout">
        <div className="card help-sidebar">
          {list.length === 0 ? <div className="empty">{t.empty}</div> : list.map((s) => (
            <button key={s.id} className={`help-guide-link ${s.id === selectedId ? "active" : ""}`} onClick={() => setSelectedId(s.id)}>
              <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
                <b>{s.name}</b>
                <span className="meta" style={{ fontSize: 11 }}>{s.vendor || catLabel(s.category)}</span>
                <span className="row" style={{ gap: 4 }}>
                  <span className={`badge ${STATUS_BADGE[s.status] || ""}`}>{s.status}</span>
                  <span className={`badge ${CRIT_BADGE[s.criticality] || ""}`}>{s.criticality}</span>
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="card">
          {!detail ? <div className="empty">{selectedId == null ? t.noneSelected : "…"}</div> : (
            <>
              <div className="card-head" style={{ alignItems: "flex-start" }}>
                <div>
                  <h2 style={{ margin: "0 0 4px" }}>{detail.name}</h2>
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <span className="chip">{catLabel(detail.category)}</span>
                    <span className={`badge ${STATUS_BADGE[detail.status] || ""}`}>{detail.status}</span>
                    <span className={`badge ${CRIT_BADGE[detail.criticality] || ""}`}>{detail.criticality}</span>
                    {detail.is_builtin && <span className="chip">{t.builtin}</span>}
                    {detail.confluence_url && <a className="chip" href={detail.confluence_url} target="_blank" rel="noreferrer">{t.synced} ↗</a>}
                  </div>
                </div>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <button className="btn-sm" onClick={() => api.download(`/api/sensors/${detail.id}/export/markdown`, `${detail.slug}.md`)}>{t.exportMd}</button>
                  <button className="btn-sm" onClick={() => api.download(`/api/sensors/${detail.id}/export/json`, `${detail.slug}.json`)}>{t.exportJson}</button>
                  {isAdmin && <button className="btn-sm" onClick={() => setPublishing({ document_id: null })}>{t.publish}</button>}
                  {isAdmin && <button className="btn-sm" onClick={() => setEditSensor(toForm(detail))}>{t.edit}</button>}
                  {isAdmin && <button className="btn-sm btn-danger" onClick={() => removeSensor(detail.id)}>{t.delete}</button>}
                </div>
              </div>

              <div className="row" style={{ gap: 16, flexWrap: "wrap", margin: "6px 0 10px", fontSize: 13 }}>
                {detail.vendor && <span><b>{t.vendor}:</b> {detail.vendor}</span>}
                {detail.product_model && <span><b>{t.model}:</b> {detail.product_model}</span>}
                {detail.owner && <span><b>{t.owner}:</b> {detail.owner}</span>}
                <span><b>{t.format}:</b> {detail.log_format}</span>
                {detail.collection_methods.length > 0 && <span><b>{t.collection}:</b> {detail.collection_methods.join(", ")}</span>}
              </div>
              {detail.tags.length > 0 && <div className="row mb" style={{ gap: 5, flexWrap: "wrap" }}>{detail.tags.map((tg) => <span key={tg} className="chip">#{tg}</span>)}</div>}

              {detail.description && <section><h3>{t.overview}</h3><Markdown text={detail.description} /></section>}

              {detail.capabilities.length > 0 && (
                <section>
                  <h3>{t.capabilities}</h3>
                  <div className="grid cols-2">
                    {detail.capabilities.map((c, i) => (
                      <div key={i} className="list-row"><div>
                        <b>{c.name} {c.category && <span className="chip">{c.category}</span>}</b>
                        {c.description && <span className="meta">{c.description}</span>}
                      </div></div>
                    ))}
                  </div>
                </section>
              )}

              {detail.deployment_notes && <section><h3>{t.deployment}</h3><Markdown text={detail.deployment_notes} /></section>}

              {detail.mitre_tactics.length > 0 && (
                <div className="row mb" style={{ gap: 5, flexWrap: "wrap" }}>
                  {detail.mitre_tactics.map((m) => <span key={m} className="chip">{m}</span>)}
                </div>
              )}

              <section>
                <div className="card-head"><h3 style={{ margin: 0 }}>{t.logSourcesH}</h3>
                  {isAdmin && <button className="btn-sm" onClick={() => setEditLog(blankLog(detail.id))}>{t.addLog}</button>}
                </div>
                {detail.log_sources.length === 0 ? <div className="empty">—</div> : (
                  <div className="table-card"><table className="data">
                    <thead><tr>
                      <th>{t.name}</th><th>{t.format}</th><th>{t.sourcetype}</th><th>{t.index}</th>
                      <th>{t.eps}</th><th>{t.retention}</th><th>{t.dataSource}</th>{isAdmin && <th></th>}
                    </tr></thead>
                    <tbody>{detail.log_sources.map((ls) => (
                      <tr key={ls.id}>
                        <td><b>{ls.name}</b>{ls.log_type && <div className="meta">{ls.log_type}</div>}
                          {ls.sample && <details><summary className="meta">{t.sample}</summary><pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>{ls.sample}</pre></details>}
                          {ls.key_fields.length > 0 && <div className="meta">{t.keyFields}: {ls.key_fields.join(", ")}</div>}
                        </td>
                        <td>{ls.format}</td><td className="mono">{ls.siem_sourcetype}</td><td className="mono">{ls.siem_index}</td>
                        <td>{ls.eps_estimate || "—"}</td><td>{ls.retention_days || "—"}</td><td>{ls.mitre_data_source || "—"}</td>
                        {isAdmin && <td><div className="row" style={{ gap: 4 }}>
                          <button className="btn-sm btn-ghost" onClick={() => setEditLog(toLogForm(ls))}>✎</button>
                          <button className="btn-sm btn-ghost" onClick={() => removeLog(ls.id)}>🗑</button>
                        </div></td>}
                      </tr>
                    ))}</tbody>
                  </table></div>
                )}
              </section>

              <section>
                <div className="card-head"><h3 style={{ margin: 0 }}>{lang === "fa" ? "اسناد" : "Documentation"}</h3>
                  {isAdmin && <button className="btn-sm" onClick={() => setEditDoc(blankDoc(detail.id))}>{t.addDoc}</button>}
                </div>
                {catalog.doc_kinds.filter((k) => docsByKind.has(k)).map((kind) => (
                  <div key={kind}>
                    <div className="nav-group-label">{catalog.doc_kind_labels[kind] || kind}</div>
                    {docsByKind.get(kind)!.map((d) => (
                      <div key={d.id} className="card" style={{ marginBottom: 10 }}>
                        <div className="card-head" style={{ alignItems: "flex-start" }}>
                          <div>
                            <b>{d.title}</b>
                            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                              {d.severity && <span className={`badge ${CRIT_BADGE[d.severity] || ""}`}>{d.severity}</span>}
                              {d.mitre_techniques.map((m) => <span key={m} className="chip">{m}</span>)}
                              {d.confluence_url && <a className="chip" href={d.confluence_url} target="_blank" rel="noreferrer">{t.open} ↗</a>}
                            </div>
                          </div>
                          {isAdmin && <div className="row" style={{ gap: 4 }}>
                            <button className="btn-sm btn-ghost" title={t.publish} onClick={() => setPublishing({ document_id: d.id })}>☁</button>
                            <button className="btn-sm btn-ghost" onClick={() => setEditDoc(toDocForm(d))}>✎</button>
                            <button className="btn-sm btn-ghost" onClick={() => removeDoc(d.id)}>🗑</button>
                          </div>}
                        </div>
                        {d.trigger && <p className="meta"><b>{t.trigger}:</b> {d.trigger}</p>}
                        {d.summary && <p className="dim">{d.summary}</p>}
                        {d.content && <Markdown text={d.content} />}
                      </div>
                    ))}
                  </div>
                ))}
              </section>
            </>
          )}
        </div>
      </div>

      {editSensor && <SensorModal initial={editSensor} catalog={catalog} t={t} onClose={() => setEditSensor(null)}
        onSaved={(id) => { setEditSensor(null); loadList(); setSelectedId(id); if (id === selectedId) loadDetail(id); }} />}
      {editLog && <LogModal initial={editLog} catalog={catalog} t={t} onClose={() => setEditLog(null)}
        onSaved={() => { setEditLog(null); refreshAll(); }} />}
      {editDoc && <DocModal initial={editDoc} catalog={catalog} t={t} onClose={() => setEditDoc(null)}
        onSaved={() => { setEditDoc(null); refreshAll(); }} />}
      {publishing && detail && <PublishModal sensor={detail} documentId={publishing.document_id} t={t}
        onClose={() => setPublishing(null)} onDone={() => { setPublishing(null); refreshAll(); }} />}
    </div>
  );
}

// --- form helpers --------------------------------------------------------
function blankSensor() {
  return {
    id: null, slug: "", name: "", vendor: "", product_model: "", category: "other", description: "",
    capabilities: [] as Capability[], deployment_notes: "", log_format: "syslog", collection_methods: "",
    status: "active", criticality: "medium", environment: "all", vendor_url: "", doc_url: "", tags: "",
    mitre_tactics: "", owner: "",
  };
}
function toForm(s: SensorDetail) {
  return {
    ...s, capabilities: s.capabilities.slice(), collection_methods: s.collection_methods.join(", "),
    tags: s.tags.join(", "), mitre_tactics: s.mitre_tactics.join(", "),
  };
}
function blankLog(sensor_id: number) {
  return { id: null, sensor_id, name: "", log_type: "", format: "syslog", sample: "", key_fields: "",
    siem_sourcetype: "", siem_index: "", mitre_data_source: "", eps_estimate: 0, retention_days: 0, order_index: 0 };
}
function toLogForm(ls: LogSource) { return { ...ls, key_fields: ls.key_fields.join(", ") }; }
function blankDoc(sensor_id: number) {
  return { id: null, sensor_id, kind: "runbook", title: "", summary: "", content: "", severity: "",
    trigger: "", mitre_techniques: "", tags: "", order_index: 0 };
}
function toDocForm(d: SensorDoc) { return { ...d, mitre_techniques: d.mitre_techniques.join(", "), tags: d.tags.join(", ") }; }

type Labels = typeof T["en"];

// --- sensor modal --------------------------------------------------------
function SensorModal({ initial, catalog, t, onClose, onSaved }: { initial: any; catalog: Catalog; t: Labels; onClose: () => void; onSaved: (id: number) => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;
  const setCap = (i: number, k: keyof Capability, v: string) =>
    setF((p: any) => ({ ...p, capabilities: p.capabilities.map((c: Capability, j: number) => j === i ? { ...c, [k]: v } : c) }));

  async function save() {
    if (!f.name.trim()) return toast("Name is required", "error");
    setBusy(true);
    const body = {
      slug: f.slug || "", name: f.name, vendor: f.vendor, product_model: f.product_model, category: f.category,
      description: f.description, capabilities: f.capabilities.filter((c: Capability) => c.name.trim()),
      deployment_notes: f.deployment_notes, log_format: f.log_format, collection_methods: csv(f.collection_methods),
      status: f.status, criticality: f.criticality, environment: f.environment, vendor_url: f.vendor_url,
      doc_url: f.doc_url, tags: csv(f.tags), mitre_tactics: csv(f.mitre_tactics), owner: f.owner,
    };
    try {
      const res = isEdit ? await api.put(`/api/sensors/${f.id}`, body) : await api.post("/api/sensors", body);
      toast(isEdit ? "Updated" : "Created", "ok");
      onSaved(res.id);
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  }

  return (
    <Modal title={isEdit ? `${t.edit}: ${initial.name}` : t.newSensor} onClose={onClose} wide
      footer={<><button className="btn-sm" onClick={onClose}>{t.cancel}</button>
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : t.save}</button></>}>
      <div className="field-row">
        <div><label>{t.name}</label><input value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
        <div><label>{t.vendor}</label><input value={f.vendor} onChange={(e) => set("vendor", e.target.value)} /></div>
        <div><label>{t.model}</label><input value={f.product_model} onChange={(e) => set("product_model", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>{t.category}</label><select value={f.category} onChange={(e) => set("category", e.target.value)}>{catalog.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div><label>{t.status}</label><select value={f.status} onChange={(e) => set("status", e.target.value)}>{catalog.statuses.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div><label>{t.criticality}</label><select value={f.criticality} onChange={(e) => set("criticality", e.target.value)}>{catalog.criticalities.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div><label>{t.environment}</label><select value={f.environment} onChange={(e) => set("environment", e.target.value)}>{catalog.environments.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
      </div>
      <div className="field-row">
        <div><label>{t.format}</label><select value={f.log_format} onChange={(e) => set("log_format", e.target.value)}>{catalog.log_formats.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div><label>{t.methods}</label><input value={f.collection_methods} onChange={(e) => set("collection_methods", e.target.value)} placeholder="syslog, api" /></div>
        <div><label>{t.owner}</label><input value={f.owner} onChange={(e) => set("owner", e.target.value)} /></div>
      </div>
      <label>{t.description}</label>
      <textarea value={f.description} onChange={(e) => set("description", e.target.value)} style={{ minHeight: 90 }} />
      <div className="card-head" style={{ marginTop: 8 }}><label style={{ margin: 0 }}>{t.capabilities}</label>
        <button className="btn-sm" onClick={() => set("capabilities", [...f.capabilities, { name: "", category: "", description: "" }])}>{t.addCap}</button></div>
      {f.capabilities.map((c: Capability, i: number) => (
        <div key={i} className="field-row" style={{ alignItems: "center" }}>
          <input placeholder={t.capName} value={c.name} onChange={(e) => setCap(i, "name", e.target.value)} />
          <input placeholder={t.capCat} value={c.category} onChange={(e) => setCap(i, "category", e.target.value)} style={{ maxWidth: 140 }} />
          <input placeholder={t.capDesc} value={c.description} onChange={(e) => setCap(i, "description", e.target.value)} />
          <button className="btn-sm btn-ghost" onClick={() => set("capabilities", f.capabilities.filter((_: any, j: number) => j !== i))}>🗑</button>
        </div>
      ))}
      <label style={{ marginTop: 8 }}>{t.deployment}</label>
      <textarea value={f.deployment_notes} onChange={(e) => set("deployment_notes", e.target.value)} style={{ minHeight: 70 }} />
      <div className="field-row">
        <div><label>{t.tags}</label><input value={f.tags} onChange={(e) => set("tags", e.target.value)} /></div>
        <div><label>{t.tactics}</label><input value={f.mitre_tactics} onChange={(e) => set("mitre_tactics", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>{t.vendorUrl}</label><input value={f.vendor_url} onChange={(e) => set("vendor_url", e.target.value)} /></div>
        <div><label>{t.docUrl}</label><input value={f.doc_url} onChange={(e) => set("doc_url", e.target.value)} /></div>
      </div>
    </Modal>
  );
}

// --- log source modal ----------------------------------------------------
function LogModal({ initial, catalog, t, onClose, onSaved }: { initial: any; catalog: Catalog; t: Labels; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.name.trim()) return toast("Name is required", "error");
    setBusy(true);
    const body = {
      name: f.name, log_type: f.log_type, format: f.format, sample: f.sample, key_fields: csv(f.key_fields),
      siem_sourcetype: f.siem_sourcetype, siem_index: f.siem_index, mitre_data_source: f.mitre_data_source,
      eps_estimate: Number(f.eps_estimate) || 0, retention_days: Number(f.retention_days) || 0, order_index: Number(f.order_index) || 0,
    };
    try {
      if (isEdit) await api.put(`/api/sensors/log-sources/${f.id}`, body);
      else await api.post(`/api/sensors/${f.sensor_id}/log-sources`, body);
      toast("Saved", "ok"); onSaved();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  }

  return (
    <Modal title={isEdit ? `${t.edit}: ${initial.name}` : t.addLog} onClose={onClose} wide
      footer={<><button className="btn-sm" onClick={onClose}>{t.cancel}</button>
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : t.save}</button></>}>
      <div className="field-row">
        <div><label>{t.name}</label><input value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
        <div><label>{t.kind}</label><input value={f.log_type} onChange={(e) => set("log_type", e.target.value)} placeholder="traffic, auth…" /></div>
        <div><label>{t.format}</label><select value={f.format} onChange={(e) => set("format", e.target.value)}>{catalog.log_formats.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
      </div>
      <div className="field-row">
        <div><label>{t.sourcetype}</label><input value={f.siem_sourcetype} onChange={(e) => set("siem_sourcetype", e.target.value)} /></div>
        <div><label>{t.index}</label><input value={f.siem_index} onChange={(e) => set("siem_index", e.target.value)} /></div>
        <div><label>{t.dataSource}</label><input value={f.mitre_data_source} onChange={(e) => set("mitre_data_source", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>{t.eps}</label><input type="number" value={f.eps_estimate} onChange={(e) => set("eps_estimate", e.target.value)} /></div>
        <div><label>{t.retention}</label><input type="number" value={f.retention_days} onChange={(e) => set("retention_days", e.target.value)} /></div>
        <div><label>{t.keyFields}</label><input value={f.key_fields} onChange={(e) => set("key_fields", e.target.value)} placeholder="src, dst" /></div>
      </div>
      <label>{t.sample}</label>
      <textarea value={f.sample} onChange={(e) => set("sample", e.target.value)} style={{ minHeight: 70, fontFamily: "var(--mono)" }} />
    </Modal>
  );
}

// --- document modal ------------------------------------------------------
function DocModal({ initial, catalog, t, onClose, onSaved }: { initial: any; catalog: Catalog; t: Labels; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;
  const isPlaybook = f.kind === "playbook";

  async function save() {
    if (!f.title.trim()) return toast("Title is required", "error");
    setBusy(true);
    const body = {
      kind: f.kind, title: f.title, summary: f.summary, content: f.content, severity: isPlaybook ? f.severity : "",
      trigger: isPlaybook ? f.trigger : "", mitre_techniques: csv(f.mitre_techniques), tags: csv(f.tags),
      order_index: Number(f.order_index) || 0,
    };
    try {
      if (isEdit) await api.put(`/api/sensors/documents/${f.id}`, body);
      else await api.post(`/api/sensors/${f.sensor_id}/documents`, body);
      toast("Saved", "ok"); onSaved();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  }

  return (
    <Modal title={isEdit ? `${t.edit}: ${initial.title}` : t.addDoc} onClose={onClose} wide
      footer={<><button className="btn-sm" onClick={onClose}>{t.cancel}</button>
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : t.save}</button></>}>
      <div className="field-row">
        <div><label>{t.kind}</label><select value={f.kind} onChange={(e) => set("kind", e.target.value)}>{catalog.doc_kinds.map((c) => <option key={c} value={c}>{catalog.doc_kind_labels[c] || c}</option>)}</select></div>
        <div><label>{t.title}</label><input value={f.title} onChange={(e) => set("title", e.target.value)} /></div>
      </div>
      {isPlaybook && (
        <div className="field-row">
          <div><label>{t.severity}</label><select value={f.severity} onChange={(e) => set("severity", e.target.value)}>
            <option value="">—</option>{["info", "low", "medium", "high", "critical"].map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          <div><label>{t.techniques}</label><input value={f.mitre_techniques} onChange={(e) => set("mitre_techniques", e.target.value)} placeholder="T1071, T1059" /></div>
        </div>
      )}
      {isPlaybook && <><label>{t.trigger}</label><textarea value={f.trigger} onChange={(e) => set("trigger", e.target.value)} style={{ minHeight: 50 }} /></>}
      <label>{t.summary}</label>
      <input value={f.summary} onChange={(e) => set("summary", e.target.value)} />
      <label>{t.content}</label>
      <textarea value={f.content} onChange={(e) => set("content", e.target.value)} style={{ minHeight: 240, fontFamily: "var(--mono)" }} />
    </Modal>
  );
}

// --- publish modal -------------------------------------------------------
type Target = { id: number; name: string; deployment_type: string };
type Space = { id: string; key: string; name: string };
function PublishModal({ sensor, documentId, t, onClose, onDone }: { sensor: SensorDetail; documentId: number | null; t: Labels; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [targets, setTargets] = useState<Target[] | null>(null);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [space, setSpace] = useState("");
  const [parent, setParent] = useState("");
  const [busy, setBusy] = useState(false);
  const doc = documentId != null ? sensor.documents.find((d) => d.id === documentId) : null;
  const conn = targets?.find((c) => c.id === connectionId) || null;

  useEffect(() => { api.get("/api/sensors/publish/targets").then(setTargets).catch((e) => toast(e.message, "error")); }, []); // eslint-disable-line

  async function loadSpaces(id: number) {
    setSpaces(null); setSpace("");
    try { setSpaces(await api.get(`/api/sensors/publish/${id}/spaces`)); }
    catch (e: any) { toast(e.message, "error"); setSpaces([]); }
  }

  async function publish() {
    if (!connectionId || !space) return toast("Select a connection and space", "error");
    setBusy(true);
    try {
      const res = await api.post(`/api/sensors/${sensor.id}/publish`, {
        connection_id: connectionId, space, parent_page_id: parent || "", document_id: documentId,
      });
      toast(`Page ${res.action}: ${res.title}`, "ok");
      onDone();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  }

  const spaceValue = (s: Space) => (conn?.deployment_type === "cloud" ? s.id : s.key);

  return (
    <Modal title={`${t.publish}: ${doc ? doc.title : sensor.name}`} onClose={onClose}
      footer={<><button className="btn-sm" onClick={onClose}>{t.cancel}</button>
        <button className="btn-primary btn-sm" onClick={publish} disabled={busy || !space}>{busy ? <span className="spin" /> : t.publishBtn}</button></>}>
      <p className="dim">{t.publishScope}: <b>{doc ? doc.title : t.wholeProfile}</b></p>
      {!targets ? <Loading /> : targets.length === 0 ? <div className="notice">{t.noTargets}</div> : (
        <>
          <label>{t.connection}</label>
          <select value={connectionId ?? ""} onChange={(e) => { const id = Number(e.target.value) || null; setConnectionId(id); if (id) loadSpaces(id); }}>
            <option value="">{t.pickConn}</option>
            {targets.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.deployment_type})</option>)}
          </select>
          {connectionId && (
            <>
              <label>{t.space}</label>
              {!spaces ? <div className="row"><span className="spin" /></div> : (
                <select value={space} onChange={(e) => setSpace(e.target.value)}>
                  <option value="">{t.pickSpace}</option>
                  {spaces.map((s) => <option key={s.id || s.key} value={spaceValue(s)}>{s.name} ({s.key})</option>)}
                </select>
              )}
              <label>{t.parent}</label>
              <input value={parent} onChange={(e) => setParent(e.target.value)} />
            </>
          )}
        </>
      )}
    </Modal>
  );
}
