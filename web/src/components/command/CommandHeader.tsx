"use client";
import { useEffect, useState } from "react";

export default function CommandHeader({ status }: { status: string }) {
  const [clock, setClock] = useState<Date | null>(null);
  useEffect(() => { const update = () => setClock(new Date()); update(); const timer = setInterval(update, 1000); return () => clearInterval(timer); }, []);
  return <header className="command-header">
    <a className="command-brand" href="/traffic"><span className="command-emblem">A</span><span>AEGIS<span>GRID</span><small>URBAN OPERATIONS COMMAND</small></span></a>
    <div className="command-title"><h1>HYDERABAD <span>DIGITAL TWIN</span></h1><p>Urban Infrastructure &amp; Disaster Operations</p></div>
    <div className="header-clock"><strong>{clock?.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" }) ?? "—"}</strong><small>{clock?.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }) ?? "System clock"} · IST</small></div>
    <div className="header-weather"><span>☂</span><div>WEATHER<small>SYNTHETIC DEMO</small></div></div>
    <div className={`command-health ${status === "ONLINE" ? "online" : "offline"}`}><i /><div><small>SYSTEM STATUS</small><strong>{status === "ONLINE" ? "OPERATIONAL" : status}</strong><span>API {status}</span></div></div>
  </header>;
}
