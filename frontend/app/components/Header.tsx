'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Timer, RefreshCw } from 'lucide-react';
import { useRefresh, IntervalOption } from './RefreshProvider';
import AuthControl from './AuthControl';

const INTERVAL_OPTIONS: { value: IntervalOption; label: string }[] = [
  { value: 15, label: '15 phút' },
  { value: 30, label: '30 phút' },
  { value: 60, label: '1 giờ' },
  { value: 1440, label: '1 ngày' },
];

const Header = () => {
  const { intervalMinutes, setIntervalMinutes, forceRefresh, isRefreshing } = useRefresh();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const currentLabel = INTERVAL_OPTIONS.find((o) => o.value === intervalMinutes)?.label ?? '30 phút';

  return (
    <header className="fixed top-0 right-0 left-64 bg-white border-b border-slate-200 z-40">
      <div className="h-20 px-8 flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-800 tracking-tight">Hệ Thống BI Dashboard Thông Minh</h1>
          <span className="px-3 py-1 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full border border-indigo-100">Enterprise Edition</span>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-sm text-slate-500 font-medium">Contoso Retail DW</div>

          {/* Auth control */}
          <AuthControl />

          {/* Manual refresh button */}
          <button
            onClick={forceRefresh}
            disabled={isRefreshing}
            title={isRefreshing ? 'Đang chạy ETL Pipeline...' : 'Làm mới dữ liệu ngay (ETL + Refresh)'}
            className="p-2 rounded-lg text-slate-500 hover:text-blue-600 hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={18} className={isRefreshing ? 'animate-spin text-blue-500' : ''} />
          </button>

          {/* Refresh interval selector */}
          <div ref={menuRef} className="relative">
            <button
              onClick={() => setOpen((o) => !o)}
              title="Tùy chỉnh thời gian cập nhật"
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                open
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 border border-transparent'
              }`}
            >
              <Timer size={16} />
              <span className="hidden sm:inline">{currentLabel}</span>
            </button>

            {open && (
              <div className="absolute right-0 top-full mt-2 w-52 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-50">
                <p className="px-4 py-1.5 text-xs text-slate-400 font-semibold uppercase tracking-wide">Tự động cập nhật</p>
                {INTERVAL_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { setIntervalMinutes(opt.value); setOpen(false); }}
                    className={`w-full px-4 py-2 text-left text-sm flex items-center justify-between transition-colors ${
                      intervalMinutes === opt.value
                        ? 'bg-blue-50 text-blue-700 font-semibold'
                        : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    {opt.label}
                    {intervalMinutes === opt.value && (
                      <span className="w-2 h-2 rounded-full bg-blue-500" />
                    )}
                  </button>
                ))}
                <div className="border-t border-slate-100 mt-1 pt-1 px-4 py-1.5">
                  <p className="text-[11px] text-slate-400">Các nhóm chỉ số thời gian thực sẽ cập nhật ngay lập tức.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
