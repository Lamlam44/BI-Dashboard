'use client';
import { useEffect, useState } from 'react';
import { Chart as ChartJS, ArcElement, Tooltip, Legend, ChartData } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import ChartDataLabels from 'chartjs-plugin-datalabels'; // Import Plugin mới
import axios from 'axios';
import { useRefresh } from '../../components/RefreshProvider';
import { API_BASE_URL } from '../../lib/api';

// Đăng ký các thành phần bao gồm cả ChartDataLabels
//ChartJS.register(ArcElement, Tooltip, Legend, ChartDataLabels);
ChartJS.register(ArcElement, Tooltip, Legend);

interface ApiResponse {
  labels: string[];
  data: number[];
}

interface Props {
  selectedYear: string;
}

// Định nghĩa 3 màu chuẩn giống với hình mẫu (Xanh lá, Đỏ, Xanh dương)
const CHART_COLORS = ['#10b981', '#ef4444', '#3b82f6'];

export default function CustomerChart({ selectedYear }: Props) {
  const { refreshTick } = useRefresh();
  const [chartData, setChartData] = useState<ChartData<'doughnut'> | null>(null);
  const [rawData, setRawData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let url = `${API_BASE_URL}/trends/api/customer-segments`;
    if (selectedYear !== 'ALL') {
      url += `?start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31`;
    }

    setLoading(true);
    setErrorMsg(null);
    setChartData(null);

    axios.get<ApiResponse>(url)
      .then(res => {
        if (!Array.isArray(res.data.labels) || res.data.labels.length === 0) {
          setRawData({ labels: [], data: [] });
          setChartData(null);
          setLoading(false);
          return;
        }
        setRawData(res.data);
        setChartData({
          labels: res.data.labels,
          datasets: [{
            data: res.data.data,
            backgroundColor: CHART_COLORS,
            borderColor: ['#fff', '#fff', '#fff'],
            borderWidth: 4, // Tăng viền trắng lên cho các lát cắt tách rời hẳn nhau
            hoverOffset: 6
          }],
        });
        setLoading(false);
      })
      .catch(err => {
        console.error("Loi goi API:", err);
        setErrorMsg('Khong the tai du lieu phan khuc khach hang.');
        setLoading(false);
      });
  }, [selectedYear, refreshTick]);

  if (loading) {
    return <p className="text-center p-10 text-gray-500">Dang tai du lieu phan khuc...</p>;
  }

  if (errorMsg) {
    return (
      <div className="w-full p-6 bg-red-50 rounded-2xl border border-red-200 text-red-700">
        {errorMsg}
      </div>
    );
  }

  if (!rawData || rawData.labels.length === 0 || !chartData) {
    return (
      <div className="w-full p-6 bg-amber-50 rounded-2xl border border-amber-200 text-amber-700">
        Khong co du lieu phan khuc khach hang cho bo loc nay.
      </div>
    );
  }

  // Tính tổng số lượng khách hàng để chia phần trăm
  const totalCustomers = rawData.data.reduce((acc, curr) => acc + curr, 0);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '60%', // Làm mỏng vòng Doughnut để nhìn thanh thoát giống ảnh
    layout: {
      padding: 40 // Chừa lề xung quanh để chữ phần trăm chĩa ra không bị cắt mất
    },
    plugins: {
      legend: {
        display: false, // Tắt chú thích mặc định của Chart.js để tự code cái mới đẹp hơn ở dưới
      },
      tooltip: {
        callbacks: {
          label: (context: any) => {
            const value = context.raw;
            const percentage = ((value / totalCustomers) * 100).toFixed(1);
            return ` ${context.label}: ${value.toLocaleString()} (${percentage}%)`;
          }
        }
      },
      datalabels: {
        color: (context: any) => CHART_COLORS[context.dataIndex], // Chữ có màu giống lát cắt
        anchor: 'end' as const,
        align: 'end' as const,
        offset: 8,
        font: {
          size: 14,
          weight: 'normal' as const,
        },
        formatter: (value: number, context: any) => {
          const percentage = Math.round((value / totalCustomers) * 100);
          const labelName = context.chart.data.labels[context.dataIndex];
          return `${labelName} ${percentage}%`; // Hiển thị chữ ví dụ: "VIP 28%"
        }
      }
    }
  };

  return (
    <div className="w-full p-6 bg-white rounded-2xl shadow-sm border border-gray-100 flex flex-col">
      {/* Tiêu đề góc trái trên */}
      <h2 className="text-lg font-bold text-gray-800 self-start mb-4">RFM Customer Segments</h2>
      
      {/* Vùng chứa Biểu đồ */}
      <div className="relative h-72 w-full flex-grow flex items-center justify-center">
        <Doughnut data={chartData} options={options} plugins={[ChartDataLabels]}/>
      </div>

      {/* Custom Legend tự code (Phần hiển thị 3 nhóm bên dưới) */}
      <div className="flex justify-center flex-wrap gap-8 mt-4 pt-4">
        {Array.isArray(rawData.labels) && rawData.labels.map((label, index) => (
          <div key={index} className="flex flex-col items-start">
            <div className="flex items-center gap-2">
              <span 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: CHART_COLORS[index] }}
              ></span>
              <span className="font-bold text-gray-800 text-sm">{label}</span>
            </div>
            {/* Hiển thị số lượng khách bên dưới */}
            <span className="text-xs text-gray-500 ml-5">
              {rawData.data[index].toLocaleString()} customers
            </span>
          </div>
        ))}
      </div>

      {/* Ghi chú: mỗi nhóm cơ bản gồm các phân khúc Advanced nào */}
      <div className="mt-4 pt-3 border-t border-gray-100">
        <p className="text-xs font-semibold text-gray-500 mb-2">📌 Mỗi nhóm bao gồm các phân khúc RFM Advanced:</p>
        <div className="space-y-1 text-xs text-gray-600">
          <div><span className="font-semibold" style={{ color: '#ef4444' }}>Khách VIP</span> — Champion, Loyal</div>
          <div><span className="font-semibold" style={{ color: '#10b981' }}>Khách Tiềm Năng</span> — Potential Loyalist, New Customer, Need Attention</div>
          <div><span className="font-semibold" style={{ color: '#3b82f6' }}>Nguy Cơ Rời Bỏ</span> — At Risk, Lost</div>
        </div>
      </div>
    </div>
  );
}
