export type EmployeeOption = {
  employee_key: number;
  employee_name: string;
  title?: string | null;
};

export type StoreOption = {
  store_key: number;
  store_name: string;
};

export type EmployeeFiltersResponse = {
  years: number[];
  months: number[];
  stores: StoreOption[];
  employees: EmployeeOption[];
};

export type DashboardKpis = {
  employee_count?: number;
  store_count?: number;
  total_net_sales?: number;
  avg_net_sales?: number;
  avg_profit_margin?: number;
  avg_return_rate?: number;
  avg_ticket_size?: number;
  total_orders?: number;
};

export type Capability = {
  key: string;
  enabled: boolean;
  reason: string;
};

export type DashboardResponse = {
  filters: Record<string, number | null>;
  kpis: DashboardKpis;
  top_performer?: {
    employee_key: number;
    employee_name: string;
    title?: string | null;
    net_sales: number;
    profit_margin: number;
    return_rate: number;
    total_orders: number;
  } | null;
  comparison: {
    delta_vs_company_avg_net_sales: number;
    delta_vs_company_avg_profit_margin: number;
    delta_vs_company_avg_return_rate: number;
  };
  capabilities: Capability[];
};

export type TrendRow = {
  year: number;
  month: number;
  net_sales: number;
  profit_margin: number;
  return_rate: number;
  total_orders: number;
};

export type TrendResponse = {
  filters: Record<string, number | null>;
  rows: TrendRow[];
};

export type LeaderboardRow = {
  employee_key: number;
  employee_name: string;
  title?: string | null;
  net_sales: number;
  profit_margin: number;
  return_rate: number;
  total_orders: number;
  avg_ticket_size: number;
  ranking: number;
};

export type LeaderboardResponse = {
  filters: Record<string, number | null>;
  rows: LeaderboardRow[];
};

export type ScatterRow = {
  employee_key: number;
  employee_name: string;
  net_sales: number;
  profit_margin: number;
  return_rate: number;
  total_orders: number;
};

export type ScatterResponse = {
  filters: Record<string, number | null>;
  rows: ScatterRow[];
};
