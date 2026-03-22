'use client';

import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { Upload, Download, Trash2, Database, AlertCircle, RefreshCw, Eye } from 'lucide-react';

const API_BASE = "http://localhost:8001";

export default function DataManagementPage() {
    const [schemas, setSchemas] = useState<any>({});
    const [selectedTable, setSelectedTable] = useState<string>('');
    const [categories, setCategories] = useState<string[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    
    // Purge states
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('');
    
    // UI state
    const [isEditingSchema, setIsEditingSchema] = useState(false);

    useEffect(() => {
        fetch(`${API_BASE}/schema`)
            .then(res => res.json())
            .then(data => {
                setSchemas(data);
                if (Object.keys(data).length > 0) {
                    setSelectedTable(Object.keys(data)[0]);
                }
            })
            .catch(err => console.error("Error loading schemas:", err));
    }, []);

    useEffect(() => {
        if (selectedTable && schemas[selectedTable]?.deletion_strategy === 'CATEGORY') {
            fetch(`${API_BASE}/categories/${selectedTable}`)
                .then(res => res.json())
                .then(data => setCategories(data.categories || []))
                .catch(err => console.error(err));
        }
    }, [selectedTable, schemas]);

    const handleDownloadTemplate = () => {
        window.open(`${API_BASE}/template/${selectedTable}`);
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        if (!selectedTable) {
            alert('Vui lòng chọn bảng dữ liệu trước khi nạp file.');
            return;
        }

        setIsUploading(true);
        const formData = new FormData();
        formData.append('table_name', selectedTable);
        formData.append('file', file);

        try {
            const res = await fetch(`${API_BASE}/ingest`, {
                method: 'POST',
                body: formData,
            });
            const result = await res.json();
            if (res.ok) {
                alert(`✅ Nạp dữ liệu thành công!\n${result.message}`);
            } else {
                alert(`❌ Lỗi: ${result.detail || result.message || 'Server từ chối'}`);
            }
        } catch (err) {
            console.error(err);
            alert('❌ Lỗi kết nối đến Server xử lý dữ liệu.');
        } finally {
            setIsUploading(false);
            e.target.value = ''; // Reset input để cho phép chọn lại file giống tên
        }
    };

    const handleUpdateTableMeta = (field: string, value: string) => {
        setSchemas((prev: any) => ({
            ...prev,
            [selectedTable]: { ...prev[selectedTable], [field]: value }
        }));
    };

    const handleUpdateColumnMeta = (colIndex: number, field: string, value: any) => {
        setSchemas((prev: any) => {
            const updatedTable = { ...prev[selectedTable] };
            const updatedCols = [...updatedTable.columns];
            updatedCols[colIndex] = { ...updatedCols[colIndex], [field]: value };
            updatedTable.columns = updatedCols;
            return {
                ...prev,
                [selectedTable]: updatedTable
            };
        });
    };

    const handleSaveSchema = async () => {
        try {
            const res = await fetch(`${API_BASE}/schema`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(schemas)
            });
            if (res.ok) {
                alert('✅ Đã lưu cấu hình Schema thành công!');
                setIsEditingSchema(false);
            } else {
                alert('Lỗi lưu cấu hình.');
            }
        } catch(e) {
            alert('Lỗi gọi API lưu cấu hình.');
        }
    };

    const handlePurge = async () => {
        if (!confirm(`CẢNH BÁO: Rủi ro xóa dữ liệu trên bảng ${selectedTable}! Bạn có chắc chắn thực hiện? Hành động này sẽ tự động được Backup.`)) return;
        
        try {
            const res = await fetch(`${API_BASE}/purge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    table_name: selectedTable,
                    start_date: startDate || undefined,
                    end_date: endDate || undefined,
                    category: selectedCategory || undefined
                })
            });
            if (!res.ok) {
                const errResult = await res.json().catch(() => ({ detail: 'Lỗi không xác định từ Server' }));
                alert(`❌ Lỗi Xóa dữ liệu: ${errResult.detail || errResult.message || 'Lỗi 500'}`);
                return;
            }
            const result = await res.json();
            alert(`✅ Xóa thành công!\nSố dòng đã xóa: ${result.deleted_rows}\nSố dòng còn lại: ${result.remaining_rows}`);
        } catch(e) {
            console.error(e);
            alert('Lỗi kết nối tới Server. Vui lòng kiểm tra lại Database.');
        }
    };

    const currentSchema = schemas[selectedTable];

    return (
        <DashboardLayout>
            <div className="p-8 space-y-8 bg-slate-50 min-h-screen">
                <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                    <Database className="text-indigo-600" /> Cổng Quản Lý Dữ Liệu Data Warehouse
                </h1>
            </div>

            {/* BẢNG ĐIỀU KHIỂN CHỌN BẢNG */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex items-end gap-4">
                <div className="flex-1">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Chọn Bảng Dữ Liệu (Table)</label>
                    <select 
                        value={selectedTable}
                        onChange={(e) => setSelectedTable(e.target.value)}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-300 rounded-lg text-slate-900 focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                        {Object.entries(schemas).map(([key, val]: any) => (
                            <option key={key} value={key}>{val.display_name} ({key})</option>
                        ))}
                    </select>
                </div>
                <button onClick={handleDownloadTemplate} className="flex items-center gap-2 px-6 py-2 bg-slate-800 text-white font-medium rounded-lg hover:bg-slate-900 transition-colors">
                    <Download size={18} /> Tải file Template
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                
                {/* VÙNG UPLOAD (Ingestion) */}
                <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                    <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
                        <Upload className="text-blue-500" /> Nạp Dữ Liệu (Append & Deduplicate)
                    </h2>
                    <p className="text-sm text-slate-500 mb-6">File Excel Upload sẽ được tự độ gộp với file gốc. Các Record trùng lặp (Primary Key) sẽ giữ bản mới nhất.</p>
                    
                    <div className={`border-2 border-dashed border-slate-300 rounded-xl p-10 flex flex-col items-center justify-center bg-slate-50 hover:bg-slate-100 transition-colors relative ${isUploading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'}`}>
                        <input type="file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" accept=".csv, .xlsx" onChange={handleFileUpload} disabled={isUploading} />
                        {isUploading ? (
                            <div className="flex flex-col items-center">
                                <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-3"></div>
                                <span className="text-blue-600 font-medium">Đang xử lý nạp dữ liệu...</span>
                            </div>
                        ) : (
                            <>
                                <Upload size={40} className="text-slate-400 mb-3" />
                                <span className="text-slate-600 font-medium">Kéo thả file CSV/XLSX vào đây hoặc click để chọn</span>
                                <span className="text-slate-400 text-sm mt-1">Dữ liệu sẽ tự động kiểm tra mô hình Schema</span>
                            </>
                        )}
                    </div>
                </div>

                {/* VÙNG XÓA DỮ LIỆU THÔNG MINH (Purge) */}
                <div className="bg-white p-6 rounded-xl border border-red-100 shadow-sm relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-red-50 rounded-bl-full -z-0"></div>
                    <h2 className="text-lg font-bold text-red-700 mb-4 flex items-center gap-2 relative z-10">
                        <Trash2 /> Xóa Dữ Liệu (Smart Purge)
                    </h2>
                    <div className="text-sm text-slate-600 mb-6 relative z-10 p-3 bg-red-50 border border-red-100 rounded-lg flex gap-3">
                        <AlertCircle className="text-red-500 flex-shrink-0" size={20} />
                        <div>Dữ liệu sẽ được <b>Backup</b> sang <code className="bg-red-100 px-1 rounded text-red-800">/backups</code> trước khi purge. Cấu hình bảo vệ: Xóa theo chế độ <b>{currentSchema?.deletion_strategy}</b>.</div>
                    </div>

                    <div className="space-y-4 relative z-10">
                        {currentSchema && (
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Cấu hình Chiến Lược Xóa (Deletion Strategy)</label>
                                <select 
                                    value={currentSchema.deletion_strategy || ''} 
                                    onChange={e => handleUpdateTableMeta('deletion_strategy', e.target.value)}
                                    className="w-full px-3 py-2 border rounded-md"
                                >
                                    <option value="DATE_RANGE">Theo khoảng ngày (DATE_RANGE)</option>
                                    <option value="CATEGORY">Theo danh mục (CATEGORY)</option>
                                </select>
                            </div>
                        )}
                        {currentSchema?.deletion_strategy === 'DATE_RANGE' ? (
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Từ ngày (Start Date)</label>
                                    <input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)} className="w-full px-3 py-2 border rounded-md" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Đến ngày (End Date)</label>
                                    <input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)} className="w-full px-3 py-2 border rounded-md" />
                                </div>
                            </div>
                        ) : (
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Chọn Nhóm Category / Thương Hiệu Cần Xóa</label>
                                <select value={selectedCategory} onChange={e=>setSelectedCategory(e.target.value)} className="w-full px-3 py-2 border rounded-md">
                                    <option value="">-- Bấm để chọn --</option>
                                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                        )}
                        <button onClick={handlePurge} className="w-full py-3 mt-2 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-colors flex items-center justify-center gap-2">
                           <Trash2 size={18}/> Xác Nhận Xóa Dữ Liệu Trực Tiếp
                        </button>
                    </div>
                </div>
            </div>

            {/* SCHEMA EDITOR */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        <Eye className="text-emerald-500" /> Cấu Hình Bảng (Schema Editor)
                    </h2>
                    <div className="flex gap-2">
                        {!isEditingSchema && (
                            <button onClick={() => setIsEditingSchema(true)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-sm">
                                Chỉnh sửa cấu hình bảng
                            </button>
                        )}
                        {isEditingSchema && (
                            <button onClick={handleSaveSchema} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg transition-colors shadow-sm">
                                Lưu Thay Đổi (Save json)
                            </button>
                        )}
                    </div>
                </div>

                {!currentSchema ? (
                    <div className="p-6 bg-slate-50 border border-slate-200 rounded-lg text-center">
                        <p className="text-slate-600 font-medium">Vui lòng chọn một bảng dữ liệu để xem schema</p>
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 gap-4 mb-6 p-4 bg-slate-50 border border-slate-200 rounded-lg">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Tên Hiển Thị (Display Name)</label>
                                <input 
                                    type="text" 
                                    value={currentSchema.display_name || ''} 
                                    onChange={e => handleUpdateTableMeta('display_name', e.target.value)}
                                    disabled={!isEditingSchema}
                                    className={`w-full px-3 py-2 border rounded-md ${!isEditingSchema ? 'bg-slate-100 text-slate-500 cursor-not-allowed' : ''}`}
                                />
                            </div>
                        </div>

                        <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-left text-sm text-slate-600">
                        <thead className="bg-slate-100 text-slate-800 font-medium">
                            <tr>
                                <th className="px-4 py-3 border-b">Tên Kỹ Thuật (Key)</th>
                                <th className="px-4 py-3 border-b">Kiểu Dữ Liệu</th>
                                <th className="px-4 py-3 border-b">Ghi Chú & Tên Đọc Hiểu</th>
                                <th className="px-4 py-3 border-b w-24 text-center">Trạng Thái</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {(currentSchema?.columns || []).map((col: any, idx: number) => (
                                <tr key={col.name + idx} className={`hover:bg-slate-50 ${col.is_hidden ? 'opacity-50 line-through' : ''}`}>
                                    <td className="px-4 py-3 font-medium text-indigo-600">
                                        <input 
                                            type="text" 
                                            value={col.name || ''} 
                                            onChange={e => handleUpdateColumnMeta(idx, 'name', e.target.value)}
                                            disabled={!isEditingSchema}
                                            className={`w-full px-2 py-1 border border-slate-200 rounded font-medium text-indigo-600 ${isEditingSchema ? 'focus:ring-1 focus:ring-indigo-500' : 'bg-transparent border-transparent cursor-default'}`}
                                        />
                                    </td>
                                    <td className="px-4 py-3"><code className="bg-slate-100 px-2 py-0.5 rounded border border-slate-200">{col.type}</code></td>
                                    <td className="px-4 py-3">
                                        <input 
                                            type="text" 
                                            value={col.description || ''} 
                                            onChange={e => handleUpdateColumnMeta(idx, 'description', e.target.value)}
                                            disabled={!isEditingSchema}
                                            className={`w-full px-2 py-1 border border-slate-200 rounded ${isEditingSchema ? 'focus:ring-1 focus:ring-indigo-500' : 'bg-transparent border-transparent cursor-default'}`}
                                        />
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        <button 
                                            onClick={() => handleUpdateColumnMeta(idx, 'is_hidden', !col.is_hidden)}
                                            disabled={!isEditingSchema}
                                            className={`text-xs px-2 py-1 border rounded ${col.is_hidden ? 'bg-slate-200 text-slate-600' : 'bg-green-100 text-green-700 border-green-200'} ${!isEditingSchema ? 'opacity-70 cursor-not-allowed' : 'hover:opacity-80'}`}
                                        >
                                            {col.is_hidden ? 'Đang Ẩn' : 'Hiển thị'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                        </div>
                    </>
                )}
            </div>
        </div>
        </DashboardLayout>
    );
}
