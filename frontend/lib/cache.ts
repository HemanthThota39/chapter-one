"use client";

import { useEffect, useRef, useState } from "react";

/** Minimal stale-while-revalidate cache — a tiny subset of SWR, just enough
 *  to stop navigation flicker when going Feed → Profile → Feed. Values live
 *  for the page's lifetime (no LRU, no persistence). */

type CacheEntry<T> = { value: T; ts: number };

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export function getCached<T>(key: string): T | undefined {
  return (store.get(key) as CacheEntry<T> | undefined)?.value;
}

export function setCached<T>(key: string, value: T): void {
  store.set(key, { value, ts: Date.now() });
}

export function invalidate(prefix: string): void {
  for (const k of store.keys()) if (k.startsWith(prefix)) store.delete(k);
}

/** Hook: returns cached data synchronously when present, then revalidates.
 *  Re-runs the fetcher when key changes OR when revalidate() is called. */
export function useSWR<T>(
  key: string | null,
  fetcher: () => Promise<T>,
): {
  data: T | undefined;
  error: Error | null;
  loading: boolean;
  mutate: (v?: T) => void;
  revalidate: () => Promise<void>;
} {
  const [data, setData] = useState<T | undefined>(() =>
    key ? getCached<T>(key) : undefined,
  );
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(!data && key !== null);
  const [tick, setTick] = useState(0);
  const mountedRef = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (key === null) return;
    let cancelled = false;
    const cached = getCached<T>(key);
    if (cached !== undefined && tick === 0) {
      setData(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    // Deduplicate concurrent requests for the same key unless forced by tick.
    let promise = inflight.get(key) as Promise<T> | undefined;
    if (!promise || tick > 0) {
      promise = fetcherRef.current();
      inflight.set(key, promise);
      promise.finally(() => inflight.delete(key));
    }
    promise
      .then((val) => {
        if (cancelled || !mountedRef.current) return;
        setCached(key, val);
        setData(val);
        setError(null);
      })
      .catch((e) => {
        if (cancelled || !mountedRef.current) return;
        setError(e as Error);
      })
      .finally(() => {
        if (cancelled || !mountedRef.current) return;
        setLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);

  return {
    data,
    error,
    loading,
    mutate: (v?: T) => {
      if (key === null) return;
      if (v !== undefined) { setCached(key, v); setData(v); setError(null); }
      else invalidate(key);
    },
    revalidate: async () => {
      if (key === null) return;
      setError(null);
      invalidate(key);
      setTick((t) => t + 1);
    },
  };
}
