'use client';
import { useEffect, useState } from 'react';
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js';
import { Bar } from 'react-chartjs-2';
import axios from 'axios';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

interface Props {
  selectedYear: string;
}

// 1. TẠO SỔ TAY CACHE CHO BIỂU ĐỒ KHUYẾN MÃI
const apiCache: Record<string, any> = {};

export default function PromotionImpactChart({ selectedYear }: Props) {
  const [chartData, setChartData] = useState<any>(null);

  useEffect(() => {
    let url = 'http://127.0.0.1:8001/api/promotion-impact';
    if (selectedYear !== 'ALL') {
      url += `?start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31`;
    }

    // 2. KIỂM TRA CACHE TRƯỚC
    if (apiCache[url]) {
      setChartData(apiCache[url]);
      return;
    }

    // 3. NẾU CHƯA CÓ, XÓA BIỂU ĐỒ CŨ ĐỂ HIỆN LOADING, RỒI GỌI API
    setChartData(null); 
    axios.get(url)
      .then(res => {
        apiCache[url] = res.data; // Ghi chép vào sổ
        setChartData(res.data);
      })
      .catch(err => console.error(err));
      
  }, [selectedYear]);

  if (!chartData) return (
    <div className="w-full p-8 bg-white rounded-2xl shadow-sm border border-gray-100 flex items-center justify-center h-[600px]">
      <span className="text-gray-500 font-medium">Đang tính toán tác động khuyến mãi...</span>
    </div>
  );

  const options = {
    responsive: true,
    maintainAspectRatio: false, 
    interaction: {
      mode: 'index' as const, 
      intersect: false,       
    },
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: { usePointStyle: true, padding: 20, font: { size: 12 } }
      },
      tooltip: {
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        titleColor: '#1f2937',                        
        titleFont: { size: 16, weight: 'bold' as const },
        bodyFont: { size: 14, weight: 500 },
        borderColor: '#e5e7eb',                       
        borderWidth: 1, 
        padding: 15, 
        displayColors: false,                         
        callbacks: {
          label: (context: any) => {
            const label = context.dataset.label || '';
            const value = context.parsed.y || 0;
            const formattedValue = new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              maximumFractionDigits: 0
            }).format(value);
            return `${label} : ${formattedValue}`;
          },
          labelTextColor: (context: any) => context.dataset.backgroundColor
        }
      }
    },
    scales: {
      x: { stacked: true, grid: { display: false }, ticks: { font: { size: 11 } } },
      y: {
        stacked: true,
        beginAtZero: true,
        border: { dash: [5, 5] },
        grid: { color: 'rgba(200, 200, 200, 0.3)' },
        ticks: {
          callback: (value: any) => value >= 1000000 ? (value / 1000000) + 'M' : (value / 1000) + 'K'
        }
      }
    },
    barPercentage: 0.7,      
    categoryPercentage: 0.8, 
  };

  return (
    <div className="w-full p-8 bg-white rounded-2xl shadow-sm border border-gray-100">
      <h2 className="text-xl font-bold text-gray-800 mb-8">
        Promotion Types Impact on Sales {selectedYear !== 'ALL' && `(${selectedYear})`}
      </h2>
      
      <div className="h-[600px] w-full">
        <Bar data={chartData} options={options} />
      </div>
      
      <p className="text-xs text-gray-400 mt-4 italic">* Lưu ý: Dữ liệu bao gồm cả doanh số Online và Offline</p>
    </div>
  );
}