import type { Map as ElectricMap } from "maplibre-gl";

const symbols = [
  { kind: "SUBSTATION", title: "Substation", color: "#f4ce76", body: "M5 5H27V27H5Z", detail: "M18 8L11 17H17L14 24L22 14H16Z" },
  { kind: "FEEDER_11KV", title: "11 kV feeder", color: "#71cfff", body: "M16 2L30 16L16 30L2 16Z", detail: "M9 16H23M16 9V23M20 12L24 16L20 20" },
  { kind: "POWER_TRANSFORMER", title: "Power transformer", color: "#d4afff", body: "M18 16A7 7 0 1 1 4 16A7 7 0 1 1 18 16M28 16A7 7 0 1 1 14 16A7 7 0 1 1 28 16", detail: "M2 16H4M28 16H30" },
  { kind: "DISTRIBUTION_TRANSFORMER", title: "Distribution transformer", color: "#76e2b8", body: "M10 5H22L25 9V25L22 28H10L7 25V9Z", detail: "M11 12H21M11 17H21M11 22H21M12 2V5M20 2V5" },
  { kind: "SUPPLY_33KV", title: "33 kV supply", color: "#d8e6f0", body: "M16 3L30 28H2Z", detail: "M16 10V22M11 17L16 22L21 17" },
  { kind: "SIGNAL_LOAD", title: "Signal load", color: "#ffb78c", body: "M10 2H22V27H10Z", detail: "M16 27V31M18 8A2 2 0 1 1 14 8A2 2 0 1 1 18 8M18 15A2 2 0 1 1 14 15A2 2 0 1 1 18 15M18 22A2 2 0 1 1 14 22A2 2 0 1 1 18 22" },
];

export function registerElectricalSymbols(map: ElectricMap) {
  for (const symbol of symbols) for (const mode of ["normal", "off", "overload"]) {
    const canvas = document.createElement("canvas");
    canvas.width = 64; canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Electrical symbols could not render");
    ctx.scale(2, 2); ctx.lineWidth = 1.8; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.fillStyle = "#0a1c28"; ctx.strokeStyle = mode === "off" ? "#ff785f" : mode === "overload" ? "#ffd34f" : symbol.color;
    const body = new Path2D(symbol.body);
    ctx.fill(body); ctx.stroke(body); ctx.stroke(new Path2D(symbol.detail));
    if (mode !== "normal") { ctx.fillStyle = mode === "off" ? "#ff785f" : "#ffd34f"; ctx.beginPath(); ctx.arc(27, 5, 3.5, 0, Math.PI * 2); ctx.fill(); }
    map.addImage(`${symbol.kind}${mode === "normal" ? "" : `-${mode}`}`, ctx.getImageData(0, 0, 64, 64), { pixelRatio: 2 });
  }
}

export function ElectricalLegend() {
  return <div className="electric-symbol-legend" aria-label="Electrical asset symbols">
    {symbols.map(s => <span key={s.kind}><svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true" fill="#0a1c28" stroke={s.color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round"><path d={s.body} /><path d={s.detail} fill="none" /></svg>{s.title}</span>)}
    <span><i className="electric-overload-key" />Yellow symbol + badge: overloaded</span><span><i className="electric-outage-key" />Red symbol + badge: supply affected</span>
  </div>;
}
