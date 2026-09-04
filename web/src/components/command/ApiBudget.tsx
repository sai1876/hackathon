"use client";
import { useEffect, useState } from "react";
import { request } from "@/lib/api";
type Budget={apis:{sku:string;used:number|null;hard_limit:number|null;remaining:number|null;status:string}[];last_google_fetch:string|null;google_enabled:boolean};
export default function ApiBudget(){
 const [data,setData]=useState<Budget|null>(null),[error,setError]=useState("");
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;const refresh=async()=>{try{const result=await request<Budget>("/system/api-usage",{},30000);if(alive){setData(result);setError("");}}catch{if(alive)setError("Budget store unavailable — Google must stay stopped");}if(alive)timer=setTimeout(refresh,30000);};void refresh();return()=>{alive=false;clearTimeout(timer);};},[]);
 return <section className="city-panel"><h2>GOOGLE API BUDGET</h2><div className="city-inventory">{data?.apis.map(a=><div key={a.sku}><span>{a.sku.replace("GOOGLE_","")}<small style={{display:"block"}}>{a.status} · {a.remaining??"?"} remaining</small></span><strong style={{fontSize:13}}>{a.used??"?"} / {a.hard_limit??"?"}</strong></div>)}</div><p className="city-note">Billing guard: persistent, fail closed<br/>Aegis routing: available<br/>{data?.google_enabled?"Manual Google reference enabled":"Route comparison disabled · Weather and other services have separate controls"}<br/>Last attempt: {data?.last_google_fetch?new Date(data.last_google_fetch).toLocaleString():"None recorded"}<br/>Application caps are not guaranteed free allowances.</p>{error&&<p role="alert">{error}</p>}</section>;
}
