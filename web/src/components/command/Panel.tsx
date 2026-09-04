import type { ReactNode } from "react";
import type { Provenance } from "@/types/operations";
export function Badge({ provenance }: { provenance: Provenance }) { return <span className={`provenance provenance-${provenance.toLowerCase()}`}>{provenance === "SYNTHETIC" ? "SYNTHETIC DEMO" : provenance}</span>; }
export default function Panel({ title, provenance, children, className = "" }: { title: string; provenance?: Provenance; children: ReactNode; className?: string }) {
  return <section className={`ops-panel ${className}`}><header className="ops-panel-heading"><h2>{title}</h2>{provenance && <Badge provenance={provenance} />}</header><div className="ops-panel-body">{children}</div></section>;
}
