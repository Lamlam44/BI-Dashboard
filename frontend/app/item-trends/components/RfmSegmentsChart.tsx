'use client';
import { useEffect, useState } from 'react';
import { useRefresh } from '../../components/RefreshProvider';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { API_BASE_URL } from '../../lib/api';

interface RfmSegment {
  rfm_segment: string;
  customer_count: number;
  avg_monetary: number;
  avg_recency: number;
}

const SEGMENT_COLORS: Record<string, string> = {
  Champion: '#22c55e',
  Loyal: '#3b82f6',
  'Potential Loyalist': '#8b5cf6',
  'New Customer': '#06b6d4',
  'Need Attention': '#f59e0b',
  'At Risk': '#f97316',
  Lost: '#ef4444',
};

const formatMoney = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

export default function RfmSegmentsChart() {
  const { refreshTick } = useRefresh();
  const [segments, setSegments] = useState<RfmSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE_URL}/data/api/rfm-segments`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === 'success' && data.segments) {
          setSegments(
            data.segments.map((s: any) => ({
              ...s,
              customer_count: Number(s.customer_count),
              avg_monetary: Number(s.avg_monetary),
              avg_recency: Number(s.avg_recency),
            })),
          );
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('RFM fetch error:', err);
        setError('Khong the tai du lieu RFM.');
        setLoading(false);
      });
  }, [refreshTick]);

  if (loading) return <p className="text-center p-6 text-gray-500">Dang tai du lieu RFM...</p>;
  if (error) return <div className="p-4 bg-red-50 rounded-lg border border-red-200 text-red-700 text-sm">{error}</div>;
  if (segments.length === 0) return <div className="p-4 bg-amber-50 rounded-lg border border-amber-200 text-amber-700 text-sm">RFM aggregate chua duoc tao. Hay chay ETL pipeline truoc.</div>;

  const totalCustomers = segments.reduce((s, r) => s + r.customer_count, 0);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h2 className="text-lg font-bold text-gray-800 mb-4">RFM Customer Segmentation (Advanced)</h2>

      {/* Bar chart */}
      <div className="h-64 mb-6">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={segments} layout="vertical" margin={{ left: 100 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis type="category" dataKey="rfm_segment" tick={{ fontSize: 12 }} width={100} />
            <Tooltip
              formatter={(value: unknown) => Number(value || 0).toLocaleString()}
              labelFormatter={(label) => `Segment: ${label}`}
            />
            <Bar dataKey="customer_count" name="Customers" radius={[0, 4, 4, 0]}>
              {segments.map((s) => (
                <Cell key={s.rfm_segment} fill={SEGMENT_COLORS[s.rfm_segment] || '#94a3b8'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Segment cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {segments.map((s) => {
          const pct = totalCustomers ? ((s.customer_count / totalCustomers) * 100).toFixed(1) : '0';
          return (
            <div
              key={s.rfm_segment}
              className="border border-slate-200 rounded-lg p-3"
              style={{ borderLeftColor: SEGMENT_COLORS[s.rfm_segment] || '#94a3b8', borderLeftWidth: 4 }}
            >
              <p className="font-semibold text-sm text-slate-800">{s.rfm_segment}</p>
              <p className="text-xs text-slate-500 mt-1">
                {s.customer_count.toLocaleString()} ({pct}%)
              </p>
              <p className="text-xs text-slate-500">Avg spend: {formatMoney(s.avg_monetary)}</p>
              <p className="text-xs text-slate-500">Avg recency: {Math.round(s.avg_recency)}d</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
