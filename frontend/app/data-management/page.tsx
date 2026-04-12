'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '../components/DashboardLayout';
import {
  Upload, Database, RefreshCw, Activity,
  Table2, FileSpreadsheet, CheckCircle2,
  XCircle, Clock, ChevronDown, ChevronUp,
  Download, FileDown,
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

const fmtNum = (n: number) => new Intl.NumberFormat('vi-VN').format(n);

type TabKey = 'overview' | 'csv';

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
// Fallback table list (used when API not yet loaded)
// ═══════════════════════════════════════════════════════════════
const FALLBACK_DIM_FACT_TABLES: { table_name: string; row_count: number }[] = [
  { table_name: 'FactSales',          row_count: 0 },
  { table_name: 'FactOnlineSales',    row_count: 0 },
  { table_name: 'FactInventory',      row_count: 0 },
  { table_name: 'FactExchangeRate',   row_count: 0 },
  { table_name: 'FactITMachine',      row_count: 0 },
  { table_name: 'FactITSLA',          row_count: 0 },
  { table_name: 'FactSalesQuota',     row_count: 0 },
  { table_name: 'FactStrategyPlan',   row_count: 0 },
  { table_name: 'DimProduct',         row_count: 0 },
  { table_name: 'DimProductCategory', row_count: 0 },
  { table_name: 'DimProductSubcategory', row_count: 0 },
  { table_name: 'DimStore',           row_count: 0 },
  { table_name: 'DimCustomer',        row_count: 0 },
  { table_name: 'DimEmployee',        row_count: 0 },
  { table_name: 'DimPromotion',       row_count: 0 },
  { table_name: 'DimDate',            row_count: 0 },
  { table_name: 'DimChannel',         row_count: 0 },
  { table_name: 'DimCurrency',        row_count: 0 },
  { table_name: 'DimGeography',       row_count: 0 },
  { table_name: 'DimSalesTerritory',  row_count: 0 },
  { table_name: 'DimAccount',         row_count: 0 },
  { table_name: 'DimEntity',          row_count: 0 },
  { table_name: 'DimMachine',         row_count: 0 },
  { table_name: 'DimScenario',        row_count: 0 },
  { table_name: 'DimOutage',          row_count: 0 },
];

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

  // Fast-refresh status banner
  const [etlRunning, setEtlRunning] = useState(false);
  const [etlMessage, setEtlMessage] = useState<string | null>(null);

  // CSV Upload
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CsvPreview | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [targetTable, setTargetTable] = useState('');
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [loadResult, setLoadResult] = useState<string | null>(null);

  // Export template — khởi tạo ngay với fallback list để dropdown luôn có dữ liệu
  const [dimFactTables, setDimFactTables] = useState<{ table_name: string; row_count: number }[]>(FALLBACK_DIM_FACT_TABLES);
  const [exportTable, setExportTable] = useState('');
  const [exportFormat, setExportFormat] = useState<'csv' | 'excel'>('excel');
  const [exportLoading, setExportLoading] = useState(false);

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

  const runFastRefresh = useCallback(async () => {
    setEtlRunning(true);
    setEtlMessage('Đang cập nhật dữ liệu real-time...');
    try {
      await axios.post(`${DM_API}/etl/fast-refresh`);
      setEtlMessage('Cập nhật dữ liệu thành công!');
      loadDwHealth();
    } catch {
      setEtlMessage('Lỗi cập nhật dữ liệu');
    } finally {
      setEtlRunning(false);
      setTimeout(() => setEtlMessage(null), 5000);
    }
  }, [loadDwHealth]);

  useEffect(() => {
    loadDwHealth();
    loadDataSources();
    // Load danh sách bảng DIM/FACT với row count từ API; fallback list luôn sẵn
    axios.get(`${DM_API}/dim-fact-tables`)
      .then(res => {
        if (Array.isArray(res.data) && res.data.length > 0) {
          setDimFactTables(res.data);
        }
      })
      .catch(() => { /* giữ nguyên fallback list */ });
  }, [loadDwHealth, loadDataSources]);

  // ── Handlers ───────────────────────────────────────────────

  // ── Handlers ───────────────────────────────────────────────

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
      let msg = `Thành công! ${res.data.rows_processed} dòng xử lý, ${res.data.rows_affected} dòng được nạp vào ${targetTable}.`;
      if (res.data.skipped_duplicate_ids?.length > 0) {
        const ids = res.data.skipped_duplicate_ids.slice(0, 30).join(', ');
        const more = res.data.skipped_duplicate_ids.length > 30 ? ` ... và ${res.data.skipped_duplicate_ids.length - 30} ID khác` : '';
        msg += `\nBỏ qua ${res.data.skipped_duplicate_ids.length} đối tượng đã tồn tại (PK trùng): ${ids}${more}`;
      }
      setLoadResult(msg);
      loadDwHealth();
      runFastRefresh();
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

  const handleExportTemplate = async () => {
    if (!exportTable) return;
    setExportLoading(true);
    try {
      const url = `${DM_API}/table-structure-template?table_name=${encodeURIComponent(exportTable)}&format=${exportFormat}`;
      const res = await axios.get(url, { responseType: 'blob' });
      const ext = exportFormat === 'excel' ? 'xlsx' : 'csv';
      const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `template_${exportTable}.${ext}`;
      link.click();
      window.URL.revokeObjectURL(blobUrl);
    } catch {
      alert('Lỗi khi xuất template');
    } finally {
      setExportLoading(false);
    }
  };

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
    { key: 'overview', label: 'Tổng quan DW', icon: <Activity size={16} /> },
    { key: 'csv', label: 'Nạp CSV/Excel', icon: <FileSpreadsheet size={16} /> },
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
              Nạp dữ liệu CSV &bull; Nguồn dữ liệu &bull; Sức khỏe Data Warehouse
            </p>
          </div>
          {/* ETL status toast */}
          {etlMessage && (
            <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
              etlRunning ? 'bg-blue-50 text-blue-700 border border-blue-200' :
              etlMessage.includes('thành công') ? 'bg-green-50 text-green-700 border border-green-200' :
              'bg-red-50 text-red-700 border border-red-200'
            }`}>
              {etlRunning && <RefreshCw size={14} className="animate-spin" />}
              {etlMessage}
            </div>
          )}
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
              <Activity className="text-emerald-500" /> Tổng Quan Data Warehouse
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
                    <li>• Nhận hóa đơn real-time từ Invoice Simulator</li>
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

        {/* ══════ TAB: CSV Upload ════════════════════════════ */}
        {activeTab === 'csv' && (
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-800 mb-2 flex items-center gap-2">
              <FileSpreadsheet className="text-orange-500" /> Nạp File CSV/Excel vào Data Warehouse
            </h2>
            <p className="text-sm text-slate-500 mb-4">
              Upload file CSV hoặc Excel, mapping cột và nạp vào bất kỳ bảng DIM hoặc FACT nào.
              <b> Bảng DIM</b>: chỉ thêm mới (bỏ qua đối tượng đã tồn tại theo PK, hiển thị danh sách bỏ qua).
              <b> Bảng FACT</b>: UPSERT, tự động giải quyết xung đột PK.
              Sau khi nạp, dữ liệu real-time hôm nay sẽ được cập nhật ngay.
            </p>

            {/* ── Export Template Block ─────────────────────────────── */}
            <div className="mb-6 p-4 bg-indigo-50 border border-indigo-200 rounded-xl">
              <h3 className="text-sm font-semibold text-indigo-800 mb-3 flex items-center gap-2">
                <FileDown size={16} /> Xuất file cấu trúc bảng (Template)
              </h3>
              <p className="text-xs text-indigo-600 mb-3">
                Tải file mẫu với cấu trúc cột đầy đủ (tên, kiểu dữ liệu, nullable...) để chuẩn bị dữ liệu nhập vào đúng định dạng.
              </p>
              <div className="flex flex-wrap gap-3 items-end">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-medium text-indigo-700 mb-1">Chọn bảng</label>
                  <select
                    value={exportTable}
                    onChange={e => setExportTable(e.target.value)}
                    className="w-full px-3 py-2 border border-indigo-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  >
                    <option value="">-- Chọn bảng DIM / FACT --</option>
                    <optgroup label="─── FACT Tables ───">
                      {dimFactTables
                        .filter(t => t.table_name.toLowerCase().startsWith('fact'))
                        .map(t => (
                          <option key={t.table_name} value={t.table_name}>
                            {t.table_name}{t.row_count > 0 ? ` (${new Intl.NumberFormat('vi-VN').format(t.row_count)} rows)` : ''}
                          </option>
                        ))}
                    </optgroup>
                    <optgroup label="─── DIM Tables ───">
                      {dimFactTables
                        .filter(t => t.table_name.toLowerCase().startsWith('dim'))
                        .map(t => (
                          <option key={t.table_name} value={t.table_name}>
                            {t.table_name}{t.row_count > 0 ? ` (${new Intl.NumberFormat('vi-VN').format(t.row_count)} rows)` : ''}
                          </option>
                        ))}
                    </optgroup>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-indigo-700 mb-1">Định dạng</label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setExportFormat('excel')}
                      className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        exportFormat === 'excel'
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-indigo-700 border-indigo-300 hover:bg-indigo-50'
                      }`}
                    >
                      Excel (.xlsx)
                    </button>
                    <button
                      onClick={() => setExportFormat('csv')}
                      className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        exportFormat === 'csv'
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-indigo-700 border-indigo-300 hover:bg-indigo-50'
                      }`}
                    >
                      CSV (.csv)
                    </button>
                  </div>
                </div>
                <button
                  onClick={handleExportTemplate}
                  disabled={!exportTable || exportLoading}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
                    !exportTable || exportLoading
                      ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-700 text-white'
                  }`}
                >
                  {exportLoading
                    ? <><RefreshCw size={15} className="animate-spin" /> Đang xuất...</>
                    : <><Download size={15} /> Tải xuống template</>
                  }
                </button>
              </div>
            </div>

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
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">Mapping cột (CSV → DW)</h3>
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
                        <><Upload size={18} /> Nạp dữ liệu vào DW</>
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

        {/* Schema & Purge tab removed */}

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
