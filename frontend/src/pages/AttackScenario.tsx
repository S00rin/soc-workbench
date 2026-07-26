import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Loading, useToast } from "../lib";

type Scenario = {
  id: string; title: string; summary: string; story: string; platform: string;
  difficulty: string; duration_minutes: number; risk: string;
  mitre: { id: string; name: string; tactic: string }[];
  prerequisites: string[]; objectives: string[];
  simulation_steps: { title: string; detail: string }[];
  telemetry: string[]; log_sources: { source: string; event_id: string; purpose: string }[];
  spl: string; triage: string[]; expected: string; false_positives: string[];
};
type Run = {
  run_id: string; status: string; mode: string; event_count: number;
  started_at: string; safety_notice: string; events: Record<string, unknown>[];
};

const TABS = ["Overview", "Simulation", "Telemetry", "Splunk detection", "Triage"] as const;

export default function AttackScenario() {
  const { scenarioId } = useParams();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [run, setRun] = useState<Run | null>(null);
  const [running, setRunning] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    setScenario(null);
    api.get(`/api/attack-lab/scenarios/${scenarioId}`)
      .then(setScenario)
      .catch((e) => { toast(e.message, "error"); navigate("/attack-lab"); });
  }, [scenarioId]);

  async function simulate() {
    setRunning(true);
    try {
      const result = await api.post(`/api/attack-lab/scenarios/${scenarioId}/simulate`);
      setRun(result);
      setTab("Telemetry");
      toast(`${result.event_count} synthetic events generated`, "ok");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setRunning(false);
    }
  }

  function copy(text: string, label: string) {
    navigator.clipboard.writeText(text).then(() => toast(`${label} copied`, "ok"));
  }

  if (!scenario) return <Loading label="Loading scenario profile…" />;

  return (
    <div className="attack-profile">
      <Link to="/attack-lab" className="profile-back">← Attack Simulation Lab</Link>
      <section className="profile-hero">
        <div>
          <div className="row mb">
            <span className={`badge ${scenario.difficulty === "beginner" ? "green" : "yellow"}`}>{scenario.difficulty}</span>
            <span className="badge">{scenario.platform}</span>
            <span className="badge">{scenario.duration_minutes} min</span>
            <span className="badge red">risk: {scenario.risk}</span>
          </div>
          <h1>{scenario.title}</h1>
          <p>{scenario.summary}</p>
          <div>{scenario.mitre.map((m) => <span className="chip" key={m.id}>{m.id} · {m.name} / {m.tactic}</span>)}</div>
        </div>
        <button className="btn-primary profile-run" disabled={running} onClick={simulate}>
          {running ? <><span className="spin" /> Generating telemetry…</> : "▶ Run safe simulation"}
        </button>
      </section>

      <div className="tabs profile-tabs">
        {TABS.map((name) => <div key={name} className={`tab ${tab === name ? "active" : ""}`} onClick={() => setTab(name)}>{name}</div>)}
      </div>

      {tab === "Overview" && (
        <div className="grid cols-2">
          <section className="card"><h3>Scenario brief</h3><p className="dim">{scenario.story}</p></section>
          <section className="card"><h3>Learning objectives</h3><CheckList items={scenario.objectives} /></section>
          <section className="card"><h3>Prerequisites</h3><CheckList items={scenario.prerequisites} /></section>
          <section className="card"><h3>Telemetry coverage</h3><div>{scenario.telemetry.map((x) => <span className="chip" key={x}>{x}</span>)}</div></section>
        </div>
      )}

      {tab === "Simulation" && (
        <section className="card">
          <div className="safety-callout"><strong>Safe mode</strong><span>This lab generates representative events only. It never executes the described behavior.</span></div>
          <div className="simulation-timeline">
            {scenario.simulation_steps.map((step, i) => (
              <div className="timeline-step" key={step.title}>
                <span>{i + 1}</span><div><h3>{step.title}</h3><p>{step.detail}</p></div>
              </div>
            ))}
          </div>
          <button className="btn-primary" disabled={running} onClick={simulate}>Generate lab telemetry</button>
        </section>
      )}

      {tab === "Telemetry" && (
        <>
          <section className="card mb">
            <div className="card-head"><h3>Required log sources</h3></div>
            <table className="data"><thead><tr><th>Source</th><th>Event / type</th><th>Detection value</th></tr></thead>
              <tbody>{scenario.log_sources.map((log) => <tr key={`${log.source}-${log.event_id}`}><td>{log.source}</td><td className="mono">{log.event_id}</td><td>{log.purpose}</td></tr>)}</tbody>
            </table>
          </section>
          {!run ? (
            <section className="card empty">Run the safe simulation to generate sample events for this class.</section>
          ) : (
            <section className="card">
              <div className="card-head">
                <div><h3>Generated evidence</h3><span className="dim mono">run {run.run_id}</span></div>
                <div className="row"><span className="badge green">{run.status}</span><button className="btn-sm" onClick={() => copy(run.events.map((e) => JSON.stringify(e)).join("\n"), "NDJSON")}>Copy NDJSON</button></div>
              </div>
              <div className="safety-callout"><strong>{run.event_count} events</strong><span>{run.safety_notice}</span></div>
              <pre className="event-console">{run.events.map((event) => JSON.stringify(event, null, 2)).join("\n")}</pre>
            </section>
          )}
        </>
      )}

      {tab === "Splunk detection" && (
        <div className="grid cols-2 detection-layout">
          <section className="card">
            <div className="card-head"><h3>Detection SPL</h3><button className="btn-sm" onClick={() => copy(scenario.spl, "SPL")}>Copy</button></div>
            <pre className="spl-code">{scenario.spl}</pre>
            <div className="row mt">
              <Link className="btn btn-primary btn-sm" to={`/splunk?spl=${encodeURIComponent(scenario.spl)}`}>Open in Splunk search</Link>
            </div>
          </section>
          <section className="card">
            <h3>Expected result</h3><p className="dim">{scenario.expected}</p>
            <hr className="hr" />
            <h3>Likely false positives</h3><CheckList items={scenario.false_positives} />
          </section>
        </div>
      )}

      {tab === "Triage" && (
        <section className="card">
          <h3>Analyst investigation path</h3>
          <div className="triage-grid">{scenario.triage.map((item, i) => <div className="triage-step" key={item}><span>{i + 1}</span><p>{item}</p></div>)}</div>
        </section>
      )}
    </div>
  );
}

function CheckList({ items }: { items: string[] }) {
  return <ul className="check-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}
