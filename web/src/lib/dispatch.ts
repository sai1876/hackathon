"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "./api";
import type { OperationsSnapshot } from "@/types/dispatch";
export const command = <T,>(path: string, data: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(data) });
export function useOperations() {
  const [data, setData] = useState<OperationsSnapshot | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false), mutation = useRef(false), sequence = useRef(0);
  const refresh = useCallback(async () => {
    const seq = ++sequence.current;
    try {
      const next = await request<OperationsSnapshot>("/operations", {}, 20000);
      if (mounted.current && seq === sequence.current) { setData(next); setConnectionError(""); }
    } catch (e) { if (mounted.current && seq === sequence.current) setConnectionError(e instanceof Error ? e.message : "Backend unavailable"); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    const requestSequence = sequence;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { if (!mutation.current) await refresh(); if (mounted.current) timer = setTimeout(poll, 3000); };
    void poll();
    return () => { mounted.current = false; clearTimeout(timer); requestSequence.current++; };
  }, [refresh]);
  const act = async (operation: () => Promise<unknown>) => {
    if (mutation.current) return false;
    mutation.current = true; sequence.current++; setBusy(true); setActionError("");
    let failure = "";
    try { await operation(); } catch (e) { failure = e instanceof Error ? e.message : "Action failed"; }
    await refresh();
    if (mounted.current) { if (failure) setActionError(failure); setBusy(false); }
    mutation.current = false;
    return !failure;
  };
  return { data, error: actionError || connectionError, connectionError, busy, act, refresh };
}
