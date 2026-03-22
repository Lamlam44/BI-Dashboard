'use client';

import { useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';

// import StatsCards from '../components/StatsCards';
// import CustomerChart from '../components/CustomerChart';
// import LocationChart from '../components/LocationChart';
// import TrendingProductsChart from '../components/TrendingProductsChart';
// import PromotionImpactChart from '../components/PromotionImpactChart';
import StatsCards from './StatsCards';
import CustomerChart from './CustomerChart';
import LocationChart from './LocationChart';
import TrendingProductsChart from './TrendingProductsChart';
import PromotionImpactChart from './PromotionImpactChart';

const ItemTrends = () => {
  const [tempYear, setTempYear] = useState<string>('ALL');
  const [appliedYear, setAppliedYear] = useState<string>('ALL');

  const availableYears = ['2007', '2008', '2009'];

  const handleApplyFilter = () => {
    setAppliedYear(tempYear);
  };

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

        {/* FILTER */}
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

        {/* STATS */}
        <StatsCards selectedYear={appliedYear} />

        {/* CUSTOMER SEGMENT */}
        <CustomerChart />

        {/* TREND + PROMOTION */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TrendingProductsChart selectedYear={appliedYear} />
          <PromotionImpactChart selectedYear={appliedYear} />
        </div>

        {/* LOCATION */}
        <LocationChart selectedYear={appliedYear} />

      </div>
    </DashboardLayout>
  );
};

export default ItemTrends;
