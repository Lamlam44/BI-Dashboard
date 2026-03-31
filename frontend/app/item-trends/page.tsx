'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '../components/DashboardLayout';
import Section from '../components/Section';
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

        {/* FILTER + YEAR ANALYSIS — hidden for store_manager */}
        {!isStoreManager && (
        <Section title="📅 Phân tích theo Năm" badge="🔗 Lọc theo năm đã chọn">
          <div className="flex flex-wrap items-center gap-3">
            <select className="border p-2 rounded" value={tempYear} onChange={(e) => setTempYear(e.target.value)}>
              <option value="ALL">All Years</option>
              {availableYears.map((year) => (
                <option key={year} value={year}>Năm {year}</option>
              ))}
            </select>
            <button onClick={handleApplyFilter} className="bg-blue-600 text-white px-4 py-2 rounded">Apply</button>
          </div>
          <StatsCards selectedYear={appliedYear} />
          <CustomerChart selectedYear={appliedYear} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <TrendingProductsChart selectedYear={appliedYear} />
            <PromotionImpactChart selectedYear={appliedYear} />
          </div>
          <LocationChart selectedYear={appliedYear} />
        </Section>
        )}

        {/* OVERALL ANALYSIS — not filtered by year */}
        <Section
          title={isStoreManager ? '📦 Quản lý Tồn kho Cửa hàng' : '📊 Phân tích Tổng hợp'}
          badge={isStoreManager ? 'Safety Stock & Stockout' : '⚠ Toàn thời gian — Không áp dụng bộ lọc năm'}
        >
          {!isStoreManager && <RfmSegmentsChart />}
          {!isStoreManager && <ProductPerformanceChart />}
          <InventoryMetricsChart />
        </Section>

      </div>
    </DashboardLayout>
  );
};

export default ItemTrends;