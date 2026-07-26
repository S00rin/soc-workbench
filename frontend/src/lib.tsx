import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { marked } from "marked";

marked.setOptions({ breaks: true, gfm: true });

// Detect Persian/Arabic script to set direction on rendered blocks.
export function isRTL(text: string): boolean {
  const rtl = (text.match(/[؀-ۿ]/g) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr && rtl > 3;
}

export function Markdown({ text }: { text: string }) {
  const html = sanitizeHtml(marked.parse(text || "", { async: false }) as string);
  return (
    <div
      className="md"
      dir={isRTL(text) ? "rtl" : "ltr"}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

const SAFE_TAGS = new Set([
  "A", "P", "BR", "STRONG", "EM", "B", "I", "UL", "OL", "LI", "BLOCKQUOTE",
  "CODE", "PRE", "H1", "H2", "H3", "H4", "H5", "H6", "HR", "TABLE", "THEAD",
  "TBODY", "TR", "TH", "TD", "DEL", "SUP", "SUB",
]);

function sanitizeHtml(value: string): string {
  // Connector and LLM text is untrusted. Keep a small presentational subset of
  // Markdown HTML and strip every event/style attribute and unsafe URL scheme.
  const documentValue = new DOMParser().parseFromString(value, "text/html");
  for (const element of Array.from(documentValue.body.querySelectorAll("*"))) {
    if (!SAFE_TAGS.has(element.tagName)) {
      element.replaceWith(documentValue.createTextNode(element.textContent || ""));
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      const keep = element.tagName === "A" && ["href", "title"].includes(attribute.name.toLowerCase());
      if (!keep) element.removeAttribute(attribute.name);
    }
    if (element.tagName === "A") {
      const href = element.getAttribute("href") || "";
      if (!/^(https?:|mailto:|\/)/i.test(href)) element.removeAttribute("href");
      else element.setAttribute("rel", "noopener noreferrer");
    }
  }
  return documentValue.body.innerHTML;
}

export function timeAgo(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

// --- Toast ---------------------------------------------------------------
type Toast = { msg: string; kind: "ok" | "error" | "info" };
const ToastCtx = createContext<(msg: string, kind?: Toast["kind"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const show = useCallback((msg: string, kind: Toast["kind"] = "info") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={`toast ${toast.kind}`}>{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-full">
      <div className="row">
        <span className="spin" /> <span>{label}</span>
      </div>
    </div>
  );
}

// --- Modal ---------------------------------------------------------------
export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={wide ? { maxWidth: 900 } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function healthBadge(h: string) {
  const cls = h === "green" ? "green" : h === "yellow" ? "yellow" : "red";
  return <span className={`badge ${cls}`}>{h}</span>;
}

export function statusBadge(s: string) {
  const map: Record<string, string> = {
    completed: "green", running: "blue", pending: "yellow", failed: "red",
    active: "green", draft: "yellow",
  };
  return <span className={`badge ${map[s] || ""}`}>{s}</span>;
}
