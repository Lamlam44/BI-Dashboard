export function formatCurrency(value?: number | null): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatPercent(value?: number | null): string {
  const ratio = Number(value || 0);
  return `${(ratio * 100).toFixed(2)}%`;
}

export function formatNumber(value?: number | null): string {
  const amount = Number(value || 0);
  return new Intl.NumberFormat('en-US').format(amount);
}
