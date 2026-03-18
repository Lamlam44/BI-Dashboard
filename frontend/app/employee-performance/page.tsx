import DashboardLayout from '../components/DashboardLayout';

const EmployeePerformance = () => {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            Employee Performance
          </h1>
          <p className="text-slate-600 mt-2">
            Track team performance and individual achievements
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              title: 'Top Performer',
              value: 'Sarah Johnson',
              subtitle: '$1.2M in sales',
            },
            {
              title: 'Team Average',
              value: '$320K',
              subtitle: 'Per employee',
            },
            {
              title: 'Target Achievement',
              value: '112%',
              subtitle: 'Of quarterly goal',
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
            Sales by Team Member
          </h2>
          <div className="space-y-4">
            {['Sarah Johnson', 'Michael Chen', 'Emily Davis', 'James Wilson'].map(
              (name, idx) => (
                <div key={idx} className="flex items-center gap-4">
                  <span className="text-sm font-medium text-slate-700 w-32">
                    {name}
                  </span>
                  <div className="flex-1 bg-slate-100 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full"
                      style={{
                        width: `${75 + Math.random() * 25}%`,
                      }}
                    />
                  </div>
                  <span className="text-sm font-medium text-slate-700 w-16">
                    {Math.floor(75 + Math.random() * 25)}%
                  </span>
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default EmployeePerformance;
