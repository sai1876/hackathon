"use client";
import {useEffect,useState} from "react";
import {request} from "@/lib/api";
type Reading={mode:string;updatedAt?:string;observedAt?:string;reason?:string;lastSuccessfulAt?:string;temperatureC?:number;condition?:string;humidityPct?:number;precipitation?:{probabilityPct?:number;accumulationMm?:number};wind?:{speedKph?:number};interval?:{startTime:string;endTime:string}};
export default function WeatherOverview(){
 const [current,setCurrent]=useState<Reading|null>(null),[hours,setHours]=useState<Reading[]>([]),[error,setError]=useState(false);
 useEffect(()=>{let alive=true,timer:ReturnType<typeof setTimeout>;const refresh=async()=>{
 const results=await Promise.allSettled([request<Reading>("/api/weather/current",{},30000),request<{mode:string;hours?:Reading[]}>("/api/weather/hourly",{},30000)]);
 if(!alive)return;
 if(results[0].status==="fulfilled"){setCurrent(results[0].value);setError(false);}else setError(true);
 setHours(results[1].status==="fulfilled"&&results[1].value.mode==="LIVE"?results[1].value.hours??[]:[]);
 timer=setTimeout(refresh,60000);};void refresh();return()=>{alive=false;clearTimeout(timer);};},[]);
 const live=current?.mode==="LIVE"&&!error;
 const fmt=(n:number|undefined,unit:string)=>n==null?"Unavailable":`${n} ${unit}`;
 const shown=hours.slice(0,12),max=Math.max(1,...shown.map(h=>h.precipitation?.accumulationMm??0));
 return <section className="city-panel"><h2>WEATHER OVERVIEW</h2><div style={{padding:18}}><span className="source-tag">{live?"LIVE · GOOGLE WEATHER":"DATA UNAVAILABLE"}</span>
 {live?<><div style={{fontSize:36,marginTop:18}}>{fmt(current.temperatureC,"°C")}</div><strong>{current.condition??"Condition unavailable"}</strong><div className="city-inventory"><div><span>Humidity</span><strong>{fmt(current.humidityPct,"%")}</strong></div><div><span>Wind</span><strong>{fmt(current.wind?.speedKph,"km/h")}</strong></div><div><span>Precipitation probability</span><strong>{fmt(current.precipitation?.probabilityPct,"%")}</strong></div></div></>:<p>{current?.reason?.replaceAll("_"," ")??"Waiting for the weather service"}</p>}
 <p className="city-note">{live?`Reading: ${new Date(current.observedAt??current.updatedAt??"").toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})} IST`:`Last successful reading: ${current?.lastSuccessfulAt??current?.observedAt??"None"}`}</p>
 <strong>Hourly precipitation forecast</strong>{shown.length?<div style={{display:"flex",alignItems:"end",height:120,gap:4,marginTop:12}}>{shown.map((h,i)=><div key={i} style={{flex:1,textAlign:"center",fontSize:10}} title={`${h.interval?.startTime}: ${fmt(h.precipitation?.accumulationMm,"mm forecast")}`}><div style={{height:80,display:"flex",alignItems:"end"}}><div style={{width:"100%",height:h.precipitation?.accumulationMm==null?0:Math.max(1,h.precipitation.accumulationMm/max*80),background:"#20aadc"}}/></div><span>{h.interval?.startTime?new Date(h.interval.startTime).toLocaleTimeString("en-IN",{hour:"2-digit",hour12:false,timeZone:"Asia/Kolkata"}):"—"}</span></div>)}</div>:<p>Forecast unavailable</p>}
 <p className="city-note">Forecast amounts are predictions. Instantaneous rainfall intensity is not supplied here. Weather data: Google Maps.</p></div></section>;
}
