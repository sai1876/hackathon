import type { LayerState } from "./OperationalLayers";
export default function LayerControls({ layers, onChange }: { layers: LayerState; onChange: (layers: LayerState) => void }) {
  return <details className="layer-controls"><summary>▱ Layers <small>SYNTHETIC DEMO</small></summary><div>{Object.entries({zones:"Exercise sectors",traffic:"Traffic conditions",flood:"Waterlogging",signal:"Traffic signals",transformer:"Transformers",hospital:"Hospitals",ambulance:"Ambulances"}).map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key as keyof LayerState]} onChange={e=>onChange({...layers,[key]:e.target.checked})} />{label}</label>)}<p>Demo layers never modify routing.</p></div></details>;
}
