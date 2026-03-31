'use client';

import Sidebar from './Sidebar';
import Header from './Header';
import AuthGuard from './AuthGuard';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

const DashboardLayout = ({ children }: DashboardLayoutProps) => {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-slate-50">
        <Sidebar />
        <div className="flex-1 ml-64 flex flex-col">
          <Header />
          <main className="flex-1 mt-20 overflow-y-auto">
            <div className="p-8">{children}</div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
};

export default DashboardLayout;
