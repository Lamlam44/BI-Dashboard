'use client';
import { useEffect, useState } from 'react';
import axios from 'axios';

interface Props {
  selectedYear: string;
}

interface Product {
  name: string;
  qty: number;
}

// 1. TẠO SỔ TAY CACHE CHO BIỂU ĐỒ SẢN PHẨM
const apiCache: Record<string, Product[]> = {};

export default function TopTrendingList({ selectedYear }: Props) {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let url = 'http://127.0.0.1:8001/api/trending-products';
    if (selectedYear !== 'ALL') {
      url += `?start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31`;
    }

    // 2. KIỂM TRA CACHE TRƯỚC
    if (apiCache[url]) {
      setProducts(apiCache[url]);
      setLoading(false);
      return;
    }

    // 3. NẾU CHƯA CÓ, GỌI API VÀ LƯU LẠI
    setLoading(true);
    axios.get(url)
      .then(res => {
        apiCache[url] = res.data; // Ghi chép vào sổ
        setProducts(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
      
  }, [selectedYear]);

  return (
    <div className="w-full p-6 bg-white rounded-2xl shadow-sm border border-gray-100">
      <h2 className="text-lg font-bold text-gray-800 mb-6">
        Top Trending Products {selectedYear !== 'ALL' && `(${selectedYear})`}
      </h2>
      
      <div className="flex justify-between text-sm font-semibold text-gray-500 mb-4 pb-2 border-b">
        <span>Product Name</span>
        <span>Qty Sold</span>
      </div>

      {loading ? (
        <div className="text-center py-10 text-gray-400 font-medium">Đang tải dữ liệu...</div>
      ) : (
        <div className="flex flex-col gap-4">
          {products.map((item, idx) => (
            <div key={idx} className="flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-indigo-500 flex items-center justify-center text-white">
                  📦
                </div>
                <span className="font-medium text-gray-700">{item.name}</span>
              </div>
              <div className="text-sm font-bold text-gray-800 bg-gray-50 px-3 py-1 rounded-md">
                {item.qty.toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}