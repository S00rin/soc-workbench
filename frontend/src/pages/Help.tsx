import { useEffect, useMemo, useState } from "react";
import "@fontsource-variable/vazirmatn/wght.css";
import { api } from "../api";
import { useAccess } from "../access";
import { Loading, Markdown, Modal, useToast } from "../lib";

type Guide = {
  id: number;
  slug: string;
  language: string;
  audience: string;
  category: string;
  title: string;
  summary: string;
  content: string;
  order_index: number;
  is_builtin: boolean;
};

const BLANK = {
  slug: "", language: "en", audience: "user", category: "General",
  title: "", summary: "", content: "", order_index: 0,
};

const LABELS = {
  en: {
    heading: "Help Guides", intro: "User and administrator guides for every module, in English and Farsi.",
    user: "User Guide", admin: "Admin Guide", newGuide: "+ New guide", edit: "Edit", delete: "Delete",
    empty: "No guides yet.", save: "Save", cancel: "Cancel",
    slug: "Slug", category: "Category", title: "Title", summary: "Summary", content: "Content (Markdown)",
    order: "Order",
  },
  fa: {
    heading: "راهنماها", intro: "راهنمای کاربر و مدیر برای هر بخش، به زبان انگلیسی و فارسی.",
    user: "راهنمای کاربر", admin: "راهنمای مدیر", newGuide: "+ راهنمای جدید", edit: "ویرایش", delete: "حذف",
    empty: "هنوز راهنمایی وجود ندارد.", save: "ذخیره", cancel: "انصراف",
    slug: "شناسه", category: "دسته", title: "عنوان", summary: "خلاصه", content: "محتوا (Markdown)",
    order: "ترتیب",
  },
};

export default function Help() {
  const access = useAccess();
  const isAdmin = access.user.role === "admin";
  const [language, setLanguage] = useState<"en" | "fa">("en");
  const [audience, setAudience] = useState<"user" | "admin">("user");
  const [guides, setGuides] = useState<Guide[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<any | null>(null);
  const toast = useToast();
  const t = LABELS[language];

  async function load() {
    try {
      const rows: Guide[] = await api.get(`/api/help/guides?language=${language}&audience=${audience}`);
      setGuides(rows);
      setSelectedId((prev) => (rows.some((r) => r.id === prev) ? prev : rows[0]?.id ?? null));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, audience]);

  const grouped = useMemo(() => {
    const map = new Map<string, Guide[]>();
    for (const g of guides || []) {
      if (!map.has(g.category)) map.set(g.category, []);
      map.get(g.category)!.push(g);
    }
    return Array.from(map.entries());
  }, [guides]);

  const selected = guides?.find((g) => g.id === selectedId) || null;

  async function remove(g: Guide) {
    if (!confirm(`Delete "${g.title}"?`)) return;
    try {
      await api.del(`/api/help/guides/${g.id}`);
      toast("Deleted", "ok");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  return (
    <div dir={language === "fa" ? "rtl" : "ltr"} lang={language} className={language === "fa" ? "fa" : undefined}>
      <div className="page-intro">
        <div><h1>{t.heading}</h1><p>{t.intro}</p></div>
        <div className="row" style={{ gap: 6 }}>
          <button className={`btn-sm ${language === "en" ? "btn-primary" : ""}`} onClick={() => setLanguage("en")}>English</button>
          <button className={`btn-sm ${language === "fa" ? "btn-primary" : ""}`} onClick={() => setLanguage("fa")}>فارسی</button>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${audience === "user" ? "active" : ""}`} onClick={() => setAudience("user")}>{t.user}</button>
        {isAdmin && <button className={`tab ${audience === "admin" ? "active" : ""}`} onClick={() => setAudience("admin")}>{t.admin}</button>}
      </div>

      {isAdmin && (
        <div className="row mb">
          <span className="spacer" />
          <button className="btn-primary btn-sm" onClick={() => setEditing({ ...BLANK, language, audience })}>{t.newGuide}</button>
        </div>
      )}

      {!guides ? (
        <Loading />
      ) : guides.length === 0 ? (
        <div className="card"><div className="empty">{t.empty}</div></div>
      ) : (
        <div className="grid help-layout">
          <div className="card help-sidebar">
            {grouped.map(([category, items]) => (
              <div key={category}>
                <div className="nav-group-label">{category}</div>
                {items.map((g) => (
                  <button
                    key={g.id}
                    className={`help-guide-link ${g.id === selectedId ? "active" : ""}`}
                    onClick={() => setSelectedId(g.id)}
                  >
                    {g.title}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <div className="card">
            {selected && (
              <>
                <div className="card-head">
                  <h2 style={{ margin: 0 }}>{selected.title}</h2>
                  {isAdmin && (
                    <span className="row" style={{ gap: 6 }}>
                      <button className="btn-sm" onClick={() => setEditing({ ...selected })}>{t.edit}</button>
                      <button className="btn-sm btn-danger" onClick={() => remove(selected)}>{t.delete}</button>
                    </span>
                  )}
                </div>
                <Markdown text={selected.content} />
              </>
            )}
          </div>
        </div>
      )}

      {editing && (
        <GuideModal
          initial={editing}
          labels={t}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function GuideModal({ initial, labels, onClose, onSaved }: { initial: any; labels: typeof LABELS["en"]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.slug.trim() || !f.title.trim()) return toast("Slug and title are required", "error");
    setBusy(true);
    const body = {
      slug: f.slug.trim(), language: f.language, audience: f.audience, category: f.category || "General",
      title: f.title, summary: f.summary, content: f.content, order_index: Number(f.order_index) || 0,
    };
    try {
      if (isEdit) await api.put(`/api/help/guides/${f.id}`, body);
      else await api.post("/api/help/guides", body);
      toast(isEdit ? "Updated" : "Created", "ok");
      onSaved();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isEdit ? `${labels.edit}: ${initial.title}` : labels.newGuide}
      onClose={onClose}
      wide
      footer={<>
        <button className="btn-sm" onClick={onClose}>{labels.cancel}</button>
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : labels.save}</button>
      </>}
    >
      <div className="field-row">
        <div><label>{labels.slug}</label><input value={f.slug} onChange={(e) => set("slug", e.target.value)} disabled={isEdit} /></div>
        <div><label>{labels.category}</label><input value={f.category} onChange={(e) => set("category", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div>
          <label>Language</label>
          <select value={f.language} onChange={(e) => set("language", e.target.value)}>
            <option value="en">English</option>
            <option value="fa">فارسی</option>
          </select>
        </div>
        <div>
          <label>Audience</label>
          <select value={f.audience} onChange={(e) => set("audience", e.target.value)}>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div><label>{labels.order}</label><input type="number" value={f.order_index} onChange={(e) => set("order_index", e.target.value)} /></div>
      </div>
      <label>{labels.title}</label>
      <input value={f.title} onChange={(e) => set("title", e.target.value)} />
      <label>{labels.summary}</label>
      <input value={f.summary} onChange={(e) => set("summary", e.target.value)} />
      <label>{labels.content}</label>
      <textarea value={f.content} onChange={(e) => set("content", e.target.value)} style={{ minHeight: 260, fontFamily: "var(--mono)" }} />
    </Modal>
  );
}
