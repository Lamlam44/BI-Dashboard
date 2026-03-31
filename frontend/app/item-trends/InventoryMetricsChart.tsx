'use client';

import { useEffect, useState } from 'react';
import axios from 'axios';
import { useRefresh } from '../components/RefreshProvider';
import { API_BASE_URL } from '../lib/api';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';

interface InvItem {
  ProductKey: number;
  ProductName: string;
  inventory_turnover: number;
  sell_through_rate: number;
  gmroi: number;
  days_of_supply: number;
}

export default function InventoryMetricsChart() {
  const { refreshTick } = useRefresh();
  const [items, setItems] = useState<InvItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    setLoading(true);
    setEmpty(false);
    axios.get(`${API_BASE_URL}/trends/api/inventory-metrics`)
      .then(res => {
        const d = res.data;
        if (d.status === 'success' && d.data?.length) {
          setItems(d.data);
        } else {
          setEmpty(true);
        }
      })
      .catch(() => setEmpty(true))
      .finally(() => setLoading(false));
  }, [refreshTick]);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <p className="text-slate-400">Đang tải Inventory Metrics...</p>
      </div>
    );
  }

  if (empty || !items.length) {
    return (
      <div className="bg-white rounded-xl border border-amber-200 p-6 shadow-sm bg-amber-50 text-amber-700">
        <p className="font-semibold">Inventory Metrics chưa khả dụng</p>
        <p className="text-sm mt-1">
          Bảng <code>agg_inventory_metrics</code> chưa được build do query trên FactInventory (8M rows) rất nặng.
          ETL sẽ tự động build khi hệ thống khởi động lần tiếp theo.
        </p>
      </div>
    );
  }

  const chartData = items.slice(0, 15).map(i => ({
    name: i.ProductName.length > 25 ? i.ProductName.slice(0, 22) + '...' : i.ProductName,
    fullName: i.ProductName,
    turnover: Number(i.inventory_turnover) || 0,
    gmroi: Number(i.gmroi) || 0,
    sellThrough: (Number(i.sell_through_rate) * 100) || 0,
  }));

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Chỉ số Kho hàng</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
            <p className="text-sm text-blue-600 font-medium">TB Inventory Turnover</p>
            <p className="text-2xl font-bold text-blue-900">
              {(items.reduce((s, i) => s + Number(i.inventory_turnover), 0) / items.length).toFixed(2)}x
            </p>
          </div>
          <div className="bg-green-50 rounded-lg p-4 border border-green-200">
            <p className="text-sm text-green-600 font-medium">TB GMROI</p>
            <p className="text-2xl font-bold text-green-900">
              {(items.reduce((s, i) => s + Number(i.gmroi), 0) / items.length).toFixed(2)}
            </p>
          </div>
          <div className="bg-purple-50 rounded-lg p-4 border border-purple-200">
            <p className="text-sm text-purple-600 font-medium">TB Sell-Through Rate</p>
            <p className="text-2xl font-bold text-purple-900">
              {((items.reduce((s, i) => s + Number(i.sell_through_rate), 0) / items.length) * 100).toFixed(1)}%
            </p>
          </div>
        </div>

        {/* Bar chart */}
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ left: 10, right: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-35} textAnchor="end" interval={0} />
              <YAxis />
              <Tooltip
                labelFormatter={(label) => {
                  const item = chartData.find(c => c.name === String(label));
                  return item?.fullName || String(label);
                }}
              />
              <Legend />
              <Bar dataKey="turnover" name="Inventory Turnover" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="gmroi" name="GMROI" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Chi tiết Inventory (Top 20)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-600">
                <th className="py-2 px-3">#</th>
                <th className="py-2 px-3">Sản phẩm</th>
                <th className="py-2 px-3 text-right">Turnover</th>
                <th className="py-2 px-3 text-right">Sell-Through</th>
                <th className="py-2 px-3 text-right">GMROI</th>
                <th className="py-2 px-3 text-right">Days of Supply</th>
              </tr>
            </thead>
            <tbody>
              {items.slice(0, 20).map((item, idx) => (
                <tr key={item.ProductKey} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="py-2 px-3 text-slate-500">{idx + 1}</td>
                  <td className="py-2 px-3 font-medium text-slate-900 max-w-xs truncate">{item.ProductName}</td>
                  <td className="py-2 px-3 text-right">{Number(item.inventory_turnover).toFixed(2)}</td>
                  <td className="py-2 px-3 text-right">{(Number(item.sell_through_rate) * 100).toFixed(1)}%</td>
                  <td className="py-2 px-3 text-right">{Number(item.gmroi).toFixed(2)}</td>
                  <td className="py-2 px-3 text-right">{Number(item.days_of_supply).toFixed(0)} ngày</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
