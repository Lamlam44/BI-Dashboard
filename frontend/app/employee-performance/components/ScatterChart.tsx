import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart as RechartsScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { ScatterResponse } from './types';
import { formatCurrency, formatPercent } from './format';

type ScatterChartProps = {
  data: ScatterResponse | null;
};

export default function ScatterChart({ data }: ScatterChartProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Net Sales vs Profit Margin</h3>
      <p className="text-xs text-slate-500 mb-3">
        This view supports fair contextual comparison between managers instead of raw totals only.
      </p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="net_sales" name="Net Sales" tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
            <YAxis
              dataKey="profit_margin"
              name="Profit Margin"
              tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
            />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              formatter={(value, name) => {
                const numericValue = Number(value || 0);
                if (name === 'profit_margin') return formatPercent(numericValue);
                if (name === 'net_sales') return formatCurrency(numericValue);
                return value;
              }}
              labelFormatter={(_, payload: any) => payload?.[0]?.payload?.employee_name || ''}
            />
            <Scatter name="Managers" data={data?.rows || []} fill="#2563eb" />
          </RechartsScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
