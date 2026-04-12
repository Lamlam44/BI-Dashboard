'use client';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useRefresh } from '../../components/RefreshProvider';
import { API_BASE_URL } from '../../lib/api';

interface Props {
  selectedYear: string;
}

export default function StatsCards({ selectedYear }: Props) {
  const { refreshTick } = useRefresh();
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let url = `${API_BASE_URL}/trends/api/summary-stats`;
    if (selectedYear !== 'ALL') {
      url += `?start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31`;
    }

    setLoading(true);
    setErrorMsg(null);
    axios.get(url)
      .then(res => {
        setStats(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setErrorMsg('Khong the tai du lieu tong quan.');
        setLoading(false);
      });
      
  }, [selectedYear, refreshTick]);

  if (errorMsg) {
    return (
      <div className="w-full max-w-5xl p-4 rounded-xl border border-red-200 bg-red-50 text-red-700">
        {errorMsg}
      </div>
    );
  }

  if (loading && !stats) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-5xl mb-12">
        <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-blue-500 text-gray-400">Dang tai...</div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-green-500 text-gray-400">Dang tai...</div>
        <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-purple-500 text-gray-400">Dang tai...</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="w-full max-w-5xl p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-700">
        Chua co du lieu tong quan cho bo loc nay.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-5xl mb-12">
      <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-blue-500">
        <p className="text-sm text-gray-500 font-medium">Tổng Doanh Thu</p>
        <p className="text-2xl font-bold text-gray-800">{loading ? '...' : stats.total_revenue}</p>
      </div>
      <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-green-500">
        <p className="text-sm text-gray-500 font-medium">Tổng Khách Hàng</p>
        <p className="text-2xl font-bold text-gray-800">{loading ? '...' : stats.total_customers}</p>
      </div>
      <div className="bg-white p-6 rounded-2xl shadow-sm border-l-4 border-purple-500">
        <p className="text-sm text-gray-500 font-medium">Phân Khúc Chủ Lực</p>
        <p className="text-2xl font-bold text-gray-800">{loading ? '...' : stats.top_segment}</p>
      </div>
    </div>
  );
}
