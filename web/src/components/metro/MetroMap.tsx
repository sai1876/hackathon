"use client";
import {useEffect,useRef,useState} from "react";
import * as maplibregl from "maplibre-gl";
import type {FeatureCollection} from "geojson";
import {request} from "@/lib/api";
import {useResilientPolling} from "@/lib/useResilientPolling";
import "./metro.css";
export type Train={motion?:string;source_trip_id?:string;speed_mps?:number;segment_m?:number;geometry?:number[][];dwell_until?:number;passengers?:number;capacity?:number;hold_until?:number;release?:boolean;crew_ready?:boolean;schedule:{station:string;arrival:number;departure:number}[];id:string;block:string;line_id:string;status:string;from_station:string;to_station:string;position:[number,number];progress:number;seconds_to_next:number;headsign:string};
export type Turnback={id:string;block:string;line_id:string;station_id:string;station:string;started_at_seconds:number;ends_at_seconds:number;duration_seconds:number;remaining_seconds:number;phase?:string;crew_ready?:boolean;next_departure_seconds:number|null;next_trip_id:string|null;next_destination:string};
export type MetroSnapshot={turnbacks?:Turnback[];turnback_quality?:{overlapping_trip_pairs:number;note:string};trains:Train[];state:{running:boolean;speed:number;sim_seconds:number;service_date:string};clock:string;note:string;source:string;station_count:number;trip_count:number;version:number};
type Network={tracks:FeatureCollection;stations:{id:string;name:string;lon:number;lat:number}[];routes:{route_id:string;route_color:string}[]};
export function useMetro(){
 return useResilientPolling<MetroSnapshot>({
  url: "/metro/snapshot",
  normalIntervalMs: 3000,
  timeoutMs: 15000,
  defaultErrorMessage: "Metro connection unavailable — displayed positions are stale"
 });
}

function legPosition(train:Train, elapsed:number):[number,number]{
 const points=train.geometry;
 if(train.status!=='IN_TRANSIT'||!points||points.length<2)return train.position;
 const lengths=points.slice(1).map((p,i)=>Math.hypot((p[0]-points[i][0])*.955,p[1]-points[i][1]));
 const total=lengths.reduce((a,b)=>a+b,0);
 let distance=Math.min(.999,train.progress+(train.speed_mps??0)*elapsed/Math.max(1,train.segment_m??1))*total;
 for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]){const f=distance/Math.max(1e-12,lengths[i]);return [points[i][0]+(points[i+1][0]-points[i][0])*f,points[i][1]+(points[i+1][1]-points[i][1])*f];}distance-=lengths[i];}
 return train.position;
}
export function MetroLayer({map}:{map:maplibregl.Map|null}){
 const {data,error}=useMetro();const [network,setNetwork]=useState<Network|null>(null),[networkError,setNetworkError]=useState("");const [visible,setVisible]=useState(true);
 const markers=useRef(new Map<string,maplibregl.Marker>());
 useEffect(()=>{let alive=true;request<Network>("/metro/network",{},30000).then(value=>{if(alive)setNetwork(value);}).catch(()=>{if(alive)setNetworkError("Metro track source unavailable");});return()=>{alive=false;};},[]);
 useEffect(()=>{
  if(!map||!network)return;
  map.addSource("metro-tracks",{type:"geojson",data:network.tracks});map.addLayer({id:"metro-tracks",type:"line",source:"metro-tracks",paint:{"line-color":["get","color"],"line-width":["interpolate",["linear"],["zoom"],10,2,15,5],"line-opacity":0.85}});
  const stations=network.stations.map(station=>{const el=document.createElement("button");el.className="metro-station-marker";el.setAttribute("aria-label",station.name+" metro station");el.title=station.name;const text=document.createElement("p");text.textContent=station.name+" · GTFS station location";const marker=new maplibregl.Marker({element:el}).setLngLat([station.lon,station.lat]).setPopup(new maplibregl.Popup({offset:10}).setDOMContent(text)).addTo(map);el.onclick=event=>{event.stopPropagation();marker.togglePopup();};return marker;});
  return()=>{stations.forEach(s=>s.remove());try{if(map.getLayer("metro-tracks"))map.removeLayer("metro-tracks");if(map.getSource("metro-tracks"))map.removeSource("metro-tracks");}catch{}};
 },[map,network]);
 useEffect(()=>{
  if(!map)return;
  if(map.getLayer("metro-tracks"))map.setLayoutProperty("metro-tracks","visibility",visible?"visible":"none");
  map.getContainer().querySelectorAll<HTMLElement>(".metro-station-marker").forEach(el=>{el.style.display=visible?"":"none";});
  const active=new Set(visible?(data?.trains??[]).map(t=>t.id):[]);
  for(const [id,marker] of markers.current)if(!active.has(id)){marker.remove();markers.current.delete(id);}
  if(!visible)return;
  for(const train of data?.trains??[]){
   let marker=markers.current.get(train.id);
   if(!marker){const el=document.createElement("button");el.className="metro-train-marker";el.innerHTML='<svg viewBox="0 0 22 28" width="20" height="26" aria-hidden="true"><rect x="2" y="1" width="18" height="24" rx="5" fill="#eefaff" stroke="currentColor" stroke-width="2"/><rect x="5" y="5" width="12" height="9" rx="2" fill="#183744"/><circle cx="7" cy="20" r="2" fill="#183744"/><circle cx="15" cy="20" r="2" fill="#183744"/></svg>';el.style.color='#'+(network?.routes.find(r=>r.route_id===train.line_id)?.route_color??'ffffff');marker=new maplibregl.Marker({element:el}).setLngLat(train.position).setPopup(new maplibregl.Popup({offset:20})).addTo(map);const current=marker;el.onclick=event=>{event.stopPropagation();current.togglePopup();};markers.current.set(train.id,marker);}
   marker.setLngLat(train.position);const el=marker.getElement();el.style.color="#"+(network?.routes.find(r=>r.route_id===train.line_id)?.route_color??"ffffff");el.setAttribute("aria-label",train.id+" simulated train");el.dataset.trainId=train.id;el.dataset.lon=String(train.position[0]);el.dataset.lat=String(train.position[1]);el.title=`${train.line_id} · ${train.status} · ${train.to_station}`;
   const content=document.createElement("div");content.style.color='#102632';content.textContent=`${train.id} · ${train.status}. ${train.from_station} → ${train.to_station}. Shared operating position; simulated, not live GPS.`;marker.getPopup().setDOMContent(content);
  }
 },[map,data,visible,network]);
 useEffect(()=>{
  if(!visible||!data)return;
  let frame=0;const received=performance.now();
  const paint=(now:number)=>{const elapsed=data.state.running?Math.min(2,(now-received)/1000*data.state.speed):0;
   for(const train of data.trains){const marker=markers.current.get(train.id);if(marker&&train.motion)marker.setLngLat(legPosition(train,elapsed));}
   frame=requestAnimationFrame(paint);
  };frame=requestAnimationFrame(paint);return()=>cancelAnimationFrame(frame);
 },[data,visible]);
 useEffect(()=>{const current=markers.current;return()=>{current.forEach(m=>m.remove());current.clear();};},[]);
 return <div className="metro-overlay-control"><button aria-pressed={visible} onClick={()=>setVisible(!visible)}>Metro routes & trains · {visible?"ON":"OFF"}</button><span>{data?.trains.length??"—"} operating trains · {data?.clock??"—"} IST · {error?"STALE":data?.state.running?"PLAYBACK":"PAUSED"} · not live GPS</span>{(error||networkError)&&<p role="alert">{error||networkError}</p>}</div>;
}
export default function MetroMap(){
 const container=useRef<HTMLDivElement>(null);const [map,setMap]=useState<maplibregl.Map|null>(null),[error,setError]=useState("");
 useEffect(()=>{if(!container.current)return;maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");let instance:maplibregl.Map;try{instance=new maplibregl.Map({container:container.current,center:[78.46,17.42],zoom:11.2,maxBounds:[[78.1,17.1],[78.8,17.8]],style:{version:8,sources:{osm:{type:"raster",tiles:["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],tileSize:256,attribution:"© OpenStreetMap contributors"}},layers:[{id:"base",type:"raster",source:"osm",paint:{"raster-saturation": -0.25,"raster-brightness-max": 1}}]}});instance.on("load",()=>setMap(instance));instance.addControl(new maplibregl.NavigationControl());}catch{queueMicrotask(()=>setError("Map unavailable; train list remains available"));return;}const observer=new ResizeObserver(()=>instance.resize());observer.observe(container.current);return()=>{observer.disconnect();instance.remove();};},[]);
 return <><div className="metro-geographic-map" ref={container} aria-label="Hyderabad metro geographic map"/>{error&&<p role="alert">{error}</p>}<MetroLayer map={map}/></>;
}
