"use client";
import { useEffect, useState } from "react";
import { initialSimulation } from "@/lib/operations";
import type { Scenario } from "@/types/operations";
export function useSimulation() {
  const [simulation, setSimulation] = useState(initialSimulation);
  useEffect(() => { if (!simulation.playing) return; const timer = setInterval(() => setSimulation(s => ({ ...s, tick: s.tick + s.speed })), 1000); return () => clearInterval(timer); }, [simulation.playing]);
  return { simulation, selectScenario: (scenario: Scenario) => setSimulation(s => ({ ...s, scenario, tick: 0, playing: false })), play: () => setSimulation(s => ({ ...s, playing: true })), pause: () => setSimulation(s => ({ ...s, playing: false })), step: () => setSimulation(s => ({ ...s, playing: false, tick: s.tick + 1 })), speed: (speed: 1|2|5) => setSimulation(s => ({ ...s, speed })), reset: () => setSimulation({ ...initialSimulation, scenario: "NORMAL" }) };
}
