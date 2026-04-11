'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import ExportPDFButton from '../components/ExportPDFButton';
import { useAuth } from '../store/useAuth';

import DashboardLayout from '../components/DashboardLayout';
import Section from '../components/Section';
import { useRefresh } from '../components/RefreshProvider';
import { authHeaders } from '../lib/api';
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

import { API_BASE_URL } from '../lib/api';

async function fetchJsonWithTimeout<T>(url: string, timeoutMs = 600000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal, headers: authHeaders() });
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
  const { user } = useAuth();
  const [filters, setFilters] = useState<EmployeeFiltersResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null);
  const [scatter, setScatter] = useState<ScatterResponse | null>(null);

  const [selectedYear, setSelectedYear] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [selectedEmployeeKey, setSelectedEmployeeKey] = useState('');

  const reportRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadFilters() {
      try {
        const res = await fetch(`${API_BASE_URL}/employee-performance/filters`, { headers: authHeaders() });
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

  const filterLabel = [selectedYear && `Năm ${selectedYear}`, selectedMonth && `Tháng ${selectedMonth}`].filter(Boolean).join(' | ') || 'Toàn bộ';

  return (
    <DashboardLayout>
      <div className="space-y-6" ref={reportRef}>
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Hiệu Suất Nhân Viên</h1>
            <p className="text-slate-600 mt-2">
              Phân tích hiệu suất làm việc theo thời gian thực dựa trên dữ liệu từ kho dữ liệu.
            </p>
          </div>
          <ExportPDFButton
            generateBlob={async () => {
              const { generateEmployeePDFBlob } = await import('../components/pdf/EmployeePDFDoc');
              return generateEmployeePDFBlob({
                dashboard,
                leaderboard,
                trend,
                filterLabel,
                username: user?.display_name || user?.username,
              });
            }}
            filename="employee-performance"
          />
        </header>

        <Section title="🏛 Bộ lọc Nhân viên" badge="Chọn Năm, Tháng, Quản lý để lọc dữ liệu bên dưới">
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
        </Section>

        {loading && <p className="text-sm text-slate-500">Đang tải dữ liệu hiệu suất nhân viên...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && !error && (
          <>
            <Section title="📊 Tổng quan Hiệu suất" badge="🔗 Year + Month + Manager">
              <KpiCards data={dashboard} />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <TopPerformerCard data={dashboard} />
                <CapabilityPanel items={dashboard?.capabilities || []} />
              </div>
            </Section>

            <Section title="📈 Xu hướng theo Thời gian" badge="🔗 Year + Manager (Month không ảnh hưởng)">
              <TrendChart data={trend} />
            </Section>

            <Section title="🏆 Bảng xếp hạng & Phân tích" badge="🔗 Year + Month (Manager không ảnh hưởng)">
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <LeaderboardTable data={leaderboard} />
                <ScatterChart data={scatter} />
              </div>
            </Section>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
