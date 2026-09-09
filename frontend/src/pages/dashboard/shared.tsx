import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";

// ---------------------------------------------------------------------------
// Data loading with optional auto-refresh. Used by every dashboard view.
// ---------------------------------------------------------------------------
export function useLiveData<T = any>(path: string, refreshMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.get(path));
      setErr("");
      setUpdatedAt(new Date());
    } catch (error: any) {
      setErr(error.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!refreshMs) return;
    timer.current = window.setInterval(refresh, refreshMs);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [refresh, refreshMs]);

  return { data, err, loading, refresh, updatedAt };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
export const fmtNum = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
export const fmtPct = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${Number(value).toFixed(value % 1 ? 1 : 0)}%`);
export const fmtMs = (value: number | null | undefined) => (value === null || value === undefined ? "—" : value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`);
export function fmtBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value; let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}
export const fmtDate = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "—");
export const toneFor = (value: number | null | undefined, good: number, warn: number, invert = false): "green" | "yellow" | "red" | "" => {
  if (value === null || value === undefined) return "";
  const v = invert ? -value : value;
  return v >= (invert ? -good : good) ? "green" : v >= (invert ? -warn : warn) ? "yellow" : "red";
};

// ---------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------
export function Section({ title, subtitle, action, children, className = "" }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <div className={`card dash-section ${className}`}>
    <div className="card-head"><div><h3>{title}</h3>{subtitle && <span className="faint">{subtitle}</span>}</div>{action}</div>
    {children}
  </div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export type Comparison = { value: number; previous: number; delta: number; delta_pct: number | null };

export function Delta({ metric, invert = false }: { metric: Comparison; invert?: boolean }) {
  if (!metric) return null;
  const direction = metric.delta > 0 ? "up" : metric.delta < 0 ? "down" : "flat";
  const good = direction === "flat" ? "" : (direction === "up") !== invert ? "good" : "bad";
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "•";
  return <span className={`delta ${direction} ${good}`} title={`Previous period: ${metric.previous}`}>
    {arrow} {Math.abs(metric.delta)}{metric.delta_pct !== null && metric.delta_pct !== undefined ? ` (${metric.delta_pct > 0 ? "+" : ""}${metric.delta_pct.toFixed(0)}%)` : ""}
  </span>;
}

export function Metric({ label, value, hint, delta, invert, tone, onClick }: { label: string; value: ReactNode; hint?: ReactNode; delta?: Comparison; invert?: boolean; tone?: string; onClick?: () => void }) {
  const Tag: any = onClick ? "button" : "div";
  return <Tag className={`metric-card ${tone || ""} ${onClick ? "clickable" : ""}`} onClick={onClick}>
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}</div>
    <div className="metric-foot">{delta ? <Delta metric={delta} invert={invert} /> : null}{hint && <span className="faint">{hint}</span>}</div>
  </Tag>;
}

export function SeverityBadge({ level }: { level: string }) {
  const map: Record<string, string> = { critical: "red", high: "red", medium: "yellow", low: "blue", info: "", unrated: "" };
  return <span className={`badge ${map[level] || ""}`}>{level}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    connected: "green", healthy: "green", completed: "green", success: "green", active: "green",
    untested: "yellow", never_run: "yellow", stale: "yellow", pending: "yellow", evaluation: "yellow",
    error: "red", failing: "red", failed: "red", disabled: "", deprecated: "", running: "blue",
  };
  return <span className={`badge ${map[status] || ""}`}>{status.replace("_", " ")}</span>;
}

// ---------------------------------------------------------------------------
// Lightweight SVG charts (no runtime dependency)
// ---------------------------------------------------------------------------
type Point = { date?: string; hour?: string; count: number; errors?: number };

export function Sparkline({ points, height = 42, color = "var(--accent)", label }: { points: Point[]; height?: number; color?: string; label?: string }) {
  const width = 200;
  const max = Math.max(1, ...points.map(p => p.count));
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 4 - (p.count / max) * (height - 8)).toFixed(1)}`).join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  const total = points.reduce((sum, p) => sum + p.count, 0);
  return <div className="sparkline">
    {label && <div className="row"><span className="dim">{label}</span><span className="spacer" /><b>{fmtNum(total)}</b></div>}
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label ? `${label} trend` : "trend"}>
      <path d={area} fill={color} opacity=".12" />
      <path d={path} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
    {points.length > 0 && <div className="row faint sparkline-axis"><span>{(points[0].date || points[0].hour || "").slice(5, 10)}</span><span className="spacer" /><span>{(points[points.length - 1].date || points[points.length - 1].hour || "").slice(5, 10)}</span></div>}
  </div>;
}

export function BarList({ data, max: maxOverride, format = fmtNum, color, limit = 8 }: { data: Record<string, number> | { name: string; count: number }[]; max?: number; format?: (v: number) => string; color?: string; limit?: number }) {
  const rows = (Array.isArray(data) ? data.map(d => [d.name, d.count] as [string, number]) : Object.entries(data || {}))
    .sort((a, b) => b[1] - a[1]).slice(0, limit);
  if (rows.length === 0) return <Empty>No data.</Empty>;
  const max = maxOverride || Math.max(1, ...rows.map(r => r[1]));
  return <div className="bar-list">{rows.map(([name, value]) => <div className="bar-row" key={name}>
    <span className="bar-name" title={name}>{name || "unknown"}</span>
    <span className="bar-track"><span style={{ width: `${Math.max(2, value / max * 100)}%`, background: color }} /></span>
    <span className="bar-value mono">{format(value)}</span>
  </div>)}</div>;
}

export function Gauge({ score, grade, size = 150 }: { score: number; grade: string; size?: number }) {
  const radius = 54; const stroke = 11;
  const circumference = Math.PI * radius; // half circle
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  const color = score >= 75 ? "var(--green)" : score >= 50 ? "var(--yellow)" : "var(--red)";
  return <div className="gauge" style={{ width: size }}>
    <svg viewBox="0 0 140 80" role="img" aria-label={`Posture score ${score} of 100`}>
      <path d="M 16 72 A 54 54 0 0 1 124 72" fill="none" stroke="var(--bg-elev-2)" strokeWidth={stroke} strokeLinecap="round" />
      <path d="M 16 72 A 54 54 0 0 1 124 72" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset} />
      <text x="70" y="62" textAnchor="middle" className="gauge-score">{score}</text>
      <text x="70" y="77" textAnchor="middle" className="gauge-grade">grade {grade}</text>
    </svg>
  </div>;
}

export function Donut({ segments, size = 110 }: { segments: { label: string; value: number; color: string }[]; size?: number }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = 15.9155; // circumference = 100
  let cumulative = 0;
  return <div className="donut" style={{ width: size, height: size }}>
    <svg viewBox="0 0 42 42" role="img" aria-label="distribution">
      <circle cx="21" cy="21" r={radius} fill="none" stroke="var(--bg-elev-2)" strokeWidth="5" />
      {total > 0 && segments.map(segment => {
        const share = segment.value / total * 100;
        const el = <circle key={segment.label} cx="21" cy="21" r={radius} fill="none" stroke={segment.color} strokeWidth="5"
          strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-cumulative + 25} />;
        cumulative += share;
        return el;
      })}
      <text x="21" y="23.5" textAnchor="middle" className="donut-total">{total}</text>
    </svg>
  </div>;
}

export function Legend({ items }: { items: { label: string; value: number; color: string }[] }) {
  return <div className="legend">{items.map(item => <span key={item.label}><i style={{ background: item.color }} />{item.label} <b>{item.value}</b></span>)}</div>;
}

export function HourlyBars({ points, height = 70 }: { points: Point[]; height?: number }) {
  const width = 600;
  const max = Math.max(1, ...points.map(p => p.count));
  const bar = width / Math.max(1, points.length);
  return <svg className="hourly-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="hourly request volume">
    {points.map((p, i) => {
      const h = p.count / max * (height - 4);
      const eh = (p.errors || 0) / max * (height - 4);
      return <g key={i}>
        <rect x={i * bar + 0.5} y={height - h} width={Math.max(0.5, bar - 1)} height={h} fill="var(--accent)" opacity=".55" />
        {eh > 0 && <rect x={i * bar + 0.5} y={height - eh} width={Math.max(0.5, bar - 1)} height={eh} fill="var(--red)" />}
      </g>;
    })}
  </svg>;
}

export function TacticGrid({ tactics }: { tactics: { tactic: string; count: number; sensors: string[] }[] }) {
  return <div className="tactic-grid">{tactics.map(item => <div key={item.tactic} className={`tactic ${item.count ? "covered" : "gap"}`} title={item.sensors.join(", ") || "No active sensor covers this tactic"}>
    <span>{item.tactic}</span><b>{item.count}</b>
  </div>)}</div>;
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return <div className="kv">{rows.map(([key, value]) => <div key={key}><span className="dim">{key}</span><b>{value}</b></div>)}</div>;
}
