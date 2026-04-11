"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import ExportPDFButton from "../components/ExportPDFButton";
import DashboardLayout from "../components/DashboardLayout";
import Section from "../components/Section";
import { useRefresh } from "../components/RefreshProvider";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Area,
} from "recharts";

type OverviewResponse = {
  forecast_total_demand: number;
  sku_count: number;
  abc_distribution: Record<string, number>;
  xyz_distribution: Record<string, number>;
  avg_daily_demand: number;
  horizon_days: number;
  last_data_date: string;
};

type AlertRow = {
  product_id: number;
  product_name: string;
  abc_class: string;
  xyz_class: string;
  mean_14: number;
  mean_90: number;
  spike_score: number;
  message: string;
};

type BulkRow = {
  product_id: number;
  product_name: string;
  category_key: number;
  abc_class: string;
  xyz_class: string;
  revenue: number;
  cv: number;
};

type ForecastPoint = {
  date: string;
  actual: number | null;
  predicted: number;
  upper_bound: number;
  lower_bound: number;
};

import { API_BASE_URL } from '../lib/api';
const API_BASE = `${API_BASE_URL}/forecast`;

async function fetchJsonWithTimeout(url: string, timeoutMs = 600000, options?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...(options || {}), signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

type ReadyResponse = {
  ready: boolean;
  recalculate_running?: boolean;
};

export default function ForecastingClient() {
  const { refreshTick } = useRefresh();
  const [horizonDays, setHorizonDays] = useState(14);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [bulkRows, setBulkRows] = useState<BulkRow[]>([]);
  const [selectedSku, setSelectedSku] = useState<number | null>(null);
  const [deepDiveData, setDeepDiveData] = useState<ForecastPoint[]>([]);
  const [deepDiveTitle, setDeepDiveTitle] = useState<string>("");

  const [abcFilter, setAbcFilter] = useState<string>("A");
  const [xyzFilter, setXyzFilter] = useState<string>("ALL");
  const reportRef = useRef<HTMLDivElement>(null);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = async () => {
    const res = await fetchJsonWithTimeout(`${API_BASE}/overview?horizon_days=${horizonDays}`, 600000);
    if (!res.ok) throw new Error("Không thể tải tổng quan");
    const data = await res.json();
    setOverview(data);
  };

  const loadAlerts = async () => {
    const res = await fetchJsonWithTimeout(`${API_BASE}/alerts?limit=20&abc_class=A`, 600000);
    if (!res.ok) throw new Error("Không thể tải cảnh báo");
    const data = await res.json();
    setAlerts(data.alerts || []);
  };

  const loadBulk = async () => {
    const params = new URLSearchParams();
    if (abcFilter !== "ALL") params.set("abc_class", abcFilter);
    if (xyzFilter !== "ALL") params.set("xyz_class", xyzFilter);
    params.set("limit", "300");

    const res = await fetchJsonWithTimeout(`${API_BASE}/bulk/query?${params.toString()}`, 600000);
    if (!res.ok) throw new Error("Không thể tải danh sách SKU");
    const data = await res.json();
    setBulkRows(data.items || []);
  };

  const loadDeepDive = async (productId: number, productName: string) => {
    const res = await fetchJsonWithTimeout(`${API_BASE}/forecast/${productId}?days_ahead=${horizonDays}`, 600000);
    if (!res.ok) throw new Error("Không thể tải dự báo chi tiết");
    const payload = await res.json();
    setDeepDiveData(payload.forecast_points || []);
    setDeepDiveTitle(`${productName} (SKU ${productId})`);
    setSelectedSku(productId);
  };

  const refreshAllLayers = async () => {
    await Promise.all([loadOverview(), loadAlerts(), loadBulk()]);
  };

  const waitForRecalculateDone = async () => {
    for (let i = 0; i < 60; i++) {
      const readyRes = await fetchJsonWithTimeout(`${API_BASE}/ready`, 600000);
      if (!readyRes.ok) throw new Error("Không thể kiểm tra trạng thái tính toán lại");
      const readyData = (await readyRes.json()) as ReadyResponse;
      if (!readyData.recalculate_running) return;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error("Đang tính toán quá lâu. Vui lòng thử lại sau.");
  };

  const recalculate = async () => {
    setIsRecalculating(true);
    setError(null);
    try {
      const res = await fetchJsonWithTimeout(`${API_BASE}/recalculate`, 600000, { method: "POST" });
      if (!res.ok) throw new Error("Tính toán lại thất bại");
      await waitForRecalculateDone();
      await refreshAllLayers();
    } catch (e: any) {
      setError(e.message || "Lỗi không xác định");
    } finally {
      setIsRecalculating(false);
    }
  };

  useEffect(() => {
    setIsLoadingData(true);
    setError(null);
    refreshAllLayers()
      .catch((e: any) => setError(e.message || "Lỗi không xác định"))
      .finally(() => setIsLoadingData(false));
  }, [horizonDays, refreshTick]);

  useEffect(() => {
    const syncRecalculateState = async () => {
      try {
        const readyRes = await fetchJsonWithTimeout(`${API_BASE}/ready`, 10000);
        if (!readyRes.ok) return;
        const readyData = (await readyRes.json()) as ReadyResponse;
        setIsRecalculating(Boolean(readyData.recalculate_running));
      } catch {
        // Keep current UI state on transient readiness check failures.
      }
    };

    syncRecalculateState();
  }, []);

  useEffect(() => {
    loadBulk().catch((e: any) => setError(e.message || "Lỗi không xác định"));
  }, [abcFilter, xyzFilter, refreshTick]);

  const chartData = useMemo(
    () =>
      deepDiveData.map((d) => ({
        date: d.date,
        predicted: Number(d.predicted ?? 0),
        upper: Number(d.upper_bound ?? 0),
        lower: Number(d.lower_bound ?? 0),
      })),
    [deepDiveData]
  );

  return (
    <DashboardLayout>
      <div className="space-y-8" ref={reportRef}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Trung Tâm Điều Khiển Dự Báo Nhu Cầu</h1>
            <p className="text-slate-600 mt-2">Quản lý theo mục tiêu và ngoại lệ cho hơn 2.000 SKU</p>
          </div>
          <div className="flex items-center gap-2">
            <ExportPDFButton
              generateBlob={async () => {
                const { generateForecastPDFBlob } = await import('../components/pdf/ForecastingPDFDoc');
                return generateForecastPDFBlob({
                  overview,
                  alerts,
                  bulkRows,
                  abcFilter,
                  xyzFilter,
                  horizonDays,
                  username: undefined,
                });
              }}
              filename="demand-forecasting"
              disabled={isLoadingData}
            />
            <button
              onClick={recalculate}
              disabled={isLoadingData || isRecalculating}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:bg-slate-400"
            >
              {isRecalculating ? "Đang tính toán lại..." : isLoadingData ? "Đang tải..." : "Tính toán lại tất cả"}
            </button>
          </div>
        </div>

        {error && <div className="bg-red-50 border border-red-200 text-red-600 p-3 rounded-lg">{error}</div>}

        <Section title="📊 Tổng quan Dự báo" badge="Horizon: ${horizonDays} ngày">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white border rounded-xl p-4">
              <p className="text-xs text-slate-500">Tổng nhu cầu dự báo ({horizonDays} ngày)</p>
              <p className="text-2xl font-bold text-slate-900">{overview?.forecast_total_demand?.toLocaleString() ?? "-"}</p>
            </div>
            <div className="bg-white border rounded-xl p-4">
              <p className="text-xs text-slate-500">Số lượng SKU</p>
              <p className="text-2xl font-bold text-slate-900">{overview?.sku_count?.toLocaleString() ?? "-"}</p>
            </div>
            <div className="bg-white border rounded-xl p-4">
              <p className="text-xs text-slate-500">Nhu cầu trung bình/ngày</p>
              <p className="text-2xl font-bold text-slate-900">{overview?.avg_daily_demand?.toLocaleString() ?? "-"}</p>
            </div>
            <div className="bg-white border rounded-xl p-4">
              <p className="text-xs text-slate-500">Ngày dữ liệu cuối</p>
              <p className="text-2xl font-bold text-slate-900">{overview?.last_data_date ?? "-"}</p>
            </div>
          </div>
        </Section>

        <Section title="🔥 Cảnh báo dị thường" badge="Sản phẩm loại A có biến động bất thường">
          <div className="overflow-auto max-h-72">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-slate-50">
                <tr>
                  <th className="text-left p-2">Mã SKU</th>
                  <th className="text-left p-2">Sản phẩm</th>
                  <th className="text-left p-2">Phân loại</th>
                  <th className="text-left p-2">TB 14 ngày</th>
                  <th className="text-left p-2">TB 90 ngày</th>
                  <th className="text-left p-2">Độ đột biến</th>
                  <th className="text-left p-2">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((r) => (
                  <tr key={r.product_id} className="border-t">
                    <td className="p-2">{r.product_id}</td>
                    <td className="p-2">{r.product_name}</td>
                    <td className="p-2">{r.abc_class}/{r.xyz_class}</td>
                    <td className="p-2">{r.mean_14.toFixed(2)}</td>
                    <td className="p-2">{r.mean_90.toFixed(2)}</td>
                    <td className="p-2 font-semibold text-rose-600">{r.spike_score.toFixed(2)}</td>
                    <td className="p-2">
                      <button
                        className="px-2 py-1 bg-indigo-600 text-white rounded"
                        onClick={() => loadDeepDive(r.product_id, r.product_name)}
                      >
                        Xem chi tiết
                      </button>
                    </td>
                  </tr>
                ))}
                {alerts.length === 0 && (
                  <tr className="border-t">
                    <td className="p-3 text-slate-500" colSpan={7}>
                      Chưa có cảnh báo. Dùng danh sách bên dưới để chọn SKU xem chi tiết.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="🔍 Lọc & Thao tác hàng loạt" badge="🔗 Lọc theo ABC/XYZ">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-slate-500 mb-1">ABC</label>
              <select className="border rounded p-2" value={abcFilter} onChange={(e) => setAbcFilter(e.target.value)}>
                <option value="ALL">ALL</option>
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">XYZ</label>
              <select className="border rounded p-2" value={xyzFilter} onChange={(e) => setXyzFilter(e.target.value)}>
                <option value="ALL">ALL</option>
                <option value="X">X</option>
                <option value="Y">Y</option>
                <option value="Z">Z</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Số ngày dự báo</label>
              <input
                type="number"
                value={horizonDays}
                min={1}
                max={60}
                className="border rounded p-2 w-24"
                onChange={(e) => setHorizonDays(Number(e.target.value))}
              />
            </div>
          </div>
          <p className="text-sm text-slate-600">Số SKU khớp: <b>{bulkRows.length}</b></p>

          <div className="overflow-auto max-h-80 border rounded-lg">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-slate-50">
                <tr>
                  <th className="text-left p-2">Mã SKU</th>
                  <th className="text-left p-2">Sản phẩm</th>
                  <th className="text-left p-2">Phân loại</th>
                  <th className="text-left p-2">Doanh thu</th>
                  <th className="text-left p-2">Hệ số CV</th>
                  <th className="text-left p-2">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {bulkRows.slice(0, 50).map((r) => (
                  <tr key={r.product_id} className="border-t">
                    <td className="p-2">{r.product_id}</td>
                    <td className="p-2">{r.product_name}</td>
                    <td className="p-2">{r.abc_class}/{r.xyz_class}</td>
                    <td className="p-2">{r.revenue.toLocaleString()}</td>
                    <td className="p-2">{r.cv.toFixed(3)}</td>
                    <td className="p-2">
                      <button
                        className="px-2 py-1 bg-indigo-600 text-white rounded"
                        onClick={() => loadDeepDive(r.product_id, r.product_name)}
                      >
                        Xem chi tiết
                      </button>
                    </td>
                  </tr>
                ))}
                {bulkRows.length === 0 && (
                  <tr className="border-t">
                    <td className="p-3 text-slate-500" colSpan={6}>Không có SKU phù hợp với bộ lọc hiện tại.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="📈 Dự báo Chi tiết" badge="Chọn SKU ở trên để xem dự báo chi tiết">
          {selectedSku ? (
            <>
              <p className="text-sm text-slate-600 mb-4">{deepDiveTitle}</p>
              <div style={{ width: "100%", height: 360 }}>
                <ResponsiveContainer>
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="upper" fill="#e2e8f0" stroke="none" fillOpacity={0.5} />
                    <Area type="monotone" dataKey="lower" fill="#ffffff" stroke="none" fillOpacity={1} />
                    <Line type="monotone" dataKey="predicted" stroke="#2563eb" strokeWidth={2.5} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="text-slate-500">Chọn một SKU từ danh sách bên trên để xem dự báo chi tiết.</div>
          )}
        </Section>
      </div>
    </DashboardLayout>
  );
}
