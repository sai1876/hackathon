export default function MapLegend() {
  return <div className="command-map-legend"><span className="legend-prefix">DEMO</span>{[["Normal","normal"],["Slow","warning"],["Congested","degraded"],["Blocked","special"],["Waterlogging","info"]].map(([label,tone])=><span key={label}><i className={`key-dot ${tone}`} />{label}</span>)}<span className="legend-actual"><i />Backend route</span></div>;
}
