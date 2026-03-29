'use client';

import { useEffect, useState } from 'react';
import axios from 'axios';
import { useRefresh } from '../components/RefreshProvider';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

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

const fmtMoney = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtNum = (v: number) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(v);

export default function KpiSummaryCards() {
  const { refreshTick } = useRefresh();
  const [kpis, setKpis] = useState<KpiData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/sale-profit/api/kpi-summary`)
      .then(res => {
        const d = res.data;
        if (d.status === 'success' && d.kpis) {
          setKpis(d.kpis);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick]);

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
      <h2 className="text-lg font-bold text-slate-900 mb-4">KPI Tổng Quan</h2>
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
