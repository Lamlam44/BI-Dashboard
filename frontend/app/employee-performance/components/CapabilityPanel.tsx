import { Capability } from './types';

type CapabilityPanelProps = {
  items: Capability[];
};

export default function CapabilityPanel({ items }: CapabilityPanelProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Capability Coverage</h3>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.key} className="border border-slate-200 rounded-lg p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-slate-900">{item.key}</p>
              <span
                className={`text-xs px-2 py-1 rounded-full ${
                  item.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                }`}
              >
                {item.enabled ? 'Enabled' : 'Not Available'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-2">{item.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
