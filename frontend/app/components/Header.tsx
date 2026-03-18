'use client';

import { useState } from 'react';
import { Search, Calendar, MapPin } from 'lucide-react';

interface FilterState {
  dateRange: {
    start: string;
    end: string;
  };
  storeLocation: string;
  searchQuery: string;
}

const Header = () => {
  const [filters, setFilters] = useState<FilterState>({
    dateRange: {
      start: '2024-01-01',
      end: '2024-12-31',
    },
    storeLocation: 'All Stores',
    searchQuery: '',
  });

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showStoreDropdown, setShowStoreDropdown] = useState(false);

  const storeOptions = [
    'All Stores',
    'Store A',
    'Store B',
    'Store C',
    'Store D',
    'Store E',
  ];

  const handleDateChange = (field: 'start' | 'end', value: string) => {
    setFilters(prev => ({
      ...prev,
      dateRange: {
        ...prev.dateRange,
        [field]: value,
      },
    }));
  };

  const handleStoreChange = (store: string) => {
    setFilters(prev => ({
      ...prev,
      storeLocation: store,
    }));
    setShowStoreDropdown(false);
  };

  const handleSearchChange = (value: string) => {
    setFilters(prev => ({
      ...prev,
      searchQuery: value,
    }));
  };

  return (
    <header className="fixed top-0 right-0 left-64 bg-white border-b border-slate-200 z-40">
      <div className="h-20 px-8 flex items-center gap-6">
        {/* Date Range Picker */}
        <div className="relative">
          <button
            onClick={() => setShowDatePicker(!showDatePicker)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors text-slate-700 text-sm font-medium"
          >
            <Calendar size={18} className="text-slate-500" />
            <span>
              {filters.dateRange.start} to {filters.dateRange.end}
            </span>
          </button>

          {/* Date Picker Dropdown */}
          {showDatePicker && (
            <div className="absolute top-12 left-0 bg-white border border-slate-200 rounded-lg shadow-lg p-4 w-80 z-50">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={filters.dateRange.start}
                    onChange={(e) =>
                      handleDateChange('start', e.target.value)
                    }
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={filters.dateRange.end}
                    onChange={(e) =>
                      handleDateChange('end', e.target.value)
                    }
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900"
                  />
                </div>
                <button
                  onClick={() => setShowDatePicker(false)}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 rounded-lg transition-colors"
                >
                  Apply
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Store Location Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowStoreDropdown(!showStoreDropdown)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors text-slate-700 text-sm font-medium"
          >
            <MapPin size={18} className="text-slate-500" />
            <span>{filters.storeLocation}</span>
          </button>

          {/* Store Dropdown Menu */}
          {showStoreDropdown && (
            <div className="absolute top-12 left-0 bg-white border border-slate-200 rounded-lg shadow-lg py-1 w-40 z-50">
              {storeOptions.map((store) => (
                <button
                  key={store}
                  onClick={() => handleStoreChange(store)}
                  className={`
                    w-full text-left px-4 py-2 text-sm transition-colors
                    ${
                      filters.storeLocation === store
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-slate-700 hover:bg-slate-50'
                    }
                  `}
                >
                  {store}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Search Bar */}
        <div className="flex-1 max-w-xs">
          <div className="relative">
            <Search
              size={18}
              className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"
            />
            <input
              type="text"
              value={filters.searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search dashboards..."
              className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white text-slate-900 placeholder-slate-400 text-sm"
            />
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
