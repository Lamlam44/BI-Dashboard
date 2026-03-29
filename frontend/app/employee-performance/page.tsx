'use client';

import { useEffect, useMemo, useState } from 'react';

import DashboardLayout from '../components/DashboardLayout';
import { useRefresh } from '../components/RefreshProvider';
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

async function fetchJsonWithTimeout<T>(url: string, timeoutMs = 600000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      throw new Error(`Request failed (${res.status})`);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(`Request timeout after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

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
  const { refreshTick } = useRefresh();
  const [filters, setFilters] = useState<EmployeeFiltersResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null);
  const [scatter, setScatter] = useState<ScatterResponse | null>(null);

  const [selectedYear, setSelectedYear] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
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
        employee_key: selectedEmployeeKey,
      }),
    [selectedEmployeeKey, selectedMonth, selectedYear]
  );

  useEffect(() => {
    let mounted = true;

    async function loadDashboardData() {
      if (!filters) return;

      setLoading(true);
      setError(null);

      try {
        // Load summary first so page can render quickly.
        const dashboardData = await fetchJsonWithTimeout<DashboardResponse>(
          `${API_BASE_URL}/employee-performance/dashboard?${sharedQuery}`,
          600000
        );

        if (mounted) {
          setDashboard(dashboardData);
          setTrend(null);
          setLeaderboard(null);
          setScatter(null);
          setLoading(false);
        }

        const [trendResult, leaderboardResult, scatterResult] = await Promise.allSettled([
          fetchJsonWithTimeout<TrendResponse>(`${API_BASE_URL}/employee-performance/trend?${sharedQuery}`),
          fetchJsonWithTimeout<LeaderboardResponse>(
            `${API_BASE_URL}/employee-performance/leaderboard?top_n=10&${sharedQuery}`
          ),
          fetchJsonWithTimeout<ScatterResponse>(`${API_BASE_URL}/employee-performance/scatter?${sharedQuery}`),
        ]);

        if (!mounted) return;

        if (trendResult.status === 'fulfilled') {
          setTrend(trendResult.value);
        }
        if (leaderboardResult.status === 'fulfilled') {
          setLeaderboard(leaderboardResult.value);
        }
        if (scatterResult.status === 'fulfilled') {
          setScatter(scatterResult.value);
        }
      } catch (err) {
        if (mounted) {
          setError((err as Error).message);
          setLoading(false);
        }
      }
    }

    loadDashboardData();
    return () => {
      mounted = false;
    };
  }, [filters, sharedQuery, refreshTick]);

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
          employees={filters?.employees || []}
          selectedYear={selectedYear}
          selectedMonth={selectedMonth}
          selectedEmployeeKey={selectedEmployeeKey}
          onYearChange={setSelectedYear}
          onMonthChange={setSelectedMonth}
          onEmployeeChange={setSelectedEmployeeKey}
        />

        {loading && <p className="text-sm text-slate-500">Loading employee performance data...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && !error && (
          <>
            {/* Section 1: Chịu ảnh hưởng bởi tất cả filter (Year + Month + Manager) */}
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-800">Tổng quan hiệu suất</h2>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-700">Year</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-100 text-emerald-700">Month</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-violet-100 text-violet-700">Manager</span>
              </div>
              <KpiCards data={dashboard} />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <TopPerformerCard data={dashboard} />
                <CapabilityPanel items={dashboard?.capabilities || []} />
              </div>
            </section>

            {/* Section 2: Year + Manager (Month không ảnh hưởng) */}
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-800">Xu hướng theo thời gian</h2>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-700">Year</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-violet-100 text-violet-700">Manager</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-400 line-through">Month</span>
              </div>
              <TrendChart data={trend} />
            </section>

            {/* Section 3: Year + Month (Manager không ảnh hưởng) */}
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-800">Bảng xếp hạng & Phân tích</h2>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-700">Year</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-100 text-emerald-700">Month</span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-400 line-through">Manager</span>
              </div>
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <LeaderboardTable data={leaderboard} />
                <ScatterChart data={scatter} />
              </div>
            </section>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
