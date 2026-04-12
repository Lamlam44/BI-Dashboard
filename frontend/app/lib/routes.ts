import { BarChart3, TrendingUp, Users, Sparkles, Database } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Single source-of-truth for role-based page access */
export const ROLE_ACCESS: Record<string, string[]> = {
  '/dashboard':            ['executive', 'regional_manager', 'store_manager', 'admin'],
  '/item-trends':          ['executive', 'regional_manager', 'store_manager', 'admin'],
  '/employee-performance': ['executive', 'regional_manager', 'admin'],
  '/forecasting':          ['executive', 'admin'],
  '/data-management':      ['admin'],
};

export const NAV_ITEMS: NavItem[] = [
  { href: '/dashboard',            label: 'Doanh Thu & Lợi Nhuận',  icon: BarChart3 },
  { href: '/item-trends',          label: 'Xu Hướng Sản Phẩm',      icon: TrendingUp },
  { href: '/employee-performance', label: 'Hiệu Suất Nhân Viên',    icon: Users },
  { href: '/forecasting',          label: 'Dự Báo AI',               icon: Sparkles },
  { href: '/data-management',      label: 'Quản Lý Dữ Liệu',        icon: Database },
];

/** Returns allowed roles for a given route, or [] if not found */
export function allowedRoles(href: string): string[] {
  return ROLE_ACCESS[href] ?? [];
}
