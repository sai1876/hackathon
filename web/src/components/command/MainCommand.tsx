"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { request } from "@/lib/api";
import "./main-command.css";
import "./command-reference.css";
import { MetroLayer } from "@/components/metro/MetroMap";
import { MetroView } from "@/components/metro/MetroCommand";
import WeatherOverview from "./CommandWeather";
import EmergencyWorkspace from "@/components/emergency/EmergencyWorkspace";
import ApiBudget from "./ApiBudget";
import SimulationInventory from "./SimulationInventory";
import ScenarioControls, {useScenario} from "./ScenarioControls";
import ElectricLayer from "./ElectricLayer";
import TrafficSignals from "@/components/traffic/TrafficSignals";
type Snapshot = { checked_at: string; tables: { table: string; count: number | null; status: string }[]; sources: { source_name: string; provenance: string; provider: string }[]; scenario_ready: boolean; scenario_reason: string };
const title = (s: string) => s.replaceAll("_", " ");

function DatabaseMap({polygon,drawing,onPoint,onFinish,focus,electric=false}:{focus?:number[][];electric?:boolean;polygon:number[][];drawing:boolean;onPoint:(point:number[])=>void;onFinish:()=>void}) {
  const [signalMap, setSignalMap] = useState<maplibregl.Map | null>(null);
  const {data:scenario}=useScenario();
  const refreshRoads=useRef<()=>void>(()=>{});
  const drawingRef=useRef(drawing),pointRef=useRef(onPoint);
  useEffect(()=>{drawingRef.current=drawing;pointRef.current=onPoint;},[drawing,onPoint]);
  useEffect(()=>{if(!signalMap?.getSource("scenario"))return;const features=(scenario?.scenarios??[]).filter(z=>z.status!=="ENDED"&&z.polygon.length>=3).map(z=>({type:"Feature" as const,properties:{kind:z.kind,blocked:z.blocked,slow:z.traffic_factor<.5},geometry:{type:"Polygon" as const,coordinates:[z.polygon]}}));if(polygon.length>=3)features.push({type:"Feature",properties:{kind:"SELECTION",blocked:false,slow:false},geometry:{type:"Polygon",coordinates:[[...polygon,polygon[0]]]}});(signalMap.getSource("scenario") as maplibregl.GeoJSONSource).setData({type:"FeatureCollection",features});},[polygon,scenario,signalMap]);

  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Zoom in to street level to see road coloring · grey = traffic unknown");
  useEffect(() => {
    if (!container.current) return;
    maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
    let map: maplibregl.Map;
    try { map = new maplibregl.Map({ container: container.current, center: [78.4667,17.425], zoom: 11.5, maxBounds: [[78.06,17.06],[78.94,17.84]], style: { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{id:"background",type:"background","paint":{"background-color":"#f7f8fa"}},{ id: "base", type: "raster", source: "osm", paint: { "raster-saturation": -0.25, "raster-brightness-min": 0, "raster-brightness-max": 1, "raster-contrast": 0, "raster-opacity": 1 } }] } }); }
    catch { queueMicrotask(() => setStatus("Map unavailable. Database status remains available below.")); return; }
    let seq = 0, disposed = false;
    const update = async () => {
      const current = ++seq, b = map.getBounds();
      if (map.getZoom() < 15) {
        map.setLayoutProperty("roads", "visibility", "none");
        setStatus("Zoom in to street level to see road coloring · grey = traffic unknown");
        return;
      }
      map.setLayoutProperty("roads", "visibility", "visible");
      setStatus("Loading visible roads…");
      const params = new URLSearchParams({west:String(Math.max(78.05,b.getWest())),south:String(Math.max(17.05,b.getSouth())),east:String(Math.min(78.95,b.getEast())),north:String(Math.min(17.85,b.getNorth()))});
      try {
        const result = await request<FeatureCollection & { metadata: { truncated: boolean } }>(`/command/roads?${params}`, {}, 30000);
        if (disposed || current !== seq) return;
        (map.getSource("roads") as maplibregl.GeoJSONSource).setData(result);
        setStatus(`Scenario roads · red = blocked, orange = congested, yellow = slow, grey = no traffic reading · ${result.features.length.toLocaleString()} visible-area segments${result.metadata.truncated ? " · display limit reached; zoom closer" : ""}`);
      } catch (e) { if (!disposed && current === seq) setStatus(e instanceof Error ? e.message : "Road query failed"); }
    };
    refreshRoads.current=()=>{if(map.getSource("roads"))void update();};
    map.on("click",e=>{if(drawingRef.current)pointRef.current([e.lngLat.lng,e.lngLat.lat]);});
    map.on("style.load", () => { map.addSource("scenario",{type:"geojson",data:{type:"FeatureCollection",features:[]}});map.addLayer({id:"scenario-fill",type:"fill",source:"scenario",paint:{"fill-color":["case",["get","blocked"],"#ed6170",["get","slow"],"#e0a844","#479fdd"],"fill-opacity":0.26}});map.addLayer({id:"scenario-outline",type:"line",source:"scenario",paint:{"line-color":["case",["get","blocked"],"#ff7d88",["get","slow"],"#f0c06f","#7dccff"],"line-width":2}});setSignalMap(map); map.addSource("roads", {type:"geojson",data:{type:"FeatureCollection",features:[]}}); map.addLayer({id:"roads",type:"line",source:"roads",minzoom:15,layout:{visibility:"none"},paint:{"line-color":["match",["get","traffic_status"],"BLOCKED","#ee4558","CONGESTED","#f97316","SLOW","#efbd38","#91a4ad"],"line-width":["interpolate",["linear"],["zoom"],15,2,18,5],"line-opacity":0.8}}); });
    map.on("zoom", () => {
      if (map.getZoom() < 15 && map.getLayer("roads")) {
        ++seq;
        map.setLayoutProperty("roads", "visibility", "none");
        setStatus("Zoom in to street level to see road coloring · grey = traffic unknown");
      }
    });
    map.on("moveend", () => { if (map.getSource("roads")) void update(); });
    map.on("render", () => { if (container.current && map.getLayer("roads")) container.current.dataset.roads = String(map.queryRenderedFeatures({ layers:["roads"] }).length); });
    map.addControl(new maplibregl.NavigationControl());
    const roadTimer=setInterval(()=>{if(map.getSource("roads")&&map.getZoom()>=15)void update();},15000);
    const observer = new ResizeObserver(() => map.resize()); observer.observe(container.current);
    return () => { disposed=true;clearInterval(roadTimer); observer.disconnect(); map.remove(); };
  }, []);
  useEffect(()=>{refreshRoads.current();},[JSON.stringify(scenario?.scenarios.map(z=>[z.id,z.blocked,Math.round(z.traffic_factor*10)]))]);
  useEffect(()=>{if(!signalMap||!focus?.length)return;const bounds=new maplibregl.LngLatBounds();focus.forEach(p=>bounds.extend(p as [number,number]));signalMap.fitBounds(bounds,{padding:50,maxZoom:15,duration:700});},[signalMap,focus]);
  return <div className="atlas-map-content">{drawing&&<div className="scenario-map-drawing" role="status">Drawing area · {polygon.length} points. Click the map to add a corner.<button disabled={polygon.length<3} onClick={onFinish}>Finish area</button></div>}<div className="main-world-map" ref={container} aria-label="Database road map"/><p className="main-map-status">{status}</p><TrafficSignals map={signalMap}/>{!electric&&<MetroLayer map={signalMap}/>}<ElectricLayer map={signalMap}/></div>;
}

type EmergencyOverview={trips:Record<string,{id:string;vehicle:string;destination:string;status:string;eta_seconds:number|null}>};
function EmergencySummary(){
 const [data,setData]=useState<EmergencyOverview|null>(null),[error,setError]=useState(false);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;const poll=async()=>{try{const next=await request<EmergencyOverview>('/emergency',{},15000);if(alive){setData(next);setError(false);}}catch{if(alive)setError(true);}if(alive)timer=setTimeout(poll,5000);};void poll();return()=>{alive=false;clearTimeout(timer);};},[]);
 const trips=Object.values(data?.trips??{}).filter(t=>!['COMPLETED','CANCELLED','REJECTED'].includes(t.status));
 return <section className="atlas-panel atlas-emergency"><h2><span>Emergency operations</span><span className="atlas-count">{data?trips.length:'—'}</span></h2>{error?<p className="atlas-empty">Emergency service unavailable.</p>:!data?<p className="atlas-empty">Reading dispatch state…</p>:!trips.length?<div className="atlas-empty"><span className="atlas-empty-icon">＋</span><strong>No active corridors</strong><p>Ambulance requests and approved missions appear here.</p></div>:<div className="atlas-list">{trips.map(t=><article key={t.id}><div><strong>{t.vehicle}</strong><small>{t.destination}</small></div><span>{t.eta_seconds==null?'ETA pending':`${Math.ceil(t.eta_seconds/60)} min`}<small>{title(t.status)}</small></span></article>)}</div>}<Link className="atlas-panel-link" href="/traffic">Open traffic command <span>↗</span></Link></section>;
}

export default function MainCommand({ department = "main" }: { department?: "main" | "electric" | "field" }) {
 const {data:shared,error:sharedError,setData:setShared}=useScenario();
 const [removing,setRemoving]=useState(false),[areaError,setAreaError]=useState('');
 const [polygon,setPolygon]=useState<number[][]>([]),[drawing,setDrawing]=useState(false);
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState('');
 const [focus,setFocus]=useState<number[][]>(),[selected,setSelected]=useState('');
 const [sheet,setSheet]=useState<'inventory'|'budget'|'metro'|'emergency'|null>(null);
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{if(sheet)dialog.current?.showModal();else dialog.current?.close();},[sheet]);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;const poll=async()=>{try{const next=await request<Snapshot>('/command/snapshot',{},30000);if(alive){setData(next);setError('');}}catch(e){if(alive)setError(e instanceof Error?e.message:'Database unavailable');}if(alive)timer=setTimeout(poll,15000);};void poll();return()=>{alive=false;clearTimeout(timer);};},[]);
 const active=shared?.scenarios.filter(z=>z.status!=='ENDED')??[];
 const selectedArea=active.find(z=>z.id===selected)??active[0];
 const selectedIndex=selectedArea?active.findIndex(z=>z.id===selectedArea.id)+1:0;
 const rain=Math.max(0,...active.map(z=>z.rain_mm_hour));
 const pending=shared?.recommendations.filter(r=>r.status==='PENDING').length??0;
 const blocked=active.filter(z=>z.blocked).length;
 const slowed=active.filter(z=>z.traffic_factor<.85&&!z.blocked).length;
 const load=shared?.electric.load_percent;
 const severity=(z:typeof active[number])=>z.kind==='METRO'?`Demand ×${z.metro_factor.toFixed(1)}`:z.blocked?'Closure':z.water_mm>=30||z.traffic_factor<.5?'Disrupted':'Monitoring';
 const locate=(z:typeof active[number])=>{setSelected(z.id);setFocus((z.station_targets?.map(s=>s.position)??z.polygon).map(p=>[...p]));document.querySelector('.atlas-map-panel')?.scrollIntoView({behavior:'smooth',block:'nearest'});};
 const removeArea=async(id:string)=>{setRemoving(true);setAreaError('');try{const next=await request<import('./ScenarioControls').ScenarioSnapshot>('/command/scenario',{method:'POST',body:JSON.stringify({action:'REMOVE',target_id:id,request_id:crypto.randomUUID()})},30000);setShared(next);setSelected('');setPolygon([]);setDrawing(false);}catch(e){setAreaError(e instanceof Error?e.message:'Area removal was not confirmed.');}finally{setRemoving(false);}};
 const path=department==='main'?'/command':department==='electric'?'/electric-command':'/lineman';
 const eventTime=(elapsed:number)=>{if(!shared)return '—';const [h,m,sec]=shared.clock.split(':').map(Number);const t=Math.max(0,Math.floor(h*3600+m*60+sec-shared.seconds+elapsed));return `${String(Math.floor(t/3600)).padStart(2,'0')}:${String(Math.floor(t%3600/60)).padStart(2,'0')}`;};
 const openOperations=()=>document.querySelector<HTMLButtonElement>('.atlas-dock-review')?.click();
 return <main className="main-command command-reference atlas-command">
  <header className="atlas-header">
   <Link href="/command" className="atlas-brand"><svg viewBox="0 0 36 42" width="34" height="40" aria-hidden="true"><path d="M18 2L33 8L30 27L18 39L6 27L3 8Z" fill="none" stroke="currentColor" strokeWidth="1.4"/><path d="M20 8L11 23H18L16 33L26 17H19Z" fill="none" stroke="currentColor" strokeWidth="1.4"/></svg><span>AEGISGRID<small>INTEGRATED CITY OPERATIONS</small></span></Link>
   <div className="atlas-title"><h1>{department==='main'?'HYDERABAD DIGITAL TWIN':department==='electric'?'ELECTRIC COMMAND':'FIELD OPERATIONS'}</h1><p>Infrastructure & emergency management</p></div>
   <div className="atlas-header-status"><div className="atlas-clock"><strong>{shared?.clock??'--:--:--'}</strong><small>IST · SHARED SIMULATION</small></div><div className="atlas-connection"><i className={error||sharedError?'down':''}/><div><small>DATABASE STATUS</small><strong>{error||sharedError?'Connection issue':shared?'Connected':'Connecting'}</strong></div></div></div>
  </header>
  <nav className="atlas-nav" aria-label="Departments">{[['/command','Command Center'],['/traffic','Traffic'],['/ambulance','Ambulance'],['/electric-command','Electric'],['/lineman','Field teams'],['/metro-command','Metro'],['/google-operations','Google Operations']].map(([href,label])=><Link key={href} href={href} aria-current={path===href?'page':undefined}>{label}</Link>)}<span className="atlas-mode"><i/>{shared?.running?'SIMULATION RUNNING':'SIMULATION PAUSED'}</span></nav>
  {(error||sharedError)&&<p className="main-warning" role="alert">{sharedError||error}</p>}
  <div className="atlas-stage">
   <aside className="atlas-rail atlas-left" aria-label="City overview and activity">
    <section className="atlas-panel"><h2>City overview <span className="atlas-tag">MODEL</span></h2><div className="atlas-overview"><div><small>Active inputs</small><strong>{shared?active.length:'—'}</strong><span>Scenario inputs</span></div><div><small>Road closures</small><strong className={blocked?'danger':''}>{shared?blocked:'—'}</strong><span>Modeled areas</span></div><div><small>Power load</small><strong className={load&&load>90?'warning':''}>{load??'—'}<em>%</em></strong><span>Of capacity</span></div><div><small>Awaiting action</small><strong className={pending?'warning':''}>{shared?pending:'—'}</strong><span>Recommendations</span></div></div></section>
    <WeatherOverview/>
    <section className="atlas-panel atlas-events"><h2>Operations feed <span className="atlas-tag">AUDIT</span></h2><div className="atlas-event-feed">{shared?.events.slice(-6).reverse().map(e=><article key={e.id}><span className={`atlas-event-icon ${e.kind.includes('REJECT')?'warning':''}`}>{e.kind.includes('RAIN')?'☂':e.kind.includes('APPROV')?'✓':e.kind.includes('TIME')||e.kind.includes('PAUSE')?'◷':'↗'}</span><div><strong>{title(e.kind).toLowerCase()}</strong><small>Shared simulation event</small></div><time>{eventTime(e.sim_seconds)}</time></article>)}{!shared?.events.length&&<p className="atlas-empty">No recorded events.</p>}</div><button className="atlas-panel-link" onClick={openOperations}>Review actions & history <span>↗</span></button></section>
    <section className="atlas-panel atlas-source-panel"><h2>Source integrity</h2><div><span><i className="atlas-source-dot"/>Google weather</span><small>Provider observation</small><span><i className="atlas-source-dot modeled"/>City simulation</span><small>Database-backed model</small><span><i className="atlas-source-dot geometry"/>Roads & metro</span><small>OSM / imported GTFS</small></div></section>
   </aside>
   <section className="atlas-map-panel city-map-column" aria-label="Operational map workspace">
    <div className="atlas-map-heading"><div><span className="atlas-map-eyebrow">HYDERABAD / CITY VIEW</span><strong>{drawing?'Define scenario boundary':'Common operating picture'}</strong></div><span className="atlas-tag">{department==='main'?'SIGNALS · METRO · POWER':'ELECTRICAL NETWORK'}</span></div>
    <DatabaseMap electric={department!=='main'} focus={focus} polygon={polygon} drawing={drawing} onPoint={p=>setPolygon(old=>[...old,p])} onFinish={()=>setDrawing(false)}/>
    <div className="atlas-map-legend"><span><i style={{background:'#60a5fa'}}/>Scenario area</span><span><i style={{background:'#e0a844'}}/>Congestion</span><span><i style={{background:'#ed6170'}}/>Closure</span><span className="atlas-map-hint">Road status appears at street zoom</span></div>
    <div className="atlas-selection"><div className="atlas-selection-heading"><span>TARGET INTELLIGENCE</span>{selectedArea?<button onClick={()=>locate(selectedArea)}>{selectedArea.kind==='METRO'?'Station group':'Area'} {selectedIndex} · {title(selectedArea.kind)} <span>⌖</span></button>:<span>No area selected</span>}{selectedArea&&department==='main'&&<button className="atlas-remove-area" disabled={removing||!!sharedError} onClick={()=>void removeArea(selectedArea.id)}>{removing?'Removing…':selectedArea.kind==='METRO'?'Remove demand ×':'Remove area ×'}</button>}</div>{areaError&&<p role="alert">{areaError}</p>}{selectedArea?.kind==='METRO'?<div className="atlas-metro-impact"><strong>Station arrivals ×{selectedArea.metro_factor.toFixed(2)}</strong><p>{selectedArea.station_targets?.map(s=>s.name).join(' · ')??'Legacy polygon target'}</p><p>{selectedArea.affected.METRO_STATION??0} selected stations · {selectedArea.status.toLowerCase()} · passengers queue and board according to the shared timetable.</p></div>:selectedArea?<><div className="atlas-selection-metrics"><div><small>Rainfall</small><strong>{selectedArea.rain_mm_hour.toFixed(0)} <em>mm/h</em></strong></div><div><small>Water depth</small><strong className={selectedArea.water_mm>=30?'warning':''}>{selectedArea.water_mm.toFixed(1)} <em>mm</em></strong></div><div><small>Road speed</small><strong>{Math.round(selectedArea.traffic_factor*100)}<em>% baseline</em></strong></div><div><small>Electrical change</small><strong>{selectedArea.electrical_impact?`${selectedArea.electrical_impact.delta_kva>0?'+':''}${Math.round(selectedArea.electrical_impact.delta_kva).toLocaleString()}`:'—'} <em>kVA</em></strong></div><div><small>Affected stations</small><strong>{selectedArea.affected.METRO_STATION??0}</strong></div></div><p>{selectedArea.affected.DISTRIBUTION_TRANSFORMER??0} transformers in area · {selectedArea.blocked?'Closure threshold reached':`${Math.max(0,150-selectedArea.water_mm).toFixed(0)} mm below closure threshold`} · {selectedArea.status.toLowerCase()}</p></>:<p>Choose an event below, draw an area, then apply it. Effects and decisions appear here as the shared clock advances.</p>}</div>
   </section>
   <aside className="atlas-rail atlas-right" aria-label="Infrastructure and response">
    <section className="atlas-panel"><h2>Scenario impact <span className="atlas-tag">SIM</span></h2><div className="atlas-area-list">{active.map((z,i)=><button className={selectedArea?.id===z.id?'selected':''} key={z.id} onClick={()=>locate(z)}><span><i className={z.blocked?'danger':z.water_mm>=30?'warning':''}/>{z.kind==='METRO'?'Station group':'Area'} {i+1}<small>{z.kind==='METRO'?`${z.station_targets?.length??0} selected stations`:`${title(z.kind).toLowerCase()} · ${z.water_mm.toFixed(0)} mm water`}</small></span><strong className={z.blocked?'danger':z.water_mm>=30?'warning':''}>{severity(z)}</strong></button>)}{!active.length&&<p className="atlas-empty">No active scenario inputs.</p>}</div><div className="atlas-summary-row"><span>Areas with disruption</span><strong className={blocked+slowed?'warning':''}>{shared?blocked+slowed:'—'}</strong></div></section>
    <section className="atlas-panel"><h2>Power grid status</h2><div className="atlas-grid-load"><div className="atlas-gauge" style={{background:`conic-gradient(${(load??0)>90?'#edaf53':'#648dce'} ${Math.min(100,Math.max(0,load??0))}%, #202936 0)`}}><div><strong>{load??'—'}<em>%</em></strong><small>CAPACITY</small></div></div><div><strong>{shared?.electric.load_kva.toLocaleString(undefined,{maximumFractionDigits:0})??'—'} <small>kVA</small></strong><p>Modeled demand</p><span>{shared?.electric.overloaded_transformers??'—'} overloaded</span></div></div><div className="atlas-grid-counts">{[['Substations','SUBSTATION'],['Feeders','FEEDER'],['Transformers','DISTRIBUTION_TRANSFORMER']].map(([label,key])=><div key={key}><strong>{shared?.asset_counts[key]?.toLocaleString()??'—'}</strong><small>{label}</small></div>)}</div><p className="atlas-provenance">Generated equipment · persisted in database</p></section>
    <section className="atlas-panel"><h2>Network impact</h2><div className="atlas-network"><div><span>Slowed road areas</span><strong className={slowed?'warning':''}>{shared?slowed:'—'}</strong></div><div><span>Highest scenario rain</span><strong>{shared?rain.toFixed(0):'—'} <small>mm/h</small></strong></div><div><span>Metro passengers waiting</span><strong>{shared?.passengers.waiting.toLocaleString()??'—'}</strong></div><div><span>Passengers onboard</span><strong>{shared?.passengers.onboard.toLocaleString()??'—'}</strong></div></div><p className="atlas-provenance">Shared model · no live passenger or traffic feed</p><button className="atlas-panel-link" onClick={()=>setSheet('metro')}>Metro timetable & movement <span>↗</span></button></section>
    <EmergencySummary/>
   </aside>
  </div>
  <ScenarioControls dock polygon={polygon} drawing={drawing} onDraw={()=>setDrawing(!drawing)} onClear={()=>{setPolygon([]);setDrawing(false);}} readOnly={department!=='main'}/>
  <footer className="atlas-footer"><span><i/>Shared database · version {shared?.version??'—'} <b>Source geometry + modeled operations</b></span><div><button onClick={()=>setSheet('budget')}>API budget</button><button onClick={()=>setSheet('inventory')}>Data & provenance</button><button onClick={()=>setSheet('emergency')}>Emergency workspace</button></div></footer>
  <dialog ref={dialog} className="atlas-dialog" onCancel={()=>setSheet(null)} onClick={e=>{if(e.target===dialog.current)setSheet(null);}}><div className="atlas-dialog-header"><h2>{sheet==='budget'?'API usage & billing guard':sheet==='inventory'?'Database inventory & provenance':sheet==='metro'?'Metro operations':'Emergency operations'}</h2><button aria-label="Close workspace" onClick={()=>setSheet(null)}>✕</button></div><div className="atlas-dialog-body">{sheet==='budget'&&<ApiBudget/>}{sheet==='metro'&&<MetroView controls/>}{sheet==='emergency'&&<EmergencyWorkspace role={department==='main'?'command':'viewer'} embedded/>}{sheet==='inventory'&&<><SimulationInventory/><div className="main-table"><table><thead><tr><th>Source table</th><th>Records</th><th>Status</th></tr></thead><tbody>{data?.tables.map(t=><tr key={t.table}><td>{title(t.table)}</td><td>{t.count?.toLocaleString()??'—'}</td><td>{t.status}</td></tr>)}</tbody></table></div></>}</div></dialog>
 </main>;
}
