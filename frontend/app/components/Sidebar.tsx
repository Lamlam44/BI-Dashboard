'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  TrendingUp,
  Users,
  Sparkles,
  Database,
} from 'lucide-react';

const Sidebar = () => {
  const pathname = usePathname();

  const navItems = [
    {
      href: '/dashboard',
      label: 'Sales & Profit',
      icon: BarChart3,
    },
    {
      href: '/item-trends',
      label: 'Item Trends',
      icon: TrendingUp,
    },
    {
      href: '/employee-performance',
      label: 'Employee Performance',
      icon: Users,
    },
    {
      href: '/forecasting',
      label: 'AI Forecasting',
      icon: Sparkles,
    },
    {
      href: '/data-management',
      label: 'Data Management',
      icon: Database,
    },
  ];

  const isActive = (href: string) => {
    if (href === '/dashboard') {
      return pathname === '/dashboard' || pathname === '/';
    }
    return pathname.startsWith(href);
  };

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-slate-900 text-slate-50 flex flex-col border-r border-slate-800">
      {/* Logo Section */}
      <div className="p-6 border-b border-slate-800">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
            <BarChart3 size={20} className="text-white" />
          </div>
          BI Dashboard
        </h1>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 overflow-y-auto py-6 px-4">
        <ul className="space-y-2">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);

            return (
              <li key={href}>
                <Link href={href}>
                  <div
                    className={`
                      flex items-center gap-3 px-4 py-3 rounded-lg
                      transition-all duration-200 cursor-pointer
                      ${
                        active
                          ? 'bg-blue-600 text-white shadow-lg'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      }
                    `}
                  >
                    <Icon size={20} className="flex-shrink-0" />
                    <span className="font-medium text-sm">{label}</span>
                    {active && (
                      <div className="ml-auto w-2 h-2 bg-blue-300 rounded-full" />
                    )}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer Section */}
      <div className="p-6 border-t border-slate-800">
        <p className="text-xs text-slate-400">
          BI Dashboard v1.0
        </p>
      </div>
    </aside>
  );
};

export default Sidebar;
