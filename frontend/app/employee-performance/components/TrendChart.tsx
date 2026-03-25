import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { TrendResponse } from './types';
import { formatCurrency, formatPercent } from './format';

type TrendChartProps = {
  data: TrendResponse | null;
};

export default function TrendChart({ data }: TrendChartProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Monthly Performance Trend</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data?.rows || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="month" />
            <YAxis yAxisId="left" tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
            />
            <Tooltip
              formatter={(value, name) => {
                const numericValue = Number(value || 0);
                if (name === 'Net Sales') return formatCurrency(numericValue);
                if (name === 'Profit Margin') return formatPercent(numericValue);
                return value;
              }}
            />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="net_sales" name="Net Sales" stroke="#1d4ed8" strokeWidth={2} />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="profit_margin"
              name="Profit Margin"
              stroke="#10b981"
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
