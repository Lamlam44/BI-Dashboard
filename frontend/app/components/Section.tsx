'use client';

export default function Section({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border border-slate-600 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-2 bg-slate-100 border-b border-slate-600">
        <h2 className="text-sm font-bold text-slate-800">{title}</h2>
        {badge && (
          <span className="text-[11px] text-slate-500 bg-white border border-slate-300 px-2.5 py-0.5 rounded-full">
            {badge}
          </span>
        )}
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </section>
  );
}
