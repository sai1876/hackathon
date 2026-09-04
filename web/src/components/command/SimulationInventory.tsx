"use client";
import {useEffect,useState} from "react";
import {request} from "@/lib/api";
type Inventory={status:string;note:string;road_coverage?:number;kinds?:Record<string,number>;runs?:{name:string;status:string}[]};
export default function SimulationInventory(){
 const [data,setData]=useState<Inventory|null>(null);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;const refresh=async()=>{try{const value=await request<Inventory>("/command/simulation-inventory",{},30000);if(alive)setData(value);}catch{if(alive)setData({status:"UNAVAILABLE",note:"Simulation database unavailable"});}if(alive)timer=setTimeout(refresh,60000);};void refresh();return()=>{alive=false;clearTimeout(timer);};},[]);
 return <details className="city-database" open><summary>Shared simulation dataset · new Supabase project</summary><p>{data?.note??"Reading the simulation database…"}</p><p>{data?.runs?.map(run=>`${run.name}: ${run.status}`).join(" · ")}</p><div className="main-table"><table><thead><tr><th>Simulation records</th><th>Count</th><th>Source</th></tr></thead><tbody>{!!data?.road_coverage&&<tr><td>ROAD TRAFFIC COVERAGE</td><td>{data.road_coverage.toLocaleString()}</td><td>Simulated states linked to reference roads</td></tr>}{Object.entries(data?.kinds??{}).map(([kind,count])=><tr key={kind}><td>{kind.replaceAll("_"," ")}</td><td>{count.toLocaleString()}</td><td>Persisted simulation seed</td></tr>)}</tbody></table></div></details>;
}
