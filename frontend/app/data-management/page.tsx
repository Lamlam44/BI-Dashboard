'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '../components/DashboardLayout';
import {
  Upload, Database, RefreshCw, Activity, Server,
  Table2, Link2, FileSpreadsheet, Play, CheckCircle2,
  XCircle, Clock, ChevronDown, ChevronUp, AlertTriangle,
  Trash2, AlertCircle, Download, Eye,
} from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../store/useAuth';
import { API_BASE_URL } from '../lib/api';
const DM_API = `${API_BASE_URL}/data`;

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

interface TableInfo {
  table_name: string;
  row_count: number;
  last_updated: string | null;
}

interface DwHealth {
  fact_tables: TableInfo[];
  dim_tables: TableInfo[];
  agg_tables: TableInfo[];
  other_tables: TableInfo[];
  total_tables: number;
}

interface DataSource {
  id: string;
  name: string;
  type: string;
  host: string;
  port: number;
  database: string;
  user: string;
  status: string;
  last_sync: string | null;
}

interface EtlStatus {
  running: boolean;
  last_run: string | null;
  last_status: string;
  last_error: string | null;
  last_duration_seconds: number | null;
  tables_built: string[];
}

interface CsvPreview {
  filename: string;
  rows: number;
  columns: string[];
  preview: Record<string, any>[];
  null_counts: Record<string, number>;
  dw_tables: Record<string, string[]>;
}

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

const fmtNum = (n: number) => new Intl.NumberFormat('en-US').format(n);

type TabKey = 'overview' | 'etl' | 'csv' | 'schema';

const StatusBadge = ({ status }: { status: string }) => {
  const colors: Record<string, string> = {
    connected: 'bg-green-100 text-green-700',
    success: 'bg-green-100 text-green-700',
    running: 'bg-blue-100 text-blue-700',
    error: 'bg-red-100 text-red-700',
    pending: 'bg-yellow-100 text-yellow-700',
    idle: 'bg-slate-100 text-slate-600',
  };
  const Icons: Record<string, React.ReactNode> = {
    connected: <CheckCircle2 size={14} />,
    success: <CheckCircle2 size={14} />,
    running: <RefreshCw size={14} className="animate-spin" />,
    error: <XCircle size={14} />,
    pending: <Clock size={14} />,
    idle: <Clock size={14} />,
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.idle}`}>
      {Icons[status] || Icons.idle} {status}
    </span>
  );
};

// ═══════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════

function DataManagementContent() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // DW Health
  const [dwHealth, setDwHealth] = useState<DwHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Data Sources
  const [dataSources, setDataSources] = useState<DataSource[]>([]);

  // ETL Status
  const [etlStatus, setEtlStatus] = useState<EtlStatus | null>(null);
  const [etlPolling, setEtlPolling] = useState(false);

  // CSV Upload
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CsvPreview | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [targetTable, setTargetTable] = useState('');
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [loadResult, setLoadResult] = useState<string | null>(null);

  // Schema Editor (keep from original)
  const [schemas, setSchemas] = useState<any>({});
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [isEditingSchema, setIsEditingSchema] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');

  // Sections toggle
  const [showDim, setShowDim] = useState(false);
  const [showOther, setShowOther] = useState(false);

  // ── Load data ──────────────────────────────────────────────

  const loadDwHealth = useCallback(() => {
    setHealthLoading(true);
    axios.get(`${DM_API}/dw-health`)
      .then(res => setDwHealth(res.data))
      .catch(() => {})
      .finally(() => setHealthLoading(false));
  }, []);

  const loadDataSources = useCallback(() => {
    axios.get(`${DM_API}/data-sources`)
      .then(res => setDataSources(Array.isArray(res.data) ? res.data : []))
      .catch(() => {});
  }, []);

  const loadEtlStatus = useCallback(() => {
    axios.get(`${DM_API}/etl/status`)
      .then(res => setEtlStatus(res.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadDwHealth();
    loadDataSources();
    loadEtlStatus();
  }, [loadDwHealth, loadDataSources, loadEtlStatus]);

  // Load schemas for Schema Editor tab
  useEffect(() => {
    fetch(`${DM_API}/schema`)
      .then(res => res.json())
      .then(data => {
        setSchemas(data);
        if (Object.keys(data).length > 0) setSelectedTable(Object.keys(data)[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedTable && schemas[selectedTable]?.deletion_strategy === 'CATEGORY') {
      fetch(`${DM_API}/categories/${selectedTable}`)
        .then(res => res.json())
        .then(data => setCategories(data))
        .catch(() => {});
    }
  }, [selectedTable, schemas]);

  // ETL polling while running
  useEffect(() => {
    if (!etlPolling) return;
    const interval = setInterval(() => {
      loadEtlStatus();
      if (etlStatus && !etlStatus.running) {
        setEtlPolling(false);
        loadDwHealth();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [etlPolling, etlStatus, loadEtlStatus, loadDwHealth]);

  // ── Handlers ───────────────────────────────────────────────

  const handleRunEtl = () => {
    axios.post(`${DM_API}/etl/run`)
      .then(() => {
        setEtlPolling(true);
        loadEtlStatus();
      })
      .catch(() => alert('Lỗi khi chạy ETL pipeline'));
  };

  const handleTestSource = (sourceId: string) => {
    axios.post(`${DM_API}/data-sources/${sourceId}/test`)
      .then(res => {
        loadDataSources();
        if (res.data.status === 'connected') {
          alert(`Kết nối thành công! ${res.data.tables?.length || 0} bảng được phát hiện.`);
        } else {
          alert(`Lỗi kết nối: ${res.data.message}`);
        }
      })
      .catch(() => alert('Lỗi test kết nối'));
  };

  const handleCsvSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvFile(file);
    setCsvPreview(null);
    setLoadResult(null);
    setCsvUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(`${DM_API}/csv-upload-preview`, formData);
      setCsvPreview(res.data);
      const autoMap: Record<string, string> = {};
      if (res.data.dw_tables && targetTable && res.data.dw_tables[targetTable]) {
        const dwCols = res.data.dw_tables[targetTable];
        for (const col of res.data.columns) {
          const match = dwCols.find((dc: string) => dc.toLowerCase() === col.toLowerCase());
          if (match) autoMap[col] = match;
        }
      }
      setColumnMapping(autoMap);
    } catch {
      alert('Lỗi đọc file CSV');
    } finally {
      setCsvUploading(false);
    }
  };

  const handleCsvLoad = async () => {
    if (!csvFile || !targetTable || Object.keys(columnMapping).length === 0) {
      alert('Vui lòng chọn file, bảng đích và mapping cột');
      return;
    }
    setCsvUploading(true);
    setLoadResult(null);

    const formData = new FormData();
    formData.append('file', csvFile);
    formData.append('target_table', targetTable);
    formData.append('column_mapping', JSON.stringify(columnMapping));

    try {
      const res = await axios.post(`${DM_API}/csv-transform-load`, formData);
      setLoadResult(`Thành công! ${res.data.rows_affected} dòng được nạp vào ${targetTable}.`);
      loadDwHealth();
    } catch (err: any) {
      setLoadResult(`Lỗi: ${err.response?.data?.detail || err.message}`);
    } finally {
      setCsvUploading(false);
    }
  };

  // Auto-map when target table changes
  useEffect(() => {
    if (!csvPreview || !targetTable || !csvPreview.dw_tables[targetTable]) return;
    const dwCols = csvPreview.dw_tables[targetTable];
    const autoMap: Record<string, string> = {};
    for (const col of csvPreview.columns) {
      const match = dwCols.find(dc => dc.toLowerCase() === col.toLowerCase());
      if (match) autoMap[col] = match;
    }
    setColumnMapping(autoMap);
  }, [targetTable, csvPreview]);

  // Schema handlers
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
      return { ...prev, [selectedTable]: updatedTable };
    });
  };

  const handleSaveSchema = async () => {
    try {
      const res = await fetch(`${DM_API}/schema`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(schemas)
      });
      if (res.ok) {
        alert('Đã lưu cấu hình Schema thành công!');
        setIsEditingSchema(false);
      } else { alert('Lỗi lưu cấu hình.'); }
    } catch { alert('Lỗi gọi API lưu cấu hình.'); }
  };

  const handlePurge = async () => {
    if (!confirm(`CẢNH BÁO: Rủi ro xóa dữ liệu trên bảng ${selectedTable}! Bạn có chắc chắn?`)) return;
    try {
      const res = await fetch(`${DM_API}/purge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table_name: selectedTable,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          category: selectedCategory || undefined
        })
      });
      const result = await res.json();
      alert(`Xóa thành công! Số dòng đã xóa: ${result.deleted_rows}, Còn lại: ${result.remaining_rows}`);
    } catch { alert('Lỗi! Vui lòng kiểm tra lại Backup.'); }
  };

  const currentSchema = schemas[selectedTable];

  // ── Render helpers ─────────────────────────────────────────

  const renderTableGroup = (title: string, tables: TableInfo[], icon: React.ReactNode, color: string) => (
    <div className="space-y-2">
      <h3 className={`text-sm font-semibold ${color} flex items-center gap-1.5`}>
        {icon} {title} ({tables.length})
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {tables.map(t => (
          <div key={t.table_name} className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 flex justify-between items-center">
            <div>
              <p className="text-sm font-medium text-slate-800 truncate" title={t.table_name}>{t.table_name}</p>
              <p className="text-xs text-slate-500">{t.last_updated ? new Date(t.last_updated).toLocaleString('vi-VN') : '—'}</p>
            </div>
            <span className="text-sm font-semibold text-slate-700">{fmtNum(t.row_count)}</span>
          </div>
        ))}
      </div>
    </div>
  );

  // Tab config
  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'DW Overview', icon: <Activity size={16} /> },
    { key: 'etl', label: 'ETL & Sources', icon: <Play size={16} /> },
    { key: 'csv', label: 'CSV Upload', icon: <FileSpreadsheet size={16} /> },
    { key: 'schema', label: 'Schema & Purge', icon: <Eye size={16} /> },
  ];

  return (
    <DashboardLayout>
      <div className="p-6 space-y-6 bg-slate-50 min-h-screen">

        {/* ── Header ─────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
              <Database className="text-indigo-600" /> Quản Lý Dữ Liệu
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              ETL Pipeline &bull; CSV Ingestion &bull; Data Sources &bull; Data Warehouse Health
            </p>
          </div>
          <button
            onClick={() => { loadDwHealth(); loadEtlStatus(); loadDataSources(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {/* ── Tab Navigation ─────────────────────────────────── */}
        <div className="flex gap-1 bg-white rounded-xl border border-slate-200 p-1 shadow-sm">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* ══════ TAB: DW Overview ═══════════════════════════ */}
        {activeTab === 'overview' && (
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
              <Activity className="text-emerald-500" /> Data Warehouse Overview
            </h2>

            {healthLoading ? (
              <p className="text-slate-400 text-sm">Đang tải thông tin...</p>
            ) : dwHealth ? (
              <div className="space-y-4">
                {/* Summary stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                    <p className="text-xs text-blue-600 font-medium">Fact Tables</p>
                    <p className="text-xl font-bold text-blue-900">{dwHealth.fact_tables.length}</p>
                  </div>
                  <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
                    <p className="text-xs text-purple-600 font-medium">Dim Tables</p>
                    <p className="text-xl font-bold text-purple-900">{dwHealth.dim_tables.length}</p>
                  </div>
                  <div className="bg-green-50 rounded-lg p-3 border border-green-200">
                    <p className="text-xs text-green-600 font-medium">Aggregate Tables</p>
                    <p className="text-xl font-bold text-green-900">{dwHealth.agg_tables.length}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                    <p className="text-xs text-slate-600 font-medium">Tổng số bảng</p>
                    <p className="text-xl font-bold text-slate-900">{dwHealth.total_tables}</p>
                  </div>
                </div>

                {renderTableGroup('Fact Tables', dwHealth.fact_tables, <Table2 size={14} />, 'text-blue-600')}
                {renderTableGroup('Aggregate Tables', dwHealth.agg_tables, <Table2 size={14} />, 'text-green-600')}

                <button
                  onClick={() => setShowDim(!showDim)}
                  className="flex items-center gap-1 text-sm text-purple-600 hover:underline"
                >
                  {showDim ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  {showDim ? 'Ẩn' : 'Hiện'} Dimension Tables ({dwHealth.dim_tables.length})
                </button>
                {showDim && renderTableGroup('Dimension Tables', dwHealth.dim_tables, <Table2 size={14} />, 'text-purple-600')}

                {dwHealth.other_tables.length > 0 && (
                  <>
                    <button
                      onClick={() => setShowOther(!showOther)}
                      className="flex items-center gap-1 text-sm text-slate-600 hover:underline"
                    >
                      {showOther ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      {showOther ? 'Ẩn' : 'Hiện'} Other Tables ({dwHealth.other_tables.length})
                    </button>
                    {showOther && renderTableGroup('Other', dwHealth.other_tables, <Table2 size={14} />, 'text-slate-600')}
                  </>
                )}
              </div>
            ) : (
              <p className="text-red-500 text-sm">Không thể tải thông tin DW</p>
            )}

            {/* Architecture Info */}
            <div className="mt-8 pt-6 border-t border-slate-200">
              <h3 className="text-md font-bold text-slate-800 mb-3 flex items-center gap-2">
                <Database className="text-indigo-500" size={18} /> Kiến trúc ETL Pipeline
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="font-semibold text-blue-800 mb-2">1. Extract (Trích xuất)</h4>
                  <ul className="text-sm text-blue-700 space-y-1">
                    <li>• Upload file CSV/Excel từ nguồn bên ngoài</li>
                    <li>• Kết nối database POS System</li>
                    <li>• Preview dữ liệu trước khi nạp</li>
                  </ul>
                </div>
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                  <h4 className="font-semibold text-orange-800 mb-2">2. Transform (Biến đổi)</h4>
                  <ul className="text-sm text-orange-700 space-y-1">
                    <li>• Mapping cột CSV → Star Schema DW</li>
                    <li>• Xây ABC classification, RFM segmentation</li>
                    <li>• Tính aggregate KPIs, inventory metrics</li>
                  </ul>
                </div>
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h4 className="font-semibold text-green-800 mb-2">3. Load (Nạp)</h4>
                  <ul className="text-sm text-green-700 space-y-1">
                    <li>• UPSERT vào bảng DW (deduplicate by PK)</li>
                    <li>• Build aggregate tables (ETL Pipeline)</li>
                    <li>• Tự động sync customer segments</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══════ TAB: ETL & Data Sources ═══════════════════ */}
        {activeTab === 'etl' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* ETL Pipeline Control */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
                <Play className="text-blue-500" /> ETL Pipeline
              </h2>
              <p className="text-sm text-slate-500 mb-4">
                Xây dựng/cập nhật bảng aggregate từ dữ liệu DW gốc: Product ABC, Customer RFM,
                KPI Summary, Store Monthly Costs.
              </p>

              {etlStatus && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">Trạng thái:</span>
                    <StatusBadge status={etlStatus.last_status} />
                  </div>
                  {etlStatus.last_run && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-500">Lần chạy cuối:</span>
                      <span className="text-slate-700">{new Date(etlStatus.last_run).toLocaleString('vi-VN')}</span>
                    </div>
                  )}
                  {etlStatus.last_duration_seconds != null && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-500">Thời gian:</span>
                      <span className="text-slate-700">{etlStatus.last_duration_seconds}s</span>
                    </div>
                  )}
                  {etlStatus.tables_built.length > 0 && (
                    <div className="text-sm">
                      <span className="text-slate-500">Tables built:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {etlStatus.tables_built.map(t => (
                          <span key={t} className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs">{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {etlStatus.last_error && (
                    <div className="text-sm text-red-600 flex items-start gap-1">
                      <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                      <span>{etlStatus.last_error}</span>
                    </div>
                  )}
                </div>
              )}

              <button
                onClick={handleRunEtl}
                disabled={etlStatus?.running}
                className={`w-full py-3 font-bold rounded-lg flex items-center justify-center gap-2 transition-colors ${
                  etlStatus?.running
                    ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
              >
                {etlStatus?.running ? (
                  <><RefreshCw size={18} className="animate-spin" /> Đang chạy ETL...</>
                ) : (
                  <><Play size={18} /> Chạy ETL Pipeline</>
                )}
              </button>
            </div>

            {/* Data Sources */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
                <Link2 className="text-purple-500" /> Nguồn Dữ Liệu (Data Sources)
              </h2>
              <p className="text-sm text-slate-500 mb-4">
                Kết nối với hệ thống POS hoặc database bên ngoài để trích xuất dữ liệu định kỳ.
              </p>

              {dataSources.length === 0 ? (
                <p className="text-sm text-slate-400">Chưa có nguồn dữ liệu nào.</p>
              ) : (
                <div className="space-y-3">
                  {dataSources.map(src => (
                    <div key={src.id} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Server size={16} className="text-slate-500" />
                          <span className="font-semibold text-slate-800">{src.name}</span>
                        </div>
                        <StatusBadge status={src.status} />
                      </div>
                      <div className="text-xs text-slate-500 space-y-0.5">
                        <p>Host: {src.host}:{src.port} | DB: {src.database} | User: {src.user}</p>
                        {src.last_sync && <p>Đồng bộ cuối: {new Date(src.last_sync).toLocaleString('vi-VN')}</p>}
                      </div>
                      <button
                        onClick={() => handleTestSource(src.id)}
                        className="mt-2 text-sm px-3 py-1 bg-white border border-slate-300 rounded hover:bg-slate-50"
                      >
                        Test kết nối
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ══════ TAB: CSV Upload ════════════════════════════ */}
        {activeTab === 'csv' && (
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-800 mb-2 flex items-center gap-2">
              <FileSpreadsheet className="text-orange-500" /> Nạp File CSV/Excel → Star Schema Transform
            </h2>
            <p className="text-sm text-slate-500 mb-4">
              Upload file CSV hoặc Excel, xem trước dữ liệu, mapping cột sang bảng DW, rồi nạp vào Data Warehouse.
              Dữ liệu sẽ tự động deduplicate theo Primary Key (UPSERT).
            </p>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Upload area */}
              <div>
                <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 flex flex-col items-center bg-slate-50 hover:bg-slate-100 transition-colors cursor-pointer relative">
                  <input
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    onChange={handleCsvSelect}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <Upload size={36} className="text-slate-400 mb-2" />
                  <span className="text-slate-600 font-medium text-center">
                    {csvFile ? csvFile.name : 'Kéo thả file CSV/Excel vào đây'}
                  </span>
                  {csvPreview && (
                    <span className="text-sm text-green-600 mt-1">
                      {csvPreview.rows} dòng, {csvPreview.columns.length} cột
                    </span>
                  )}
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Bảng đích (Target Table)</label>
                  <select
                    value={targetTable}
                    onChange={e => setTargetTable(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  >
                    <option value="">-- Chọn bảng --</option>
                    {csvPreview && Object.keys(csvPreview.dw_tables).map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Column mapping */}
              <div>
                {csvPreview && targetTable && csvPreview.dw_tables[targetTable] ? (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">Column Mapping (CSV → DW)</h3>
                    <div className="max-h-72 overflow-y-auto space-y-2">
                      {csvPreview.columns.map(col => (
                        <div key={col} className="flex items-center gap-2">
                          <span className="text-sm text-slate-700 w-40 truncate" title={col}>{col}</span>
                          <span className="text-slate-400">→</span>
                          <select
                            value={columnMapping[col] || ''}
                            onChange={e => {
                              const newMap = { ...columnMapping };
                              if (e.target.value) newMap[col] = e.target.value;
                              else delete newMap[col];
                              setColumnMapping(newMap);
                            }}
                            className="flex-1 px-2 py-1 border border-slate-300 rounded text-sm"
                          >
                            <option value="">-- Bỏ qua --</option>
                            {csvPreview.dw_tables[targetTable].map(dc => (
                              <option key={dc} value={dc}>{dc}</option>
                            ))}
                          </select>
                        </div>
                      ))}
                    </div>

                    <button
                      onClick={handleCsvLoad}
                      disabled={csvUploading || Object.keys(columnMapping).length === 0}
                      className={`w-full mt-4 py-3 font-bold rounded-lg flex items-center justify-center gap-2 transition-colors ${
                        csvUploading || Object.keys(columnMapping).length === 0
                          ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                          : 'bg-orange-600 hover:bg-orange-700 text-white'
                      }`}
                    >
                      {csvUploading ? (
                        <><RefreshCw size={18} className="animate-spin" /> Đang nạp...</>
                      ) : (
                        <><Upload size={18} /> Transform & Load vào DW</>
                      )}
                    </button>

                    {loadResult && (
                      <div className={`mt-3 p-3 rounded-lg text-sm ${
                        loadResult.startsWith('Thành công') ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
                      }`}>
                        {loadResult}
                      </div>
                    )}
                  </div>
                ) : csvPreview ? (
                  <div className="flex items-center justify-center h-full text-sm text-slate-400">
                    Chọn bảng đích để bắt đầu mapping cột
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-sm text-slate-400">
                    Upload file CSV/Excel để xem trước
                  </div>
                )}
              </div>
            </div>

            {/* Preview table */}
            {csvPreview && csvPreview.preview.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Xem trước dữ liệu (10 dòng đầu)</h3>
                <div className="overflow-x-auto max-h-64 border border-slate-200 rounded-lg">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-100 sticky top-0">
                      <tr>
                        {csvPreview.columns.map(col => (
                          <th key={col} className="px-3 py-2 text-left text-slate-700 font-medium whitespace-nowrap">{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {csvPreview.preview.map((row, idx) => (
                        <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                          {csvPreview.columns.map(col => (
                            <td key={col} className="px-3 py-1.5 whitespace-nowrap text-slate-600 max-w-[200px] truncate">
                              {row[col] != null ? String(row[col]) : <span className="text-slate-300">NULL</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══════ TAB: Schema & Purge ═══════════════════════ */}
        {activeTab === 'schema' && (
          <div className="space-y-6">
            {/* Table Selector */}
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
              <button
                onClick={() => window.open(`${DM_API}/template/${selectedTable}`)}
                className="flex items-center gap-2 px-6 py-2 bg-slate-800 text-white font-medium rounded-lg hover:bg-slate-900 transition-colors"
              >
                <Download size={18} /> Tải Template
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Purge */}
              <div className="bg-white p-6 rounded-xl border border-red-100 shadow-sm relative overflow-hidden">
                <div className="absolute top-0 right-0 w-32 h-32 bg-red-50 rounded-bl-full -z-0"></div>
                <h2 className="text-lg font-bold text-red-700 mb-4 flex items-center gap-2 relative z-10">
                  <Trash2 /> Xóa Dữ Liệu (Smart Purge)
                </h2>
                <div className="text-sm text-slate-600 mb-4 relative z-10 p-3 bg-red-50 border border-red-100 rounded-lg flex gap-3">
                  <AlertCircle className="text-red-500 flex-shrink-0" size={20} />
                  <div>Dữ liệu sẽ được <b>Backup</b> trước khi purge. Chế độ: <b>{currentSchema?.deletion_strategy}</b></div>
                </div>

                <div className="space-y-4 relative z-10">
                  {currentSchema && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Chiến Lược Xóa</label>
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
                        <label className="block text-sm font-medium text-slate-700 mb-1">Từ ngày</label>
                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-full px-3 py-2 border rounded-md" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">Đến ngày</label>
                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="w-full px-3 py-2 border rounded-md" />
                      </div>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Chọn Category</label>
                      <select value={selectedCategory} onChange={e => setSelectedCategory(e.target.value)} className="w-full px-3 py-2 border rounded-md">
                        <option value="">-- Chọn --</option>
                        {categories.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  )}
                  <button onClick={handlePurge} className="w-full py-3 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg">
                    <Trash2 size={18} className="inline mr-2" /> Xác Nhận Xóa Dữ Liệu
                  </button>
                </div>
              </div>

              {/* Schema Editor */}
              <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                    <Eye className="text-emerald-500" /> Schema Editor
                  </h2>
                  <div>
                    {!isEditingSchema ? (
                      <button onClick={() => setIsEditingSchema(true)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg text-sm">
                        Chỉnh sửa
                      </button>
                    ) : (
                      <button onClick={handleSaveSchema} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg text-sm">
                        Lưu Thay Đổi
                      </button>
                    )}
                  </div>
                </div>

                {!currentSchema ? (
                  <p className="text-slate-500 text-sm text-center py-6">Chọn bảng để xem schema</p>
                ) : (
                  <>
                    <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <label className="block text-xs font-medium text-slate-500 mb-1">Tên Hiển Thị</label>
                      <input
                        type="text"
                        value={currentSchema.display_name || ''}
                        onChange={e => handleUpdateTableMeta('display_name', e.target.value)}
                        disabled={!isEditingSchema}
                        className={`w-full px-3 py-1.5 border rounded-md text-sm ${!isEditingSchema ? 'bg-slate-100 text-slate-500' : ''}`}
                      />
                    </div>

                    <div className="overflow-x-auto max-h-80 rounded-lg border border-slate-200">
                      <table className="w-full text-left text-xs text-slate-600">
                        <thead className="bg-slate-100 text-slate-800 font-medium sticky top-0">
                          <tr>
                            <th className="px-3 py-2 border-b">Cột</th>
                            <th className="px-3 py-2 border-b">Kiểu</th>
                            <th className="px-3 py-2 border-b">Ghi Chú</th>
                            <th className="px-3 py-2 border-b w-16 text-center">TT</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {(currentSchema?.columns || []).map((col: any, idx: number) => (
                            <tr key={col.name + idx} className={`hover:bg-slate-50 ${col.is_hidden ? 'opacity-50' : ''}`}>
                              <td className="px-3 py-2 font-medium text-indigo-600">
                                <input
                                  type="text" value={col.name || ''}
                                  onChange={e => handleUpdateColumnMeta(idx, 'name', e.target.value)}
                                  disabled={!isEditingSchema}
                                  className={`w-full px-1 py-0.5 border rounded text-xs ${isEditingSchema ? '' : 'bg-transparent border-transparent'}`}
                                />
                              </td>
                              <td className="px-3 py-2"><code className="bg-slate-100 px-1 py-0.5 rounded text-xs">{col.type}</code></td>
                              <td className="px-3 py-2">
                                <input
                                  type="text" value={col.description || ''}
                                  onChange={e => handleUpdateColumnMeta(idx, 'description', e.target.value)}
                                  disabled={!isEditingSchema}
                                  className={`w-full px-1 py-0.5 border rounded text-xs ${isEditingSchema ? '' : 'bg-transparent border-transparent'}`}
                                />
                              </td>
                              <td className="px-3 py-2 text-center">
                                <button
                                  onClick={() => handleUpdateColumnMeta(idx, 'is_hidden', !col.is_hidden)}
                                  disabled={!isEditingSchema}
                                  className={`text-xs px-1.5 py-0.5 border rounded ${col.is_hidden ? 'bg-slate-200 text-slate-600' : 'bg-green-100 text-green-700'}`}
                                >
                                  {col.is_hidden ? 'Ẩn' : 'On'}
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
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}

export default function DataManagementPage() {
  const router = useRouter();
  const { user } = useAuth();

  useEffect(() => {
    if (user && user.role !== 'admin') {
      router.replace('/dashboard');
    }
  }, [user, router]);

  if (!user || user.role !== 'admin') {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-[60vh] text-slate-500">
          Đang chuyển hướng...
        </div>
      </DashboardLayout>
    );
  }

  return <DataManagementContent />;
}
