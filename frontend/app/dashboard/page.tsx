import DashboardLayout from '../components/DashboardLayout';

const Dashboard = () => {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Page Title */}
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            Sales & Profit
          </h1>
          <p className="text-slate-600 mt-2">
            Monitor your sales performance and profit margins
          </p>
        </div>

        {/* Dashboard Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[
            {
              title: 'Total Sales',
              value: '$2.4M',
              change: '+12.5%',
              positive: true,
            },
            {
              title: 'Profit Margin',
              value: '28.5%',
              change: '+2.3%',
              positive: true,
            },
            {
              title: 'Transactions',
              value: '12,584',
              change: '-3.2%',
              positive: false,
            },
            {
              title: 'Avg. Order Value',
              value: '$190.50',
              change: '+5.1%',
              positive: true,
            },
          ].map((card, idx) => (
            <div
              key={idx}
              className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm hover:shadow-md transition-shadow"
            >
              <p className="text-slate-600 text-sm font-medium">{card.title}</p>
              <p className="text-2xl font-bold text-slate-900 mt-2">
                {card.value}
              </p>
              <p
                className={`text-sm font-medium mt-3 ${
                  card.positive ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {card.positive ? '↑' : '↓'} {card.change} vs last month
              </p>
            </div>
          ))}
        </div>

        {/* Chart Placeholder */}
        <div className="bg-white rounded-lg border border-slate-200 p-8 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-6">
            Sales Trend
          </h2>
          <div className="h-64 flex items-center justify-center bg-slate-50 rounded-lg border border-dashed border-slate-300">
            <p className="text-slate-500">Chart placeholder - Add your charting library here</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
