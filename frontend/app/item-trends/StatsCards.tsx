'use client';
import { useEffect, useState } from 'react';
import axios from 'axios';

interface Props {
  selectedYear: string;
}

// TẠO CUỐN SỔ TAY GHI NHỚ (Biến toàn cục của file này)
// Nó sẽ lưu trữ theo cấu trúc: { "url_nam_2007": data, "url_nam_2008": data }
const apiCache: Record<string, any> = {};

export default function StatsCards({ selectedYear }: Props) {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let url = 'http://127.0.0.1:8001/api/summary-stats';
    if (selectedYear !== 'ALL') {
      url += `?start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31`;
    }

    // BƯỚC 1: KIỂM TRA SỔ TAY TRƯỚC
    // Nếu url này đã có trong sổ tay, lấy ra dùng luôn và DỪNG LẠI (return)
    if (apiCache[url]) {
      setStats(apiCache[url]);
      setLoading(false);
      return; 
    }

    // BƯỚC 2: NẾU CHƯA CÓ TRONG SỔ, MỚI BẬT LOADING VÀ GỌI API
    setLoading(true);
    axios.get(url)
      .then(res => {
        // Ghi chép kết quả mới lấy được vào sổ tay để lần sau dùng
        apiCache[url] = res.data; 
        
        setStats(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
      
  }, [selectedYear]);

  if (!stats) return null;

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