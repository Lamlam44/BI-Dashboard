import { DashboardResponse } from './types';
import { formatCurrency, formatNumber, formatPercent } from './format';

type TopPerformerCardProps = {
  data: DashboardResponse | null;
};

export default function TopPerformerCard({ data }: TopPerformerCardProps) {
  const top = data?.top_performer;

  if (!top) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900">Top Performer</h3>
        <p className="text-sm text-slate-500 mt-2">No data available for selected filters.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900">Top Performer</h3>
      <p className="text-xl font-bold text-blue-700 mt-3">{top.employee_name}</p>
      <p className="text-sm text-slate-500">{top.title || 'Store Manager'}</p>
      <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
        <div>
          <p className="text-slate-500">Net Sales</p>
          <p className="font-semibold text-slate-900">{formatCurrency(top.net_sales)}</p>
        </div>
        <div>
          <p className="text-slate-500">Profit Margin</p>
          <p className="font-semibold text-slate-900">{formatPercent(top.profit_margin)}</p>
        </div>
        <div>
          <p className="text-slate-500">Return Rate</p>
          <p className="font-semibold text-slate-900">{formatPercent(top.return_rate)}</p>
        </div>
        <div>
          <p className="text-slate-500">Orders</p>
          <p className="font-semibold text-slate-900">{formatNumber(top.total_orders)}</p>
        </div>
      </div>
    </div>
  );
}
