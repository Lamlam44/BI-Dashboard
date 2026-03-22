'use client';

import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
} from 'chart.js';
import { Line, Pie } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
);

const Dashboard = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`http://localhost:8001/api/dashboard/sales?t=${Date.now()}`, { cache: 'no-store' })
      .then(res => res.json())
      .then(resData => {
        setData(resData);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching dashboard data', err);
        setLoading(false);
      });
  }, []);

  // Show loading state
  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex justify-center items-center h-screen">
          <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      </DashboardLayout>
    );
  }

  // Không return sớm nữa, để hiển thị Chart rỗng thay bì màn hình báo lỗi rỗng.
  const isDataEmpty = data?.status === 'empty' || !data;
  
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);
  };

  const lineChartData = {
    labels: data.trend?.labels || [],
    datasets: [
      {
        label: 'Doanh Số (Sales)',
        data: data.trend?.data || [],
        borderColor: 'rgb(53, 162, 235)',
        backgroundColor: 'rgba(53, 162, 235, 0.5)',
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  };

  const pieChartData = {
    labels: data.store_pie?.labels || [],
    datasets: [
      {
        data: data.store_pie?.data || [],
        backgroundColor: [
          'rgba(255, 99, 132, 0.8)',
          'rgba(54, 162, 235, 0.8)',
          'rgba(255, 206, 86, 0.8)',
          'rgba(75, 192, 192, 0.8)',
          'rgba(153, 102, 255, 0.8)',
          'rgba(255, 159, 64, 0.8)',
        ],
        borderWidth: 1,
      },
    ],
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 p-8">
        {/* Page Title */}
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            Sales & Profit
          </h1>
          <p className="text-slate-600 mt-2">
            Báo cáo Doanh số tổng quát toàn hệ thống (Cập nhật lần cuối: <span className="font-semibold">{isDataEmpty ? 'Chưa có' : data.last_updated}</span>)
            {isDataEmpty && <span className="ml-2 text-red-500 font-medium">(Hệ thống hiện đang trống dữ liệu)</span>}
          </p>
        </div>

        {/* Dashboard Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition-shadow transition-transform transform hover:-translate-y-1">
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider">Tổng Doanh Thu</p>
            <p className="text-3xl font-bold text-slate-900 mt-2">{formatCurrency(data?.total || 0)}</p>
          </div>
          <div className="bg-white rounded-xl border border-indigo-100 p-6 shadow-sm hover:shadow-md transition-shadow transition-transform transform hover:-translate-y-1 bg-gradient-to-r from-white to-indigo-50">
            <p className="text-indigo-600 text-sm font-semibold uppercase tracking-wider">YTD (Từ đầu năm)</p>
            <p className="text-3xl font-bold text-indigo-700 mt-2">{formatCurrency(data?.ytd || 0)}</p>
          </div>
          <div className="bg-white rounded-xl border border-blue-100 p-6 shadow-sm hover:shadow-md transition-shadow transition-transform transform hover:-translate-y-1 bg-gradient-to-r from-white to-blue-50">
            <p className="text-blue-600 text-sm font-semibold uppercase tracking-wider">MTD (Từ đầu tháng)</p>
            <p className="text-3xl font-bold text-blue-700 mt-2">{formatCurrency(data?.mtd || 0)}</p>
          </div>
        </div>

        {/* Charts Section */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm xl:col-span-2 hover:shadow-md transition-shadow">
            <h2 className="text-lg font-bold text-slate-800 mb-6 border-b pb-2">Xu Hướng Bán Hàng (Sales Trend)</h2>
            <div className="h-[350px] w-full">
              <Line 
                data={lineChartData} 
                options={{ 
                  responsive: true, 
                  maintainAspectRatio: false,
                  plugins: { 
                    legend: { position: 'top' as const },
                    tooltip: { mode: 'index', intersect: false }
                  },
                  scales: {
                    y: { beginAtZero: true }
                  }
                }} 
              />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm hover:shadow-md transition-shadow">
            <h2 className="text-lg font-bold text-slate-800 mb-6 border-b pb-2">Tỷ Trọng Doanh Thu Theo Cửa Hàng</h2>
            <div className="h-[350px] w-full flex justify-center items-center">
              <Pie 
                data={pieChartData} 
                options={{ 
                  responsive: true, 
                  maintainAspectRatio: false,
                  plugins: { 
                    legend: { position: 'bottom' as const } 
                  } 
                }} 
              />
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
