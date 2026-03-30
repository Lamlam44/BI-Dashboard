"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useRefresh } from '../components/RefreshProvider';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import KpiSummaryCards from './KpiSummaryCards';
import { SalesPerSqftChart, BudgetVsActualChart, StockoutRateChart, SafetyStockChart } from './AdvancedKpiCharts';
import { authHeaders } from '../lib/api';
import { useAuth } from '../store/useAuth';

type SalesDashboardResponse = {
  status: 'success' | 'empty' | 'error';
  message?: string;
  ytd: number;
  mtd: number;
  total: number;
  ytd_profit: number;
  mtd_profit: number;
  total_profit: number;
  avg_profit_margin: number;
  yoy_growth: number;
  mom_growth: number;
  trend: {
    labels: string[];
    data: number[];
  };
  profit_trend: {
    labels: string[];
    data: number[];
  };
  store_pie: {
    labels: string[];
    data: number[];
  };
  last_updated: string | null;
};

type ChannelData = {
  channel: string;
  revenue: number;
  profit: number;
  transactions: number;
  share_pct: number;
};

type ChannelResponse = {
  status: string;
  channels: ChannelData[];
  total_revenue: number;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
const PIE_COLORS = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#14b8a6', '#64748b'];

const formatMoney = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);

const formatPercent = (value: number) => `${((value || 0) * 100).toFixed(1)}%`;

const tooltipMoney = (value: unknown) => {
  const parsed = typeof value === 'number' ? value : Number(value || 0);
  return formatMoney(Number.isFinite(parsed) ? parsed : 0);
};

async function fetchJsonWithTimeout<T>(url: string, timeoutMs = 120000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`Failed to load sales dashboard (${response.status})`);
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/* ── Time-filter presets ────────────────────────── */
type PresetKey = 'all' | 'ytd' | '12m' | '6m' | '3m' | '1m' | 'custom';
interface Preset { key: PresetKey; label: string }
const PRESETS: Preset[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'ytd', label: 'YTD' },
  { key: '12m', label: '12 tháng' },
  { key: '6m', label: '6 tháng' },
  { key: '3m', label: '3 tháng' },
  { key: '1m', label: '1 tháng' },
  { key: 'custom', label: 'Tùy chọn' },
];

function presetToRange(key: PresetKey): { start: string | null; end: string | null } {
  if (key === 'all') return { start: null, end: null };
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const d = new Date(now);
  switch (key) {
    case 'ytd':  d.setMonth(0, 1); break;
    case '12m':  d.setMonth(d.getMonth() - 12); break;
    case '6m':   d.setMonth(d.getMonth() - 6); break;
    case '3m':   d.setMonth(d.getMonth() - 3); break;
    case '1m':   d.setMonth(d.getMonth() - 1); break;
    default:     return { start: null, end: null };
  }
  return { start: d.toISOString().slice(0, 10), end };
}

const Dashboard = () => {
  const { refreshTick, realtimeSummary } = useRefresh();
  const { user } = useAuth();
  const role = user?.role || 'store_manager';
  const isStoreManager = role === 'store_manager';
  const isRegionalManager = role === 'regional_manager';
  const showMultiStoreCharts = !isStoreManager; // pie, sqft, budget
  const showGlobalCharts = role === 'executive' || role === 'admin'; // channel, stockout, safety, realtime, KPI agg
  const [data, setData] = useState<SalesDashboardResponse | null>(null);
  const [channelData, setChannelData] = useState<ChannelResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ── Time filter state ── */
  const [preset, setPreset] = useState<PresetKey>('all');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  const dateRange = useMemo(() => {
    if (preset === 'custom') return { start: customStart || null, end: customEnd || null };
    return presetToRange(preset);
  }, [preset, customStart, customEnd]);

  const buildQS = useCallback((base: string) => {
    const params = new URLSearchParams();
    if (dateRange.start) params.set('start_date', dateRange.start);
    if (dateRange.end) params.set('end_date', dateRange.end);
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  }, [dateRange]);

  useEffect(() => {
    let mounted = true;
    async function loadDashboard() {
      setLoading(true);
      setError(null);
      try {
        const [salesPayload, channelPayload] = await Promise.all([
          fetchJsonWithTimeout<SalesDashboardResponse>(
            buildQS(`${API_BASE_URL}/sale-profit/api/dashboard/sales`),
            180000,
          ),
          showGlobalCharts
            ? fetchJsonWithTimeout<ChannelResponse>(
                buildQS(`${API_BASE_URL}/sale-profit/api/channels`),
                60000,
              ).catch(() => null)
            : Promise.resolve(null),
        ]);
        if (mounted) {
          setData(salesPayload);
          if (channelPayload) setChannelData(channelPayload);
        }
      } catch (err) {
        if (mounted) {
          setError((err as Error).message);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadDashboard();
    return () => {
      mounted = false;
    };
  }, [refreshTick, buildQS]);

  const trendRows = useMemo(() => {
    const labels = data?.trend?.labels || [];
    const salesValues = data?.trend?.data || [];
    const profitValues = data?.profit_trend?.data || [];
    return labels.map((label, idx) => ({
      date: label,
      sales: salesValues[idx] || 0,
      profit: profitValues[idx] || 0,
    }));
  }, [data]);

  const pieRows = useMemo(() => {
    const labels = data?.store_pie?.labels || [];
    const values = data?.store_pie?.data || [];
    return labels.map((label, idx) => ({ name: String(label), value: values[idx] || 0 }));
  }, [data]);

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Sales & Profit</h1>
            <p className="text-slate-600 mt-1">
              Dashboard thong ke doanh thu theo ngay, YTD/MTD va ty trong theo cua hang
            </p>
          </div>
        </div>

        {/* ── Time Filter Bar ── */}
        <div className="flex flex-wrap items-center gap-2 bg-white border border-slate-200 rounded-lg px-4 py-3 shadow-sm">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => setPreset(p.key)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                preset === p.key
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {p.label}
            </button>
          ))}
          {preset === 'custom' && (
            <div className="flex items-center gap-2 ml-2">
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="border border-slate-300 rounded-md px-2 py-1 text-sm"
              />
              <span className="text-slate-400">→</span>
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="border border-slate-300 rounded-md px-2 py-1 text-sm"
              />
            </div>
          )}
        </div>

        {loading && <p className="text-sm text-slate-500">Loading sales dashboard...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {/* ── Realtime Today (SSE-driven) — executive & admin only ── */}
        {showGlobalCharts && realtimeSummary && (
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
              </span>
              <h2 className="text-sm font-semibold text-blue-800">
                Today Live &mdash; {realtimeSummary.metric_date}
              </h2>
              {realtimeSummary.last_updated && (
                <span className="ml-auto text-xs text-blue-500">
                  Updated {new Date(realtimeSummary.last_updated).toLocaleTimeString()}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                { label: 'Today Revenue', value: formatMoney(realtimeSummary.today_revenue) },
                { label: 'Today Profit', value: formatMoney(realtimeSummary.today_profit) },
                { label: 'Today Orders', value: realtimeSummary.today_orders.toLocaleString() },
                { label: 'Items Sold', value: realtimeSummary.today_items_sold.toLocaleString() },
                { label: 'MTD Revenue', value: formatMoney(realtimeSummary.mtd_revenue) },
                { label: 'MTD Profit', value: formatMoney(realtimeSummary.mtd_profit) },
              ].map((c) => (
                <div key={c.label} className="bg-white/70 rounded-lg p-3 text-center">
                  <p className="text-xs text-slate-500">{c.label}</p>
                  <p className="text-lg font-bold text-slate-900 mt-0.5">{c.value}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && !error && data?.status === 'empty' && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">
            {data.message || 'Du lieu sale_profit dang trong, vui long thu refresh cache.'}
          </div>
        )}

        {!loading && !error && (
          <>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {[
            {
              title: 'YTD Sales',
              value: formatMoney(data?.ytd || 0),
              subtitle: 'Year-to-date tong doanh thu',
            },
            {
              title: 'Total Profit',
              value: formatMoney(data?.total_profit || 0),
              subtitle: 'Tong loi nhuan (Sales - Cost)',
            },
            {
              title: 'Profit Margin',
              value: formatPercent(data?.avg_profit_margin || 0),
              subtitle: 'Bien loi nhuan trung binh',
            },
            {
              title: 'YoY Growth',
              value: `${(data?.yoy_growth || 0) >= 0 ? '+' : ''}${(data?.yoy_growth || 0).toFixed(1)}%`,
              subtitle: 'So voi cung ky nam truoc',
              color: (data?.yoy_growth || 0) >= 0 ? 'text-green-600' : 'text-red-600',
            },
            {
              title: 'MoM Growth',
              value: `${(data?.mom_growth || 0) >= 0 ? '+' : ''}${(data?.mom_growth || 0).toFixed(1)}%`,
              subtitle: 'So voi thang truoc',
              color: (data?.mom_growth || 0) >= 0 ? 'text-green-600' : 'text-red-600',
            },
            {
              title: 'Last Updated',
              value: data?.last_updated || 'N/A',
              subtitle: 'Ngay du lieu gan nhat',
            },
          ].map((card, idx) => (
            <div
              key={idx}
              className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow"
            >
              <p className="text-slate-600 text-sm font-medium">{card.title}</p>
              <p className={`text-xl font-bold mt-2 ${'color' in card && card.color ? card.color : 'text-slate-900'}`}>
                {card.value}
              </p>
              <p className="text-xs text-slate-500 mt-2">{card.subtitle}</p>
            </div>
          ))}
        </div>

        {/* KPI Summary from Aggregate Tables — executive & admin only */}
        {showGlobalCharts && (
          <KpiSummaryCards startDate={dateRange.start} endDate={dateRange.end} />
        )}

        <div className={`grid grid-cols-1 ${showMultiStoreCharts ? 'xl:grid-cols-2' : ''} gap-6`}>
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900 mb-4">Sales Trend</h2>
            <div className="h-72">
              {trendRows.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendRows}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={30} />
                    <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                    <Tooltip formatter={tooltipMoney} />
                    <Line type="monotone" dataKey="sales" stroke="#2563eb" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="profit" stroke="#16a34a" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-500">Khong co du lieu trend.</div>
              )}
            </div>
          </div>

          {/* Top Stores pie — hide for store_manager (only 1 store = meaningless) */}
          {showMultiStoreCharts && (
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900 mb-4">Top Stores by Sales</h2>
            <div className="h-72">
              {pieRows.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieRows} dataKey="value" nameKey="name" outerRadius={110}>
                      {pieRows.map((_, idx) => (
                        <Cell key={`store-${idx}`} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={tooltipMoney} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-500">Khong co du lieu store pie.</div>
              )}
            </div>

            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              {pieRows.slice(0, 6).map((row, idx) => (
                <div key={row.name} className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded px-3 py-2">
                  <span className="truncate pr-2">{row.name}</span>
                  <span className="font-semibold">{formatMoney(row.value)}</span>
                </div>
              ))}
            </div>
          </div>
          )}
        </div>

        {/* Channel Breakdown — executive & admin only */}
        {showGlobalCharts && channelData && channelData.channels && channelData.channels.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-slate-900">Channel Breakdown (Online vs Offline)</h2>
              {!(dateRange.start || dateRange.end) && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-300 px-3 py-1 text-xs font-medium text-amber-700">
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  Toàn thời gian — không áp dụng bộ lọc ngày
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={channelData.channels}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="channel" />
                    <YAxis tickFormatter={(v) => `${Math.round(v / 1_000_000)}M`} />
                    <Tooltip formatter={tooltipMoney} />
                    <Legend />
                    <Bar dataKey="revenue" name="Revenue" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="profit" name="Profit" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-3">
                {channelData.channels.map((ch) => (
                  <div key={ch.channel} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-semibold text-slate-900">{ch.channel}</span>
                      <span className="text-sm font-medium text-blue-600">{ch.share_pct}%</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <p className="text-slate-500">Revenue</p>
                        <p className="font-semibold">{formatMoney(ch.revenue)}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Profit</p>
                        <p className="font-semibold">{formatMoney(ch.profit)}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Transactions</p>
                        <p className="font-semibold">{ch.transactions.toLocaleString()}</p>
                      </div>
                    </div>
                    {/* Share bar */}
                    <div className="mt-2 w-full bg-slate-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${ch.channel === 'Online' ? 'bg-blue-500' : 'bg-green-500'}`}
                        style={{ width: `${ch.share_pct}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Advanced KPIs Row — hide for store_manager (single store = not meaningful) */}
        {showMultiStoreCharts && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <SalesPerSqftChart startDate={dateRange.start} endDate={dateRange.end} />
          <BudgetVsActualChart startDate={dateRange.start} endDate={dateRange.end} />
        </div>
        )}

        {/* Stockout & Safety Stock — executive & admin only (inventory metrics) */}
        {showGlobalCharts && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <StockoutRateChart />
          <SafetyStockChart />
        </div>
        )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
