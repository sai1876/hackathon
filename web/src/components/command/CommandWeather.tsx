"use client";
import {useEffect,useState} from "react";
import {request} from "@/lib/api";
type Reading={mode:string;updatedAt?:string;observedAt?:string;reason?:string;lastSuccessfulAt?:string;temperatureC?:number;condition?:string;humidityPct?:number;precipitation?:{probabilityPct?:number;accumulationMm?:number};wind?:{speedKph?:number};interval?:{startTime:string;endTime:string}};
export default function WeatherOverview(){
 const [current,setCurrent]=useState<Reading|null>(null),[hours,setHours]=useState<Reading[]>([]),[error,setError]=useState(false);
 useEffect(()=>{let alive=true,timer:ReturnType<typeof setTimeout>;const refresh=async()=>{
 const results=await Promise.allSettled([request<Reading>("/api/weather/current",{},30000),request<{mode:string;hours?:Reading[]}>("/api/weather/hourly",{},30000)]);
 if(!alive)return;
 if(results[0].status==='fulfilled'){setCurrent(results[0].value);setError(false);}else setError(true);
 setHours(results[1].status==='fulfilled'&&results[1].value.mode==='LIVE'?results[1].value.hours??[]:[]);
 timer=setTimeout(refresh,60000);};void refresh();return()=>{alive=false;clearTimeout(timer);};},[]);
 const live=current?.mode==='LIVE'&&!error;
 const fmt=(n:number|undefined,unit:string)=>n==null?'—':`${n}${unit}`;
 const shown=hours.slice(0,12),max=Math.max(1,...shown.map(h=>h.precipitation?.accumulationMm??0));
 const hour=(time?:string)=>time?new Date(time).toLocaleTimeString('en-IN',{hour:'2-digit',hour12:false,timeZone:'Asia/Kolkata'}):'—';
 const observed=current?.observedAt??current?.updatedAt;
 return <section className="city-panel atlas-panel atlas-weather"><h2>Weather overview <span className="atlas-tag">{live?'GOOGLE':'UNAVAILABLE'}</span></h2><div className="atlas-weather-body">
 {live?<><div className="atlas-weather-reading"><svg viewBox="0 0 64 52" width="54" height="44" aria-hidden="true"><circle cx="42" cy="17" r="12" fill="#d4ae64"/><path d="M15 40C2 40 2 21 15 20C19 3 42 10 42 23C58 21 61 41 47 41Z" fill="#8198b0"/><path d="M17 46h25" stroke="#506780" strokeWidth="2" strokeLinecap="round"/></svg><div><strong>{fmt(current.temperatureC,'°')}<em>C</em></strong><span>{current.condition??'Condition unavailable'}</span></div></div><div className="atlas-weather-stats"><div><small>Humidity</small><strong>{fmt(current.humidityPct,'%')}</strong></div><div><small>Wind</small><strong>{fmt(current.wind?.speedKph,' km/h')}</strong></div><div><small>Rain chance</small><strong>{fmt(current.precipitation?.probabilityPct,'%')}</strong></div></div></>:<p className="atlas-empty">{current?.reason?.replaceAll('_',' ')??'Waiting for weather service'}</p>}
 <div className="atlas-forecast-title"><span>Precipitation forecast</span><small>mm / hour</small></div>{shown.length?<div className="atlas-forecast" aria-label="Hourly rainfall forecast">{shown.map((h,i)=><div key={i} title={`${h.interval?.startTime}: ${fmt(h.precipitation?.accumulationMm,' mm forecast')}`}><div className="atlas-forecast-bar"><i style={{height:h.precipitation?.accumulationMm==null?'0':`${Math.max(1,h.precipitation.accumulationMm/max*100)}%`}}/></div><span>{i%3===0?hour(h.interval?.startTime):''}</span></div>)}</div>:<p className="atlas-forecast-empty">Hourly forecast unavailable</p>}
 <p className="atlas-provenance">{live&&observed?`Observed ${new Date(observed).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Kolkata'})} IST`:'No current observation'} · Google Maps</p>
 </div></section>;
}
