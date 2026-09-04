import type { EmergencyVehicle } from "@/types/operations";
import Panel from "./Panel";
export default function EmergencyVehicles({ vehicles, onSelect }: { vehicles: EmergencyVehicle[]; onSelect: (vehicle: EmergencyVehicle) => void }) {
  return <Panel title="Emergency vehicles" provenance="SYNTHETIC"><div className="vehicle-list">{vehicles.map(v=><button key={v.id} onClick={()=>onSelect(v)}><span className="vehicle-symbol">✚</span><span><strong>{v.id}</strong><small>{v.route}</small></span><span><b>{v.eta} min</b><small className={v.delay ? "critical" : "normal"}>{v.delay ? `+${v.delay} min` : "On time"}</small></span></button>)}</div><small className="panel-note">Illustrative ETAs · no dispatch or tracking feed</small></Panel>;
}
