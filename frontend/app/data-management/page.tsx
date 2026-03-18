import DashboardLayout from '../components/DashboardLayout';

const DataManagement = () => {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            Data Management
          </h1>
          <p className="text-slate-600 mt-2">
            Manage data sources, quality, and integration
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              title: 'Data Sources',
              value: '12',
              subtitle: 'Connected systems',
            },
            {
              title: 'Data Quality',
              value: '98.5%',
              subtitle: 'Overall completeness',
            },
            {
              title: 'Last Sync',
              value: '2 mins ago',
              subtitle: 'Real-time updates',
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
            Data Source Status
          </h2>
          <div className="space-y-4">
            {[
              { name: 'Sales Database', status: 'Connected', lastSync: '2 mins' },
              { name: 'Inventory System', status: 'Connected', lastSync: '5 mins' },
              { name: 'Employee Records', status: 'Connected', lastSync: '10 mins' },
              { name: 'Weather API', status: 'Connected', lastSync: '1 hour' },
            ].map((source, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-4 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full" />
                  <div>
                    <p className="font-medium text-slate-900">{source.name}</p>
                    <p className="text-sm text-slate-500">
                      Last sync: {source.lastSync}
                    </p>
                  </div>
                </div>
                <span className="text-green-700 font-medium text-sm">
                  {source.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default DataManagement;
