import { EmployeeOption, StoreOption } from './types';

type FiltersBarProps = {
  years: number[];
  months: number[];
  stores: StoreOption[];
  employees: EmployeeOption[];
  selectedYear: string;
  selectedMonth: string;
  selectedStoreKey: string;
  selectedEmployeeKey: string;
  onYearChange: (value: string) => void;
  onMonthChange: (value: string) => void;
  onStoreChange: (value: string) => void;
  onEmployeeChange: (value: string) => void;
};

export default function FiltersBar(props: FiltersBarProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <label className="text-sm text-slate-700">
        <span className="block mb-1 font-medium">Year</span>
        <select
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          value={props.selectedYear}
          onChange={(e) => props.onYearChange(e.target.value)}
        >
          <option value="">All</option>
          {props.years.map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm text-slate-700">
        <span className="block mb-1 font-medium">Month</span>
        <select
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          value={props.selectedMonth}
          onChange={(e) => props.onMonthChange(e.target.value)}
        >
          <option value="">All</option>
          {props.months.map((month) => (
            <option key={month} value={month}>
              {month}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm text-slate-700">
        <span className="block mb-1 font-medium">Store</span>
        <select
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          value={props.selectedStoreKey}
          onChange={(e) => props.onStoreChange(e.target.value)}
        >
          <option value="">All</option>
          {props.stores.map((store) => (
            <option key={store.store_key} value={store.store_key}>
              {store.store_name}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm text-slate-700">
        <span className="block mb-1 font-medium">Store Manager</span>
        <select
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          value={props.selectedEmployeeKey}
          onChange={(e) => props.onEmployeeChange(e.target.value)}
        >
          <option value="">All</option>
          {props.employees.map((employee) => (
            <option key={employee.employee_key} value={employee.employee_key}>
              {employee.employee_name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
