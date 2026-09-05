import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Keep a view in step with the database.
 *
 * Every screen in this app reads state that other people change — a manager
 * approves while a rep is looking at the quote, stock moves while fulfilment
 * is open, a customer counters while the pipeline is on screen. A fetch on
 * mount alone leaves whoever is watching with a stale page and no hint of it.
 *
 * Polling rather than websockets: the server is a plain request/response API,
 * and adding a socket layer would be a second source of truth to keep
 * consistent for a refresh interval a person cannot perceive anyway.
 *
 * Three things make it behave rather than hammer:
 *  - refetch on window focus, which is when staleness is actually noticed
 *  - pause entirely while the tab is hidden, so a backgrounded tab costs zero
 *  - never overlap requests, so a slow response cannot stack up a queue
 */
export interface LiveState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** true only for the first load, so the UI can skeleton once and then
   *  refresh in place without flashing */
  initialLoading: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useLiveData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  intervalMs = 10_000,
): LiveState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const inFlight = useRef(false);
  const mounted = useRef(true);
  // held in a ref so a new closure each render does not restart the interval
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const next = await fetcherRef.current();
      if (!mounted.current) return;
      setData(next);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      if (!mounted.current) return;
      // Keep the last good data on screen. Blanking a working view because one
      // poll failed is a worse outcome than briefly showing slightly old rows.
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mounted.current) {
        setLoading(false);
        setInitialLoading(false);
      }
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    setInitialLoading(true);
    run();

    const tick = window.setInterval(() => {
      if (document.visibilityState === "visible") run();
    }, intervalMs);

    const onFocus = () => {
      if (document.visibilityState === "visible") run();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);

    return () => {
      mounted.current = false;
      window.clearInterval(tick);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs, run]);

  return { data, error, loading, initialLoading, lastUpdated, refresh: run };
}

/**
 * A counter that ticks on an interval and whenever the tab regains focus.
 *
 * Add it to an existing `useEffect` dependency array and that effect re-runs
 * on the same schedule as `useLiveData`, without restructuring the screen.
 * Screens that already carry pagination, filters and search keep all of it —
 * they just stop being a snapshot of whenever they happened to mount.
 *
 *   const tick = useAutoRefresh();
 *   useEffect(() => { ...existing fetch... }, [page, filter, tick]);
 *
 * Paused while the tab is hidden, so a backgrounded tab costs nothing.
 */
export function useAutoRefresh(intervalMs = 12_000): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const bump = () => {
      if (document.visibilityState === "visible") setTick((t) => t + 1);
    };
    const id = window.setInterval(bump, intervalMs);
    window.addEventListener("focus", bump);
    document.addEventListener("visibilitychange", bump);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", bump);
      document.removeEventListener("visibilitychange", bump);
    };
  }, [intervalMs]);

  return tick;
}
