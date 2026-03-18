import DashboardLayout from '../components/DashboardLayout';

const ItemTrends = () => {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Item Trends</h1>
          <p className="text-slate-600 mt-2">
            Analyze product performance and market trends
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              title: 'Top Product',
              value: 'Product XYZ',
              subtitle: '$450K in sales',
            },
            {
              title: 'Category Growth',
              value: '+34.2%',
              subtitle: 'Electronics',
            },
            {
              title: 'Supply Status',
              value: '94%',
              subtitle: 'In Stock',
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
              <p className="text-slate-500 text-sm mt-3">{card.subtitle}</p>
            </div>
          ))}
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-8 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900 mb-6">
            Product Performance
          </h2>
          <div className="h-64 flex items-center justify-center bg-slate-50 rounded-lg border border-dashed border-slate-300">
            <p className="text-slate-500">Chart placeholder</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ItemTrends;
