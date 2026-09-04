import type { Incident, MapMode } from "@/types/aegis";
export default function IncidentPanel({ incidents, mode, busy, error, onInject, onResolve, onRefresh, onSelect }: { incidents: Incident[]; mode: MapMode; busy: boolean; error: string; onInject: () => void; onResolve: (id: string) => void; onRefresh: () => void; onSelect: (id: string) => void }) {
  return <section className="panel incident-panel"><div className="section-heading"><span className="eyebrow">02 / INCIDENT CONTROL</span><span className="incident-count">{incidents.length.toString().padStart(2, "0")}</span></div>
    <div className="incident-title"><h2>Active incidents</h2><span className="synthetic">BACKEND RUNTIME</span></div>
    <p className="muted">Inject a synthetic blockage. The routing engine recalculates the current path.</p>
    <button className={`incident-button ${mode === "incident" ? "armed" : ""}`} disabled={busy} onClick={onInject}>{busy ? "Updating incidents…" : mode === "incident" ? "Cancel injection · click map to place" : "+ Inject Incident"}</button>
    {error && <p className="error-note" role="alert">{error} <button onClick={onRefresh} disabled={busy}>Refresh incidents</button></p>}
    <div className="incident-list">{incidents.length === 0 ? <p className="quiet-state">No active incidents in this runtime.</p> : incidents.map(item => <article className="incident-card" key={item.id}><div className="section-heading"><strong>Road blockage</strong><span className="synthetic">{item.provenance || "UNKNOWN"}</span></div><p>{item.lat.toFixed(5)}, {item.lon.toFixed(5)}</p><small>{item.affected_edges.length ? `${item.affected_edges.length} directed edge affected` : "Not matched in the current route graph"}</small><div className="incident-card-bottom"><span>SEVERITY {item.severity}/5</span><button disabled={busy} onClick={() => onResolve(item.id)}>Resolve ↗</button></div></article>)}</div>
    {incidents.map(i => <button className="inspect-incident" key={i.id} onClick={() => onSelect(i.id)}>Inspect {i.incident_type.replaceAll("_", " ").toLowerCase()} ↗</button>)}
    <p className="footnote">Backend runtime only · SYNTHETIC injection closes a directed edge within 150 m. Reset demo does not resolve incidents.</p>
  </section>;
}
