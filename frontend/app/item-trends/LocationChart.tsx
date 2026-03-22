'use client';
import { useEffect, useState } from 'react';
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js';
import { Bar } from 'react-chartjs-2';
import axios from 'axios';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

interface Props {
  selectedYear: string;
}

export default function LocationChart({ selectedYear }: Props) {
  const [allData, setAllData] = useState<any>(null); 
  const [chartData, setChartData] = useState<any>(null); 
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    axios.get('http://127.0.0.1:8003/api/sales-by-location')
      .then(res => {
        if (res.data.status === "error") {
          setErrorMsg(res.data.message);
        } else {
          setAllData({ labels: res.data.labels, datasets: res.data.datasets });
        }
      })
      .catch(err => setErrorMsg("Lỗi kết nối: " + err.message));
  }, []);

  useEffect(() => {
    if (allData && selectedYear) {
      if (!Array.isArray(allData.datasets)) return;
      let filteredDatasets = selectedYear === "ALL"
        ? allData.datasets
        : allData.datasets.filter((d: any) => d.label.includes(selectedYear));

      setChartData({ labels: allData.labels, datasets: filteredDatasets });
    }
  }, [selectedYear, allData]);

  if (errorMsg) return <p className="text-red-500 font-bold mt-8 p-4 bg-red-50 rounded-lg">{errorMsg}</p>;
  if (!chartData) return <div className="h-[500px] mt-8 flex items-center justify-center bg-white rounded-2xl"><p className="text-gray-500 animate-pulse">Đang tải biểu đồ...</p></div>;

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
        labels: { usePointStyle: true, padding: 25, font: { size: 13 } }
      },
      tooltip: {
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        titleColor: '#111827', // Màu tiêu đề (quốc gia)
        bodyColor: '#1f2937',  // BẢN SỬA: Đổi màu chữ doanh số thành xám đậm để hiển thị trên nền trắng!
        bodyFont: { size: 14, weight: 'bold' as const }, // BẢN SỬA: weight phải là chuỗi
        borderColor: '#e5e7eb',
        borderWidth: 1,
        padding: 15,
        displayColors: true,
        callbacks: {
          label: function(context: any) {
            const label = context.dataset.label || '';
            const value = context.parsed.y || 0; // Lấy giá trị chính xác
            
            // Format tiền tệ cho đẹp (VD: $1,500,000)
            const formattedValue = new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 0,
              maximumFractionDigits: 0
            }).format(value);

            return `${label}: ${formattedValue}`;
          }
        }
      }
    },
    scales: {
      x: { grid: { display: false }, ticks: { font: { weight: 'bold' as const, size: 13 } } },
      y: { 
        grid: { color: 'rgba(200,200,200,0.2)' }, 
        ticks: { 
          callback: (val: any) => val >= 1000000 ? `$${val / 1000000}M` : `$${val / 1000}k` 
        } 
      }
    }
  };

  return (
    <div className="w-full p-8 bg-white rounded-2xl shadow-sm border border-gray-100">
      <h2 className="text-xl font-bold text-gray-800 uppercase tracking-tight mb-8">
        Global Revenue by Geography {selectedYear !== 'ALL' && <span className="text-blue-600 ml-2">({selectedYear})</span>}
      </h2>
      <div className="h-[500px]">
        {chartData.datasets?.length > 0 ? (
            <Bar data={chartData} options={options} />
        ) : (
            <div className="flex items-center justify-center h-full text-gray-500">Không có dữ liệu.</div>
        )}
      </div>
    </div>
  );
}
