import type { DepartmentRecommendation } from "@/types/operations";
import Panel, { Badge } from "./Panel";
export function RecommendationCard({ item }: { item: DepartmentRecommendation }) {
  return <details className="recommendation-card" open={item.provenance === "DERIVED"}><summary><span><strong>{item.department}</strong><small>{item.incident}</small></span><span className={`criticality ${item.criticalLevel.toLowerCase()}`}>{item.criticalLevel}</span></summary><div className="recommendation-detail"><Badge provenance={item.provenance} /><dl>{[
    ["Incident",item.incident], ["Why this matters",item.whyThisMatters], ["Critical level",item.criticalLevel], ["Recommended action",item.recommendedAction], ["Why this solution",item.whyThisSolution], ["Expected result",item.expectedResult], ["Dependencies",item.dependencies.join(" · ")], ["Fallback",item.fallback], ["Confidence",item.confidence], ["Evidence",item.evidence.join(" · ")],
  ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></div></details>;
}
export default function Recommendations({ items }: { items: DepartmentRecommendation[] }) {
  return <Panel title="Department recommendations"><p className="panel-note">Advisory only · operator approval required</p>{items.map(item=><RecommendationCard item={item} key={item.id} />)}</Panel>;
}
