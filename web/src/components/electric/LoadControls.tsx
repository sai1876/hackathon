"use client";
import { useState } from "react";

export type LoadTelemetry = { demand_kw: number; supplied_kw: number; capacity_kw: number; utilization_percent: number; demand_percent: number; load_percent: number; overload_seconds: number; status: string };

export default function LoadControls({ id, value, busy, running, onLoad, onReset }: { id: string; value: LoadTelemetry; busy: boolean; running: boolean; onLoad: (percent: number) => void; onReset: () => void }) {
  const [draft, setDraft] = useState<number | null>(null);
  const percent = draft ?? value.load_percent;
  const apply = () => { if (draft !== null && draft !== value.load_percent) onLoad(draft); setDraft(null); };
  return <section className="electric-load-controls" aria-label="Asset load controls">
    <h3>Adjust demand · {id}</h3>
    <p>Increase or reduce demand on this asset and its connected loads.</p>
    <label>Demand multiplier: {percent}% of baseline<input aria-label="Demand multiplier" type="range" min="0" max="400" step="5" value={percent} disabled={busy} onChange={e => setDraft(Number(e.target.value))} onPointerUp={apply} onKeyUp={apply} onBlur={apply} /></label>
    <div className="electric-load-presets">{[50,100,150,200,300].map(n => <button key={n} disabled={busy} onClick={() => { setDraft(null); onLoad(n); }}>{n}% load</button>)}</div>
    <p className="muted">Release the slider to apply. Parent and child multipliers combine. {running ? "The backend clock is running." : "Clock paused — press Run to observe overload protection over time."}</p>
    <dl className="electric-load-values"><div><dt>Demand</dt><dd>{value.demand_kw.toLocaleString()} kW</dd></div><div><dt>Supplied</dt><dd>{value.supplied_kw.toLocaleString()} kW</dd></div><div><dt>Modeled limit</dt><dd>{value.capacity_kw.toLocaleString()} kW</dd></div><div><dt>Loading</dt><dd>{value.utilization_percent}%</dd></div></dl>
    <progress max="200" value={value.utilization_percent} aria-label="Asset loading" />
    <p role="status"><strong>{value.status.replaceAll("_", " ")}</strong>{value.status === "OVERLOADED" ? ` · ${value.overload_seconds}/10 seconds above limit before protection trips` : ""}</p>
    {value.status === "TRIPPED" && <><p>Protection disconnected this asset. Reduce demand below its limit, then reset.</p><button disabled={busy || value.demand_percent > 100} onClick={onReset}>Reset protection</button></>}
    <small>Limits are generated as 135% of baseline demand. This is a simplified overload model, not measured equipment capacity or a power-flow calculation.</small>
  </section>;
}
