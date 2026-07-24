import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Loading, Modal, statusBadge, timeAgo, useToast } from "../lib";
import PriceAnalyzerWorkspace from "./PriceAnalyzerWorkspace";

export type Contract = {
  id: number; title: string; customer: string; project_id: number | null;
  language: string; status: string; source_type: string; source_ref: string;
  coefficients: any; schedule_start: string; summary: string; notes: string;
  created_by: string; created_at: string; updated_at: string;
};

export default function PriceAnalyzer() {
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [creating, setCreating] = useState<"none" | "text" | "file">("none");
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const selectedId = params.get("contract") ? Number(params.get("contract")) : null;

  async function load() {
    try {
      setContracts(await api.get("/api/price-analyzer/contracts"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function select(id: number | null) {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("contract");
    else next.set("contract", String(id));
    setParams(next);
  }

  async function remove(c: Contract) {
    if (!confirm(`Delete "${c.title}"?`)) return;
    try {
      await api.del(`/api/price-analyzer/contracts/${c.id}`);
      toast("Deleted", "ok");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (selectedId) {
    return (
      <PriceAnalyzerWorkspace
        contractId={selectedId}
        onBack={() => select(null)}
        onDeleted={() => { select(null); load(); }}
      />
    );
  }

  if (!contracts) return <Loading />;

  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Price Analyzer</h1>
          <p>Turn a Persian or English contract into an editable effort estimate, WBS, Gantt schedule, RACI matrix and cost breakdown.</p>
        </div>
      </div>
      <div className="row mb">
        <span className="spacer" />
        <button className="btn-sm" onClick={() => setCreating("text")}>+ Paste contract text</button>
        <button className="btn-primary btn-sm" onClick={() => setCreating("file")}>+ Upload contract</button>
      </div>

      {contracts.length === 0 ? (
        <div className="card"><div className="empty">No contracts yet. Upload or paste one to get started.</div></div>
      ) : (
        <div className="grid cols-2">
          {contracts.map((c) => (
            <div className="card" key={c.id}>
              <div className="card-head">
                <div>
                  <h3 style={{ marginBottom: 2 }}>{c.title}</h3>
                  {c.customer && <div className="dim" style={{ fontSize: 12.5 }}>{c.customer}</div>}
                </div>
                {statusBadge(c.status)}
              </div>
              <div className="row" style={{ justifyContent: "space-between", marginTop: 10 }}>
                <span className="faint" style={{ fontSize: 12 }}>{c.language.toUpperCase()} · updated {timeAgo(c.updated_at)}</span>
                <span className="row" style={{ gap: 6 }}>
                  <button className="btn-sm" onClick={() => select(c.id)}>Open</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(c)}>Delete</button>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {creating !== "none" && (
        <NewContractModal
          mode={creating}
          onClose={() => setCreating("none")}
          onCreated={(id) => { setCreating("none"); load(); select(id); }}
        />
      )}
    </>
  );
}

function NewContractModal({ mode, onClose, onCreated }: { mode: "text" | "file"; onClose: () => void; onCreated: (id: number) => void }) {
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [language, setLanguage] = useState("fa");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function save() {
    if (!title.trim()) return toast("Title is required", "error");
    if (mode === "text" && !text.trim()) return toast("Paste the contract text", "error");
    if (mode === "file" && !file) return toast("Choose a file", "error");
    setBusy(true);
    try {
      let created: any;
      if (mode === "text") {
        created = await api.post("/api/price-analyzer/contracts", { title, customer, language, text });
      } else {
        const form = new FormData();
        form.append("file", file as File);
        form.append("title", title);
        form.append("customer", customer);
        form.append("language", language);
        created = await api.upload("/api/price-analyzer/contracts/upload", form);
      }
      toast("Contract created", "ok");
      onCreated(created.id);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={mode === "text" ? "Paste contract text" : "Upload contract"}
      onClose={onClose}
      wide
      footer={<>
        <button className="btn-sm" onClick={onClose}>Cancel</button>
        <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Create"}</button>
      </>}
    >
      <div className="field-row">
        <div><label>Title</label><input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></div>
        <div><label>Customer</label><input value={customer} onChange={(e) => setCustomer(e.target.value)} /></div>
        <div>
          <label>Language</label>
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="fa">فارسی</option>
            <option value="en">English</option>
          </select>
        </div>
      </div>
      {mode === "text" ? (
        <>
          <label>Contract text</label>
          <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 220 }} />
        </>
      ) : (
        <>
          <label>Contract file (PDF, DOCX, TXT, HTML, ...)</label>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </>
      )}
    </Modal>
  );
}
