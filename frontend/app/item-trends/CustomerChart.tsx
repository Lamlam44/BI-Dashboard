'use client';
import { useEffect, useState } from 'react';
import { Chart as ChartJS, ArcElement, Tooltip, Legend, ChartData } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import ChartDataLabels from 'chartjs-plugin-datalabels'; // Import Plugin mới
import axios from 'axios';

// Đăng ký các thành phần bao gồm cả ChartDataLabels
//ChartJS.register(ArcElement, Tooltip, Legend, ChartDataLabels);
ChartJS.register(ArcElement, Tooltip, Legend);

interface ApiResponse {
  labels: string[];
  data: number[];
}

// Định nghĩa 3 màu chuẩn giống với hình mẫu (Xanh lá, Đỏ, Xanh dương)
const CHART_COLORS = ['#10b981', '#ef4444', '#3b82f6'];

export default function CustomerChart() {
  const [chartData, setChartData] = useState<ChartData<'doughnut'> | null>(null);
  const [rawData, setRawData] = useState<ApiResponse | null>(null);

  useEffect(() => {
    axios.get<ApiResponse>('http://127.0.0.1:8001/api/customer-segments')
      .then(res => {
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
      })
      .catch(err => console.error("Lỗi gọi API:", err));
  }, []);

  if (!chartData || !rawData) return <p className="text-center p-10 text-gray-500">Đang tải dữ liệu từ AI...</p>;

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
        {rawData.labels.map((label, index) => (
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
    </div>
  );
}