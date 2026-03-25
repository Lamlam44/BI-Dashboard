import { LeaderboardResponse } from './types';
import { formatCurrency, formatNumber, formatPercent } from './format';

type LeaderboardTableProps = {
  data: LeaderboardResponse | null;
};

export default function LeaderboardTable({ data }: LeaderboardTableProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm overflow-x-auto">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Top Store Managers</h3>
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="py-2 text-left">Rank</th>
            <th className="py-2 text-left">Manager</th>
            <th className="py-2 text-right">Net Sales</th>
            <th className="py-2 text-right">Profit Margin</th>
            <th className="py-2 text-right">Return Rate</th>
            <th className="py-2 text-right">Orders</th>
          </tr>
        </thead>
        <tbody>
          {(data?.rows || []).map((row) => (
            <tr key={row.employee_key} className="border-b border-slate-100">
              <td className="py-2 text-slate-700">#{row.ranking}</td>
              <td className="py-2">
                <p className="font-medium text-slate-900">{row.employee_name}</p>
                <p className="text-xs text-slate-500">{row.title || 'Store Manager'}</p>
              </td>
              <td className="py-2 text-right font-medium text-slate-900">{formatCurrency(row.net_sales)}</td>
              <td className="py-2 text-right">{formatPercent(row.profit_margin)}</td>
              <td className="py-2 text-right">{formatPercent(row.return_rate)}</td>
              <td className="py-2 text-right">{formatNumber(row.total_orders)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
