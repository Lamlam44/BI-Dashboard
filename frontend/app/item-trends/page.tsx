'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios';
import ExportPDFButton from '../components/ExportPDFButton';
import DashboardLayout from '../components/DashboardLayout';
import Section from '../components/Section';
import { useAuth } from '../store/useAuth';

import StatsCards from './components/StatsCards';
import CustomerChart from './components/CustomerChart';
import LocationChart from './components/LocationChart';
import TrendingProductsChart from './components/TrendingProductsChart';
import PromotionImpactChart from './components/PromotionImpactChart';
import RfmSegmentsChart from './components/RfmSegmentsChart';
import ProductPerformanceChart from './components/ProductPerformanceChart';
import InventoryMetricsChart from './components/InventoryMetricsChart';
import { allowedRoles } from '../lib/routes';
import { API_BASE_URL } from '../lib/api';

const ALLOWED_ROLES = allowedRoles('/item-trends');

const ItemTrends = () => {
  const router = useRouter();
  const { user } = useAuth();
  const isStoreManager = user?.role === 'store_manager';

  useEffect(() => {
    if (user && !ALLOWED_ROLES.includes(user.role)) {
      router.replace('/dashboard');
    }
  }, [user, router]);

  const reportRef = useRef<HTMLDivElement>(null);
  const [tempYear, setTempYear] = useState<string>('ALL');
  const [appliedYear, setAppliedYear] = useState<string>('ALL');
  const [availableYears, setAvailableYears] = useState<string[]>([]);

  useEffect(() => {
    axios.get(`${API_BASE_URL}/trends/api/available-years`)
      .then(res => {
        setAvailableYears((res.data as number[]).map(String));
      })
      .catch(() => {
        setAvailableYears(['2007', '2008', '2009']);
      });
  }, []);

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
      <div className="space-y-8" ref={reportRef}>

        {/* HEADER */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Xu Hướng Sản Phẩm</h1>
            <p className="text-slate-600 mt-2">
              Phân tích hiệu suất sản phẩm và xu hướng thị trường
            </p>
          </div>
          <ExportPDFButton
            contentRef={reportRef}
            filename="item-trends"
            reportTitle="Báo cáo Xu Hướng Sản Phẩm"
            filterInfo={appliedYear === 'ALL' ? 'Toàn thời gian' : `Năm ${appliedYear}`}
          />
        </div>

        {/* FILTER + YEAR ANALYSIS — hidden for store_manager */}
        {!isStoreManager && (
        <Section title="📅 Phân tích theo Năm" badge="🔗 Lọc theo năm đã chọn">
          <div className="flex flex-wrap items-center gap-3">
            <select className="border p-2 rounded" value={tempYear} onChange={(e) => setTempYear(e.target.value)}>
              <option value="ALL">Tất cả Năm</option>
              {availableYears.map((year) => (
                <option key={year} value={year}>Năm {year}</option>
              ))}
            </select>
            <button onClick={handleApplyFilter} className="bg-blue-600 text-white px-4 py-2 rounded">Áp dụng</button>
          </div>
          <StatsCards selectedYear={appliedYear} />
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
          {!isStoreManager && <CustomerChart selectedYear="ALL" />}
          {!isStoreManager && <RfmSegmentsChart />}
          {!isStoreManager && <ProductPerformanceChart />}
          <InventoryMetricsChart />
        </Section>

      </div>
    </DashboardLayout>
  );
};

export default ItemTrends;