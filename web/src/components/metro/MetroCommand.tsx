"use client";

import Link from "next/link";

import {useMetro} from "./MetroMap";
import MetroSchematic from "./MetroSchematic";
import ScenarioControls from "@/components/command/ScenarioControls";
import "@/components/command/main-command.css";
import MetroOperations from "./MetroOperations";
import MetroServiceDays from "./MetroServiceDays";
import "./metro.css";
 export function MetroView({controls=false}:{controls?:boolean}){
  const {data,error}=useMetro();
  return <section className="metro-view"><header><div><span className="metro-badge">DATABASE OPERATING MODEL · SIMULATED POSITIONS</span><h2>Hyderabad Metro · network operations</h2><p>3 lines · {data?.station_count??57} stations · {data?.trip_count??"—"} scheduled trips in feed</p></div><strong>{data?.state.service_date ?? "—"} · {data?.clock??"—"} IST<br/>{error ? "STALE" : data?.state.running ? "RUNNING" : "PAUSED"} · {data?.state.speed??1}×</strong></header>{error&&<p role="alert" className="metro-error">{error}</p>}

 <ScenarioControls polygon={[]} drawing={false} onDraw={()=>{}} onClear={()=>{}} readOnly/><MetroOperations setup={controls}/><MetroServiceDays/><MetroSchematic data={data}/>
 <Link href="/command">All trains follow the shared clock in Central Scenario Controls →</Link>

 <p className="metro-note">{data?.note??"Loading timetable state from Supabase…"}</p>
 {!controls&&<div className="metro-train-cards">{data?.trains.map(train=><article key={train.id}><strong>{train.line_id} · {train.id}</strong><span>{train.status}</span><p>{train.from_station} → {train.to_station}</p><small>{train.seconds_to_next}s estimated time to next transition · vehicle {train.block}</small></article>)}</div>}
 </section>;
}
export default function MetroCommand(){return <main className="metro-page"><nav><Link href="/command">AEGISGRID / Command Center</Link><Link href="/traffic">Traffic</Link><Link href="/ambulance">Ambulance</Link><Link href="/electric-command">Electric Command</Link><Link href="/metro-pilot">Metro Pilot</Link></nav><h1>Metro Command</h1><MetroView/></main>;}
