import type { Incident } from "@/types/aegis";
import type { Alert, FloodState, OperationalMetric, PowerState, TrafficState } from "@/types/operations";
import { agents } from "@/lib/operations";
import Panel, { Badge } from "./Panel";

export function CityOverview({ traffic, flood, power, incidents }: { traffic: TrafficState; flood: FloodState; power: PowerState; incidents: Incident[] }) {
  const metrics: OperationalMetric[] = [
    { label: "OVERALL RISK", value: flood.risk > 60 ? "HIGH" : "MODERATE", level: flood.risk > 60 ? "HIGH" : "MODERATE", provenance: "SYNTHETIC" },
    { label: "TRAFFIC LOAD", value: traffic.load, unit: "%", level: "MODERATE", provenance: traffic.provenance },
    { label: "WATER RISK", value: flood.risk, unit: "%", level: "HIGH", provenance: flood.provenance },
    { label: "POWER LOAD", value: power.load, unit: "%", level: "MODERATE", provenance: power.provenance },
  ];
  return <Panel title="City overview" provenance="SYNTHETIC"><div className="city-metrics">{metrics.map(m => <div key={m.label} className={`metric ${m.level.toLowerCase()}`}><span>{m.label}</span><strong>{m.value}<small>{m.unit}</small></strong></div>)}</div><div className="runtime-count"><span>Backend runtime incidents</span><strong>{incidents.length.toString().padStart(2,"0")}</strong></div></Panel>;
}
export function WeatherPanel({ flood }: { flood: FloodState }) {
  return <Panel title="Weather / environment" provenance={flood.provenance}><div className="weather-summary"><span className="weather-symbol">☂</span><div><strong>{flood.rainfall}<small> mm/hr</small></strong><span>{flood.rainfall ? "Heavy rain exercise" : "Dry weather exercise"}</span></div><div className="weather-forecast"><small>NEXT 2 HRS</small><b>{flood.forecast} mm</b></div></div><svg className="rain-chart" viewBox="0 0 280 83" role="img" aria-label="Synthetic rainfall trend, not observed measurements"><path d="M0 12H280M0 37H280M0 62H280" stroke="#223b49" strokeWidth=".6" />{flood.trend.map((v,i)=><rect key={i} x={i*11.6} y={70-v*1.4} width="7.5" height={v*1.4+1} fill={i>18 ? "#37657a" : "#259ace"} />)}<path d={`M0,${70-flood.trend[0]*1.4} ${flood.trend.map((v,i)=>`L${i*11.6+3},${70-v*1.4}`).join(" ")}`} fill="none" stroke="#64d7ff" strokeWidth="1" /></svg><div className="chart-axis"><span>−60 min</span><span>Exercise trend</span><span>Now</span></div></Panel>;
}
export function LiveAlerts({ alerts, incidents, onSelect }: { alerts: Alert[]; incidents: Incident[]; onSelect: (id: string) => void }) {
  return <Panel title="Live alerts / exercise feed"><div className="alert-feed">{incidents.map(i=><button className="alert-row" key={i.id} onClick={()=>onSelect(i.id)}><span className="alert-symbol critical">!</span><span><strong>{i.incident_type.replaceAll("_"," ")}</strong><small>{i.affected_edges.length} matched edges · BACKEND / {i.provenance}</small></span><i className="alert-dot high" /></button>)}{alerts.map(a=><div className="alert-row" key={a.id}><span className={`alert-symbol ${a.level.toLowerCase()}`}>{a.symbol}</span><span><strong>{a.title}</strong><small>{a.location}</small><em>SYNTHETIC</em></span><i className={`alert-dot ${a.level.toLowerCase()}`} /></div>)}{!alerts.length && !incidents.length && <p className="ops-muted">No runtime alerts. Normal demo scenario.</p>}</div></Panel>;
}
export function AgentStatusPanel() {
  return <Panel title="AI coordination" provenance="SYNTHETIC"><div className="agent-grid">{agents.map(a=><div className="agent-item" key={a.department}><span>{a.symbol}</span><div><strong>{a.department}</strong><small>{a.state}</small></div></div>)}</div><p className="panel-note">Department templates only · no AI agents connected.</p></Panel>;
}
export function ZoneRisk({ flood }: { flood: FloodState }) {
  return <Panel title="Zone risk summary" provenance="SYNTHETIC"><div className="zone-list">{["North", "East", "West", "South"].map((z,i)=><div key={z}><span className={`zone-dot zone-${i}`} /><strong>{z} sector</strong><span className={i===1 && flood.risk>60 ? "critical" : "warning"}>{i===1 && flood.risk>60 ? "HIGH" : "MODERATE"}</span></div>)}</div><small className="panel-note">Exercise sectors · not official boundaries</small></Panel>;
}
export function TrafficStatus({ state }: { state: TrafficState }) {
  return <Panel title="Traffic status" provenance={state.provenance}><div className="traffic-summary"><div className="traffic-gauge" style={{background:`conic-gradient(#55cb90 0 ${state.normal}%,#e9bd4f ${state.normal}% ${state.normal+state.slow}%,#eb7645 ${state.normal+state.slow}% ${100-state.blocked}%,#bd81ee ${100-state.blocked}% 100%)`}}><div><strong>{state.load}%</strong><small>DEMO LOAD</small></div></div><div className="traffic-key">{[["Normal",state.normal,"normal"],["Slow",state.slow,"warning"],["Congested",state.congested,"degraded"],["Blocked",state.blocked,"special"]].map(([label,value,tone])=><div key={label}><i className={`key-dot ${tone}`} /><span>{label}</span><b>{value}%</b></div>)}</div></div></Panel>;
}
export function PowerStatus({ state }: { state: PowerState }) {
  return <Panel title="Power grid" provenance={state.provenance}><div className="power-total"><span>EXERCISE TRANSFORMERS</span><b>{state.total}</b></div><div className="power-metrics">{[["Normal",state.normal,"normal"],["Overload",state.overloaded,"warning"],["Failed",state.failed,"critical"],["Maint.",state.maintenance,"info"]].map(([label,value,tone])=><div key={label}><span className={String(tone)}>{label}</span><strong>{value}</strong></div>)}</div></Panel>;
}
export { Badge };
