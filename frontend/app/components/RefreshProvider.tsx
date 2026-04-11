'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

/* ──────────────────────────────────────────────────────────
   Refresh Context
   1) Scheduled auto-refresh at user-chosen interval
      (15 min / 30 min / 1 h / 1 day) → bumps `refreshTick`
   2) Real-time SSE from /realtime/stream → pushes live metrics
   ────────────────────────────────────────────────────────── */

import { API_BASE_URL } from '../lib/api';

export type IntervalOption = 15 | 30 | 60 | 1440; // minutes

export interface RealtimeSummary {
  today_revenue: number;
  today_cost: number;
  today_profit: number;
  today_orders: number;
  today_items_sold: number;
  today_discount: number;
  mtd_revenue: number;
  mtd_profit: number;
  mtd_orders: number;
  last_updated: string | null;
  metric_date: string;
}

interface RefreshContextValue {
  /** Incremented each time scheduled refresh fires – pages re-fetch when this changes */
  refreshTick: number;
  /** The chosen auto-refresh interval in minutes */
  intervalMinutes: IntervalOption;
  /** Change the auto-refresh interval */
  setIntervalMinutes: (m: IntervalOption) => void;
  /** Latest real-time summary from SSE (null until first push) */
  realtimeSummary: RealtimeSummary | null;
  /** Force an immediate refresh: triggers backend ETL then bumps tick */
  forceRefresh: () => void;
  /** True while ETL is running after a manual refresh */
  isRefreshing: boolean;
}

const RefreshContext = createContext<RefreshContextValue>({
  refreshTick: 0,
  intervalMinutes: 30,
  setIntervalMinutes: () => {},
  realtimeSummary: null,
  forceRefresh: () => {},
  isRefreshing: false,
});

export const useRefresh = () => useContext(RefreshContext);

const STORAGE_KEY = 'bi_refresh_interval';

function loadSavedInterval(): IntervalOption {
  if (typeof window === 'undefined') return 30;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && [15, 30, 60, 1440].includes(Number(saved))) return Number(saved) as IntervalOption;
  return 30;
}

export default function RefreshProvider({ children }: { children: React.ReactNode }) {
  const [intervalMinutes, setIntervalMinutesState] = useState<IntervalOption>(30);
  const [refreshTick, setRefreshTick] = useState(0);
  const [realtimeSummary, setRealtimeSummary] = useState<RealtimeSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load saved interval from localStorage on mount
  useEffect(() => {
    setIntervalMinutesState(loadSavedInterval());
  }, []);

  const setIntervalMinutes = useCallback((m: IntervalOption) => {
    setIntervalMinutesState(m);
    localStorage.setItem(STORAGE_KEY, String(m));
  }, []);

  const forceRefresh = useCallback(() => {
    setIsRefreshing(true);
    // Trigger backend ETL pipeline (fire-and-forget, no auth required)
    fetch(`${API_BASE_URL}/data/etl/run`, { method: 'POST' }).catch(() => {});
    // Bump refreshTick after 2s to let ETL start processing
    setTimeout(() => {
      setRefreshTick((t) => t + 1);
      setIsRefreshing(false);
    }, 2000);
  }, []);

  // Scheduled auto-refresh timer
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    const ms = intervalMinutes * 60 * 1000;
    timerRef.current = setInterval(() => {
      setRefreshTick((t) => t + 1);
    }, ms);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [intervalMinutes]);

  // SSE real-time connection to /realtime/stream
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API_BASE_URL}/realtime/stream`);
      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as RealtimeSummary;
          if (data && data.today_revenue !== undefined) {
            setRealtimeSummary(data);
          }
        } catch { /* ignore parse errors */ }
      };
      es.onerror = () => { /* auto-reconnect built into EventSource */ };
    } catch { /* EventSource not supported */ }
    return () => { if (es) es.close(); };
  }, []);

  return (
    <RefreshContext.Provider
      value={{ refreshTick, intervalMinutes, setIntervalMinutes, realtimeSummary, forceRefresh, isRefreshing }}
    >
      {children}
    </RefreshContext.Provider>
  );
}
