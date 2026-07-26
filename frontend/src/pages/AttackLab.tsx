import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Loading, useToast } from "../lib";

type Scenario = {
  id: string;
  title: string;
  summary: string;
  platform: "windows" | "linux" | "web" | "network";
  difficulty: string;
  duration_minutes: number;
  risk: string;
  mitre: { id: string; name: string; tactic: string }[];
  telemetry: string[];
};

const PLATFORMS = ["all", "windows", "linux", "web", "network"] as const;
const ICONS: Record<string, string> = { windows: "⊞", linux: "⌁", web: "◎", network: "⌘" };

export default function AttackLab() {
  const [items, setItems] = useState<Scenario[] | null>(null);
  const [platform, setPlatform] = useState<(typeof PLATFORMS)[number]>("all");
  const [query, setQuery] = useState("");
  const toast = useToast();

  useEffect(() => {
    api.get("/api/attack-lab/scenarios")
      .then((data) => setItems(data.items))
      .catch((e) => toast(e.message, "error"));
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (items || []).filter((item) => {
      const platformMatch = platform === "all" || item.platform === platform;
      const text = `${item.title} ${item.summary} ${item.mitre.map((m) => `${m.id} ${m.name}`).join(" ")}`.toLowerCase();
      return platformMatch && (!needle || text.includes(needle));
    });
  }, [items, platform, query]);

  if (!items) return <Loading label="Loading attack scenarios…" />;

  const beginner = items.filter((item) => item.difficulty === "beginner").length;
  const techniques = new Set(items.flatMap((item) => item.mitre.map((m) => m.id))).size;

  return (
    <div className="attack-lab">
      <section className="lab-hero mb">
        <div>
          <span className="lab-kicker">DEFENDER TRAINING ENVIRONMENT</span>
          <h1>Attack Simulation Lab</h1>
          <p>Teach the full detection loop: understand adversary behavior, generate safe telemetry, inspect the evidence, and validate the hunt in Splunk.</p>
          <div className="row">
            <span className="badge green">Telemetry-only execution</span>
            <span className="dim">No host commands or network packets are executed</span>
          </div>
        </div>
        <div className="lab-hero-stats">
          <div><strong>{items.length}</strong><span>scenarios</span></div>
          <div><strong>{techniques}</strong><span>ATT&CK techniques</span></div>
          <div><strong>{beginner}</strong><span>beginner labs</span></div>
        </div>
      </section>

      <div className="lab-toolbar mb">
        <div className="pill-toggle">
          {PLATFORMS.map((p) => (
            <button key={p} className={platform === p ? "active" : ""} onClick={() => setPlatform(p)}>
              {p === "all" ? "All platforms" : p[0].toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
        <input
          aria-label="Search scenarios"
          className="lab-search"
          placeholder="Search title, behavior, or ATT&CK ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? <div className="card empty">No matching scenarios.</div> : (
        <div className="lab-grid">
          {filtered.map((item) => (
            <Link className="scenario-card" to={`/attack-lab/${item.id}`} key={item.id}>
              <div className="scenario-card-top">
                <span className={`platform-mark ${item.platform}`}>{ICONS[item.platform]}</span>
                <div className="row">
                  <span className={`badge ${item.difficulty === "beginner" ? "green" : "yellow"}`}>{item.difficulty}</span>
                  <span className="badge">{item.duration_minutes} min</span>
                </div>
              </div>
              <h2>{item.title}</h2>
              <p>{item.summary}</p>
              <div className="scenario-techniques">
                {item.mitre.map((technique) => <span className="chip" key={technique.id}>{technique.id} · {technique.tactic}</span>)}
              </div>
              <div className="scenario-card-foot">
                <span>{item.telemetry.length} telemetry sources</span>
                <span className="open-lab">Open lab →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
