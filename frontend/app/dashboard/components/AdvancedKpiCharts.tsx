'use client';

import { useEffect, useState } from 'react';
import api, { API_BASE_URL } from '../../lib/api';
import { useRefresh } from '../../components/RefreshProvider';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from 'recharts';

const fmtMoney = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

/* ─── Sales per Sq Ft ──────────────────────────────── */
interface SqftStore {
  store_key: number;
  store_name: string;
  selling_area_size: number;
  net_sales: number;
  sales_per_sqft: number;
}

interface DateFilterProps {
  startDate?: string | null;
  endDate?: string | null;
}

export function SalesPerSqftChart({ startDate, endDate }: DateFilterProps = {}) {
  const { refreshTick } = useRefresh();
  const [stores, setStores] = useState<SqftStore[]>([]);
  const [avg, setAvg] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    api.get(`${API_BASE_URL}/sale-profit/api/sales-per-sqft`, { params })
      .then(res => {
        if (res.data.status === 'success') {
          setStores(res.data.stores.slice(0, 15));
          setAvg(res.data.avg_sales_per_sqft);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick, startDate, endDate]);

  if (loading) return <div className="animate-pulse h-64 bg-slate-100 rounded-lg" />;
  if (!stores.length) return null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">Sales per Square Foot</h2>
        <span className="text-sm text-slate-500">Avg: <strong>{fmtMoney(avg)}</strong>/sqft</span>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={stores} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `$${Math.round(v)}`} />
            <YAxis type="category" dataKey="store_name" width={120} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: any) => fmtMoney(Number(v))} />
            <Bar dataKey="sales_per_sqft" name="$/sqft" fill="#6366f1" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ─── Budget vs Actual ─────────────────────────────── */
interface BudgetStore {
  store_key: number;
  store_name: string;
  actual_sales: number;
  budget_sales: number;
  attainment_pct: number;
}

export function BudgetVsActualChart({ startDate, endDate }: DateFilterProps = {}) {
  const { refreshTick } = useRefresh();
  const [stores, setStores] = useState<BudgetStore[]>([]);
  const [overall, setOverall] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    api.get(`${API_BASE_URL}/sale-profit/api/budget-vs-actual`, { params })
      .then(res => {
        if (res.data.status === 'success') {
          setStores(res.data.stores.slice(0, 10));
          setOverall(res.data.overall_attainment);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick, startDate, endDate]);

  if (loading) return <div className="animate-pulse h-64 bg-slate-100 rounded-lg" />;
  if (!stores.length) return null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">Budget vs Actual</h2>
        <span className={`text-sm font-semibold ${overall >= 100 ? 'text-green-600' : 'text-amber-600'}`}>
          Đạt: {overall}%
        </span>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={stores}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="store_name" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" height={60} />
            <YAxis tickFormatter={(v) => `${Math.round(v / 1_000_000)}M`} />
            <Tooltip formatter={(v: any) => fmtMoney(Number(v))} />
            <Legend />
            <Bar dataKey="budget_sales" name="Budget" fill="#94a3b8" radius={[4, 4, 0, 0]} />
            <Bar dataKey="actual_sales" name="Actual" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ─── Stockout Rate ────────────────────────────────── */
interface StockoutData {
  stockout_rate: number;
  stockout_count: number;
  total_count: number;
  top_stockouts: Array<{ ProductName: string; stores_affected: number }>;
}

const STOCKOUT_COLORS = ['#ef4444', '#22c55e'];

export function StockoutRateChart() {
  const { refreshTick } = useRefresh();
  const [data, setData] = useState<StockoutData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`${API_BASE_URL}/data/api/stockout-rate`)
      .then(res => {
        if (res.data.status === 'success') setData(res.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick]);

  if (loading) return <div className="animate-pulse h-48 bg-slate-100 rounded-lg" />;
  if (!data) return null;

  const pieData = [
    { name: 'Stockout', value: data.stockout_count },
    { name: 'In Stock', value: data.total_count - data.stockout_count },
  ];

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">Stockout Rate</h2>
        <span
          title="Dữ liệu tồn kho là snapshot hiện tại, không phân tầng theo ngày"
          className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 border border-gray-300 px-3 py-1 text-xs font-medium text-gray-500 cursor-default select-none"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
          Không áp dụng bộ lọc thời gian
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={70} innerRadius={40}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={STOCKOUT_COLORS[i]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <p className="text-center text-2xl font-bold text-red-600">{data.stockout_rate}%</p>
        </div>
        <div>
          <p className="text-sm text-slate-500 mb-2">Top sản phẩm hết hàng:</p>
          <ul className="space-y-1 text-sm">
            {data.top_stockouts?.slice(0, 5).map((item, i) => (
              <li key={i} className="flex justify-between">
                <span className="truncate pr-2">{item.ProductName}</span>
                <span className="text-red-600 font-medium">{item.stores_affected} stores</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/* ─── Safety Stock ─────────────────────────────────── */
interface SafetyData {
  summary: {
    below_safety: number;
    near_safety: number;
    adequate: number;
    total: number;
  };
}

const SS_COLORS = ['#ef4444', '#f59e0b', '#22c55e'];

export function SafetyStockChart() {
  const { refreshTick } = useRefresh();
  const [data, setData] = useState<SafetyData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`${API_BASE_URL}/data/api/safety-stock`)
      .then(res => {
        if (res.data.status === 'success') setData(res.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick]);

  if (loading) return <div className="animate-pulse h-48 bg-slate-100 rounded-lg" />;
  if (!data) return null;

  const s = data.summary;
  const pieData = [
    { name: 'Below Safety', value: s.below_safety },
    { name: 'Near Safety', value: s.near_safety },
    { name: 'Adequate', value: s.adequate },
  ];

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">Safety Stock Analysis</h2>
        <span
          title="Dữ liệu tồn kho là snapshot hiện tại, không phân tầng theo ngày"
          className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 border border-gray-300 px-3 py-1 text-xs font-medium text-gray-500 cursor-default select-none"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 115.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
          Không áp dụng bộ lọc thời gian
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={70} innerRadius={40}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={SS_COLORS[i]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-3">
          {[
            { label: 'Dưới mức an toàn', count: s.below_safety, color: 'text-red-600' },
            { label: 'Gần mức an toàn', count: s.near_safety, color: 'text-amber-600' },
            { label: 'Đủ hàng', count: s.adequate, color: 'text-green-600' },
          ].map((item, i) => (
            <div key={i} className="flex justify-between items-center">
              <span className="text-sm text-slate-600">{item.label}</span>
              <span className={`font-bold ${item.color}`}>{item.count.toLocaleString()}</span>
            </div>
          ))}
          <div className="pt-2 border-t border-slate-200">
            <div className="flex justify-between items-center">
              <span className="text-sm font-medium text-slate-700">Tổng</span>
              <span className="font-bold text-slate-900">{s.total.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
