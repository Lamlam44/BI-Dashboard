"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ExportPDFButton from '../components/ExportPDFButton';
import DashboardLayout from '../components/DashboardLayout';
import Section from '../components/Section';
import { useRefresh } from '../components/RefreshProvider';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import KpiSummaryCards from './KpiSummaryCards';
import { SalesPerSqftChart, BudgetVsActualChart, StockoutRateChart, SafetyStockChart } from './AdvancedKpiCharts';
import { authHeaders } from '../lib/api';
import { useAuth } from '../store/useAuth';

/* ── Types ──────────────────────────────────────────── */
type DashRes = {
  status: 'success' | 'empty' | 'error'; message?: string;
  ytd: number; mtd: number; total: number;
  ytd_profit: number; mtd_profit: number; total_profit: number;
  avg_profit_margin: number; yoy_growth: number; mom_growth: number;
  trend: { labels: string[]; data: number[] };
  profit_trend: { labels: string[]; data: number[] };
  store_pie: { labels: string[]; data: number[] };
  last_updated: string | null;
};
type ChRes = {
  status: string;
  channels: { channel: string; revenue: number; profit: number; transactions: number; share_pct: number }[];
  total_revenue: number;
};

/* ── Helpers ────────────────────────────────────────── */
import { API_BASE_URL } from '../lib/api';
const PIE_COLORS = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#14b8a6', '#64748b'];

const fmt$ = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v || 0);
const fmtPct = (v: number) => `${((v || 0) * 100).toFixed(1)}%`;
const tip$ = (v: unknown) => fmt$(typeof v === 'number' ? v : Number(v || 0));

async function fetchJ<T>(url: string, ms = 120_000): Promise<T> {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try {
    const r = await fetch(url, { signal: c.signal, headers: authHeaders() });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally { clearTimeout(t); }
}

/* ── Alert border for KPI cards ─────────────────────── */
const alertBdr = (t: string, v: number) =>
  t === 'margin' ? (v > 0.2 ? 'border-l-green-500' : v > 0.1 ? 'border-l-amber-500' : 'border-l-red-500')
  : t === 'growth' ? (v >= 0 ? 'border-l-green-500' : 'border-l-red-500')
  : 'border-l-blue-500';

/* ── Time-filter presets ────────────────────────────── */
type PK = 'all' | 'ytd' | '12m' | '6m' | '3m' | '1m' | 'custom';
const PRESETS: { key: PK; label: string }[] = [
  { key: 'all', label: 'Tất cả' }, { key: 'ytd', label: 'YTD' },
  { key: '12m', label: '12 tháng' }, { key: '6m', label: '6 tháng' },
  { key: '3m', label: '3 tháng' }, { key: '1m', label: '1 tháng' },
  { key: 'custom', label: 'Tùy chọn' },
];

function toRange(k: PK) {
  if (k === 'all') return { start: null as string | null, end: null as string | null };
  const now = new Date(), end = now.toISOString().slice(0, 10), d = new Date(now);
  if (k === 'ytd') d.setMonth(0, 1);
  else if (k === '12m') d.setMonth(d.getMonth() - 12);
  else if (k === '6m') d.setMonth(d.getMonth() - 6);
  else if (k === '3m') d.setMonth(d.getMonth() - 3);
  else if (k === '1m') d.setMonth(d.getMonth() - 1);
  else return { start: null, end: null };
  return { start: d.toISOString().slice(0, 10), end };
}

/* ════════════════════════════════════════════════════
   MAIN COMPONENT
   ════════════════════════════════════════════════════ */
export default function Dashboard() {
  const { refreshTick, realtimeSummary } = useRefresh();
  const { user } = useAuth();
  const role = user?.role || 'store_manager';
  const showMultiStore = role !== 'store_manager';
  const showGlobal = role === 'executive' || role === 'admin';

  const [data, setData] = useState<DashRes | null>(null);
  const [chData, setChData] = useState<ChRes | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* time filter */
  const [preset, setPreset] = useState<PK>('all');
  const [cStart, setCStart] = useState('');
  const [cEnd, setCEnd] = useState('');
  const dr = useMemo(() =>
    preset === 'custom' ? { start: cStart || null, end: cEnd || null } : toRange(preset),
  [preset, cStart, cEnd]);

  const qs = useCallback((b: string) => {
    const p = new URLSearchParams();
    if (dr.start) p.set('start_date', dr.start);
    if (dr.end) p.set('end_date', dr.end);
    const s = p.toString();
    return s ? `${b}?${s}` : b;
  }, [dr]);

  /* drill-down state */
  const reportRef = useRef<HTMLDivElement>(null);

  const [drillYear, setDrillYear] = useState<string | null>(null);
  /* rolling average toggle */
  const [showMA, setShowMA] = useState(false);
  /* what-if sliders */
  const [revDelta, setRevDelta] = useState(0);
  const [costDelta, setCostDelta] = useState(0);

  /* ── Fetch ── */
  useEffect(() => {
    let ok = true;
    (async () => {
      setLoading(true); setError(null);
      try {
        const [s, c] = await Promise.all([
          fetchJ<DashRes>(qs(`${API_BASE_URL}/sale-profit/api/dashboard/sales`), 180_000),
          showGlobal ? fetchJ<ChRes>(qs(`${API_BASE_URL}/sale-profit/api/channels`), 60_000).catch(() => null) : null,
        ]);
        if (ok) { setData(s); if (c) setChData(c); }
      } catch (e) { if (ok) setError((e as Error).message); }
      finally { if (ok) setLoading(false); }
    })();
    return () => { ok = false; };
  }, [refreshTick, qs, showGlobal]);

  /* ── Derived data ── */
  const trendRows = useMemo(() => {
    const l = data?.trend?.labels || [], s = data?.trend?.data || [], p = data?.profit_trend?.data || [];
    return l.map((d, i) => ({ date: d, sales: s[i] || 0, profit: p[i] || 0 }));
  }, [data]);

  /* Drill-down: yearly aggregation */
  const yearRows = useMemo(() => {
    const m = new Map<string, { sales: number; profit: number }>();
    trendRows.forEach(r => {
      const y = r.date.slice(0, 4), c = m.get(y) || { sales: 0, profit: 0 };
      m.set(y, { sales: c.sales + r.sales, profit: c.profit + r.profit });
    });
    return Array.from(m, ([date, v]) => ({ date, ...v })).sort((a, b) => a.date.localeCompare(b.date));
  }, [trendRows]);

  /* Drill-down: month rows for selected year */
  const monthRows = useMemo(() =>
    drillYear ? trendRows.filter(r => r.date.startsWith(drillYear)) : [],
  [trendRows, drillYear]);

  /* Chart data with rolling average */
  const chartData = useMemo(() => {
    const rows = drillYear ? monthRows : yearRows;
    return rows.map((r, i, a) => {
      const w = a.slice(Math.max(0, i - 2), i + 1);
      return { ...r, ma: Math.round(w.reduce((s, x) => s + x.sales, 0) / w.length) };
    });
  }, [drillYear, monthRows, yearRows]);

  const pieRows = useMemo(() => {
    const l = data?.store_pie?.labels || [], v = data?.store_pie?.data || [];
    return l.map((n, i) => ({ name: String(n), value: v[i] || 0 }));
  }, [data]);

  /* What-If projected values */
  const wif = useMemo(() => {
    const rev = data?.total || 0, prof = data?.total_profit || 0, cost = rev - prof;
    const nRev = rev * (1 + revDelta / 100), nCost = cost * (1 + costDelta / 100), nProf = nRev - nCost;
    return { rev: nRev, prof: nProf, margin: nRev ? nProf / nRev : 0, dRev: nRev - rev, dProf: nProf - prof };
  }, [data, revDelta, costDelta]);

  const ok = !loading && !error && data && data.status !== 'empty';

  /* ── RENDER ── */
  const filterLabel = preset === 'all' ? 'Toàn thời gian'
    : preset === 'custom' ? `${cStart || '?'} → ${cEnd || '?'}`
    : PRESETS.find(p => p.key === preset)?.label || preset;

  return (
    <DashboardLayout>
      <div className="space-y-5" ref={reportRef}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Bảng Điều Khiển Doanh Thu & Lợi Nhuận</h1>
            <p className="text-slate-500 text-sm">Tổng quan doanh thu, lợi nhuận và phân tích kinh doanh</p>
          </div>
          <ExportPDFButton
            generateBlob={async () => {
              const { generateSalesPDFBlob } = await import('../components/pdf/SalesProfitPDFDoc');
              return generateSalesPDFBlob({
                data: data!,
                chData,
                trendRows,
                pieRows,
                filterLabel,
                username: user?.display_name || user?.username,
                role,
              });
            }}
            filename="sales-profit-dashboard"
            disabled={!ok}
          />
        </div>

        {/* ═══ TIME FILTER ═══ */}
        <Section title="⏱ Bộ lọc Thời gian" badge="Áp dụng cho tất cả mục bên dưới (trừ Tồn kho)">
          <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map(p => (
              <button key={p.key} onClick={() => { setPreset(p.key); setDrillYear(null); }}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                  preset === p.key ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
                {p.label}
              </button>
            ))}
            {preset === 'custom' && (
              <div className="flex items-center gap-2 ml-2">
                <input type="date" value={cStart} onChange={e => setCStart(e.target.value)}
                  className="border border-slate-300 rounded px-2 py-1 text-sm" />
                <span className="text-slate-400">→</span>
                <input type="date" value={cEnd} onChange={e => setCEnd(e.target.value)}
                  className="border border-slate-300 rounded px-2 py-1 text-sm" />
              </div>
            )}
          </div>
        </Section>

        {loading && <p className="text-sm text-slate-500">Đang tải dữ liệu...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {/* ═══ REALTIME TODAY ═══ */}
        {showGlobal && realtimeSummary && (
          <Section title="🟢 Dữ liệu Real-time Hôm nay" badge={`SSE • ${realtimeSummary.last_updated ? new Date(realtimeSummary.last_updated).toLocaleTimeString() : ''}`}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {([
                ['Today Revenue', fmt$(realtimeSummary.today_revenue)],
                ['Today Profit', fmt$(realtimeSummary.today_profit)],
                ['Today Orders', realtimeSummary.today_orders.toLocaleString()],
                ['Items Sold', realtimeSummary.today_items_sold.toLocaleString()],
                ['MTD Revenue', fmt$(realtimeSummary.mtd_revenue)],
                ['MTD Profit', fmt$(realtimeSummary.mtd_profit)],
              ] as [string, string][]).map(([l, v]) => (
                <div key={l} className="bg-blue-50 rounded-lg p-3 text-center">
                  <p className="text-xs text-slate-500">{l}</p>
                  <p className="text-lg font-bold text-slate-900">{v}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {!loading && !error && data?.status === 'empty' && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">
            {data.message || 'Không có dữ liệu.'}
          </div>
        )}

        {ok && (
          <>
            {/* ═══ CORE KPIs WITH ALERT COLORS ═══ */}
            <Section title="📊 Chỉ số Kinh doanh Chính (KPIs)" badge="🔗 Lọc theo thời gian">
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                {([
                  { t: 'YTD Sales', v: fmt$(data!.ytd), a: alertBdr('default', 0) },
                  { t: 'Total Profit', v: fmt$(data!.total_profit), a: alertBdr('default', 0) },
                  { t: 'Profit Margin', v: fmtPct(data!.avg_profit_margin), a: alertBdr('margin', data!.avg_profit_margin) },
                  { t: 'YoY Growth', v: `${data!.yoy_growth >= 0 ? '+' : ''}${data!.yoy_growth.toFixed(1)}%`, a: alertBdr('growth', data!.yoy_growth) },
                  { t: 'MoM Growth', v: `${data!.mom_growth >= 0 ? '+' : ''}${data!.mom_growth.toFixed(1)}%`, a: alertBdr('growth', data!.mom_growth) },
                  { t: 'Last Updated', v: data!.last_updated || 'N/A', a: 'border-l-slate-400' },
                ]).map((c, i) => (
                  <div key={i} className={`bg-white rounded-lg border border-slate-200 border-l-4 ${c.a} p-4`}>
                    <p className="text-xs text-slate-500">{c.t}</p>
                    <p className="text-xl font-bold mt-1">{c.v}</p>
                  </div>
                ))}
              </div>
              {showGlobal && <KpiSummaryCards startDate={dr.start} endDate={dr.end} />}
            </Section>

            {/* ═══ TREND + DRILL-DOWN + TIME INTELLIGENCE ═══ */}
            <Section title="📈 Xu hướng Doanh thu (Drill-Down)" badge="🔗 Lọc theo thời gian • Click cột để khoan sâu">
              {/* Breadcrumb + MA toggle */}
              <div className="flex items-center gap-2 text-sm">
                <button onClick={() => setDrillYear(null)}
                  className={`px-2.5 py-1 rounded ${!drillYear ? 'bg-blue-100 text-blue-700 font-semibold' : 'text-blue-600 hover:underline'}`}>
                  📊 Tổng theo Năm
                </button>
                {drillYear && (
                  <>
                    <span className="text-slate-400">›</span>
                    <span className="bg-blue-100 text-blue-700 font-semibold px-2.5 py-1 rounded">📅 {drillYear}</span>
                  </>
                )}
                {drillYear && (
                  <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none">
                    <input type="checkbox" checked={showMA} onChange={e => setShowMA(e.target.checked)} className="rounded" />
                    Đường trung bình trượt (MA-3)
                  </label>
                )}
              </div>

              <div className="h-72">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    {!drillYear ? (
                      <BarChart data={chartData} onClick={(e: any) => { if (e?.activeLabel) setDrillYear(e.activeLabel); }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis tickFormatter={v => `${Math.round(v / 1_000_000)}M`} />
                        <Tooltip formatter={tip$} />
                        <Legend />
                        <Bar dataKey="sales" name="Doanh thu" fill="#2563eb" radius={[4, 4, 0, 0]} cursor="pointer" />
                        <Bar dataKey="profit" name="Lợi nhuận" fill="#16a34a" radius={[4, 4, 0, 0]} cursor="pointer" />
                      </BarChart>
                    ) : (
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tickFormatter={v => `${Math.round(v / 1000)}k`} />
                        <Tooltip formatter={tip$} />
                        <Legend />
                        <Line type="monotone" dataKey="sales" name="Doanh thu" stroke="#2563eb" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="profit" name="Lợi nhuận" stroke="#16a34a" strokeWidth={2} dot={false} />
                        {showMA && <Line type="monotone" dataKey="ma" name="MA-3" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 5" dot={false} />}
                      </LineChart>
                    )}
                  </ResponsiveContainer>
                ) : <div className="h-full flex items-center justify-center text-slate-400">Không có dữ liệu.</div>}
              </div>
              <p className="text-xs text-slate-400 text-center italic">
                {drillYear ? '↑ Click "Tổng theo Năm" để quay lại (Drill-Up)' : '↓ Click vào cột năm để xem chi tiết từng tháng (Drill-Down)'}
              </p>
            </Section>

            {/* ═══ WHAT-IF ANALYSIS ═══ */}
            <Section title="🔮 Phân tích What-If (Giả lập Kịch bản)" badge="Mô phỏng — không phụ thuộc bộ lọc">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Giả sử Doanh thu thay đổi:{' '}
                      <span className={revDelta >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {revDelta >= 0 ? '+' : ''}{revDelta}%
                      </span>
                    </label>
                    <input type="range" min={-50} max={50} value={revDelta}
                      onChange={e => setRevDelta(+e.target.value)} className="w-full mt-1 accent-blue-600" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Giả sử Chi phí thay đổi:{' '}
                      <span className={costDelta <= 0 ? 'text-green-600' : 'text-red-600'}>
                        {costDelta >= 0 ? '+' : ''}{costDelta}%
                      </span>
                    </label>
                    <input type="range" min={-50} max={50} value={costDelta}
                      onChange={e => setCostDelta(+e.target.value)} className="w-full mt-1 accent-blue-600" />
                  </div>
                  <button onClick={() => { setRevDelta(0); setCostDelta(0); }}
                    className="text-xs text-blue-600 hover:underline">↺ Reset về 0%</button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {([
                    { l: 'Doanh thu dự kiến', v: fmt$(wif.rev), d: wif.dRev },
                    { l: 'Lợi nhuận dự kiến', v: fmt$(wif.prof), d: wif.dProf },
                    { l: 'Biên LN dự kiến', v: `${(wif.margin * 100).toFixed(1)}%`, d: 0 },
                    { l: 'Doanh thu hiện tại', v: fmt$(data!.total), d: 0 },
                  ]).map((c, i) => (
                    <div key={i} className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                      <p className="text-xs text-slate-500">{c.l}</p>
                      <p className="text-lg font-bold">{c.v}</p>
                      {c.d !== 0 && (
                        <p className={`text-xs ${c.d >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {c.d >= 0 ? '+' : ''}{fmt$(c.d)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </Section>

            {/* ═══ STORE ANALYSIS ═══ */}
            {showMultiStore && (
              <Section title="🏪 Phân tích Cửa hàng" badge="🔗 Lọc theo thời gian">
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  <div className="bg-white rounded-lg border border-slate-200 p-5">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Stores by Sales</h3>
                    <div className="h-56">
                      {pieRows.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie data={pieRows} dataKey="value" nameKey="name" outerRadius={90}>
                              {pieRows.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                            </Pie>
                            <Tooltip formatter={tip$} />
                          </PieChart>
                        </ResponsiveContainer>
                      ) : <div className="h-full flex items-center justify-center text-slate-400">N/A</div>}
                    </div>
                    <div className="grid grid-cols-2 gap-1.5 text-xs mt-2">
                      {pieRows.slice(0, 6).map((r, i) => (
                        <div key={r.name} className="flex items-center justify-between bg-slate-50 rounded px-2 py-1.5 border border-slate-100">
                          <span className="flex items-center gap-1 truncate">
                            <span className="w-2 h-2 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                            <span className="truncate">{r.name}</span>
                          </span>
                          <span className="font-medium ml-1">{fmt$(r.value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <SalesPerSqftChart startDate={dr.start} endDate={dr.end} />
                </div>
                <BudgetVsActualChart startDate={dr.start} endDate={dr.end} />
              </Section>
            )}

            {/* ═══ CHANNEL BREAKDOWN ═══ */}
            {showGlobal && chData?.channels?.length ? (
              <Section title="🌐 Kênh Bán hàng (Online vs Offline)" badge={dr.start ? '🔗 Lọc theo thời gian' : 'Toàn thời gian'}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chData.channels}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="channel" />
                        <YAxis tickFormatter={v => `${Math.round(v / 1_000_000)}M`} />
                        <Tooltip formatter={tip$} />
                        <Legend />
                        <Bar dataKey="revenue" name="Revenue" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="profit" name="Profit" fill="#22c55e" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="space-y-3">
                    {chData.channels.map(ch => (
                      <div key={ch.channel} className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                        <div className="flex justify-between mb-1.5">
                          <span className="font-semibold text-sm">{ch.channel}</span>
                          <span className="text-sm font-medium text-blue-600">{ch.share_pct}%</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div><p className="text-slate-500">Revenue</p><p className="font-semibold">{fmt$(ch.revenue)}</p></div>
                          <div><p className="text-slate-500">Profit</p><p className="font-semibold">{fmt$(ch.profit)}</p></div>
                          <div><p className="text-slate-500">Txns</p><p className="font-semibold">{ch.transactions.toLocaleString()}</p></div>
                        </div>
                        <div className="mt-1.5 w-full bg-slate-200 rounded-full h-1.5">
                          <div className={`h-1.5 rounded-full ${ch.channel === 'Online' ? 'bg-blue-500' : 'bg-green-500'}`}
                            style={{ width: `${ch.share_pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </Section>
            ) : null}

            {/* ═══ INVENTORY (NOT TIME-FILTERED) ═══ */}
            {showGlobal && (
              <Section title="📦 Phân tích Tồn kho" badge="⚠ Snapshot hiện tại — Không áp dụng bộ lọc thời gian">
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  <StockoutRateChart />
                  <SafetyStockChart />
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
