import { DashboardResponse } from './types';
import { formatCurrency, formatNumber, formatPercent } from './format';

type KpiCardsProps = {
  data: DashboardResponse | null;
};

export default function KpiCards({ data }: KpiCardsProps) {
  const kpis = data?.kpis || {};

  const cards = [
    {
      title: 'Total Net Sales',
      value: formatCurrency(kpis.total_net_sales),
      subtitle: `Avg / manager: ${formatCurrency(kpis.avg_net_sales)}`,
    },
    {
      title: 'Average Profit Margin',
      value: formatPercent(kpis.avg_profit_margin),
      subtitle: `vs company avg: ${formatPercent(data?.comparison.delta_vs_company_avg_profit_margin)}`,
    },
    {
      title: 'Average Return Rate',
      value: formatPercent(kpis.avg_return_rate),
      subtitle: `vs company avg: ${formatPercent(data?.comparison.delta_vs_company_avg_return_rate)}`,
    },
    {
      title: 'Total Orders',
      value: formatNumber(kpis.total_orders),
      subtitle: `Avg ticket: ${formatCurrency(kpis.avg_ticket_size)}`,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      {cards.map((card) => (
        <article key={card.title} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <p className="text-sm text-slate-500 font-medium">{card.title}</p>
          <p className="text-2xl font-bold text-slate-900 mt-2">{card.value}</p>
          <p className="text-xs text-slate-500 mt-2">{card.subtitle}</p>
        </article>
      ))}
    </div>
  );
}
