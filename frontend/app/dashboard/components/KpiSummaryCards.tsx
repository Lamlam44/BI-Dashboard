'use client';

import { useEffect, useState } from 'react';
import api, { API_BASE_URL } from '../../lib/api';
import { useRefresh } from '../../components/RefreshProvider';

interface KpiData {
  total_revenue: number;
  total_transactions: number;
  avg_transaction_value: number;
  avg_basket_size: number;
  gross_margin: number;
  unique_customers: number;
  product_count: number;
  active_stores?: number;
}

interface KpiSummaryCardsProps {
  startDate?: string | null;
  endDate?: string | null;
}

const fmtMoney = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtNum = (v: number) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(v);

export default function KpiSummaryCards({ startDate, endDate }: KpiSummaryCardsProps = {}) {
  const { refreshTick } = useRefresh();
  const [kpis, setKpis] = useState<KpiData | null>(null);
  const [loading, setLoading] = useState(true);
  const isFiltered = !!(startDate || endDate);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    api.get(`${API_BASE_URL}/sale-profit/api/kpi-summary`, { params })
      .then(res => {
        const d = res.data;
        if (d.status === 'success' && d.kpis) {
          setKpis(d.kpis);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick, startDate, endDate]);

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(7)].map((_, i) => (
          <div key={i} className="bg-white rounded-lg border border-slate-200 p-4 animate-pulse h-24" />
        ))}
      </div>
    );
  }

  if (!kpis) return null;

  const cards = [
    {
      label: 'Tổng doanh thu',
      value: fmtMoney(kpis.total_revenue || 0),
      icon: '💰',
      color: 'border-blue-500',
    },
    {
      label: 'Tổng giao dịch',
      value: fmtNum(kpis.total_transactions || 0),
      icon: '🧾',
      color: 'border-purple-500',
    },
    {
      label: 'Giá trị TB / giao dịch',
      value: fmtMoney(kpis.avg_transaction_value || 0),
      icon: '🛒',
      color: 'border-green-500',
    },
    {
      label: 'Số lượng TB / đơn hàng',
      value: (kpis.avg_basket_size || 0).toFixed(1) + ' items',
      icon: '📦',
      color: 'border-orange-500',
    },
    {
      label: 'Biên lợi nhuận gộp',
      value: (kpis.gross_margin || 0).toFixed(1) + '%',
      icon: '📊',
      color: 'border-emerald-500',
    },
    {
      label: 'Khách hàng',
      value: fmtNum(kpis.unique_customers || 0),
      icon: '👥',
      color: 'border-cyan-500',
    },
    {
      label: 'Sản phẩm',
      value: fmtNum(kpis.product_count || 0),
      icon: '🏷️',
      color: 'border-rose-500',
    },
  ];

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-900">KPI Tổng Quan</h2>
        {!isFiltered && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-300 px-3 py-1 text-xs font-medium text-amber-700">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            Toàn thời gian — không áp dụng bộ lọc ngày
          </span>
        )}
        {isFiltered && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-300 px-3 py-1 text-xs font-medium text-blue-700">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
            </svg>
            Theo khoảng thời gian đã chọn
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4">
        {cards.map((c, idx) => (
          <div key={idx} className={`rounded-lg border-l-4 ${c.color} bg-slate-50 p-4`}>
            <div className="text-xl mb-1">{c.icon}</div>
            <p className="text-xs text-slate-500 font-medium">{c.label}</p>
            <p className="text-lg font-bold text-slate-900 mt-1">{c.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
