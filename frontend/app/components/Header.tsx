'use client';

import React from 'react';

const Header = () => {
  return (
    <header className="fixed top-0 right-0 left-64 bg-white border-b border-slate-200 z-40">
      <div className="h-20 px-8 flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-800 tracking-tight">BI Dashboard Intelligence System</h1>
          <span className="px-3 py-1 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full border border-indigo-100">Enterprise Edition</span>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-sm text-slate-500 font-medium">Contoso Retail DW</div>
          <div className="h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-bold border border-slate-300">
            A
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
