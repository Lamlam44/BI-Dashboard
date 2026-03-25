'use client';

import { useEffect, useMemo, useState } from 'react';

import DashboardLayout from '../components/DashboardLayout';
import CapabilityPanel from './components/CapabilityPanel';
import FiltersBar from './components/FiltersBar';
import KpiCards from './components/KpiCards';
import LeaderboardTable from './components/LeaderboardTable';
import ScatterChart from './components/ScatterChart';
import TopPerformerCard from './components/TopPerformerCard';
import TrendChart from './components/TrendChart';
import {
  DashboardResponse,
  EmployeeFiltersResponse,
  LeaderboardResponse,
  ScatterResponse,
  TrendResponse,
} from './components/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

function buildQuery(params: Record<string, string>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '') {
      query.set(key, value);
    }
  });
  return query.toString();
}

export default function EmployeePerformancePage() {
  const [filters, setFilters] = useState<EmployeeFiltersResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null);
  const [scatter, setScatter] = useState<ScatterResponse | null>(null);

  const [selectedYear, setSelectedYear] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [selectedStoreKey, setSelectedStoreKey] = useState('');
  const [selectedEmployeeKey, setSelectedEmployeeKey] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadFilters() {
      try {
        const res = await fetch(`${API_BASE_URL}/employee-performance/filters`);
        if (!res.ok) throw new Error('Failed to load filter options');
        const data = (await res.json()) as EmployeeFiltersResponse;
        if (mounted) {
          setFilters(data);
          if (data.years.length > 0) {
            setSelectedYear(String(data.years[0]));
          }
        }
      } catch (err) {
        if (mounted) {
          setError((err as Error).message);
        }
      }
    }

    loadFilters();
    return () => {
      mounted = false;
    };
  }, []);

  const sharedQuery = useMemo(
    () =>
      buildQuery({
        year: selectedYear,
        month: selectedMonth,
        store_key: selectedStoreKey,
        employee_key: selectedEmployeeKey,
      }),
    [selectedEmployeeKey, selectedMonth, selectedStoreKey, selectedYear]
  );

  useEffect(() => {
    let mounted = true;

    async function loadDashboardData() {
      if (!filters) return;

      setLoading(true);
      setError(null);

      try {
        const [dashboardRes, trendRes, leaderboardRes, scatterRes] = await Promise.all([
          fetch(`${API_BASE_URL}/employee-performance/dashboard?${sharedQuery}`),
          fetch(`${API_BASE_URL}/employee-performance/trend?${sharedQuery}`),
          fetch(`${API_BASE_URL}/employee-performance/leaderboard?top_n=10&${sharedQuery}`),
          fetch(`${API_BASE_URL}/employee-performance/scatter?${sharedQuery}`),
        ]);

        if (!dashboardRes.ok || !trendRes.ok || !leaderboardRes.ok || !scatterRes.ok) {
          throw new Error('Failed to load employee performance data');
        }

        const [dashboardData, trendData, leaderboardData, scatterData] = await Promise.all([
          dashboardRes.json(),
          trendRes.json(),
          leaderboardRes.json(),
          scatterRes.json(),
        ]);

        if (mounted) {
          setDashboard(dashboardData as DashboardResponse);
          setTrend(trendData as TrendResponse);
          setLeaderboard(leaderboardData as LeaderboardResponse);
          setScatter(scatterData as ScatterResponse);
        }
      } catch (err) {
        if (mounted) {
          setError((err as Error).message);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadDashboardData();
    return () => {
      mounted = false;
    };
  }, [filters, sharedQuery]);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <header>
          <h1 className="text-3xl font-bold text-slate-900">Employee Performance</h1>
          <p className="text-slate-600 mt-2">
            Real-time performance analytics for store managers based on available warehouse attributes.
          </p>
        </header>

        <FiltersBar
          years={filters?.years || []}
          months={filters?.months || []}
          stores={filters?.stores || []}
          employees={filters?.employees || []}
          selectedYear={selectedYear}
          selectedMonth={selectedMonth}
          selectedStoreKey={selectedStoreKey}
          selectedEmployeeKey={selectedEmployeeKey}
          onYearChange={setSelectedYear}
          onMonthChange={setSelectedMonth}
          onStoreChange={setSelectedStoreKey}
          onEmployeeChange={setSelectedEmployeeKey}
        />

        {loading && <p className="text-sm text-slate-500">Loading employee performance data...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && !error && (
          <>
            <KpiCards data={dashboard} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <TopPerformerCard data={dashboard} />
              <CapabilityPanel items={dashboard?.capabilities || []} />
            </div>
            <TrendChart data={trend} />
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <LeaderboardTable data={leaderboard} />
              <ScatterChart data={scatter} />
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
