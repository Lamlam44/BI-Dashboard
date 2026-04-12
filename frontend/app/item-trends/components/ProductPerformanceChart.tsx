'use client';

import { useEffect, useState } from 'react';
import axios from 'axios';
import { useRefresh } from '../../components/RefreshProvider';
import { API_BASE_URL } from '../../lib/api';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';

interface Product {
  ProductKey: number;
  ProductName: string;
  total_revenue: number;
  total_quantity: number;
  gross_profit: number;
  profit_margin: number;
  abc_class: string;
  revenue_rank: number;
}

interface AbcItem {
  abc_class: string;
  product_count: number;
  class_revenue: number;
}

const ABC_COLORS: Record<string, string> = { A: '#22c55e', B: '#f59e0b', C: '#ef4444' };

const fmtMoney = (v: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

const fmtShort = (v: number) => {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

export default function ProductPerformanceChart() {
  const { refreshTick } = useRefresh();
  const [products, setProducts] = useState<Product[]>([]);
  const [abc, setAbc] = useState<AbcItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API_BASE_URL}/trends/api/product-performance`)
      .then(res => {
        const d = res.data;
        if (d.status === 'success') {
          setProducts(d.top_products || []);
          setAbc(d.abc_distribution || []);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [refreshTick]);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <p className="text-slate-400">Đang tải Product Performance...</p>
      </div>
    );
  }

  if (!products.length) {
    return (
      <div className="bg-white rounded-xl border border-amber-200 p-6 shadow-sm bg-amber-50 text-amber-700">
        Chưa có dữ liệu Product Performance. Vui lòng chạy ETL pipeline.
      </div>
    );
  }

  const top10 = products.slice(0, 10).map(p => ({
    name: p.ProductName.length > 30 ? p.ProductName.slice(0, 27) + '...' : p.ProductName,
    fullName: p.ProductName,
    revenue: p.total_revenue,
    profit: p.gross_profit,
    abc: p.abc_class,
  }));

  const pieData = abc.map(a => ({
    name: `Class ${a.abc_class}`,
    value: a.product_count,
    revenue: a.class_revenue,
  }));

  const totalProducts = abc.reduce((s, a) => s + a.product_count, 0);

  return (
    <div className="space-y-6">
      {/* ABC Distribution Summary */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Phân loại ABC sản phẩm</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Pie chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={100} label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}>
                  {pieData.map((item, idx) => (
                    <Cell key={idx} fill={ABC_COLORS[item.name.replace('Class ', '')] || '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: any, name: any, props: any) => [
                  `${v} sản phẩm (${fmtMoney(props.payload.revenue)})`, name
                ]} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* ABC Cards */}
          <div className="space-y-3">
            {abc.map(a => (
              <div key={a.abc_class} className="flex items-center gap-4 bg-slate-50 rounded-lg p-4 border border-slate-200">
                <div
                  className="w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-lg"
                  style={{ backgroundColor: ABC_COLORS[a.abc_class] || '#94a3b8' }}
                >
                  {a.abc_class}
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-slate-900">
                    Class {a.abc_class} — {a.product_count} sản phẩm
                    <span className="text-slate-500 font-normal text-sm ml-2">
                      ({((a.product_count / totalProducts) * 100).toFixed(1)}%)
                    </span>
                  </p>
                  <p className="text-sm text-slate-600">Doanh thu: {fmtMoney(a.class_revenue)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top 10 Products Bar Chart */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Top 10 sản phẩm theo doanh thu</h2>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={top10} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => fmtShort(v)} />
              <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(v: any) => fmtMoney(Number(v))}
                labelFormatter={(label) => {
                  const item = top10.find(p => p.name === String(label));
                  return item?.fullName || String(label);
                }}
              />
              <Legend />
              <Bar dataKey="revenue" name="Doanh thu" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              <Bar dataKey="profit" name="Lợi nhuận" fill="#22c55e" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Product Table */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Chi tiết sản phẩm (Top 20)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-600">
                <th className="py-2 px-3">#</th>
                <th className="py-2 px-3">Sản phẩm</th>
                <th className="py-2 px-3 text-right">Doanh thu</th>
                <th className="py-2 px-3 text-right">Số lượng</th>
                <th className="py-2 px-3 text-right">Lợi nhuận</th>
                <th className="py-2 px-3 text-right">Biên LN</th>
                <th className="py-2 px-3 text-center">ABC</th>
              </tr>
            </thead>
            <tbody>
              {products.slice(0, 20).map((p, idx) => (
                <tr key={p.ProductKey} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="py-2 px-3 text-slate-500">{p.revenue_rank}</td>
                  <td className="py-2 px-3 font-medium text-slate-900 max-w-xs truncate">{p.ProductName}</td>
                  <td className="py-2 px-3 text-right">{fmtMoney(p.total_revenue)}</td>
                  <td className="py-2 px-3 text-right">{Math.round(p.total_quantity).toLocaleString()}</td>
                  <td className="py-2 px-3 text-right text-green-600">{fmtMoney(p.gross_profit)}</td>
                  <td className="py-2 px-3 text-right">{(p.profit_margin * 100).toFixed(1)}%</td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-white text-xs font-bold"
                      style={{ backgroundColor: ABC_COLORS[p.abc_class] || '#94a3b8' }}
                    >
                      {p.abc_class}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
