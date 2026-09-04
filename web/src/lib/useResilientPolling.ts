"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { request } from "./api";
import { PollingLifecycleManager, calculateBackoff } from "./pollingLifecycle";

export { PollingLifecycleManager, calculateBackoff };

export interface ResilientPollingOptions {
  url: string;
  normalIntervalMs?: number;
  timeoutMs?: number;
  defaultErrorMessage?: string;
  enabled?: boolean;
}

export function useResilientPolling<T>({
  url,
  normalIntervalMs = 3000,
  timeoutMs = 15000,
  defaultErrorMessage = "Backend connection unavailable — data may be stale",
  enabled = true
}: ResilientPollingOptions) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [isStale, setIsStale] = useState<boolean>(false);
  const [lastSync, setLastSync] = useState<string | null>(null);

  const managerRef = useRef<PollingLifecycleManager<T> | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const manager = new PollingLifecycleManager<T>(
      (signal) => request<T>(url, { signal }, timeoutMs),
      {
        onSuccess: (next) => {
          setData(next);
          setError("");
          setIsStale(false);
          setLastSync(new Date().toLocaleTimeString());
        },
        onError: (errMsg) => {
          setIsStale(true);
          setError(errMsg);
        }
      },
      normalIntervalMs,
      defaultErrorMessage
    );
    managerRef.current = manager;
    void manager.poll();

    return () => {
      manager.cancel();
      managerRef.current = null;
    };
  }, [url, enabled, normalIntervalMs, timeoutMs, defaultErrorMessage]);

  const refresh = useCallback(() => {
    if (managerRef.current) {
      void managerRef.current.poll(true);
    }
  }, []);

  return { data, error, isStale, lastSync, setData, setError, refresh };
}
