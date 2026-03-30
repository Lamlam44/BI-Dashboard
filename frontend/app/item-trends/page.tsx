'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../store/useAuth';

import StatsCards from './StatsCards';
import CustomerChart from './CustomerChart';
import LocationChart from './LocationChart';
import TrendingProductsChart from './TrendingProductsChart';
import PromotionImpactChart from './PromotionImpactChart';
import RfmSegmentsChart from './RfmSegmentsChart';
import ProductPerformanceChart from './ProductPerformanceChart';
import InventoryMetricsChart from './InventoryMetricsChart';

const ALLOWED_ROLES = ['executive', 'regional_manager', 'store_manager', 'admin'];

const ItemTrends = () => {
  const router = useRouter();
  const { user } = useAuth();
  const isStoreManager = user?.role === 'store_manager';

  useEffect(() => {
    if (user && !ALLOWED_ROLES.includes(user.role)) {
      router.replace('/dashboard');
    }
  }, [user, router]);

  const [tempYear, setTempYear] = useState<string>('ALL');
  const [appliedYear, setAppliedYear] = useState<string>('ALL');

  const availableYears = ['2007', '2008', '2009'];

  const handleApplyFilter = () => {
    setAppliedYear(tempYear);
  };

  if (!user || !ALLOWED_ROLES.includes(user.role)) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-[60vh] text-slate-500">
          Đang chuyển hướng...
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">

        {/* HEADER */}
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Item Trends</h1>
          <p className="text-slate-600 mt-2">
            Analyze product performance and market trends
          </p>
        </div>

        {/* FILTER — hidden for store_manager (only inventory relevant) */}
        {!isStoreManager && (
        <div className="flex flex-wrap items-center gap-3 bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
          <select
            className="border p-2 rounded"
            value={tempYear}
            onChange={(e) => setTempYear(e.target.value)}
          >
            <option value="ALL">All Years</option>
            {availableYears.map((year) => (
              <option key={year} value={year}>
                Năm {year}
              </option>
            ))}
          </select>

          <button
            onClick={handleApplyFilter}
            className="bg-blue-600 text-white px-4 py-2 rounded"
          >
            Apply
          </button>
        </div>
        )}

        {/* ── Phân tích theo năm — hidden for store_manager ── */}
        {!isStoreManager && (
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-800">Phân tích theo năm</h2>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-700">
              {appliedYear === 'ALL' ? 'Tất cả năm' : `Năm ${appliedYear}`}
            </span>
          </div>
          <StatsCards selectedYear={appliedYear} />
          <CustomerChart selectedYear={appliedYear} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <TrendingProductsChart selectedYear={appliedYear} />
            <PromotionImpactChart selectedYear={appliedYear} />
          </div>
          <LocationChart selectedYear={appliedYear} />
        </section>
        )}

        {/* ── Phân tích tổng hợp (không bị ảnh hưởng bởi filter) ── */}
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-800">
              {isStoreManager ? 'Quản lý Tồn kho Cửa hàng' : 'Phân tích tổng hợp'}
            </h2>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-500">
              {isStoreManager ? 'Safety Stock & Stockout' : 'Toàn thời gian'}
            </span>
          </div>
          {!isStoreManager && <RfmSegmentsChart />}
          {!isStoreManager && <ProductPerformanceChart />}
          <InventoryMetricsChart />
        </section>

      </div>
    </DashboardLayout>
  );
};

export default ItemTrends;